"""Values and the protocol shared by every tool that starts a command."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True, kw_only=True, frozen=True)
class Command:
    argv: tuple[str, ...]
    cwd: Path | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@runtime_checkable
class CommandRunner(Protocol):
    async def run(self, command: Command, timeout_seconds: float) -> CommandResult: ...
