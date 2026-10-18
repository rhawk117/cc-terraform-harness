"""The recording command runner fake and the fixture that hands it to tests."""

import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from tf_harness_mcp.errors import HarnessError
from tf_harness_mcp.runner.errors import CommandNotFoundError
from tf_harness_mcp.runner.policy import ReadOnlyCommandPolicy, ReadOnlyOptions

if TYPE_CHECKING:
    from tf_harness_mcp.runner.domain import Command, CommandResult
    from tf_harness_mcp.runner.policy import CommandPrefix


class UnscriptedCommandError(HarnessError):
    def __init__(self, *, command: str) -> None:
        self.command = command
        super().__init__(f'no scripted result for command: {command}')


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedCall:
    command: Command
    timeout_seconds: float


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordingCommandRunner:
    options: ReadOnlyOptions = field(default_factory=ReadOnlyOptions)
    results: dict[CommandPrefix, CommandResult] = field(default_factory=dict)
    missing: set[CommandPrefix] = field(default_factory=set)
    calls: list[RecordedCall] = field(default_factory=list)

    def script(self, argv: CommandPrefix, result: CommandResult) -> None:
        self.results[argv] = result

    def script_missing_binary(self, argv: CommandPrefix) -> None:
        self.missing.add(argv)

    async def run(self, command: Command, timeout_seconds: float) -> CommandResult:
        policy = ReadOnlyCommandPolicy(command=command, options=self.options)
        if problem := policy.get_command_problem():
            raise problem

        self.calls.append(RecordedCall(command=command, timeout_seconds=timeout_seconds))
        if command.argv in self.missing:
            raise CommandNotFoundError(command=command.argv[0])

        result = self.results.get(command.argv)
        if result is None:
            raise UnscriptedCommandError(command=shlex.join(command.argv))

        return result


@pytest.fixture
def recording_runner() -> RecordingCommandRunner:
    return RecordingCommandRunner()
