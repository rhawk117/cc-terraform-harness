import asyncio
import re
import sys
from dataclasses import dataclass
from functools import reduce
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet

HIT_LINE = re.compile(r'^(?P<path>.+):(?P<line>\d+): (?P<rule>[A-Z]+\d+) ')
PLAN = """---
mode: extract  # pulled out of prod
module: modules/network
sources: [envs/prod]
callers: [envs/prod, envs/dev]
terraform: ">= 1.9"
status: approved
approved_by: user
---

## Inventory

The VPC and its subnets in envs/prod.

## Interface

name, cidr_block in; vpc_id out.

## Moved map

| root | from | to |
| --- | --- | --- |
| envs/prod | `aws_vpc.main` | `module.network.aws_vpc.this` |
| envs/dev | aws_vpc.main | module.network.aws_vpc.this |

## Chunks

| id | title | owned | outcome | status |
| --- | --- | --- | --- | --- |
| C1 | write the module | modules/network/main.tf | create-only | done |
| C2 | wire prod | envs/prod/main.tf, envs/prod/moved.tf | moves-only | pending |

## Expected plan

- envs/prod: 0 to add, 0 to change, 0 to destroy
- `envs/dev`: 0 to add, 0 to change, 0 to destroy

## Open questions

None.
"""
SECOND_CHUNK = '| C2 | wire prod | envs/prod/main.tf, envs/prod/moved.tf | moves-only | pending |'
DEV_ROW = '| envs/dev | aws_vpc.main | module.network.aws_vpc.this |\n'


def apply_edit(text: str, edit: tuple[str, str]) -> str:
    return text.replace(*edit)


@dataclass(slots=True, kw_only=True, frozen=True)
class PlanScenario:
    name: str
    edits: tuple[tuple[str, str], ...] = ()
    require_approved: bool = False
    hits: tuple[tuple[int, str], ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)

    @property
    def text(self) -> str:
        return reduce(apply_edit, self.edits, PLAN)

    @property
    def arguments(self) -> tuple[str, ...]:
        return ('--require-approved',) if self.require_approved else ()


@dataclass(slots=True, kw_only=True, frozen=True)
class ValidatePlanRun:
    exit_code: int
    stdout: tuple[str, ...]
    stderr: tuple[str, ...]


