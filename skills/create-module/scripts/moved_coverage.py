"""Check that every address a refactor removed from a root keeps its state through a moved block.

Usage: moved_coverage.py [--base REF] ROOT [ROOT ...]

For each ROOT directory, reads the `resource "T" "N"` and `module "N"` blocks in its .tf files at
git REF (default HEAD) and in the working tree. Every address declared at REF and gone now must be
the `from` of a `moved` block (the address, one of its instances or a nested object) or of a
`removed` block in that root's working-tree .tf files. Data sources hold no state and are ignored.
Prints one `path:line: RULE message` line per finding:

- MC1: an address removed since REF with no moved or removed block; reported on ROOT:1.
- MC2: a moved `to` names a module call or resource the root does not declare now.
- MC3: a moved `to` names a resource inside a local module that the module does not declare.
- MC4: two moved blocks share the same `from`.

A clean run says the moves are written, not that each lands on the right object or instance key.
Exit status: 0 when nothing was found, 1 when something was, 2 on a usage error, a missing ROOT,
or a REF git cannot resolve there.
"""

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from itertools import accumulate, chain
from operator import attrgetter
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
SOURCE = re.compile(r'^\s*source\s*=\s*"([^"]+)"', re.MULTILINE)
FROM = re.compile(r'^\s*from\s*=\s*(\S.*?)\s*$', re.MULTILINE)
TO = re.compile(r'^\s*to\s*=\s*(\S.*?)\s*$', re.MULTILINE)
MODULE_ADDRESS = re.compile(r'module\.([\w-]+)(?:\[[^\]]*\])?(?:\.(.+))?')
RESOURCE_ADDRESS = re.compile(r'([\w-]+)\.([\w-]+)(?:\[[^\]]*\])?')
LOCAL_SOURCE = ('./', '../')


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


@dataclass(slots=True, kw_only=True, frozen=True)
class Block:
    kind: str
    labels: tuple[str, ...]
    line: int
    body: str

    def read_attribute(self, pattern: re.Pattern[str]) -> str:
        found = pattern.search(self.body)
        return found.expand(r'\1') if found else ''


def create_block(code: str, span: tuple[int, int]) -> Block:
    open_at, close_at = span
    line_start = code.rfind('\n', 0, open_at) + 1
    header = HEADER.fullmatch(code[line_start:open_at].strip())
    return Block(
        kind=header.expand(r'\1') if header else '',
        labels=tuple(LABEL.findall(header.expand(r'\2'))) if header else (),
        line=code.count('\n', 0, open_at) + 1,
        body=code[open_at + 1 : close_at],
    )


def parse_blocks(text: str) -> list[Block]:
    code = TOKEN.sub(mask_for_code, text)
    spans = find_spans(TOKEN.sub(mask_for_skeleton, text))
    return [create_block(code, span) for span in spans]


@dataclass(slots=True, kw_only=True, frozen=True)
class Hit:
    path: Path
    line: int
    rule: str
    message: str

    def describe(self) -> str:
        return f'{self.path}:{self.line}: {self.rule} {self.message}'


@dataclass(slots=True, kw_only=True, frozen=True)
class Move:
    path: Path
    line: int
    kind: str
    source: str
    target: str

    def covers(self, address: str) -> bool:
        nested = self.source.startswith((f'{address}[', f'{address}.'))
        return self.source == address or (self.kind == 'moved' and nested)

    def report(self, rule: str, message: str) -> Hit:
        return Hit(path=self.path, line=self.line, rule=rule, message=message)


@dataclass(slots=True, kw_only=True, frozen=True)
class Declarations:
    resources: frozenset[str]
    modules: dict[str, str]

    @property
    def addresses(self) -> frozenset[str]:
        return self.resources | {f'module.{name}' for name in self.modules}


def declare(texts: list[str]) -> Declarations:
    blocks = list(chain.from_iterable(map(parse_blocks, texts)))
    resources = {'.'.join(block.labels) for block in blocks if block.kind == 'resource'}
    modules = {
        block.labels[0]: block.read_attribute(SOURCE)
        for block in blocks
        if block.kind == 'module' and block.labels
    }
    return Declarations(resources=frozenset(resources), modules=modules)


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def declare_directory(directory: Path) -> Declarations:
    return declare(list(map(read_text, sorted(directory.glob('*.tf')))))


def create_move(path: Path, block: Block) -> Move:
    source, target = block.read_attribute(FROM), block.read_attribute(TO)
    return Move(path=path, line=block.line, kind=block.kind, source=source, target=target)


