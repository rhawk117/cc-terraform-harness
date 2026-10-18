"""Plain values describing the blocks of a module and the module graph of a project."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.structure.errors import FileProblem


@dataclass(slots=True, kw_only=True, frozen=True)
class Block:
    kind: str
    labels: tuple[str, ...]
    file: Path
    start_line: int
    end_line: int
    source: str | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleIndex:
    directory: Path
    blocks: tuple[Block, ...]
    problems: tuple[FileProblem, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleNode:
    index: ModuleIndex
    calls: tuple[Path, ...]


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
