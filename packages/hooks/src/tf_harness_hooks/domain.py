"""Values and the handler type shared by every hook subcommand."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, TextIO

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from tf_harness_mcp.runner.domain import CommandRunner
    from tf_harness_mcp.runner.policy import ReadOnlyOptions

type Subcommand = Literal['fmt', 'read', 'session-start']

SUBCOMMANDS: Final[tuple[Subcommand, ...]] = ('fmt', 'read', 'session-start')


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


@dataclass(slots=True, kw_only=True, frozen=True)
class HookSpec:
    handler: Handler
    runner_options: ReadOnlyOptions
    needs_file: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class HookIo:
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO


@dataclass(slots=True, kw_only=True, frozen=True)
class HookSession:
    spec: HookSpec
    environ: Mapping[str, str]
    io: HookIo
    runner: CommandRunner
