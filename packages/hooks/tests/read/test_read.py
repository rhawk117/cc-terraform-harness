import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from tf_harness_hooks.domain import HookRequest
from tf_harness_hooks.read import CHECK_TIMEOUT_SECONDS, CONTEXT_LIMIT, report_file_findings
from tf_harness_mcp.runner.domain import CommandResult
from tf_harness_mcp.runner.errors import CommandTimeoutError
from tf_harness_mcp.tools.diagnostics.tests.scripting import (
    TFLINT_ARGV,
    VALIDATE_ARGV,
    create_range,
    create_validate_json,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.runner.domain import Command
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

pytestmark = pytest.mark.unit

MISSING_PLUGIN = (
    'Failed to initialize plugins; Plugin "aws" not found. Did you run "tflint --init"?'
)


def create_validate_diagnostic(summary: str, filename: str | None, line: int = 1) -> dict[str, Any]:
    diagnostic: dict[str, Any] = {'severity': 'error', 'summary': summary, 'detail': ''}
    if filename is not None:
        diagnostic['range'] = create_range(filename, line)
    return diagnostic


def create_tflint_issue(message: str, filename: str, line: int) -> dict[str, Any]:
    return {
        'rule': {'name': 'terraform_unused_declarations', 'severity': 'warning'},
        'message': message,
        'range': create_range(filename, line),
    }


def create_tflint_json(*issues: dict[str, Any], errors: tuple[str, ...] = ()) -> str:
    return json.dumps({
        'issues': list(issues),
        'errors': [{'message': message, 'severity': 'error'} for message in errors],
    })


def succeed(stdout: str) -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr='')


@dataclass(slots=True, kw_only=True, frozen=True)
class ReadScenario:
    project_root: Path
    runner: RecordingCommandRunner

    def script(self, validate: str, tflint: str) -> None:
        self.runner.script(VALIDATE_ARGV, succeed(validate))
        self.runner.script(TFLINT_ARGV, succeed(tflint))

    async def read(self, name: str) -> str | None:
        request = HookRequest(
            event_name='PostToolUse',
            project_root=self.project_root,
            runner=self.runner,
            file_path=self.project_root / name,
        )
        output = await report_file_findings(request)
        return None if output is None else output.additional_context


@pytest.fixture
def scenario(project_root: Path, recording_runner: RecordingCommandRunner) -> ReadScenario:
    (project_root / '.terraform').mkdir()
    return ReadScenario(project_root=project_root, runner=recording_runner)


@pytest.fixture
def uninitialized(project_root: Path, recording_runner: RecordingCommandRunner) -> ReadScenario:
    return ReadScenario(project_root=project_root, runner=recording_runner)


