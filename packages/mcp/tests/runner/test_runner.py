import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest
from tf_harness_mcp.runner.domain import Command
from tf_harness_mcp.runner.errors import (
    CommandNotAllowedError,
    CommandNotFoundError,
    CommandTimeoutError,
)
from tf_harness_mcp.runner.policy import (
    AllowedCommand,
    ReadOnlyCommandPolicy,
    ReadOnlyOptions,
    default_read_only_commands,
)
from tf_harness_mcp.runner.process import create_command_runner

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from tf_harness_mcp.runner.domain import CommandRunner

READ_STDIN = 'import sys; print(repr(sys.stdin.read()))'
PRINT_ENV = 'import os, sys; print(os.environ.get(sys.argv[1], "unset"))'
PRINT_CWD = 'import pathlib; print(pathlib.Path.cwd().resolve())'
GIT_DIFF_PINS = ('diff', '--no-ext-diff', '--no-textconv', '--no-color', '--no-prefix')


def python_options() -> ReadOnlyOptions:
    return ReadOnlyOptions(commands=(AllowedCommand(prefix=(sys.executable, '-c')),))


def python_command(script: str, *args: str, cwd: Path | None = None) -> Command:
    return Command(argv=(sys.executable, '-c', script, *args), cwd=cwd)


def terraform_command(*args: str) -> Command:
    return Command(argv=('terraform', *args))


def git_command(*args: str) -> Command:
    return Command(argv=('git', *args))


def allowed_command_cases() -> pytest.MarkDecorator:
    names = {
        'version': terraform_command('version'),
        'version-json': terraform_command('version', '-json'),
        'fmt-check': terraform_command('fmt', '-check'),
        'fmt-check-recursive': terraform_command('fmt', '-check', '-recursive', '-no-color'),
        'validate': terraform_command('validate'),
        'validate-json': terraform_command('validate', '-json', '-no-color'),
        'providers-schema-json': terraform_command('providers', 'schema', '-json'),
        'tflint': Command(argv=('tflint',)),
        'tflint-json': Command(argv=('tflint', '--format=json', '--recursive')),
        'git-resolve': git_command(
            'rev-parse', '--verify', '--quiet', '--end-of-options', 'main^{commit}'
        ),
        'git-merge-base': git_command('merge-base', 'a' * 40, 'HEAD'),
        'git-diff': git_command(*GIT_DIFF_PINS, '--name-status', '-z', 'b' * 40, '--', '*.tf'),
        'git-ls-files': git_command('ls-files', '--others', '--exclude-standard', '-z'),
        'git-cat-file': git_command('cat-file', 'blob', 'b' * 40 + ':./main.tf'),
    }
    params: list[ParameterSet] = [pytest.param(cmd, id=name) for name, cmd in names.items()]
    return pytest.mark.parametrize('command', params)


def refused_command_cases() -> pytest.MarkDecorator:
    names = {
        'init': terraform_command('init'),
        'plan': terraform_command('plan'),
        'apply': terraform_command('apply'),
        'version-prefix-only': terraform_command(),
        'other-binary': Command(argv=('rm', '-rf', 'x')),
        'shell-string': Command(argv=('sh', '-c', 'terraform version')),
        'empty': Command(argv=()),
        'fmt-without-check': terraform_command('fmt'),
        'fmt-write-only': terraform_command('fmt', '-write=true'),
        'fmt-check-not-first': terraform_command('fmt', '-recursive', '-check'),
        'providers': terraform_command('providers'),
        'providers-lock': terraform_command('providers', 'lock'),
        'providers-mirror': terraform_command(
            'providers', 'mirror', '-platform=linux_amd64', 'out'
        ),
        'providers-schema-without-json': terraform_command('providers', 'schema'),
        'providers-json-without-schema': terraform_command('providers', '-json'),
        'tflint-fix': Command(argv=('tflint', '--fix')),
        'tflint-fix-last': Command(argv=('tflint', '--format=json', '--fix')),
        'tflint-fix-with-value': Command(argv=('tflint', '--fix=true')),
        'tflint-init': Command(argv=('tflint', '--init')),
        'tflint-init-last': Command(argv=('tflint', '--recursive', '--init')),
        'git-diff-output': git_command(*GIT_DIFF_PINS, '--output=x', 'HEAD'),
        'git-diff-output-separate': git_command(*GIT_DIFF_PINS, '--output', 'x', 'HEAD'),
        'git-diff-output-last': git_command(*GIT_DIFF_PINS, 'HEAD', '--output=x'),
        'git-diff-ext-diff': git_command(*GIT_DIFF_PINS, '--ext-diff', 'HEAD'),
        'git-diff-textconv': git_command(*GIT_DIFF_PINS, '--textconv', 'HEAD'),
        'git-diff-without-pins': git_command('diff', 'HEAD'),
        'git-diff-without-textconv-pin': git_command('diff', '--no-ext-diff', 'HEAD'),
        'git-diff-pins-not-first': git_command('diff', 'HEAD', *GIT_DIFF_PINS[1:]),
        'git-global-option': Command(argv=('git', '-C', 'x', 'diff', *GIT_DIFF_PINS[1:])),
        'git-config-option': Command(argv=('git', '-c', 'core.pager=x', 'merge-base', 'a', 'b')),
        'git-push': git_command('push'),
        'git-checkout': git_command('checkout', 'main'),
        'git-config': git_command('config', 'user.name', 'x'),
        'git-rev-parse-without-pins': git_command('rev-parse', 'HEAD'),
        'git-ls-files-without-others': git_command('ls-files'),
        'git-cat-file-without-blob': git_command('cat-file', '-p', 'HEAD'),
    }
    params: list[ParameterSet] = [pytest.param(cmd, id=name) for name, cmd in names.items()]
    return pytest.mark.parametrize('command', params)


