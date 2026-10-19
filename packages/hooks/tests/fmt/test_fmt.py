from typing import TYPE_CHECKING

import pytest
from tf_harness_hooks.cli import create_hook_specs
from tf_harness_hooks.domain import HookRequest
from tf_harness_hooks.fmt import FMT_TIMEOUT_SECONDS, format_file
from tf_harness_hooks.policy import FMT_WRITE_PREFIX
from tf_harness_mcp.runner.domain import Command, CommandResult
from tf_harness_mcp.runner.errors import CommandTimeoutError
from tf_harness_mcp.runner.policy import ReadOnlyCommandPolicy
from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_hooks.domain import Subcommand
    from tf_harness_mcp.runner.errors import CommandNotAllowedError
    from tf_harness_mcp.runner.policy import ReadOnlyOptions

pytestmark = pytest.mark.unit


@pytest.fixture
def fmt_runner() -> RecordingCommandRunner:
    return RecordingCommandRunner(options=create_hook_specs()['fmt'].runner_options)


class TestFormatFile:
    parse_error = 'Error: Unclosed configuration block\n\n  on main.tf line 1\n'

    def request(self, project_root: Path, runner: RecordingCommandRunner, name: str) -> HookRequest:
        return HookRequest(
            event_name='PostToolUse',
            project_root=project_root,
            runner=runner,
            file_path=project_root / name,
        )

    async def test_rewrite_gives_one_notice_line(
        self, project_root: Path, fmt_runner: RecordingCommandRunner
    ) -> None:
        request = self.request(project_root, fmt_runner, 'main.tf')
        argv = (*FMT_WRITE_PREFIX, str(project_root / 'main.tf'))
        fmt_runner.script(argv, CommandResult(returncode=0, stdout=f'{argv[-1]}\n', stderr=''))

        output = await format_file(request)

        assert output is not None
        assert output.additional_context == f'terraform fmt rewrote {argv[-1]}'
        assert '\n' not in output.additional_context
        assert [call.command.argv for call in fmt_runner.calls] == [argv]
        assert [call.timeout_seconds for call in fmt_runner.calls] == [FMT_TIMEOUT_SECONDS]
        assert FMT_TIMEOUT_SECONDS == 15

    async def test_unchanged_file_gives_no_output(
        self, project_root: Path, fmt_runner: RecordingCommandRunner
    ) -> None:
        argv = (*FMT_WRITE_PREFIX, str(project_root / 'main.tf'))
        fmt_runner.script(argv, CommandResult(returncode=0, stdout='', stderr=''))

        assert await format_file(self.request(project_root, fmt_runner, 'main.tf')) is None

    async def test_parse_error_passes_stderr_trimmed(
        self, project_root: Path, fmt_runner: RecordingCommandRunner
    ) -> None:
        argv = (*FMT_WRITE_PREFIX, str(project_root / 'main.tf'))
        fmt_runner.script(argv, CommandResult(returncode=2, stdout='', stderr=self.parse_error))

        output = await format_file(self.request(project_root, fmt_runner, 'main.tf'))

        assert output is not None
        assert output.additional_context == self.parse_error.strip()

    async def test_file_name_with_metacharacters_stays_one_argv_element(
        self, project_root: Path, fmt_runner: RecordingCommandRunner
    ) -> None:
        name = 'a b;$(x).tf'
        argv = (*FMT_WRITE_PREFIX, str(project_root / name))
        fmt_runner.script(argv, CommandResult(returncode=0, stdout='', stderr=''))

        await format_file(self.request(project_root, fmt_runner, name))

        assert fmt_runner.calls[0].command.argv == argv
        assert fmt_runner.calls[0].command.argv[-1] == str(project_root / name)

    async def test_missing_binary_is_silent(
        self, project_root: Path, fmt_runner: RecordingCommandRunner
    ) -> None:
        fmt_runner.script_missing_binary((*FMT_WRITE_PREFIX, str(project_root / 'main.tf')))

        assert await format_file(self.request(project_root, fmt_runner, 'main.tf')) is None

    async def test_timeout_gives_one_notice_naming_the_limit(self, project_root: Path) -> None:
        class TimingOutRunner:
            async def run(self, command: Command, timeout_seconds: float) -> CommandResult:
                raise CommandTimeoutError(
                    command=' '.join(command.argv), timeout_seconds=timeout_seconds
                )

        request = HookRequest(
            event_name='PostToolUse',
            project_root=project_root,
            runner=TimingOutRunner(),
            file_path=project_root / 'main.tf',
        )

        output = await format_file(request)

        assert output is not None
        assert '15s' in output.additional_context

    async def test_request_without_a_file_gives_no_output(
        self, project_root: Path, fmt_runner: RecordingCommandRunner
    ) -> None:
        request = HookRequest(
            event_name='PostToolUse', project_root=project_root, runner=fmt_runner
        )

        assert await format_file(request) is None
        assert fmt_runner.calls == []


class TestFmtPolicy:
    fmt_argv = (*FMT_WRITE_PREFIX, '/project/main.tf')

    def problem_for(
        self, options: ReadOnlyOptions, argv: tuple[str, ...]
    ) -> CommandNotAllowedError | None:
        return ReadOnlyCommandPolicy(
            command=Command(argv=argv), options=options
        ).get_command_problem()

    def test_fmt_policy_allows_the_write_argv(self) -> None:
        assert self.problem_for(create_hook_specs()['fmt'].runner_options, self.fmt_argv) is None

    @pytest.mark.parametrize(
        'argv',
        [
            ('terraform', 'validate'),
            ('terraform', 'fmt', '-check', '/project/main.tf'),
            ('terraform', 'fmt', '-list=true', '-no-color', '-recursive', '/p/main.tf'),
            ('git', 'diff'),
        ],
    )
    def test_fmt_policy_allows_nothing_else(self, argv: tuple[str, ...]) -> None:
        assert self.problem_for(create_hook_specs()['fmt'].runner_options, argv) is not None

    @pytest.mark.parametrize('subcommand', ['read', 'session-start'])
    def test_default_read_only_commands_still_refuse_the_write_argv(
        self, subcommand: Subcommand
    ) -> None:
        options = create_hook_specs()[subcommand].runner_options

        assert self.problem_for(options, self.fmt_argv) is not None