class TestFindingSelection:
    validate = create_validate_json(
        create_validate_diagnostic('Unsupported argument', 'main.tf', 4),
        create_validate_diagnostic('Duplicate variable', 'other.tf', 9),
        create_validate_diagnostic('Missing required provider', None),
    )
    tflint = create_tflint_json(
        create_tflint_issue('"unused" is declared but not used', 'main.tf', 7),
        create_tflint_issue('"other" is declared but not used', 'other.tf', 2),
        create_tflint_issue('"extra" is not set', 'prod.tfvars', 3),
        errors=('Failed to check ruleset',),
    )

    async def test_tf_read_keeps_its_file_and_file_less_validate_errors(
        self, scenario: ReadScenario
    ) -> None:
        scenario.script(self.validate, self.tflint)

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
        self, scenario: ReadScenario
    ) -> None:
        scenario.script(self.validate, self.tflint)

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
            create_validate_json(create_validate_diagnostic('Duplicate', 'other.tf')),
            create_tflint_json(create_tflint_issue('unused', 'other.tf', 2)),
        )

        assert await scenario.read('main.tf') is None

    async def test_skipped_checks_add_nothing(self, scenario: ReadScenario) -> None:
        scenario.runner.script_missing_binary(VALIDATE_ARGV)
        scenario.runner.script_missing_binary(TFLINT_ARGV)

        assert await scenario.read('main.tf') is None

    async def test_both_checks_run_in_the_module_with_30_second_timeouts(
        self, scenario: ReadScenario
    ) -> None:
        scenario.script(create_validate_json(), create_tflint_json())

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
        scenario.runner.script(VALIDATE_ARGV, succeed(create_validate_json()))
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
            create_validate_json(), create_tflint_json(errors=('Failed to check ruleset',))
        )

        context = await scenario.read('main.tf')

        assert context == 'tflint failed: Failed to check ruleset'

    async def test_failed_line_precedes_the_read_files_own_findings(
        self, scenario: ReadScenario
    ) -> None:
        scenario.script(
            create_validate_json(),
            create_tflint_json(
                create_tflint_issue('unused', 'main.tf', 7), errors=('Failed to check ruleset',)
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
            succeed(create_tflint_json(create_tflint_issue('unused', 'main.tf', 7))),
        )

        context = await uninitialized.read('main.tf')

        assert context is not None
        init_line, *tflint_lines = context.splitlines()
        assert init_line.startswith('terraform validate did not run: run terraform init in ')
        assert tflint_lines[0] == 'tflint:'
        assert [call.command.argv for call in uninitialized.runner.calls] == [TFLINT_ARGV]

    async def test_missing_tflint_plugins_become_one_init_line(
        self, scenario: ReadScenario
    ) -> None:
        scenario.script(
            create_validate_json(),
            create_tflint_json(errors=(MISSING_PLUGIN, MISSING_PLUGIN.replace('"aws"', '"gcp"'))),
        )

        context = await scenario.read('main.tf')

        assert (
            context == f'tflint plugins are missing: run tflint --init in {scenario.project_root}'
        )

    async def test_no_recorded_argv_runs_an_init(self, uninitialized: ReadScenario) -> None:
        uninitialized.runner.script(
            TFLINT_ARGV, succeed(create_tflint_json(errors=(MISSING_PLUGIN,)))
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


class TestOutputBudget:
    finding_count = 5_000

    async def test_thousands_of_findings_fit_the_context_limit_with_an_omitted_count(
        self, scenario: ReadScenario
    ) -> None:
        validate = create_validate_json(
            *(
                create_validate_diagnostic(f'Unsupported argument {number}', 'main.tf', number)
                for number in range(self.finding_count)
            )
        )
        tflint = create_tflint_json(
            *(
                create_tflint_issue(f'"v{number}" is unused', 'main.tf', number)
                for number in range(self.finding_count)
            )
        )
        scenario.script(validate, tflint)

        context = await scenario.read('main.tf')

        assert context is not None
        lines = context.splitlines()
        assert len(context) < CONTEXT_LIMIT
        assert lines[0] == 'terraform validate:'
        assert lines[1] == '0: error Unsupported argument 0'
        shown = sum(1 for line in lines[:-1] if line[:1].isdigit())
        assert lines[-1] == f'{2 * self.finding_count - shown} more findings omitted'

    async def test_header_only_section_dropped_by_a_spent_budget_is_counted(
        self, scenario: ReadScenario
    ) -> None:
        validate = create_validate_json(
            *(
                create_validate_diagnostic(f'Unsupported argument {number}', 'main.tf', number)
                for number in range(self.finding_count)
            )
        )
        scenario.script(validate, create_tflint_json(errors=(MISSING_PLUGIN,)))

        context = await scenario.read('main.tf')

        assert context is not None
        lines = context.splitlines()
        assert 'tflint --init' not in context
        shown = sum(1 for line in lines[:-1] if line[:1].isdigit())
        assert lines[-1] == f'{self.finding_count - shown + 1} more findings omitted'

    async def test_wire_envelope_carries_the_text(self, scenario: ReadScenario) -> None:
        scenario.script(
            create_validate_json(create_validate_diagnostic('Bad', 'main.tf', 2)),
            create_tflint_json(),
        )
        request = HookRequest(
            event_name='PostToolUse',
            project_root=scenario.project_root,
            runner=scenario.runner,
            file_path=scenario.project_root / 'main.tf',
        )

        output = await report_file_findings(request)

        assert output is not None
        assert output.to_wire() == {
            'hookSpecificOutput': {
                'hookEventName': 'PostToolUse',
                'additionalContext': 'terraform validate:\n2: error Bad',
            }
        }
