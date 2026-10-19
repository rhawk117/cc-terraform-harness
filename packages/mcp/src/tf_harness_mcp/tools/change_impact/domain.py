"""Values the change_impact git layer reads and the result the tool returns."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from tf_harness_mcp.structure.domain import Location

type ChangeStatus = Literal['added', 'modified', 'deleted']
type BlockStatus = Literal['added', 'modified', 'removed']
type InterfaceKind = Literal['variable', 'output']
type InterfaceChangeKind = Literal['added', 'removed', 'type_changed', 'default_changed']


def create_change_statuses() -> dict[str, ChangeStatus]:
    return {'A': 'added', 'D': 'deleted'}


@dataclass(slots=True, kw_only=True, frozen=True)
class GitOptions:
    timeout_seconds: float
    statuses: dict[str, ChangeStatus] = field(default_factory=create_change_statuses)


@dataclass(slots=True, kw_only=True, frozen=True)
class LineRange:
    start: int
    count: int


@dataclass(slots=True, kw_only=True, frozen=True)
class ChangedFile:
    path: str
    status: ChangeStatus
    ranges: tuple[LineRange, ...] = ()


@dataclass(slots=True, kw_only=True, frozen=True)
class ChangeSet:
    base_commit: str
    files: tuple[ChangedFile, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class ChangedBlock:
    kind: str
    labels: list[str]
    status: BlockStatus
    location: Location


@dataclass(slots=True, kw_only=True, frozen=True)
class InterfaceChange:
    module: str
    kind: InterfaceKind
    name: str
    change: InterfaceChangeKind
    before: str | None = None
    after: str | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class AffectedRoot:
    root: str
    module: str
    path: list[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class ProblemEntry:
    path: str
    message: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ChangeImpact:
    base_commit: str
    blocks: list[ChangedBlock]
    interface: list[InterfaceChange]
    roots: list[AffectedRoot]
    problems: list[ProblemEntry]


@dataclass(slots=True, kw_only=True, frozen=True)
class Variable:
    type: str | None
    default: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleInterface:
    variables: dict[str, Variable]
    outputs: frozenset[str]
