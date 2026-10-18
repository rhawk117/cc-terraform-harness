"""The read-only command policy: which argv prefixes a runner may start."""

import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tf_harness_mcp.runner.errors import CommandNotAllowedError

if TYPE_CHECKING:
    from tf_harness_mcp.runner.domain import Command

type CommandPrefix = tuple[str, ...]


def default_read_only_prefixes() -> tuple[CommandPrefix, ...]:
    return (('terraform', 'version'),)


@dataclass(slots=True, kw_only=True, frozen=True)
class ReadOnlyOptions:
    prefixes: tuple[CommandPrefix, ...] = field(default_factory=default_read_only_prefixes)


@dataclass(slots=True, kw_only=True, frozen=True)
class ReadOnlyCommandPolicy:
    command: Command
    options: ReadOnlyOptions

    def is_allowed_by(self, prefix: CommandPrefix) -> bool:
        return bool(prefix) and self.command.argv[: len(prefix)] == prefix

    def get_command_problem(self) -> CommandNotAllowedError | None:
        if any(self.is_allowed_by(prefix) for prefix in self.options.prefixes):
            return None

        return CommandNotAllowedError(command=shlex.join(self.command.argv))
