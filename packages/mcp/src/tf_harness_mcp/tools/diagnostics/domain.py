"""Values and the protocol shared by every diagnostics check."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from tf_harness_mcp.runner.domain import CommandResult

type CheckStatus = Literal['passed', 'failed', 'skipped']


@dataclass(slots=True, kw_only=True, frozen=True)
class Finding:
    severity: str
    summary: str
    detail: str = ''
    file: str | None = None
    line: int | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class CheckReport:
    status: CheckStatus
    reason: str | None = None
    findings: list[Finding] = field(default_factory=list)


@runtime_checkable
class Check(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def argv(self) -> tuple[str, ...]: ...

    @property
    def timeout_seconds(self) -> float: ...

    def interpret(self, result: CommandResult) -> CheckReport: ...
