"""Resolves pytest arguments for the pytest action, then summarizes its run."""

import argparse
import html
import os
import platform
import secrets
import sys
from dataclasses import dataclass, field
from importlib.metadata import version
from io import StringIO
from itertools import chain, groupby
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from xml.etree import ElementTree as ET

from coverage import Coverage
from coverage.exceptions import NoDataError

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from xml.etree.ElementTree import Element

type ProblemKind = Literal['failure', 'error']


@dataclass(slots=True, kw_only=True, frozen=True)
class PytestRun:
    results_dir: Path
    workers: str
    random_seed: int
    markers: str
    extra_arguments: Sequence[str]

    @property
    def junit_report(self) -> Path:
        return self.results_dir.joinpath('junit.xml')

    @property
    def coverage_html(self) -> Path:
        return self.results_dir.joinpath('htmlcov')

    @property
    def marker_arguments(self) -> Sequence[str]:
        if not self.markers:
            return ()
        return ('-m', self.markers)

    @property
    def arguments(self) -> Sequence[str]:
        return (
            '--numprocesses',
            self.workers,
            '--dist',
            'worksteal',
            '--randomly-seed',
            str(self.random_seed),
            '--junitxml',
            str(self.junit_report),
            '--cov-report',
            f'html:{self.coverage_html}',
            *self.marker_arguments,
            *self.extra_arguments,
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class Problem:
    kind: ProblemKind
    test_id: str
    message: str
    details: str

    @property
    def headline(self) -> str:
        return self.message.partition('\n')[0]


@dataclass(slots=True, kw_only=True, frozen=True)
class SuiteTotals:
    tests: int
    failures: int
    errors: int
    skipped: int
    expected_failures: int
    seconds: float

    @property
    def passed(self) -> int:
        return self.tests - self.failures - self.errors - self.skipped

    @property
    def plain_skips(self) -> int:
        return self.skipped - self.expected_failures

    @property
    def succeeded(self) -> bool:
        return self.failures + self.errors == 0


@dataclass(slots=True, kw_only=True, frozen=True)
class JunitReport:
    totals: SuiteTotals
    problems: Sequence[Problem]


@dataclass(slots=True, kw_only=True, frozen=True)
class CoverageSummary:
    total: float
    table: str


@dataclass(slots=True, kw_only=True, frozen=True)
class SummaryContext:
    random_seed: str
    workers: str


@dataclass(slots=True, kw_only=True, frozen=True)
class SummaryLimits:
    detailed_problems: int = 20
    listed_problems: int = 100
    traceback_characters: int = 4_000
    minimum_fence_length: int = 3


def sum_suite_attribute(suites: Sequence[Element], name: str) -> float:
    return sum(float(suite.get(name, '0')) for suite in suites)


def read_case_problems(case: Element) -> Iterator[Problem]:
    test_id = '::'.join((case.get('classname', ''), case.get('name', '')))
    for kind in ('failure', 'error'):
        for outcome in case.findall(kind):
            yield Problem(
                kind=kind,
                test_id=test_id,
                message=outcome.get('message', ''),
                details=outcome.text or '',
            )


def read_junit_report(path: Path) -> JunitReport:
    root = ET.parse(path).getroot()  # noqa: S314 - pytest wrote this file in this job, and stdlib expat refuses entity expansion attacks
    suites = list(root.iter('testsuite'))
    xfails = [skip for skip in root.iter('skipped') if skip.get('type') == 'pytest.xfail']
    totals = SuiteTotals(
        tests=int(sum_suite_attribute(suites, 'tests')),
        failures=int(sum_suite_attribute(suites, 'failures')),
        errors=int(sum_suite_attribute(suites, 'errors')),
        skipped=int(sum_suite_attribute(suites, 'skipped')),
        expected_failures=len(xfails),
        seconds=sum_suite_attribute(suites, 'time'),
    )
    problems = chain.from_iterable(map(read_case_problems, root.iter('testcase')))
    return JunitReport(totals=totals, problems=tuple(problems))


def read_coverage_summary() -> CoverageSummary | None:
    coverage = Coverage()
    coverage.load()
    table = StringIO()
    try:
        total = coverage.report(file=table, output_format='markdown')
    except NoDataError:
        return None
    return CoverageSummary(total=total, table=table.getvalue())


def code_fence_for(text: str, minimum_length: int) -> str:
    runs = (len(list(group)) for character, group in groupby(text) if character == '`')
    longest = max(runs, default=0)
    return '`' * max(minimum_length, longest + 1)


@dataclass(slots=True, kw_only=True, frozen=True)
class OverviewSection:
    totals: SuiteTotals
    context: SummaryContext
    coverage: CoverageSummary | None

    @property
    def headline(self) -> str:
        totals = self.totals
        if totals.succeeded:
            return f'## :white_check_mark: pytest passed {totals.passed} tests'
        return f'## :x: pytest: {totals.failures} failed, {totals.errors} errored'

    @property
    def results_row(self) -> str:
        totals = self.totals
        duration = f'{totals.seconds:.2f}s'
        cells = (
            totals.passed,
            totals.failures,
            totals.errors,
            totals.plain_skips,
            totals.expected_failures,
            duration,
        )
        joined = ' | '.join(map(str, cells))
        return f'| {joined} |'

    @property
    def coverage_line(self) -> str:
        if self.coverage is None:
            return '- **Coverage** no data recorded'
        return f'- **Coverage** {self.coverage.total:.1f}% total'

    def render(self) -> str:
        seed = self.context.random_seed
        pytest_version = version('pytest')
        return '\n'.join((
            self.headline,
            '',
            '| Passed | Failed | Errors | Skipped | Xfailed | Duration |',
            '| -----: | -----: | -----: | ------: | ------: | -------: |',
            self.results_row,
            '',
            f'- **Python** {platform.python_version()}, **pytest** {pytest_version}',
            f'- **Workers** {self.context.workers}',
            f'- **Random seed** {seed}, reproduce with `pytest --randomly-seed={seed}`',
            self.coverage_line,
        ))


@dataclass(slots=True, kw_only=True, frozen=True)
class ProblemsSection:
    problems: Sequence[Problem]
    limits: SummaryLimits = field(default_factory=SummaryLimits)

    def render(self) -> str:
        if not self.problems:
            return ''
        detailed = self.problems[: self.limits.detailed_problems]
        unlisted = self.problems[self.limits.detailed_problems :]
        sections = ['### Failures and errors', *map(self.render_problem, detailed)]
        if unlisted:
            sections.append(self.render_unlisted(unlisted))
        return '\n\n'.join(sections)

    def render_problem(self, problem: Problem) -> str:
        details = self.truncate_traceback(problem.details)
        fence = code_fence_for(details, self.limits.minimum_fence_length)
        test_id = html.escape(problem.test_id)
        headline = html.escape(problem.headline)
        summary = f'<code>{test_id}</code> {problem.kind}: {headline}'
        return '\n'.join((
            f'<details><summary>{summary}</summary>',
            '',
            f'{fence}text',
            details,
            fence,
            '',
            '</details>',
        ))

    def render_unlisted(self, problems: Sequence[Problem]) -> str:
        shown = problems[: self.limits.listed_problems]
        hidden = len(problems) - len(shown)
        lines = [f'{len(problems)} more without tracebacks:', '']
        lines.extend(f'- `{problem.test_id}` {problem.kind}' for problem in shown)
        if hidden:
            lines.append(f'- and {hidden} more, see the job log')
        return '\n'.join(lines)

    def truncate_traceback(self, details: str) -> str:
        limit = self.limits.traceback_characters
        if len(details) <= limit:
            return details
        return f'(last {limit} of {len(details)} characters)\n{details[-limit:]}'


@dataclass(slots=True, kw_only=True, frozen=True)
class CoverageSection:
    coverage: CoverageSummary | None

    def render(self) -> str:
        if self.coverage is None:
            return ''
        heading = '### Coverage\n\n<details><summary>Coverage by file</summary>'
        return f'{heading}\n\n{self.coverage.table}\n</details>'


def render_step_summary(
    report: JunitReport,
    coverage: CoverageSummary | None,
    context: SummaryContext,
) -> str:
    sections = (
        OverviewSection(totals=report.totals, context=context, coverage=coverage),
        ProblemsSection(problems=report.problems),
        CoverageSection(coverage=coverage),
    )
    rendered = (section.render() for section in sections)
    return '\n\n'.join(filter(None, rendered)) + '\n'


def parse_random_seed(value: str) -> int | None:
    if not value:
        return None
    return int(value)


def split_pytest_arguments(value: str) -> Sequence[str]:
    return tuple(filter(None, map(str.strip, value.splitlines())))


def choose_random_seed(requested: int | None) -> int:
    if requested is None:
        return secrets.randbits(32)
    return requested


def write_step_outputs(outputs: Mapping[str, str]) -> None:
    output_file = os.getenv('GITHUB_OUTPUT')
    if not output_file:
        return
    with Path(output_file).open('a', encoding='utf-8') as step_outputs:
        step_outputs.writelines(f'{name}={value}\n' for name, value in outputs.items())


def resolve_pytest_run(arguments: argparse.Namespace) -> int:
    run = PytestRun(
        results_dir=arguments.results_dir,
        workers=arguments.workers,
        random_seed=choose_random_seed(arguments.random_seed),
        markers=arguments.markers,
        extra_arguments=arguments.pytest_args,
    )
    write_step_outputs({
        'random-seed': str(run.random_seed),
        'junit-report': str(run.junit_report),
        'coverage-html': str(run.coverage_html),
    })
    sys.stdout.write(''.join(f'{argument}\0' for argument in run.arguments))
    return 0


def summarize_pytest_run(arguments: argparse.Namespace) -> int:
    junit_report: Path = arguments.junit_report
    if not junit_report.is_file():
        sys.stdout.write('## :x: pytest wrote no JUnit report, see the job log\n')
        return 1

    context = SummaryContext(
        random_seed=arguments.random_seed,
        workers=arguments.workers,
    )
    summary = render_step_summary(
        read_junit_report(junit_report),
        read_coverage_summary(),
        context,
    )

    sys.stdout.write(summary)
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='pytest_ci',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    verbs = parser.add_subparsers(dest='verb', required=True)

    resolve_parser = verbs.add_parser('resolve', help='print pytest arguments, NUL ended')
    resolve_parser.add_argument('--results-dir', type=Path, required=True)
    resolve_parser.add_argument('--workers', required=True)
    resolve_parser.add_argument('--markers', default='')
    resolve_parser.add_argument('--random-seed', type=parse_random_seed, default=None)
    resolve_parser.add_argument('--pytest-args', type=split_pytest_arguments, default=())

    summarize_parser = verbs.add_parser('summarize', help='print step summary Markdown')
    summarize_parser.add_argument('--junit-report', type=Path, required=True)
    summarize_parser.add_argument('--random-seed', required=True)
    summarize_parser.add_argument('--workers', required=True)

    return parser


def main() -> int:
    arguments = create_parser().parse_args()
    if arguments.verb == 'resolve':
        return resolve_pytest_run(arguments)

    return summarize_pytest_run(arguments)


if __name__ == '__main__':
    raise SystemExit(main())
