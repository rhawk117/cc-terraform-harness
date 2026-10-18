"""Rules for a base ref and for a git command's outcome."""

import re
import shlex
from dataclasses import dataclass
from itertools import zip_longest
from typing import TYPE_CHECKING

from tf_harness_mcp.tools.change_impact.domain import ChangedBlock, InterfaceChange, LineRange
from tf_harness_mcp.tools.change_impact.errors import GitCommandFailedError, InvalidBaseRefError
from tf_harness_mcp.tools.describe.domain import Location

if TYPE_CHECKING:
    from tf_harness_mcp.runner.domain import CommandResult
    from tf_harness_mcp.structure.domain import Block
    from tf_harness_mcp.tools.change_impact.domain import (
        BlockStatus,
        InterfaceChangeKind,
        ModuleInterface,
    )

type BlockIdentity = tuple[str, tuple[str, ...]]

HUNK_HEADER = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', re.ASCII)


@dataclass(slots=True, kw_only=True, frozen=True)
class BaseRefPolicy:
    base_ref: str

    @property
    def is_option_like(self) -> bool:
        return self.base_ref.startswith('-')

    def get_base_ref_problem(self) -> InvalidBaseRefError | None:
        if not self.base_ref or self.is_option_like:
            return InvalidBaseRefError(base_ref=self.base_ref)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class GitResultPolicy:
    argv: tuple[str, ...]
    result: CommandResult

    def get_git_problem(self) -> GitCommandFailedError | None:
        if self.result.returncode == 0:
            return None

        return GitCommandFailedError(
            command=shlex.join(('git', *self.argv)),
            returncode=self.result.returncode,
            stderr=self.result.stderr,
        )


def parse_hunk_ranges(diff: str) -> tuple[LineRange, ...]:
    matches = map(HUNK_HEADER.match, diff.splitlines())
    return tuple(
        LineRange(start=int(match[1]), count=int(match[2] or 1)) for match in matches if match
    )


def split_nul(output: str) -> list[str]:
    return [token for token in output.split('\0') if token]


def normalize_expression(text: str) -> str:
    return ' '.join(text.split())


def locate_block(block: Block) -> Location:
    return Location(file=str(block.file), start_line=block.start_line, end_line=block.end_line)


def make_block_change(block: Block, status: BlockStatus) -> ChangedBlock:
    return ChangedBlock(
        kind=block.kind, labels=list(block.labels), status=status, location=locate_block(block)
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class RangeTouchPolicy:
    lines: LineRange
    block: Block

    @property
    def last_line(self) -> int:
        return self.lines.start + self.lines.count - 1

    @property
    def touches(self) -> bool:
        if self.lines.count == 0:
            return self.block.start_line <= self.lines.start < self.block.end_line

        return self.lines.start <= self.block.end_line and self.last_line >= self.block.start_line


type BlockPair = tuple[Block | None, Block | None]


@dataclass(slots=True, kw_only=True, frozen=True)
class BlockChangePolicy:
    base: tuple[Block, ...]
    current: tuple[Block, ...]
    ranges: tuple[LineRange, ...]

    def is_touched(self, block: Block) -> bool:
        return any(RangeTouchPolicy(lines=lines, block=block).touches for lines in self.ranges)

    def pair_blocks(self) -> list[BlockPair]:
        base = group_by_identity(self.base)
        current = group_by_identity(self.current)
        identities = base.keys() | current.keys()
        return [
            pair
            for identity in sorted(identities)
            for pair in zip_longest(base.get(identity, []), current.get(identity, []))
        ]

    def classify(self, pair: BlockPair) -> ChangedBlock | None:
        before, after = pair
        if after is None and before:
            return make_block_change(before, 'removed')

        if before is None and after:
            return make_block_change(after, 'added')

        if after and self.is_touched(after):
            return make_block_change(after, 'modified')

        return None

    def list_changes(self) -> list[ChangedBlock]:
        changes = (self.classify(pair) for pair in self.pair_blocks())
        return [change for change in changes if change]


def group_by_identity(blocks: tuple[Block, ...]) -> dict[BlockIdentity, list[Block]]:
    groups: dict[BlockIdentity, list[Block]] = {}
    for block in blocks:
        groups.setdefault((block.kind, block.labels), []).append(block)

    return groups


VARIABLE_FACETS: dict[InterfaceChangeKind, str] = {
    'type_changed': 'type',
    'default_changed': 'default',
}


@dataclass(slots=True, kw_only=True, frozen=True)
class InterfacePolicy:
    module: str
    base: ModuleInterface
    current: ModuleInterface

    def create_variable_change(self, name: str, change: InterfaceChangeKind) -> InterfaceChange:
        facet = VARIABLE_FACETS.get(change)
        if facet is None:
            return InterfaceChange(module=self.module, kind='variable', name=name, change=change)

        return InterfaceChange(
            module=self.module,
            kind='variable',
            name=name,
            change=change,
            before=getattr(self.base.variables[name], facet),
            after=getattr(self.current.variables[name], facet),
        )

    def compare_variable(self, name: str) -> list[InterfaceChange]:
        before = self.base.variables.get(name)
        after = self.current.variables.get(name)
        if before is None:
            return [self.create_variable_change(name, 'added')]

        if after is None:
            return [self.create_variable_change(name, 'removed')]

        return [
            self.create_variable_change(name, change)
            for change, facet in VARIABLE_FACETS.items()
            if getattr(before, facet) != getattr(after, facet)
        ]

    def list_variable_changes(self) -> list[InterfaceChange]:
        names = sorted(self.base.variables.keys() | self.current.variables.keys())
        return [change for name in names for change in self.compare_variable(name)]

    def list_output_changes(self) -> list[InterfaceChange]:
        added = sorted(self.current.outputs - self.base.outputs)
        removed = sorted(self.base.outputs - self.current.outputs)
        return [
            *(
                InterfaceChange(module=self.module, kind='output', name=n, change='added')
                for n in added
            ),
            *(
                InterfaceChange(module=self.module, kind='output', name=n, change='removed')
                for n in removed
            ),
        ]

    def list_changes(self) -> list[InterfaceChange]:
        return [*self.list_variable_changes(), *self.list_output_changes()]
