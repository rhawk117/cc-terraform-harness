from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.tools.diagnostics.tests.scripting import (
    FMT_ARGV,
    TFLINT_ARGV,
    VALIDATE_ARGV,
    Scripted,
    call_diagnostics,
    create_validate_json,
    fail,
    read_report,
    succeed,
)

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet
    from mcp import Client
    from tf_harness_mcp.runner.domain import CommandResult
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner
    from tf_harness_mcp.tools.diagnostics.tests.scripting import Report


@dataclass(slots=True, kw_only=True, frozen=True)
class FailureBranch:
    name: str
    check: str
    argv: tuple[str, ...]
    result: CommandResult
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)

    @property
    def summary(self) -> str:
        return f'{self.check} exited with {self.result.returncode} and printed no usable output'

    @property
    def detail(self) -> str:
        return self.result.stderr.strip()


def check_failure_branch_cases() -> pytest.MarkDecorator:
    fmt_unexpected_exit = FailureBranch(
        name='fmt-unexpected-exit',
        check='fmt',
        argv=FMT_ARGV,
        result=fail(2, stderr='Error: unsupported argument\n'),
    )
    validate_not_json = FailureBranch(
        name='validate-not-json',
        check='validate',
        argv=VALIDATE_ARGV,
        result=fail(1, stdout='not json', stderr='terraform crashed\n'),
    )
    tflint_not_json = FailureBranch(
        name='tflint-not-json',
        check='tflint',
        argv=TFLINT_ARGV,
        result=fail(1, stdout='not json', stderr='tflint crashed\n'),
    )
    tflint_exit_without_issues = FailureBranch(
        name='tflint-exit-without-issues',
        check='tflint',
        argv=TFLINT_ARGV,
        result=fail(2, stdout='{"issues": [], "errors": []}', stderr='plugin failed to start\n'),
    )
    return pytest.mark.parametrize(
        'branch',
        [
            fmt_unexpected_exit.param,
            validate_not_json.param,
            tflint_not_json.param,
            tflint_exit_without_issues.param,
        ],
    )


@pytest.mark.unit
class TestDiagnosticsOnUnusableCheckOutput:
    passing_stdout = (
        ('fmt', FMT_ARGV, ''),
        ('validate', VALIDATE_ARGV, create_validate_json()),
        ('tflint', TFLINT_ARGV, '{"issues": [], "errors": []}'),
    )

    @pytest.fixture
    def scripted(
        self, recording_runner: RecordingCommandRunner, module: Path, branch: FailureBranch
    ) -> Scripted:
        for check, argv, stdout in self.passing_stdout:
            result = branch.result if check == branch.check else succeed(stdout)
            recording_runner.script(argv, result)
        return Scripted(runner=recording_runner, module=module)

    @pytest.fixture
    async def report(self, client: Client, scripted: Scripted) -> Report:
        return read_report(await call_diagnostics(client, scripted.module))

    @check_failure_branch_cases()
    async def test_check_fails_with_its_exit_code_and_stderr(
        self, report: Report, branch: FailureBranch
    ) -> None:
        check = report['checks'][branch.check]

        assert check['status'] == 'failed'
        assert [
            (item['severity'], item['summary'], item['detail']) for item in check['findings']
        ] == [('error', branch.summary, branch.detail)]
