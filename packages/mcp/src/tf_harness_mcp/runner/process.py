"""The anyio command runner and the factory that builds it at the edge."""

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

import anyio

from tf_harness_mcp.runner.domain import CommandResult
from tf_harness_mcp.runner.errors import CommandTimeoutError
from tf_harness_mcp.runner.policy import ReadOnlyCommandPolicy, ReadOnlyOptions

if TYPE_CHECKING:
    from collections.abc import Mapping

    from tf_harness_mcp.runner.domain import Command, CommandRunner

CHECKPOINT_DISABLE = 'CHECKPOINT_DISABLE'


@dataclass(slots=True, kw_only=True, frozen=True)
class AnyioCommandRunner:
    environ: Mapping[str, str]
    options: ReadOnlyOptions

    async def run(self, command: Command, timeout_seconds: float) -> CommandResult:
        policy = ReadOnlyCommandPolicy(command=command, options=self.options)
        if problem := policy.get_command_problem():
            raise problem

        environment = {**self.environ, CHECKPOINT_DISABLE: '1'}
        try:
            with anyio.fail_after(timeout_seconds):
                completed = await anyio.run_process(
                    list(command.argv),
                    cwd=command.cwd,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    check=False,
                )
        except TimeoutError as err:
            raise CommandTimeoutError(
                command=shlex.join(command.argv), timeout_seconds=timeout_seconds
            ) from err

        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout.decode(errors='replace'),
            stderr=completed.stderr.decode(errors='replace'),
        )


def create_command_runner(
    environ: Mapping[str, str] | None = None, options: ReadOnlyOptions | None = None
) -> CommandRunner:
    return AnyioCommandRunner(
        environ=dict(os.environ) if environ is None else environ,
        options=options or ReadOnlyOptions(),
    )
