"""The read-only command policy: which argv prefixes a runner may start."""

import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tf_harness_mcp.runner.errors import CommandNotAllowedError

if TYPE_CHECKING:
    from tf_harness_mcp.runner.domain import Command

type CommandPrefix = tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class AllowedCommand:
    prefix: CommandPrefix
    forbidden_flags: tuple[str, ...] = ()


def default_read_only_commands() -> tuple[AllowedCommand, ...]:
    return (
        AllowedCommand(prefix=('terraform', 'version')),
        AllowedCommand(prefix=('terraform', 'fmt', '-check')),
        AllowedCommand(prefix=('terraform', 'validate')),
        AllowedCommand(prefix=('terraform', 'providers', 'schema', '-json')),
        AllowedCommand(prefix=('tflint',), forbidden_flags=('--fix', '--init')),
        AllowedCommand(
            prefix=('git', 'rev-parse', '--verify', '--quiet', '--end-of-options'),
        ),
        AllowedCommand(prefix=('git', 'merge-base')),
        AllowedCommand(
            prefix=('git', 'diff', '--no-ext-diff', '--no-textconv'),
            forbidden_flags=('--output', '--ext-diff', '--textconv'),
        ),
        AllowedCommand(prefix=('git', 'ls-files', '--others', '--exclude-standard')),
        AllowedCommand(prefix=('git', 'cat-file', 'blob')),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ReadOnlyOptions:
    commands: tuple[AllowedCommand, ...] = field(default_factory=default_read_only_commands)


@dataclass(slots=True, kw_only=True, frozen=True)
class ReadOnlyCommandPolicy:
    command: Command
    options: ReadOnlyOptions

    def has_flag(self, flag: str) -> bool:
        return any(arg == flag or arg.startswith(f'{flag}=') for arg in self.command.argv)

    def is_allowed_by(self, allowed: AllowedCommand) -> bool:
        if not allowed.prefix or self.command.argv[: len(allowed.prefix)] != allowed.prefix:
            return False

        return not any(map(self.has_flag, allowed.forbidden_flags))

    def get_command_problem(self) -> CommandNotAllowedError | None:
        if any(map(self.is_allowed_by, self.options.commands)):
            return None

        return CommandNotAllowedError(command=shlex.join(self.command.argv))
