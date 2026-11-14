"""Lint a Terraform module directory for what stops it being reused by several callers.

Usage: module_lint.py MODULE_DIR [MODULE_DIR ...]

Reads the .tf files directly in each MODULE_DIR, so examples/, tests/ and nested modules are not
scanned, and prints one `path:line: RULE message` line per finding; MODULE_DIR:1 when missing.

- ML1: a provider block; the calling root configures providers.
- ML2: a backend or cloud block; only a root module has state settings.
- ML3: no required_providers block, or a required provider without a version constraint.
- ML4: no required_version.
- ML5: a variable without a type, or with type = any.
- ML6: a variable without a description.
- ML7: an output without a description.
- ML8: a hardcoded environment name, region or account ID in a resource, module or locals block.
- ML9: no README.md.

A hit is a cue to look, not a verdict. Exit status: 0 when nothing was found, 1 when something
was, 2 on a usage error or a MODULE_DIR that is not a directory.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from functools import reduce
from itertools import accumulate, chain
from operator import attrgetter, methodcaller
from pathlib import Path

TOKEN = re.compile(
    r'(?P<string>"(?:[^"\\\n]|\\.)*")'
    r'|(?P<heredoc><<-?(?P<tag>\w+)\n.*?\n\s*(?P=tag)\b)'
    r'|(?P<comment>(?:#|//)[^\n]*|/\*.*?\*/)',
    re.DOTALL,
)
BRACE = re.compile(r'[{}]')
HEADER = re.compile(r'([\w-]+)((?:\s+"[^"]*")*)\s*(=)?')
LABEL = re.compile(r'"([^"]*)"')
ENVIRONMENT = r'"(?:dev|staging|stage|prod|production)"'
REGION = r'"(?:us|eu|ap|sa|ca|me|af|il|mx|cn)(?:-gov|-iso[a-z]*)?-[a-z]+-\d+"'
ACCOUNT = r'"[^"\n]*(?<!\d)\d{12}(?!\d)[^"\n]*"'
LITERAL = re.compile(rf'(?P<environment>{ENVIRONMENT})|(?P<region>{REGION})|(?P<account>{ACCOUNT})')
ANY_TYPE = re.compile(r'^\s*type\s*=\s*any\s*$', re.MULTILINE)
LITERAL_KINDS = frozenset({'resource', 'module', 'locals'})


def blank(text: str) -> str:
    return re.sub(r'[^\n]', ' ', text)


def mask_for_code(match: re.Match[str]) -> str:
    return match[0] if match['string'] is not None else blank(match[0])


def mask_for_skeleton(match: re.Match[str]) -> str:
    return f'"{blank(match[0][1:-1])}"' if match['string'] is not None else blank(match[0])


def find_spans(skeleton: str) -> list[tuple[int, int]]:
    marks = [(found.start(), 1 if found[0] == '{' else -1) for found in BRACE.finditer(skeleton)]
    depths = list(accumulate(change for _, change in marks))
    pairs = list(zip(marks, depths, strict=True))
    opens = [at for (at, change), depth in pairs if change == 1 and depth == 1]
    closes = [at for (at, change), depth in pairs if change == -1 and depth == 0]
    return list(zip(opens, closes, strict=False))


def blank_span(text: str, span: tuple[int, int]) -> str:
    start, end = span
    return text[: start + 1] + blank(text[start + 1 : end]) + text[end:]


@dataclass(slots=True, kw_only=True, frozen=True)
class Source:
    code: str
    skeleton: str
    first_line: int


@dataclass(slots=True, kw_only=True, frozen=True)
class Block:
    kind: str
    labels: tuple[str, ...]
    body: Source

    @property
    def line(self) -> int:
        return self.body.first_line

    @property
    def own_text(self) -> str:
        return reduce(blank_span, find_spans(self.body.skeleton), self.body.code)

    def has_attribute(self, name: str) -> bool:
        return re.search(rf'^\s*{name}\s*=', self.own_text, re.MULTILINE) is not None

    def find_literal_lines(self) -> list[tuple[int, str]]:
        code = self.body.code
        found = LITERAL.finditer(code)
        return [
            (self.line + code.count('\n', 0, item.start()), item.lastgroup or '') for item in found
        ]


def slice_source(source: Source, span: tuple[int, int]) -> Source:
    open_at, close_at = span
    return Source(
        code=source.code[open_at + 1 : close_at],
        skeleton=source.skeleton[open_at + 1 : close_at],
        first_line=source.first_line + source.code.count('\n', 0, open_at),
    )


def create_block(source: Source, span: tuple[int, int]) -> Block:
    open_at = span[0]
    line_start = source.code.rfind('\n', 0, open_at) + 1
    header = HEADER.fullmatch(source.code[line_start:open_at].strip())
    return Block(
        kind=header.expand(r'\1') if header else '',
        labels=tuple(LABEL.findall(header.expand(r'\2'))) if header else (),
        body=slice_source(source, span),
    )


def parse_source(source: Source) -> list[Block]:
    return [create_block(source, span) for span in find_spans(source.skeleton)]


def find_children(block: Block, kind: str) -> list[Block]:
    return [child for child in parse_source(block.body) if child.kind == kind]


def parse_file(path: Path) -> list[Block]:
    text = path.read_text(encoding='utf-8', errors='replace')
    code, skeleton = TOKEN.sub(mask_for_code, text), TOKEN.sub(mask_for_skeleton, text)
    return parse_source(Source(code=code, skeleton=skeleton, first_line=1))


@dataclass(slots=True, kw_only=True, frozen=True)
class Hit:
    path: Path
    line: int
    rule: str
    message: str

    def describe(self) -> str:
        return f'{self.path}:{self.line}: {self.rule} {self.message}'


@dataclass(slots=True, kw_only=True, frozen=True)
class Located:
    path: Path
    block: Block

    @property
    def name(self) -> str:
        return next(iter(self.block.labels), self.block.kind)

    def report(self, rule: str, message: str) -> Hit:
        return Hit(path=self.path, line=self.block.line, rule=rule, message=message)


def locate_children(item: Located, kind: str) -> list[Located]:
    children = parse_source(item.block.body)
    matching = [child for child in children if kind in {'', child.kind}]
    return [Located(path=item.path, block=child) for child in matching]


def locate(path: Path) -> list[Located]:
    return [Located(path=path, block=block) for block in parse_file(path)]


def report_all(items: list[Located], rule: str, message: str) -> list[Hit]:
    return [item.report(rule, message.format(name=item.name)) for item in items]


def report_literals(item: Located) -> list[Hit]:
    messages = {
        'environment': 'hardcoded environment name; take it as an input',
        'region': 'hardcoded region; the caller provider sets it, or take it as an input',
        'account': 'hardcoded account ID; use aws_caller_identity or an input',
    }
    lines = item.block.find_literal_lines()
    return [
        Hit(path=item.path, line=line, rule='ML8', message=messages[kind]) for line, kind in lines
    ]


def lacks(items: list[Located], name: str) -> list[Located]:
    return [item for item in items if not item.block.has_attribute(name)]


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleDirectory:
    path: Path
    located: tuple[Located, ...]

    def of_kind(self, kind: str) -> list[Located]:
        return [item for item in self.located if item.block.kind == kind]

    def nested(self, kind: str) -> list[Located]:
        terraform = self.of_kind('terraform')
        return list(chain.from_iterable(locate_children(item, kind) for item in terraform))

    def report_module(self, rule: str, message: str) -> list[Hit]:
        return [Hit(path=self.path, line=1, rule=rule, message=message)]

    def check_state_settings(self) -> list[Hit]:
        providers = report_all(self.of_kind('provider'), 'ML1', 'provider block "{name}"')
        settings = [*self.nested('backend'), *self.nested('cloud')]
        message = 'backend or cloud block in a child module'
        return [*providers, *report_all(settings, 'ML2', message)]

    def check_versions(self) -> list[Hit]:
        required = self.nested('required_providers')
        entries = list(chain.from_iterable(locate_children(item, '') for item in required))
        message = 'provider "{name}" has no version constraint'
        unpinned = report_all(lacks(entries, 'version'), 'ML3', message)
        missing = [] if required else self.report_module('ML3', 'no required_providers block')
        terraform = self.of_kind('terraform')
        pinned = any(item.block.has_attribute('required_version') for item in terraform)
        core = [] if pinned else self.report_module('ML4', 'no required_version')
        return [*missing, *unpinned, *core]

    def check_interface(self) -> list[Hit]:
        variables = self.of_kind('variable')
        loose = [item for item in variables if ANY_TYPE.search(item.block.own_text)]
        return [
            *report_all(lacks(variables, 'type'), 'ML5', 'variable "{name}" has no type'),
            *report_all(loose, 'ML5', 'variable "{name}" has type any'),
            *report_all(
                lacks(variables, 'description'), 'ML6', 'variable "{name}" has no description'
            ),
            *report_all(
                lacks(self.of_kind('output'), 'description'),
                'ML7',
                'output "{name}" has no description',
            ),
        ]

    def check_literals(self) -> list[Hit]:
        scanned = (item for item in self.located if item.block.kind in LITERAL_KINDS)
        return list(chain.from_iterable(map(report_literals, scanned)))

    def check(self) -> list[Hit]:
        documented = self.path.joinpath('README.md').is_file()
        readme = [] if documented else self.report_module('ML9', 'no README.md')
        checks = (self.check_state_settings, self.check_versions, self.check_interface)
        return [*chain.from_iterable(check() for check in checks), *self.check_literals(), *readme]


def read_module(path: Path) -> ModuleDirectory:
    files = sorted(path.glob('*.tf'))
    return ModuleDirectory(path=path, located=tuple(chain.from_iterable(map(locate, files))))


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('modules', nargs='+', type=Path, metavar='MODULE_DIR')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    if missing := [str(path) for path in args.modules if not path.is_dir()]:
        print(f'module_lint: no such directory: {", ".join(missing)}', file=sys.stderr)
        return 2

    modules = map(read_module, args.modules)
    found = chain.from_iterable(map(methodcaller('check'), modules))
    hits = sorted(found, key=attrgetter('path', 'line', 'rule'))
    for hit in hits:
        print(hit.describe())

    return 1 if hits else 0


if __name__ == '__main__':
    raise SystemExit(main())