def read_moves(path: Path) -> list[Move]:
    blocks = parse_blocks(read_text(path))
    return [create_move(path, block) for block in blocks if block.kind in {'moved', 'removed'}]


@dataclass(slots=True, kw_only=True, frozen=True)
class GitTree:
    git: str
    root: Path
    ref: str

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        command = [self.git, '-C', str(self.root), *args]
        return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603 - argv is a fixed git command plus the caller's ref and paths

    def resolves(self) -> bool:
        commit = f'{self.ref}^{{commit}}'
        return self.run('rev-parse', '--verify', '--quiet', commit).returncode == 0

    def read(self, name: str) -> str:
        return self.run('show', f'{self.ref}:./{name}').stdout

    def declare(self) -> Declarations:
        listing = self.run('ls-tree', '--name-only', self.ref, '.').stdout.splitlines()
        return declare([self.read(name) for name in listing if name.endswith('.tf')])


def split_target(target: str) -> tuple[str | None, str]:
    module = MODULE_ADDRESS.fullmatch(target)
    rest = module.expand(r'\2') if module and module[2] else ''
    rest = rest if module else target
    resource = RESOURCE_ADDRESS.fullmatch(rest)
    name = resource.expand(r'\1.\2') if resource and not rest.startswith('module.') else ''
    return (module.expand(r'\1') if module else None, name)


def check_local_module(directory: Path, move: Move, resource: str) -> Hit | None:
    if not directory.is_dir():
        return move.report('MC3', f'{move.target}: local module {directory} does not exist')

    declared = resource in declare_directory(directory).resources
    return None if declared else move.report('MC3', f'{move.target}: {directory} lacks {resource}')


@dataclass(slots=True, kw_only=True, frozen=True)
class RootState:
    root: Path
    base: Declarations
    now: Declarations
    moves: tuple[Move, ...]

    @property
    def moved(self) -> list[Move]:
        return [move for move in self.moves if move.kind == 'moved']

    def is_uncovered(self, address: str) -> bool:
        return not any(move.covers(address) for move in self.moves)

    def find_uncovered(self) -> list[Hit]:
        removed = sorted(self.base.addresses - self.now.addresses)
        message = 'was declared at the base ref and has no moved or removed block'
        uncovered = filter(self.is_uncovered, removed)
        return [
            Hit(path=self.root, line=1, rule='MC1', message=f'{address} {message}')
            for address in uncovered
        ]

    def find_duplicates(self) -> list[Hit]:
        sources = [move.source for move in self.moved]
        repeated = (move for index, move in enumerate(self.moved) if move.source in sources[:index])
        return [move.report('MC4', f'duplicate from {move.source}') for move in repeated]

    def check_target(self, move: Move) -> Hit | None:
        module, resource = split_target(move.target)
        if module is None:
            declared = not resource or resource in self.now.resources
            return None if declared else move.report('MC2', f'{move.target} is not declared here')

        if module not in self.now.modules:
            return move.report('MC2', f'{move.target}: module "{module}" is not declared here')

        source = self.now.modules[module]
        if not resource or not source.startswith(LOCAL_SOURCE):
            return None

        return check_local_module(self.root.joinpath(source), move, resource)

    def check(self) -> list[Hit]:
        targets = [hit for hit in map(self.check_target, self.moved) if hit is not None]
        return [*self.find_uncovered(), *targets, *self.find_duplicates()]


def check_root(tree: GitTree) -> list[Hit]:
    files = sorted(tree.root.glob('*.tf'))
    moves = tuple(chain.from_iterable(map(read_moves, files)))
    now = declare(list(map(read_text, files)))
    return RootState(root=tree.root, base=tree.declare(), now=now, moves=moves).check()


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--base', default='HEAD', metavar='REF')
    parser.add_argument('roots', nargs='+', type=Path, metavar='ROOT')
    return parser


def fail(message: str) -> int:
    print(f'moved_coverage: {message}', file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    if missing := [str(root) for root in args.roots if not root.is_dir()]:
        return fail(f'no such directory: {", ".join(missing)}')

    if (git := shutil.which('git')) is None:
        return fail('git is not on PATH')

    trees = [GitTree(git=git, root=root, ref=args.base) for root in args.roots]
    if unresolved := [str(tree.root) for tree in trees if not tree.resolves()]:
        return fail(f'cannot resolve {args.base} in {", ".join(unresolved)}')

    found = chain.from_iterable(map(check_root, trees))
    hits = sorted(found, key=attrgetter('path', 'line', 'rule'))
    for hit in hits:
        print(hit.describe())

    return 1 if hits else 0


if __name__ == '__main__':
    raise SystemExit(main())
