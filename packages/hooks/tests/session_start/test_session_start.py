import json
from typing import TYPE_CHECKING

import pytest
from tf_harness_hooks.domain import HookRequest
from tf_harness_hooks.policy import (
    SESSION_START_PROBES,
    TERRAFORM_LS_VERSION_ARGV,
    TERRAFORM_VERSION_ARGV,
    TFLINT_VERSION_ARGV,
    runner_options,
)
from tf_harness_hooks.session_start import PROBE_TIMEOUT_SECONDS, report_tool_versions
from tf_harness_mcp.runner.domain import Command, CommandResult
from tf_harness_mcp.runner.errors import CommandTimeoutError
from tf_harness_mcp.runner.policy import ReadOnlyCommandPolicy
from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_hooks.domain import HookOutput
    from tf_harness_mcp.runner.errors import CommandNotAllowedError

pytestmark = pytest.mark.unit

TERRAFORM_JSON = json.dumps({'terraform_version': '1.15.8', 'platform': 'linux_amd64'})
TFLINT_OUTPUT = 'TFLint version 0.64.0\n+ ruleset.terraform (0.15.0-bundled)\n'
TERRAFORM_LS_OUTPUT = '0.39.0\nplatform: linux/amd64\ngo: go1.24\ncompiler: gc\n'


def succeed(stdout: str) -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr='')


@pytest.fixture
def probe_runner() -> RecordingCommandRunner:
    runner = RecordingCommandRunner(options=runner_options('session-start'))
    runner.script(TERRAFORM_VERSION_ARGV, succeed(TERRAFORM_JSON))
    runner.script(TFLINT_VERSION_ARGV, succeed(TFLINT_OUTPUT))
    runner.script(TERRAFORM_LS_VERSION_ARGV, succeed(TERRAFORM_LS_OUTPUT))
    return runner


async def report(project_root: Path, runner: RecordingCommandRunner) -> HookOutput:
    request = HookRequest(event_name='SessionStart', project_root=project_root, runner=runner)
    output = await report_tool_versions(request)
    assert output is not None
    return output


class TestVersionReport:
    async def test_all_present_gives_three_version_lines(
        self, project_root: Path, probe_runner: RecordingCommandRunner
    ) -> None:
        output = await report(project_root, probe_runner)

        assert output.additional_context.splitlines() == [
            'terraform: 1.15.8',
            'tflint: 0.64.0',
            'terraform-ls: 0.39.0',
        ]

    async def test_output_is_a_session_start_envelope(
        self, project_root: Path, probe_runner: RecordingCommandRunner
    ) -> None:
        output = await report(project_root, probe_runner)

        assert output.to_wire()['hookSpecificOutput']['hookEventName'] == 'SessionStart'

    async def test_each_probe_runs_once_with_a_ten_second_timeout(
        self, project_root: Path, probe_runner: RecordingCommandRunner
    ) -> None:
        await report(project_root, probe_runner)

        assert [call.command.argv for call in probe_runner.calls] == list(SESSION_START_PROBES)
        assert {call.timeout_seconds for call in probe_runner.calls} == {10.0}
        assert PROBE_TIMEOUT_SECONDS == 10.0


class TestMissingBinaries:
    @pytest.mark.parametrize(
        ('argv', 'name', 'degrades'),
        [
            (TERRAFORM_VERSION_ARGV, 'terraform', 'fmt hook'),
            (TFLINT_VERSION_ARGV, 'tflint', 'tflint check'),
            (TERRAFORM_LS_VERSION_ARGV, 'terraform-ls', 'language server'),
        ],
    )
    async def test_missing_binary_is_reported_with_what_it_degrades(
        self,
        project_root: Path,
        probe_runner: RecordingCommandRunner,
        argv: tuple[str, ...],
        name: str,
        degrades: str,
    ) -> None:
        probe_runner.script_missing_binary(argv)

        lines = (await report(project_root, probe_runner)).additional_context.splitlines()

        missing = [line for line in lines if line.startswith(f'{name}: not found')]
        assert len(missing) == 1
        assert degrades in missing[0]
        assert len(lines) == 3

    async def test_all_missing_still_reports_three_lines(
        self, project_root: Path, probe_runner: RecordingCommandRunner
    ) -> None:
        for argv in SESSION_START_PROBES:
            probe_runner.script_missing_binary(argv)

        output = await report(project_root, probe_runner)

        assert output.additional_context.count('not found') == 3


class TestProbeFailures:
    async def test_timeout_names_the_binary_and_the_limit(self, project_root: Path) -> None:
        class TimingOutRunner:
            async def run(self, command: Command, timeout_seconds: float) -> CommandResult:
                raise CommandTimeoutError(
                    command=' '.join(command.argv), timeout_seconds=timeout_seconds
                )

        request = HookRequest(
            event_name='SessionStart', project_root=project_root, runner=TimingOutRunner()
        )

        output = await report_tool_versions(request)

        assert output is not None
        assert output.additional_context.splitlines() == [
            'terraform: version check timed out after 10s',
            'tflint: version check timed out after 10s',
            'terraform-ls: version check timed out after 10s',
        ]

    async def test_non_zero_exit_names_the_binary_and_the_code(
        self, project_root: Path, probe_runner: RecordingCommandRunner
    ) -> None:
        probe_runner.script(
            TFLINT_VERSION_ARGV, CommandResult(returncode=2, stdout='', stderr='boom')
        )

        lines = (await report(project_root, probe_runner)).additional_context.splitlines()

        assert lines[1] == 'tflint: version check exited with code 2'
        assert lines[0] == 'terraform: 1.15.8'

    @pytest.mark.parametrize('stdout', ['', 'not json', '[]', '{"other": 1}'])
    async def test_unreadable_terraform_json_is_reported(
        self, project_root: Path, probe_runner: RecordingCommandRunner, stdout: str
    ) -> None:
        probe_runner.script(TERRAFORM_VERSION_ARGV, succeed(stdout))

        lines = (await report(project_root, probe_runner)).additional_context.splitlines()

        assert lines[0] == 'terraform: installed, version not readable'

    async def test_empty_tflint_output_is_reported(
        self, project_root: Path, probe_runner: RecordingCommandRunner
    ) -> None:
        probe_runner.script(TFLINT_VERSION_ARGV, succeed(''))

        lines = (await report(project_root, probe_runner)).additional_context.splitlines()

        assert lines[1] == 'tflint: installed, version not readable'


class TestSessionStartPolicy:
    def problem_for(self, argv: tuple[str, ...]) -> CommandNotAllowedError | None:
        return ReadOnlyCommandPolicy(
            command=Command(argv=argv), options=runner_options('session-start')
        ).get_command_problem()

    @pytest.mark.parametrize('argv', SESSION_START_PROBES)
    def test_allows_the_three_probe_argvs(self, argv: tuple[str, ...]) -> None:
        assert self.problem_for(argv) is None

    @pytest.mark.parametrize(
        'argv',
        [
            ('terraform', 'validate'),
            ('terraform', 'version'),
            ('tflint', '--init'),
            ('tflint',),
            ('terraform-ls', 'serve'),
            ('git', 'diff'),
        ],
    )
    def test_refuses_every_other_argv(self, argv: tuple[str, ...]) -> None:
        assert self.problem_for(argv) is not None

    def test_read_keeps_the_default_policy(self) -> None:
        options = runner_options('read')

        problem = ReadOnlyCommandPolicy(
            command=Command(argv=('terraform', 'validate')), options=options
        ).get_command_problem()
        assert problem is None
