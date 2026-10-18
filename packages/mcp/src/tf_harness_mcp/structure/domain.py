"""Plain values describing the blocks of a module and the module graph of a project."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.structure.errors import FileProblem


@dataclass(slots=True, kw_only=True, frozen=True)
class Location:
    file: str
    start_line: int
    end_line: int


@dataclass(slots=True, kw_only=True, frozen=True)
class Block:
    kind: str
    labels: tuple[str, ...]
    file: Path
    start_line: int
    end_line: int
    source: str | None = None

    @property
    def location(self) -> Location:
        return Location(file=str(self.file), start_line=self.start_line, end_line=self.end_line)


@dataclass(slots=True, kw_only=True, frozen=True)
class RequiredProvider:
    local_name: str
    source: str | None
    version: str | None
    file: Path
    start_line: int
    end_line: int

    @property
    def location(self) -> Location:
        return Location(file=str(self.file), start_line=self.start_line, end_line=self.end_line)


@dataclass(slots=True, kw_only=True, frozen=True)
class Attribute:
    name: str
    expression: str
    string: str | None
    flag: bool
    file: Path
    start_line: int
    end_line: int

    @property
    def location(self) -> Location:
        return Location(file=str(self.file), start_line=self.start_line, end_line=self.end_line)


@dataclass(slots=True, kw_only=True, frozen=True)
class BlockEntry:
    block: Block
    attributes: tuple[Attribute, ...]
    required_providers: tuple[RequiredProvider, ...] = ()

    def get_attribute(self, name: str) -> Attribute | None:
        return next((attribute for attribute in self.attributes if attribute.name == name), None)


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleIndex:
    directory: Path
    blocks: tuple[Block, ...]
    problems: tuple[FileProblem, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleNode:
    index: ModuleIndex
    calls: tuple[Path, ...]


type CallPaths = dict[Path, tuple[Path, ...]]


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleGraph:
    root: Path
    modules: tuple[ModuleNode, ...]

    @property
    def called_directories(self) -> frozenset[Path]:
        return frozenset(call for module in self.modules for call in module.calls)

    @property
    def root_modules(self) -> tuple[Path, ...]:
        called = self.called_directories
        directories = (module.index.directory for module in self.modules)
        return tuple(directory for directory in directories if directory not in called)

    @property
    def calls_by_directory(self) -> dict[Path, tuple[Path, ...]]:
        return {module.index.directory: module.calls for module in self.modules}

    def extend_paths(
        self, paths: CallPaths, seen: frozenset[Path], calls: dict[Path, tuple[Path, ...]]
    ) -> CallPaths:
        return {
            call: path + (call,)
            for path in paths.values()
            for call in calls.get(path[-1], ())
            if call not in seen
        }

    def find_call_path(self, start: Path, target: Path) -> tuple[Path, ...] | None:
        paths: CallPaths = {start: (start,)}
        calls = self.calls_by_directory
        seen = frozenset(paths)
        while paths and target not in paths:
            paths = self.extend_paths(paths, seen, calls)
            seen = frozenset(seen | paths.keys())

        return paths.get(target)

    def find_root_paths(self, directory: Path) -> tuple[tuple[Path, ...], ...]:
        paths = (self.find_call_path(root, directory) for root in self.root_modules)
        return tuple(path for path in paths if path is not None)
