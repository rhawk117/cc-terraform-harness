import ast
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

import pytest

pytestmark = pytest.mark.agents


@dataclass(slots=True, kw_only=True, frozen=True)
class BuiltinUse:
    path: Path
    line: int
    name: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ParsedSource:
    path: Path
    tree: ast.Module

    def select_banned_names(self, banned: frozenset[str]) -> Iterator[ast.Name]:
        names = (node for node in ast.walk(self.tree) if isinstance(node, ast.Name))
        return (name for name in names if name.id in banned)

    def describe_use(self, node: ast.Name) -> BuiltinUse:
        return BuiltinUse(path=self.path, line=node.lineno, name=node.id)

    def find_banned_uses(self, banned: frozenset[str]) -> Iterator[BuiltinUse]:
        return map(self.describe_use, self.select_banned_names(banned))


def parse_source(path: Path) -> ParsedSource:
    parsed_tree = ast.parse(path.read_bytes(), filename=path)
    return ParsedSource(path=path, tree=parsed_tree)


class TestBannedBuiltins:
    roots = ('packages', 'tests')
    banned = frozenset({
        '__import__',
        'globals',
        'locals',
        'staticmethod',
        'vars',
        'eval',
        'exec',
    })

    @pytest.fixture
    def sources(self, pytestconfig: pytest.Config) -> tuple[ParsedSource, ...]:
        folders = map(pytestconfig.rootpath.joinpath, self.roots)
        paths = chain.from_iterable(folder.rglob('*.py') for folder in folders)
        return tuple(map(parse_source, paths))

    def test_source_avoids_banned_builtins(self, sources: tuple[ParsedSource, ...]) -> None:
        found = chain.from_iterable(source.find_banned_uses(self.banned) for source in sources)
        assert tuple(found) == ()