async def run_validate_plan(command: tuple[str, ...], cwd: Path) -> ValidatePlanRun:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        *command,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return ValidatePlanRun(
        exit_code=process.returncode or 0,
        stdout=tuple(stdout.decode().splitlines()),
        stderr=tuple(stderr.decode().splitlines()),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ValidatePlanHarness:
    script: Path
    directory: Path
    arguments: tuple[str, ...] = ()

    def validate(self) -> ValidatePlanRun:
        command = (str(self.script), *self.arguments)
        return asyncio.run(run_validate_plan(command, self.directory))


def read_hits(run: ValidatePlanRun) -> list[tuple[int, str]]:
    matches = [HIT_LINE.match(line) for line in run.stdout]
    return [(int(match['line']), match['rule']) for match in matches if match]


def create_scenario(name: str, *edits: tuple[str, str]) -> PlanScenario:
    return PlanScenario(name=name, edits=edits)


def create_failing_scenario(name: str, edit: tuple[str, str], hit: tuple[int, str]) -> PlanScenario:
    return PlanScenario(name=name, edits=(edit,), hits=(hit,))


def create_scenario_cases(scenarios: list[PlanScenario]) -> pytest.MarkDecorator:
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def validate_plan_frontmatter_cases() -> pytest.MarkDecorator:
    frontmatter = PLAN[: PLAN.index('\n## Inventory')]
    return create_scenario_cases([
        create_failing_scenario('no-frontmatter', (frontmatter, ''), (1, 'PV1')),
        create_failing_scenario('unclosed-frontmatter', ('user\n---\n', 'user\n'), (1, 'PV1')),
        create_failing_scenario('missing-key', ('terraform: ">= 1.9"\n', ''), (1, 'PV2')),
        create_failing_scenario('unknown-mode', ('mode: extract', 'mode: split'), (2, 'PV3')),
        create_failing_scenario(
            'unknown-status', ('status: approved', 'status: shipped'), (7, 'PV3')
        ),
        create_failing_scenario(
            'unknown-approver', ('approved_by: user', 'approved_by: nobody'), (8, 'PV3')
        ),
        create_failing_scenario(
            'callers-not-a-list',
            ('callers: [envs/prod, envs/dev]', 'callers: envs/prod'),
            (5, 'PV3'),
        ),
    ])


def validate_plan_section_cases() -> pytest.MarkDecorator:
    return create_scenario_cases([
        create_failing_scenario(
            'missing-section', ('## Open questions\n\nNone.\n', ''), (1, 'PV4')
        ),
        create_failing_scenario(
            'caller-without-plan-line',
            ('- `envs/dev`: 0 to add, 0 to change, 0 to destroy\n', ''),
            (33, 'PV5'),
        ),
        create_failing_scenario('caller-without-moved-row', (DEV_ROW, ''), (19, 'PV6')),
    ])


def validate_plan_chunk_cases() -> pytest.MarkDecorator:
    rows = PLAN[PLAN.index('| C1') : PLAN.index('\n\n## Expected plan') + 1]
    return create_scenario_cases([
        create_failing_scenario('no-chunk-rows', (rows, ''), (26, 'PV7')),
        create_failing_scenario(
            'chunk-out-of-sequence', ('| C2 | wire', '| C3 | wire'), (31, 'PV7')
        ),
        create_failing_scenario(
            'chunk-owns-nothing',
            (SECOND_CHUNK, '| C2 | wire prod | - | moves-only | pending |'),
            (31, 'PV8'),
        ),
        create_failing_scenario(
            'unknown-outcome', ('| moves-only |', '| some-changes |'), (31, 'PV9')
        ),
        create_failing_scenario(
            'unknown-chunk-status', ('| pending |', '| queued |'), (31, 'PV10')
        ),
    ])


def validate_plan_approval_cases() -> pytest.MarkDecorator:
    draft = ('status: approved', 'status: draft')
    return create_scenario_cases([
        PlanScenario(name='draft-plan', edits=(draft,), require_approved=True, hits=((7, 'PV11'),)),
        PlanScenario(name='approved-plan', require_approved=True),
        PlanScenario(
            name='in-progress-plan',
            edits=(('status: approved', 'status: in-progress'),),
            require_approved=True,
        ),
        create_scenario('draft-plan-without-the-flag', draft),
    ])


def validate_plan_clean_cases() -> pytest.MarkDecorator:
    return create_scenario_cases([
        create_scenario('extract-plan'),
        create_scenario(
            'refactor-needs-no-moved-rows', ('mode: extract', 'mode: refactor'), (DEV_ROW, '')
        ),
        create_scenario('new-module', ('mode: extract', 'mode: new'), ('[envs/prod]', '[]')),
    ])


@pytest.fixture
def validate_plan(repository_root: Path) -> Path:
    return repository_root.joinpath('skills', 'create-module', 'scripts', 'validate_plan.py')


@pytest.mark.integration
class TestValidatePlanRules:
    @pytest.fixture
    def harness(
        self, validate_plan: Path, tmp_path: Path, scenario: PlanScenario
    ) -> ValidatePlanHarness:
        tmp_path.joinpath('MODULE-PLAN.md').write_text(scenario.text, encoding='utf-8')
        return ValidatePlanHarness(
            script=validate_plan, directory=tmp_path, arguments=scenario.arguments
        )

    def assert_reports_exactly(self, harness: ValidatePlanHarness, scenario: PlanScenario) -> None:
        run = harness.validate()
        assert read_hits(run) == list(scenario.hits)
        assert run.exit_code == (1 if scenario.hits else 0)

    @validate_plan_frontmatter_cases()
    def test_malformed_frontmatter_is_reported(
        self, harness: ValidatePlanHarness, scenario: PlanScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @validate_plan_section_cases()
    def test_missing_section_or_caller_coverage_is_reported(
        self, harness: ValidatePlanHarness, scenario: PlanScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @validate_plan_chunk_cases()
    def test_malformed_chunk_is_reported(
        self, harness: ValidatePlanHarness, scenario: PlanScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @validate_plan_approval_cases()
    def test_unapproved_plan_is_reported_only_when_approval_is_required(
        self, harness: ValidatePlanHarness, scenario: PlanScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @validate_plan_clean_cases()
    def test_valid_plan_is_not_reported(
        self, harness: ValidatePlanHarness, scenario: PlanScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)


@pytest.mark.integration
class TestValidatePlanCommandLine:
    @pytest.fixture
    def named_plan(self, validate_plan: Path, tmp_path: Path) -> ValidatePlanHarness:
        plan = tmp_path.joinpath('plans', 'network.md')
        plan.parent.mkdir()
        plan.write_text(PLAN.replace('status: approved', 'status: bogus'), encoding='utf-8')
        return ValidatePlanHarness(script=validate_plan, directory=tmp_path, arguments=(str(plan),))

    @pytest.fixture
    def absent_plan(self, validate_plan: Path, tmp_path: Path) -> ValidatePlanHarness:
        return ValidatePlanHarness(script=validate_plan, directory=tmp_path)

    def test_explicit_path_is_named_in_each_hit(self, named_plan: ValidatePlanHarness) -> None:
        run = named_plan.validate()
        assert run.exit_code == 1
        statuses = 'draft, approved, in-progress, done'
        expected = f'{named_plan.arguments[0]}:7: PV3 status must be one of {statuses}'
        assert run.stdout == (expected,)

    def test_missing_default_plan_is_a_usage_error(self, absent_plan: ValidatePlanHarness) -> None:
        run = absent_plan.validate()
        assert run.exit_code == 2
        assert run.stdout == ()
        assert 'MODULE-PLAN.md' in run.stderr[0]
