from typing import TYPE_CHECKING

import pytest
from tf_harness_hooks.domain import HookRequest
from tf_harness_hooks.read import CONTEXT_LIMIT, Section, render, report_file_findings
from tf_harness_mcp.tools.diagnostics.tests.scripting import create_validate_json

if TYPE_CHECKING:
    from conftest import FindingFactory, ReadScenario

pytestmark = pytest.mark.unit


class TestOutputBudget:
    finding_count = 5_000

    @pytest.fixture(scope='class')
    @classmethod
    def validate(cls, findings: FindingFactory) -> str:
        return create_validate_json(
            *(
                findings.validate_diagnostic(f'Unsupported argument {number}', 'main.tf', number)
                for number in range(cls.finding_count)
            )
        )

    def shown_count(self, lines: list[str]) -> int:
        return sum(1 for line in lines[:-1] if line[:1].isdigit())

    async def test_thousands_of_findings_fit_the_context_limit_with_an_omitted_count(
        self, scenario: ReadScenario, validate: str
    ) -> None:
        tflint = scenario.findings.tflint_json(
            *(
                scenario.findings.tflint_issue(f'"v{number}" is unused', 'main.tf', number)
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
        assert lines[-1] == f'{2 * self.finding_count - self.shown_count(lines) + 1} lines omitted'

    async def test_header_only_section_dropped_by_a_spent_budget_is_counted(
        self, scenario: ReadScenario, validate: str, missing_plugin: str
    ) -> None:
        scenario.script(validate, scenario.findings.tflint_json(errors=(missing_plugin,)))

        context = await scenario.read('main.tf')

        assert context is not None
        lines = context.splitlines()
        assert 'tflint --init' not in context
        assert lines[-1] == f'{self.finding_count - self.shown_count(lines) + 1} lines omitted'

    def test_header_alone_overflowing_the_budget_is_counted_as_one_omitted_line(self) -> None:
        header = 'h' * 300
        section_count = CONTEXT_LIMIT // len(header) + 5
        sections = [Section(header=header, lines=['1: error x']) for _ in range(section_count)]

        lines = render(sections).splitlines()

        kept_count = len(lines) - 1
        assert 0 < kept_count < 2 * section_count
        assert lines[-1] == f'{2 * section_count - kept_count} lines omitted'
        assert len('\n'.join(lines)) <= CONTEXT_LIMIT

    async def test_wire_envelope_carries_the_text(self, scenario: ReadScenario) -> None:
        scenario.script(
            create_validate_json(scenario.findings.validate_diagnostic('Bad', 'main.tf', 2)),
            scenario.findings.tflint_json(),
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