@pytest.mark.unit
class TestDefaultReadOnlyCommands:
    def test_default_read_only_commands_pin_the_ten_prefixes_in_order(self) -> None:
        assert tuple(command.prefix for command in default_read_only_commands()) == (
            ('terraform', 'version'),
            ('terraform', 'fmt', '-check'),
            ('terraform', 'validate'),
            ('terraform', 'providers', 'schema', '-json'),
            ('tflint',),
            ('git', 'rev-parse', '--verify', '--quiet', '--end-of-options'),
            ('git', 'merge-base'),
            ('git', 'diff', '--no-ext-diff', '--no-textconv'),
            ('git', 'ls-files', '--others', '--exclude-standard'),
            ('git', 'cat-file', 'blob'),
        )

    def test_default_read_only_commands_forbid_flags_only_on_tflint_and_git_diff(self) -> None:
        forbidden = {
            command.prefix: command.forbidden_flags
            for command in default_read_only_commands()
            if command.forbidden_flags
        }

        assert forbidden == {
            ('tflint',): ('--fix', '--init'),
            ('git', 'diff', '--no-ext-diff', '--no-textconv'): (
                '--output',
                '--ext-diff',
                '--textconv',
            ),
        }


@pytest.mark.unit
class TestReadOnlyCommandPolicy:
    def find_problem(self, command: Command) -> CommandNotAllowedError | None:
        policy = ReadOnlyCommandPolicy(command=command, options=ReadOnlyOptions())
        return policy.get_command_problem()

    @allowed_command_cases()
    def test_read_only_command_is_allowed(self, command: Command) -> None:
        assert self.find_problem(command) is None

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
class TestMissingBinary:
    timeout = 10.0
    binary = 'tf-harness-missing-binary'

    @pytest.fixture
    def runner(self) -> CommandRunner:
        options = ReadOnlyOptions(commands=(AllowedCommand(prefix=(self.binary,)),))
        return create_command_runner(options=options)

    async def test_missing_binary_is_named(self, runner: CommandRunner) -> None:
        with pytest.raises(CommandNotFoundError) as raised:
            await runner.run(Command(argv=(self.binary,)), self.timeout)

        assert raised.value.command == self.binary

    async def test_missing_working_directory_is_not_a_missing_binary(self, tmp_path: Path) -> None:
        runner = create_command_runner(options=python_options())
        command = python_command(PRINT_CWD, cwd=tmp_path.joinpath('absent'))

        with pytest.raises(FileNotFoundError):
            await runner.run(command, self.timeout)


@pytest.mark.unit
class TestCommandWorkingDirectory:
    timeout = 10.0

    @pytest.fixture
    def runner(self) -> CommandRunner:
        return create_command_runner(options=python_options())

    @pytest.fixture
    def resolved_tmp_path(self, tmp_path: Path) -> Path:
        return tmp_path.resolve()

    @pytest.fixture
    def resolved_process_directory(self) -> Path:
        return Path.cwd().resolve()

    async def test_child_starts_in_the_command_directory(
        self, runner: CommandRunner, tmp_path: Path, resolved_tmp_path: Path
    ) -> None:
        result = await runner.run(python_command(PRINT_CWD, cwd=tmp_path), self.timeout)

        assert result.stdout.strip() == str(resolved_tmp_path)

    async def test_child_inherits_the_process_directory_without_one(
        self, runner: CommandRunner, resolved_process_directory: Path
    ) -> None:
        result = await runner.run(python_command(PRINT_CWD), self.timeout)

        assert result.stdout.strip() == str(resolved_process_directory)

    async def test_refused_command_is_refused_in_any_directory(
        self, runner: CommandRunner, tmp_path: Path
    ) -> None:
        command = Command(argv=('terraform', 'apply'), cwd=tmp_path)

        with pytest.raises(CommandNotAllowedError):
            await runner.run(command, self.timeout)


@pytest.mark.unit
class TestChildStdin:
    server_stdin = b'mcp protocol bytes'
    server_script = f"""
import sys
import anyio
from tf_harness_mcp.runner.domain import Command
from tf_harness_mcp.runner.policy import AllowedCommand, ReadOnlyOptions
from tf_harness_mcp.runner.process import create_command_runner

async def main():
    options = ReadOnlyOptions(commands=(AllowedCommand(prefix=(sys.executable, '-c')),))
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
