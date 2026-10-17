"""Fail when source code uses builtins that ruff's banned-api cannot ban."""

import ast
from dataclasses import dataclass
from itertools import chain
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@dataclass(slots=True, kw_only=True, frozen=True)
class BannedBuiltinUse:
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

    def describe_use(self, node: ast.Name) -> BannedBuiltinUse:
        return BannedBuiltinUse(path=self.path, line=node.lineno, name=node.id)

    def find_banned_uses(self, banned: frozenset[str]) -> Iterator[BannedBuiltinUse]:
        return map(self.describe_use, self.select_banned_names(banned))


def parse_source(path: Path) -> ParsedSource:
    return ParsedSource(path=path, tree=ast.parse(path.read_bytes(), filename=path))


class TestBannedBuiltins:
    roots = ('src', 'tests')
    banned = frozenset({
        '__import__',
        'globals',
        'hasattr',
        'locals',
        'staticmethod',
        'vars',
    })

    @pytest.fixture
    def sources(self, pytestconfig: pytest.Config) -> tuple[ParsedSource, ...]:
        folders = map(pytestconfig.rootpath.joinpath, self.roots)
        paths = sorted(chain.from_iterable(folder.rglob('*.py') for folder in folders))
        return tuple(map(parse_source, paths))

    def test_source_avoids_banned_builtins(self, sources: tuple[ParsedSource, ...]) -> None:
        found = (source.find_banned_uses(self.banned) for source in sources)
        assert tuple(chain.from_iterable(found)) == ()
