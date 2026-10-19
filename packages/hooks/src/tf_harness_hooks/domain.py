"""Values and the handler type shared by every hook subcommand."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, TextIO

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from tf_harness_mcp.runner.domain import CommandRunner

type Subcommand = Literal['fmt', 'read', 'session-start']

SUBCOMMANDS: Final[tuple[Subcommand, ...]] = ('fmt', 'read', 'session-start')
FILE_SUBCOMMANDS: Final[frozenset[Subcommand]] = frozenset({'fmt', 'read'})


@dataclass(slots=True, kw_only=True, frozen=True)
class HookRequest:
    event_name: str
    project_root: Path
    runner: CommandRunner
    file_path: Path | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class HookOutput:
    event_name: str
    additional_context: str

    def to_wire(self) -> dict[str, dict[str, str]]:
        return {
            'hookSpecificOutput': {
                'hookEventName': self.event_name,
                'additionalContext': self.additional_context,
            }
        }


type Handler = Callable[[HookRequest], Awaitable[HookOutput | None]]


async def ignore_event(_request: HookRequest) -> HookOutput | None:
    return None


def default_handlers() -> dict[Subcommand, Handler]:
    return dict.fromkeys(SUBCOMMANDS, ignore_event)


@dataclass(slots=True, kw_only=True, frozen=True)
class HookIo:
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO


@dataclass(slots=True, kw_only=True, frozen=True)
class HookSession:
    subcommand: Subcommand
    environ: Mapping[str, str]
    io: HookIo
    runner: CommandRunner
    handlers: Mapping[Subcommand, Handler]
