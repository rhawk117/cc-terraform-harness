"""Plain values making up the summary describe returns."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from tf_harness_mcp.structure.domain import Location

type TargetKind = Literal['module', 'file', 'tfvars']


@dataclass(slots=True, kw_only=True, frozen=True)
class VariableEntry:
    name: str
    type: str | None
    has_default: bool
    description: str | None
    sensitive: bool
    location: Location


@dataclass(slots=True, kw_only=True, frozen=True)
class OutputEntry:
    name: str
    description: str | None
    sensitive: bool
    location: Location


@dataclass(slots=True, kw_only=True, frozen=True)
class ObjectEntry:
    type: str
    name: str
    location: Location


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleCallEntry:
    name: str
    source: str | None
    location: Location


@dataclass(slots=True, kw_only=True, frozen=True)
class ProviderEntry:
    local_name: str
    source: str | None
    version: str | None
    location: Location


@dataclass(slots=True, kw_only=True, frozen=True)
class AssignmentEntry:
    name: str
    location: Location


@dataclass(slots=True, kw_only=True, frozen=True)
class ProblemEntry:
    path: str
    message: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleSummary:
    path: str
    kind: TargetKind
    variables: list[VariableEntry]
    outputs: list[OutputEntry]
    resources: list[ObjectEntry]
    data_sources: list[ObjectEntry]
    module_calls: list[ModuleCallEntry]
    required_providers: list[ProviderEntry]
    problems: list[ProblemEntry]


@dataclass(slots=True, kw_only=True, frozen=True)
class TfvarsSummary:
    path: str
    kind: TargetKind
    declared: list[AssignmentEntry]
    undeclared: list[AssignmentEntry]
    problems: list[ProblemEntry]
