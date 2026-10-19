"""The read subcommand: validate and lint the read file's module and report that file's findings."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from tf_harness_mcp.runner.errors import CommandTimeoutError
from tf_harness_mcp.tools.diagnostics.services import (
    DiagnosticsService,
    TflintCheck,
    ValidateCheck,
)

from tf_harness_hooks.domain import HookOutput

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.tools.diagnostics.domain import Check, CheckReport, Finding

    from tf_harness_hooks.domain import HookRequest

CHECK_TIMEOUT_SECONDS: Final = 30.0
CONTEXT_LIMIT: Final = 10_000
OMITTED_RESERVE: Final = 80
LINE_LIMIT: Final = 300
TFLINT_INIT_HINT: Final = 'tflint --init'
TERRAFORM_DIRECTORY: Final = '.terraform'


@dataclass(slots=True, kw_only=True, frozen=True)
class Section:
    header: str
    lines: list[str] = field(default_factory=list)


def clip(text: str) -> str:
    return text if len(text) <= LINE_LIMIT else f'{text[: LINE_LIMIT - 3]}...'


def format_finding(finding: Finding) -> str:
    line = '-' if finding.line is None else str(finding.line)
    return clip(f'{line}: {finding.severity} {finding.summary}')


def targets_file(finding: Finding, module: Path, file_path: Path) -> bool:
    return finding.file is not None and module.joinpath(finding.file) == file_path


def lacks_plugins(report: CheckReport) -> bool:
    return any(
        finding.scope == 'tool' and TFLINT_INIT_HINT in finding.summary
        for finding in report.findings
    )


async def run_check(request: HookRequest, check: Check, module: Path) -> CheckReport | None:
    service = DiagnosticsService(runner=request.runner, checks=(check,))
    try:
        return (await service.run(module))[check.name]
    except CommandTimeoutError:
        return None


def timeout_section(name: str) -> Section:
    return Section(header=f'{name} timed out after {CHECK_TIMEOUT_SECONDS:g}s')


async def check_validate(request: HookRequest, module: Path, file_path: Path) -> Section | None:
    if not (module.joinpath(TERRAFORM_DIRECTORY)).is_dir():
        return Section(
            header=clip(
                f'terraform validate skipped: {module} has no {TERRAFORM_DIRECTORY} directory'
            )
        )

    report = await run_check(request, ValidateCheck(timeout_seconds=CHECK_TIMEOUT_SECONDS), module)
    if report is None:
        return timeout_section('terraform validate')

    findings = [
        finding
        for finding in report.findings
        if finding.scope != 'file' or targets_file(finding, module, file_path)
    ]
    if not findings:
        return None

    return Section(header='terraform validate:', lines=list(map(format_finding, findings)))


def failure_section(finding: Finding) -> Section:
    detail_lines = finding.detail.splitlines()
    detail = f': {detail_lines[0]}' if detail_lines else ''
    return Section(header=clip(f'tflint failed: {finding.summary}{detail}'))


async def check_tflint(request: HookRequest, module: Path, file_path: Path) -> list[Section]:
    report = await run_check(request, TflintCheck(timeout_seconds=CHECK_TIMEOUT_SECONDS), module)
    if report is None:
        return [timeout_section('tflint')]

    if report.status == 'skipped':
        return []

    if lacks_plugins(report):
        return [
            Section(header=clip(f'tflint plugins are missing: run {TFLINT_INIT_HINT} in {module}'))
        ]

    sections: list[Section] = []
    if failure := next((finding for finding in report.findings if finding.scope == 'tool'), None):
        sections.append(failure_section(failure))

    findings = [finding for finding in report.findings if targets_file(finding, module, file_path)]
    if findings:
        sections.append(Section(header='tflint:', lines=list(map(format_finding, findings))))

    return sections


@dataclass(slots=True, kw_only=True, frozen=True)
class ContextBudget:
    limit: int

    def fit(self, lines: list[str]) -> tuple[list[str], int]:
        kept: list[str] = []
        used = 0
        for line in lines:
            cost = len(line) + 1
            if not kept and used + cost > self.limit:
                return [], len(lines)

            if used + cost <= self.limit:
                kept.append(line)
                used += cost

        return kept, len(lines) - len(kept)


def render(sections: list[Section]) -> str:
    kept: list[str] = []
    omitted = 0
    for section in sections:
        spent = sum(len(line) + 1 for line in kept)
        budget = ContextBudget(limit=CONTEXT_LIMIT - OMITTED_RESERVE - spent)
        fitted, dropped = budget.fit([section.header, *section.lines])
        kept.extend(fitted)
        omitted += dropped

    if omitted:
        kept.append(f'{omitted} lines omitted')

    return '\n'.join(kept)


async def report_file_findings(request: HookRequest) -> HookOutput | None:
    if request.file_path is None:
        return None

    module = request.file_path.parent
    validate_section = await check_validate(request, module, request.file_path)
    tflint_sections = await check_tflint(request, module, request.file_path)
    sections = [*filter(None, [validate_section]), *tflint_sections]
    if not sections:
        return None

    return HookOutput(event_name=request.event_name, additional_context=render(sections))
