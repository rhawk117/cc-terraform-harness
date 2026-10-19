from typing import TYPE_CHECKING

import pytest
from tf_harness_hooks.domain import HookRequest
from tf_harness_hooks.read import (
    CHECK_TIMEOUT_SECONDS,
    report_file_findings,
)
from tf_harness_mcp.runner.domain import CommandResult
from tf_harness_mcp.runner.errors import CommandTimeoutError
from tf_harness_mcp.tools.diagnostics.tests.scripting import (
    TFLINT_ARGV,
    VALIDATE_ARGV,
    create_validate_json,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.runner.domain import Command
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

    from conftest import ReadScenario

pytestmark = pytest.mark.unit


class TestFindingSelection:
    @pytest.fixture
    def validate(self, scenario: ReadScenario) -> str:
        findings = scenario.findings
        return create_validate_json(
            findings.validate_diagnostic('Unsupported argument', 'main.tf', 4),
            findings.validate_diagnostic('Duplicate variable', 'other.tf', 9),
            findings.validate_diagnostic('Missing required provider', None),
        )

    @pytest.fixture
    def tflint(self, scenario: ReadScenario) -> str:
        findings = scenario.findings
        return findings.tflint_json(
            findings.tflint_issue('"unused" is declared but not used', 'main.tf', 7),
            findings.tflint_issue('"other" is declared but not used', 'other.tf', 2),
            findings.tflint_issue('"extra" is not set', 'prod.tfvars', 3),
            errors=('Failed to check ruleset',),
        )

    async def test_tf_read_keeps_its_file_and_file_less_validate_errors(
        self, scenario: ReadScenario, validate: str, tflint: str
    ) -> None:
        scenario.script(validate, tflint)

        context = await scenario.read('main.tf')

        assert context == (
            'terraform validate:\n'
            '4: error Unsupported argument\n'
            '-: error Missing required provider\n'
            'tflint failed: Failed to check ruleset\n'
            'tflint:\n'
            '7: warning terraform_unused_declarations: "unused" is declared but not used'
        )

    async def test_tfvars_read_keeps_its_file_and_file_less_validate_errors(
        self, scenario: ReadScenario, validate: str, tflint: str
    ) -> None:
        scenario.script(validate, tflint)

        context = await scenario.read('prod.tfvars')

        assert context == (
            'terraform validate:\n'
            '-: error Missing required provider\n'
            'tflint failed: Failed to check ruleset\n'
            'tflint:\n'
            '3: warning terraform_unused_declarations: "extra" is not set'
        )

    async def test_nothing_kept_gives_no_output(self, scenario: ReadScenario) -> None:
        scenario.script(
            create_validate_json(scenario.findings.validate_diagnostic('Duplicate', 'other.tf')),
            scenario.findings.tflint_json(scenario.findings.tflint_issue('unused', 'other.tf', 2)),
        )

        assert await scenario.read('main.tf') is None

    async def test_skipped_checks_add_nothing(self, scenario: ReadScenario) -> None:
        scenario.runner.script_missing_binary(VALIDATE_ARGV)
        scenario.runner.script_missing_binary(TFLINT_ARGV)

        assert await scenario.read('main.tf') is None

    async def test_both_checks_run_in_the_module_with_30_second_timeouts(
        self, scenario: ReadScenario
    ) -> None:
        scenario.script(create_validate_json(), scenario.findings.tflint_json())

        await scenario.read('main.tf')

        calls = scenario.runner.calls
        assert [call.command.argv for call in calls] == [VALIDATE_ARGV, TFLINT_ARGV]
        assert {call.command.cwd for call in calls} == {scenario.project_root}
        assert [call.timeout_seconds for call in calls] == [30.0, 30.0]
        assert CHECK_TIMEOUT_SECONDS == 30


class TestTflintFailures:
    async def test_unparseable_output_gives_one_failed_line_with_the_first_stderr_line(
        self, scenario: ReadScenario
    ) -> None:
        scenario.runner.script(VALIDATE_ARGV, scenario.findings.succeed(create_validate_json()))
        scenario.runner.script(
            TFLINT_ARGV,
            CommandResult(returncode=2, stdout='not json', stderr='config broken\nsecond line\n'),
        )

        context = await scenario.read('main.tf')

        assert context == (
            'tflint failed: tflint exited with 2 and printed no usable output: config broken'
        )

    async def test_non_plugin_error_gives_one_failed_line(self, scenario: ReadScenario) -> None:
        scenario.script(
            create_validate_json(),
            scenario.findings.tflint_json(errors=('Failed to check ruleset',)),
        )

        context = await scenario.read('main.tf')

        assert context == 'tflint failed: Failed to check ruleset'

    async def test_failed_line_precedes_the_read_files_own_findings(
        self, scenario: ReadScenario
    ) -> None:
        scenario.script(
            create_validate_json(),
            scenario.findings.tflint_json(
                scenario.findings.tflint_issue('unused', 'main.tf', 7),
                errors=('Failed to check ruleset',),
            ),
        )

        context = await scenario.read('main.tf')

        assert context == (
            'tflint failed: Failed to check ruleset\n'
            'tflint:\n'
            '7: warning terraform_unused_declarations: unused'
        )


class TestInitHints:
    async def test_module_without_terraform_directory_swaps_validate_for_an_init_line(
        self, uninitialized: ReadScenario
    ) -> None:
        uninitialized.runner.script(
            TFLINT_ARGV,
            uninitialized.findings.succeed(
                uninitialized.findings.tflint_json(
                    uninitialized.findings.tflint_issue('unused', 'main.tf', 7)
                )
            ),
        )

        context = await uninitialized.read('main.tf')

        assert context is not None
        init_line, *tflint_lines = context.splitlines()
        assert init_line.startswith('terraform validate skipped: ')
        assert tflint_lines[0] == 'tflint:'
        assert [call.command.argv for call in uninitialized.runner.calls] == [TFLINT_ARGV]

    async def test_missing_tflint_plugins_become_one_init_line(
        self, scenario: ReadScenario, missing_plugin: str
    ) -> None:
        scenario.script(
            create_validate_json(),
            scenario.findings.tflint_json(
                errors=(missing_plugin, missing_plugin.replace('"aws"', '"gcp"'))
            ),
        )

        context = await scenario.read('main.tf')

        assert (
            context == f'tflint plugins are missing: run tflint --init in {scenario.project_root}'
        )

    async def test_no_recorded_argv_runs_an_init(
        self, uninitialized: ReadScenario, missing_plugin: str
    ) -> None:
        uninitialized.runner.script(
            TFLINT_ARGV,
            uninitialized.findings.succeed(
                uninitialized.findings.tflint_json(errors=(missing_plugin,))
            ),
        )

        await uninitialized.read('main.tf')

        for call in uninitialized.runner.calls:
            assert 'init' not in call.command.argv
            assert '--init' not in call.command.argv


class TestFailures:
    async def test_timeout_gives_a_line_naming_the_limit(self, project_root: Path) -> None:
        (project_root / '.terraform').mkdir()

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

        output = await report_file_findings(request)

        assert output is not None
        assert output.additional_context == (
            'terraform validate timed out after 30s\ntflint timed out after 30s'
        )

    async def test_request_without_a_file_gives_no_output(
        self, project_root: Path, recording_runner: RecordingCommandRunner
    ) -> None:
        request = HookRequest(
            event_name='PostToolUse', project_root=project_root, runner=recording_runner
        )

        assert await report_file_findings(request) is None
        assert recording_runner.calls == []
