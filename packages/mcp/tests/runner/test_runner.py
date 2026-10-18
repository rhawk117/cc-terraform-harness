import shutil
import sys
from typing import TYPE_CHECKING

import anyio
import pytest
from tf_harness_mcp.runner.domain import Command
from tf_harness_mcp.runner.errors import CommandNotAllowedError, CommandTimeoutError
from tf_harness_mcp.runner.policy import ReadOnlyCommandPolicy, ReadOnlyOptions
from tf_harness_mcp.runner.process import create_command_runner

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from tf_harness_mcp.runner.domain import CommandRunner

READ_STDIN = 'import sys; print(repr(sys.stdin.read()))'
PRINT_ENV = 'import os, sys; print(os.environ.get(sys.argv[1], "unset"))'


def python_options() -> ReadOnlyOptions:
    return ReadOnlyOptions(prefixes=((sys.executable, '-c'),))


def python_command(script: str, *args: str) -> Command:
    return Command(argv=(sys.executable, '-c', script, *args))


def terraform_command(*args: str) -> Command:
    return Command(argv=('terraform', *args))


def refused_command_cases() -> pytest.MarkDecorator:
    names = {
        'init': terraform_command('init'),
        'plan': terraform_command('plan'),
        'apply': terraform_command('apply'),
        'version-prefix-only': terraform_command(),
        'other-binary': Command(argv=('rm', '-rf', 'x')),
        'shell-string': Command(argv=('sh', '-c', 'terraform version')),
        'empty': Command(argv=()),
    }
    params: list[ParameterSet] = [pytest.param(cmd, id=name) for name, cmd in names.items()]
    return pytest.mark.parametrize('command', params)


@pytest.mark.unit
class TestReadOnlyCommandPolicy:
    def find_problem(self, command: Command) -> CommandNotAllowedError | None:
        policy = ReadOnlyCommandPolicy(command=command, options=ReadOnlyOptions())
        return policy.get_command_problem()

    def test_default_set_holds_terraform_version_only(self) -> None:
        assert ReadOnlyOptions().prefixes == (('terraform', 'version'),)

    @pytest.mark.parametrize('args', [('version',), ('version', '-json')])
    def test_terraform_version_is_allowed(self, args: tuple[str, ...]) -> None:
        assert self.find_problem(terraform_command(*args)) is None

    @refused_command_cases()
    def test_command_outside_the_set_is_refused(self, command: Command) -> None:
        assert isinstance(self.find_problem(command), CommandNotAllowedError)


@pytest.mark.unit
class TestAnyioCommandRunner:
    timeout = 10.0

    @pytest.fixture
    def runner(self) -> CommandRunner:
        return create_command_runner({'KEEP_ME': 'kept'}, python_options())

    async def read_variable(self, runner: CommandRunner, name: str) -> str:
        result = await runner.run(python_command(PRINT_ENV, name), self.timeout)
        return result.stdout.strip()

    async def test_sets_checkpoint_disable(self, runner: CommandRunner) -> None:
        assert await self.read_variable(runner, 'CHECKPOINT_DISABLE') == '1'

    async def test_merges_the_given_environment(self, runner: CommandRunner) -> None:
        assert await self.read_variable(runner, 'KEEP_ME') == 'kept'

    async def test_defaults_to_the_process_environment(self) -> None:
        runner = create_command_runner(options=python_options())

        assert await self.read_variable(runner, 'PATH') != 'unset'

    async def test_argv_is_never_passed_to_a_shell(self, runner: CommandRunner) -> None:
        script = 'import sys; print(sys.argv[1])'
        literal = 'a; echo pwned'

        result = await runner.run(python_command(script, literal), self.timeout)

        assert result.stdout.strip() == literal

    async def test_reports_exit_status_and_stderr(self, runner: CommandRunner) -> None:
        script = 'import sys; sys.stderr.write("bad"); sys.exit(3)'

        result = await runner.run(python_command(script), self.timeout)

        assert (result.returncode, result.stderr) == (3, 'bad')

    async def test_refuses_command_outside_the_set(self, runner: CommandRunner) -> None:
        with pytest.raises(CommandNotAllowedError):
            await runner.run(terraform_command('apply'), self.timeout)

    async def test_timeout_error_names_the_command(self, runner: CommandRunner) -> None:
        command = python_command('import time; time.sleep(30)')

        with pytest.raises(CommandTimeoutError) as raised:
            await runner.run(command, 0.2)

        assert 'time.sleep(30)' in str(raised.value)
        assert raised.value.timeout_seconds == 0.2


@pytest.mark.unit
class TestChildStdin:
    server_stdin = b'mcp protocol bytes'
    server_script = f"""
import sys
import anyio
from tf_harness_mcp.runner.domain import Command
from tf_harness_mcp.runner.policy import ReadOnlyOptions
from tf_harness_mcp.runner.process import create_command_runner

async def main():
    options = ReadOnlyOptions(prefixes=((sys.executable, '-c'),))
    command = Command(argv=(sys.executable, '-c', {READ_STDIN!r}))
    result = await create_command_runner(options=options).run(command, 10.0)
    print(result.stdout.strip())

anyio.run(main)
"""

    @pytest.fixture
    def server_argv(self) -> list[str]:
        return [sys.executable, '-c', self.server_script]

    async def test_child_stdin_is_closed(self, server_argv: list[str]) -> None:
        server = await anyio.run_process(server_argv, input=self.server_stdin, check=False)

        assert server.stdout.decode().strip() == "''"


@pytest.mark.integration
@pytest.mark.skipif(shutil.which('terraform') is None, reason='terraform is not on PATH')
class TestTerraformVersion:
    async def test_runs_terraform_version_json(self) -> None:
        runner = create_command_runner()

        result = await runner.run(terraform_command('version', '-json'), 30.0)

        assert result.returncode == 0
        assert '"terraform_version"' in result.stdout
