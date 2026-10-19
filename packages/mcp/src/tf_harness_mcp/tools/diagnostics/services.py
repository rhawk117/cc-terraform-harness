"""Run the diagnostics checks through the injected command runner and build the tool."""

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from tf_harness_mcp.policies import containment
from tf_harness_mcp.policies.budget import create_output_budget
from tf_harness_mcp.runner.domain import Command
from tf_harness_mcp.runner.errors import CommandNotFoundError
from tf_harness_mcp.tools.diagnostics.domain import CheckReport, Finding
from tf_harness_mcp.tools.diagnostics.errors import DirectoryExpectedError
from tf_harness_mcp.tools.diagnostics.schemas import TflintOutput, ValidateOutput

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.policies.budget import OutputBudget
    from tf_harness_mcp.runner.domain import CommandResult, CommandRunner
    from tf_harness_mcp.settings import Settings
    from tf_harness_mcp.tools.diagnostics.domain import Check, CheckStatus

FMT_UNFORMATTED_EXIT = 3


def parse_output[Model: BaseModel](model: type[Model], result: CommandResult) -> Model | None:
    try:
        return model.model_validate_json(result.stdout)
    except ValidationError:
        return None


def get_directory_problem(directory: Path) -> DirectoryExpectedError | None:
    if directory.is_dir():
        return None

    return DirectoryExpectedError(path=directory)


def create_failure_report(name: str, result: CommandResult) -> CheckReport:
    finding = Finding(
        scope='tool',
        severity='error',
        summary=f'{name} exited with {result.returncode} and printed no usable output',
        detail=result.stderr.strip(),
    )
    return CheckReport(status='failed', findings=[finding])


@dataclass(slots=True, kw_only=True, frozen=True)
class FormatCheck:
    timeout_seconds: float
    name: str = 'fmt'
    argv: tuple[str, ...] = ('terraform', 'fmt', '-check', '-list=true', '-no-color')

    def interpret(self, result: CommandResult) -> CheckReport:
        if result.returncode == 0:
            return CheckReport(status='passed')

        if result.returncode != FMT_UNFORMATTED_EXIT:
            return create_failure_report(self.name, result)

        names = filter(None, map(str.strip, result.stdout.splitlines()))
        findings = [
            Finding(scope='file', severity='error', summary='file is not formatted', file=name)
            for name in names
        ]
        return CheckReport(status='failed', findings=findings)


@dataclass(slots=True, kw_only=True, frozen=True)
class ValidateCheck:
    timeout_seconds: float
    name: str = 'validate'
    argv: tuple[str, ...] = ('terraform', 'validate', '-json', '-no-color')

    def interpret(self, result: CommandResult) -> CheckReport:
        output = parse_output(ValidateOutput, result)
        if output is None:
            return create_failure_report(self.name, result)

        findings = [
            Finding(
                scope='module' if diagnostic.file is None else 'file',
                severity=diagnostic.severity,
                summary=diagnostic.summary,
                detail=diagnostic.detail,
                file=diagnostic.file,
                line=diagnostic.line,
            )
            for diagnostic in output.diagnostics
        ]
        status: CheckStatus = 'passed' if output.valid else 'failed'
        return CheckReport(status=status, findings=findings)


def read_tflint_findings(output: TflintOutput) -> list[Finding]:
    issues = [
        Finding(
            scope='file',
            severity=issue.rule.severity,
            summary=f'{issue.rule.name}: {issue.message}',
            file=issue.file,
            line=issue.line,
        )
        for issue in output.issues
    ]
    errors = [
        Finding(scope='tool', severity=error.severity, summary=error.message)
        for error in output.errors
    ]
    return [*issues, *errors]


@dataclass(slots=True, kw_only=True, frozen=True)
class TflintCheck:
    timeout_seconds: float
    name: str = 'tflint'
    argv: tuple[str, ...] = ('tflint', '--format=json', '--no-color')

    def interpret(self, result: CommandResult) -> CheckReport:
        output = parse_output(TflintOutput, result)
        if output is None:
            return create_failure_report(self.name, result)

        findings = read_tflint_findings(output)
        if findings:
            return CheckReport(status='failed', findings=findings)

        if result.returncode:
            return create_failure_report(self.name, result)

        return CheckReport(status='passed')


@dataclass(slots=True, kw_only=True, frozen=True)
class DiagnosticsService:
    runner: CommandRunner
    checks: tuple[Check, ...]

    async def run_check(self, check: Check, directory: Path) -> CheckReport:
        command = Command(argv=check.argv, cwd=directory)
        try:
            result = await self.runner.run(command, check.timeout_seconds)
        except CommandNotFoundError as err:
            return CheckReport(status='skipped', reason=str(err))

        return check.interpret(result)

    async def run(self, directory: Path) -> dict[str, CheckReport]:
        return {check.name: await self.run_check(check, directory) for check in self.checks}


@dataclass(slots=True, kw_only=True, frozen=True)
class DiagnosticsTool:
    root: Path
    budget: OutputBudget
    service: DiagnosticsService

    def resolve_directory(self, directory: containment.ProjectPath) -> Path:
        resolved = containment.resolve_project_path(self.root, directory)
        if problem := get_directory_problem(resolved):
            raise problem

        return resolved

    async def diagnostics(self, directory: containment.ProjectPath) -> dict[str, Any]:
        """Check one Terraform module directory without changing it.

        Runs the terraform fmt check, terraform validate and tflint in the directory and returns
        each check's status (passed, failed or skipped) with its findings, each carrying the file
        and line when the tool reports one. A check whose binary is not on PATH is skipped with
        the reason. The directory is relative to the project root or absolute inside it.
        """
        resolved = self.resolve_directory(directory)
        reports = await self.service.run(resolved)
        checks = {name: asdict(report) for name, report in reports.items()}
        return self.budget.apply({'directory': str(resolved), 'checks': checks})


def create_diagnostics_tool(runner: CommandRunner, settings: Settings) -> DiagnosticsTool:
    checks = (
        FormatCheck(timeout_seconds=settings.validate_timeout_seconds),
        ValidateCheck(timeout_seconds=settings.validate_timeout_seconds),
        TflintCheck(timeout_seconds=settings.lint_timeout_seconds),
    )
    return DiagnosticsTool(
        root=settings.project_root,
        budget=create_output_budget(settings),
        service=DiagnosticsService(runner=runner, checks=checks),
    )
