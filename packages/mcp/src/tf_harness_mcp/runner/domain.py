"""Values and the protocol shared by every tool that starts a command."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(slots=True, kw_only=True, frozen=True)
class Command:
    argv: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@runtime_checkable
class CommandRunner(Protocol):
    async def run(self, command: Command, timeout_seconds: float) -> CommandResult: ...
