"""Grep Terraform for the smells writing-terraform treats as stop signs.

Scans every .tf, .tfvars and .tftest.hcl file under each PATH, skipping .terraform directories,
and prints one `path:line: RULE message` line per hit. RULE is the review-module rubric ID:
SE1 and SE4 for secrets and static keys, SE6 for wildcard IAM, BR10 for weakened safety
settings, DE3 for hardcoded account and AMI IDs, VE6 for stale idioms, VE4 for unpinned modules.

A hit is a cue to look, not a verdict. A clean run says nothing about the provider schema, the
plan, or whether the change does what was asked. Exit status: 0 when nothing matched, 1 when
something did, 2 on a usage error or missing path.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from itertools import accumulate, chain, filterfalse, starmap
from operator import attrgetter, methodcaller
from pathlib import Path
from typing import Protocol, runtime_checkable

TERRAFORM_SUFFIXES = ('.tf', '.tfvars', '.tftest.hcl')
SKIPPED_DIRECTORY = '.terraform'
CREDENTIAL_WORD = r'(?:password|passwd|secret|token(?!s)|api_?key|access_?key|private_?key)'
NOT_CREDENTIAL_SUFFIX = (
    r'_(?:arn|ids?|names?|ttl|version|length|type|policy|enabled|count|days|source|mode)'
)
CREDENTIAL_NAME = rf'(?![a-z0-9_]*{NOT_CREDENTIAL_SUFFIX}\b)[a-z0-9_]*{CREDENTIAL_WORD}[a-z0-9_]*'
CREDENTIAL_LITERAL = rf'^\s*"?{CREDENTIAL_NAME}"?\s*[=:]\s*"[^"$]'
ACCESS_KEY_RESOURCE = r'^\s*resource\s+"aws_iam_access_key"'
IAM_WILDCARD = r'\b(?:actions?|resources?|principals?|identifiers|aws)"?\s*[=:]\s*\[?\s*"\*"'
DELETION_PROTECTION_OFF = r'^\s*(?:enable_)?deletion_protection(?:_enabled)?\s*=\s*false'
ACCOUNT_ID = (
    r'^(?!\s*(?:allowed|forbidden)_account_ids\b).*'
    r'(?:arn:aws[a-z-]*:[a-z0-9-]*:[a-z0-9-]*:\d{12}\b|"\d{12}")'
)
AMI_ID = r'"ami-[0-9a-f]{8,17}"'
ALB_RESOURCE = r'^\s*(?:resource|data)\s+"aws_alb(?:_[a-z_]+)?"'
BLOCK_HEADER = re.compile(r'^\s*([a-z_]+)((?:\s+"[^"]*")*)\s*\{')
BLOCK_LABEL = re.compile(r'"([^"]*)"')
MODULE_SOURCE = re.compile(r'^\s*source\s*=\s*"([^"]+)"')
MODULE_VERSION = re.compile(r'^\s*version\s*=')
GIT_SOURCE = re.compile(r'^(?:git::|git@|github\.com/|bitbucket\.org/)|\.git(?:$|[/?])')
REGISTRY_SOURCE = re.compile(r'^(?:[a-z0-9.-]+\.[a-z]+/)?[\w-]+/[\w-]+/[\w-]+(?://[^?]*)?$')


@dataclass(slots=True, kw_only=True, frozen=True)
class Hit:
    path: Path
    line: int
    rule: str
    message: str

    def describe(self) -> str:
        return f'{self.path}:{self.line}: {self.rule} {self.message}'


@dataclass(slots=True, kw_only=True, frozen=True)
class SourceLine:
    number: int
    text: str

    @property
    def is_comment(self) -> bool:
        return self.text.lstrip().startswith(('#', '//'))

    @property
    def depth_change(self) -> int:
        return 0 if self.is_comment else self.text.count('{') - self.text.count('}')


@dataclass(slots=True, kw_only=True, frozen=True)
class Block:
    kind: str
    labels: tuple[str, ...]
    lines: tuple[SourceLine, ...]

    @property
    def first_label(self) -> str:
        return next(iter(self.labels), '')

    def find_line(self, pattern: re.Pattern[str]) -> SourceLine | None:
        return next((line for line in self.lines if pattern.search(line.text)), None)


@runtime_checkable
class BlockRule(Protocol):
    def check(self, path: Path, block: Block) -> Hit | None: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class LineRule:
    rule: str
    message: str
    pattern: re.Pattern[str]

    def check(self, path: Path, line: SourceLine) -> Hit | None:
        if not self.pattern.search(line.text):
            return None

        return Hit(path=path, line=line.number, rule=self.rule, message=self.message)


@dataclass(slots=True, kw_only=True, frozen=True)
class BlockLineRule:
    rule: str
    message: str
    kind: str
    label: re.Pattern[str]
    pattern: re.Pattern[str]

    def check(self, path: Path, block: Block) -> Hit | None:
        if block.kind != self.kind or not self.label.fullmatch(block.first_label):
            return None

        if line := block.find_line(self.pattern):
            return Hit(path=path, line=line.number, rule=self.rule, message=self.message)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleSource:
    block: Block
    line: SourceLine
    value: str

    @property
    def is_unpinned_git(self) -> bool:
        return GIT_SOURCE.search(self.value) is not None and 'ref=' not in self.value

    @property
    def is_unpinned_registry(self) -> bool:
        is_registry = REGISTRY_SOURCE.match(self.value) is not None
        return is_registry and self.block.find_line(MODULE_VERSION) is None

    def get_pinning_problem(self) -> str | None:
        if self.is_unpinned_git:
            return 'git module source without ?ref=; pin a tag or commit'

        if self.is_unpinned_registry:
            return 'registry module without a version constraint'

        return None


def read_module_source(block: Block) -> ModuleSource | None:
    line = block.find_line(MODULE_SOURCE) if block.kind == 'module' else None
    value = MODULE_SOURCE.search(line.text) if line else None
    if line is None or value is None:
        return None

    return ModuleSource(block=block, line=line, value=value.group(1))


@dataclass(slots=True, kw_only=True, frozen=True)
class UnpinnedModuleRule:
    rule: str = 'VE4'

    def check(self, path: Path, block: Block) -> Hit | None:
        source = read_module_source(block)
        if source is None or (message := source.get_pinning_problem()) is None:
            return None

        return Hit(path=path, line=source.line.number, rule=self.rule, message=message)


@dataclass(slots=True, kw_only=True, frozen=True)
class RuleSet:
    line_rules: tuple[LineRule, ...]
    block_rules: tuple[BlockRule, ...]


def create_line_rule(rule: str, message: str, pattern: str) -> LineRule:
    return LineRule(rule=rule, message=message, pattern=re.compile(pattern, re.IGNORECASE))


def create_line_rules() -> tuple[LineRule, ...]:
    specs = (
        ('SE1', 'secret-named argument set to a literal', CREDENTIAL_LITERAL),
        ('SE1', 'AWS access key ID literal', r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'),
        ('SE1', 'private key literal', r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
        ('SE4', 'static access key resource; its secret lands in state', ACCESS_KEY_RESOURCE),
        ('SE6', 'wildcard in an IAM action, resource or principal', IAM_WILDCARD),
        ('SE6', 'service-wide IAM action', r'"[a-z0-9-]+:\*"'),
        ('BR10', 'prevent_destroy turned off', r'^\s*prevent_destroy\s*=\s*false'),
        ('BR10', 'deletion protection turned off', DELETION_PROTECTION_OFF),
        ('BR10', 'final snapshot skipped on destroy', r'^\s*skip_final_snapshot\s*=\s*true'),
        ('BR10', 'force_destroy deletes contents on destroy', r'^\s*force_destroy\s*=\s*true'),
        ('DE3', 'hardcoded account ID; use aws_caller_identity or a variable', ACCOUNT_ID),
        ('DE3', 'hardcoded AMI ID; use an aws_ami data source or a variable', AMI_ID),
        ('VE6', 'aws_alb is the superseded name; aws_lb is current', ALB_RESOURCE),
    )
    return tuple(starmap(create_line_rule, specs))


def create_block_rules() -> tuple[BlockRule, ...]:
    inline_acl = BlockLineRule(
        rule='VE6',
        message='inline acl on aws_s3_bucket; use aws_s3_bucket_acl or ownership controls',
        kind='resource',
        label=re.compile('aws_s3_bucket'),
        pattern=re.compile(r'^\s*acl\s*='),
    )
    secret_default = BlockLineRule(
        rule='SE1',
        message='secret-named variable with a literal default',
        kind='variable',
        label=re.compile(CREDENTIAL_NAME, re.IGNORECASE),
        pattern=re.compile(r'^\s*default\s*=\s*"[^"$]'),
    )
    return (inline_acl, secret_default, UnpinnedModuleRule())


def read_lines(path: Path) -> tuple[SourceLine, ...]:
    texts = path.read_text(encoding='utf-8', errors='replace').splitlines()
    return tuple(SourceLine(number=number, text=text) for number, text in enumerate(texts, 1))


def create_block(lines: tuple[SourceLine, ...]) -> Block:
    header = BLOCK_HEADER.match(lines[0].text)
    kind = header.group(1) if header else ''
    labels = tuple(BLOCK_LABEL.findall(header.group(2))) if header else ()
    return Block(kind=kind, labels=labels, lines=lines)


def find_block_end(depths: tuple[int, ...], start: int) -> int:
    last_line = len(depths) - 2
    closing = range(start, last_line + 1)
    return next((index for index in closing if depths[index + 1] <= 0), last_line)


def split_blocks(lines: tuple[SourceLine, ...]) -> list[Block]:
    depths = tuple(accumulate(map(attrgetter('depth_change'), lines), initial=0))
    starts = [
        index
        for index, line in enumerate(lines)
        if depths[index] == 0 and BLOCK_HEADER.match(line.text)
    ]
    return [create_block(lines[start : find_block_end(depths, start) + 1]) for start in starts]


@dataclass(slots=True, kw_only=True, frozen=True)
class FileScanner:
    rules: RuleSet
    path: Path

    def check_line(self, line: SourceLine) -> tuple[Hit | None, ...]:
        return tuple(rule.check(self.path, line) for rule in self.rules.line_rules)

    def check_block(self, block: Block) -> tuple[Hit | None, ...]:
        return tuple(rule.check(self.path, block) for rule in self.rules.block_rules)

    def scan(self) -> list[Hit]:
        lines = read_lines(self.path)
        code_lines = filterfalse(attrgetter('is_comment'), lines)
        line_hits = chain.from_iterable(map(self.check_line, code_lines))
        block_hits = chain.from_iterable(map(self.check_block, split_blocks(lines)))
        return [hit for hit in chain(line_hits, block_hits) if hit is not None]


def is_terraform_file(path: Path) -> bool:
    return path.name.endswith(TERRAFORM_SUFFIXES) and SKIPPED_DIRECTORY not in path.parts


def find_terraform_files(root: Path) -> list[Path]:
    candidates = [root] if root.is_file() else sorted(root.rglob('*'))
    return list(filter(is_terraform_file, candidates))


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('paths', nargs='+', type=Path, metavar='PATH')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    if missing := [str(path) for path in args.paths if not path.exists()]:
        print(f'smell_grep: no such path: {", ".join(missing)}', file=sys.stderr)
        return 2

    rules = RuleSet(line_rules=create_line_rules(), block_rules=create_block_rules())
    files = chain.from_iterable(map(find_terraform_files, args.paths))
    scanners = (FileScanner(rules=rules, path=path) for path in files)
    hits = chain.from_iterable(map(methodcaller('scan'), scanners))
    ordered = sorted(hits, key=attrgetter('path', 'line', 'rule'))
    for hit in ordered:
        print(hit.describe())

    return 1 if ordered else 0


if __name__ == '__main__':
    raise SystemExit(main())
