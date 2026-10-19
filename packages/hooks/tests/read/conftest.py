import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from tf_harness_hooks.domain import HookRequest
from tf_harness_hooks.read import report_file_findings
from tf_harness_mcp.runner.domain import CommandResult
from tf_harness_mcp.tools.diagnostics.tests.scripting import (
    TFLINT_ARGV,
    VALIDATE_ARGV,
    create_range,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner


@dataclass(slots=True, kw_only=True, frozen=True)
class FindingFactory:
    def validate_diagnostic(
        self, summary: str, filename: str | None, line: int = 1
    ) -> dict[str, Any]:
        diagnostic: dict[str, Any] = {'severity': 'error', 'summary': summary, 'detail': ''}
        if filename is not None:
            diagnostic['range'] = create_range(filename, line)
        return diagnostic

    def tflint_issue(self, message: str, filename: str, line: int) -> dict[str, Any]:
        return {
            'rule': {'name': 'terraform_unused_declarations', 'severity': 'warning'},
            'message': message,
            'range': create_range(filename, line),
        }

    def tflint_json(self, *issues: dict[str, Any], errors: tuple[str, ...] = ()) -> str:
        return json.dumps({
            'issues': list(issues),
            'errors': [{'message': message, 'severity': 'error'} for message in errors],
        })

    def succeed(self, stdout: str) -> CommandResult:
        return CommandResult(returncode=0, stdout=stdout, stderr='')


@dataclass(slots=True, kw_only=True, frozen=True)
class ReadScenario:
    project_root: Path
    runner: RecordingCommandRunner
    findings: FindingFactory

    def script(self, validate: str, tflint: str) -> None:
        self.runner.script(VALIDATE_ARGV, self.findings.succeed(validate))
        self.runner.script(TFLINT_ARGV, self.findings.succeed(tflint))

    async def read(self, name: str) -> str | None:
        request = HookRequest(
            event_name='PostToolUse',
            project_root=self.project_root,
            runner=self.runner,
            file_path=self.project_root / name,
        )
        output = await report_file_findings(request)
        return None if output is None else output.additional_context


@pytest.fixture(scope='session')
def findings() -> FindingFactory:
    return FindingFactory()


@pytest.fixture
def scenario(
    project_root: Path, recording_runner: RecordingCommandRunner, findings: FindingFactory
) -> ReadScenario:
    (project_root / '.terraform').mkdir()
    return ReadScenario(project_root=project_root, runner=recording_runner, findings=findings)


@pytest.fixture
def uninitialized(
    project_root: Path, recording_runner: RecordingCommandRunner, findings: FindingFactory
) -> ReadScenario:
    return ReadScenario(project_root=project_root, runner=recording_runner, findings=findings)


@pytest.fixture
def missing_plugin() -> str:
    return 'Failed to initialize plugins; Plugin "aws" not found. Did you run "tflint --init"?'
