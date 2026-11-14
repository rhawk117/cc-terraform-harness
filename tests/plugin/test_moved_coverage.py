import asyncio
import re
import shutil
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet

HIT_LINE = re.compile(r'^(?P<path>.+):(?P<line>\d+): (?P<rule>[A-Z]+\d+) ')
GIT = shutil.which('git') or 'git'
BASE_ROOT = (
    'resource "aws_vpc" "main" {\n'
    '  cidr_block = "10.0.0.0/16"\n'
    '}\n'
    'resource "aws_subnet" "private" {\n'
    '  count  = 2\n'
    '  vpc_id = aws_vpc.main.id\n'
    '}\n'
    'data "aws_region" "current" {}\n'
)
MODULE = 'resource "aws_vpc" "this" {}\nresource "aws_subnet" "private" {}\n'
CALL = 'module "network" {\n  source = "../../modules/network"\n}\n'
SUBNET = 'aws_subnet.private'


def write_moved(source: str, target: str) -> str:
    return f'moved {{\n  from = {source}\n  to   = {target}\n}}\n\n'


VPC_MOVED = write_moved('aws_vpc.main', 'module.network.aws_vpc.this')
SUBNET_MOVED = write_moved(SUBNET, f'module.network.{SUBNET}')
SUBNET_REMOVED = f'removed {{\n  from = {SUBNET}\n  lifecycle {{\n    destroy = false\n  }}\n}}\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class MoveScenario:
    name: str
    root: str = CALL
    moved: str
    hits: tuple[tuple[str, int, str], ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


@dataclass(slots=True, kw_only=True, frozen=True)
class MovedCoverageRun:
    exit_code: int
    stdout: tuple[str, ...]
    stderr: tuple[str, ...]


async def run_process(command: tuple[str, ...], cwd: Path) -> MovedCoverageRun:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return MovedCoverageRun(
        exit_code=process.returncode or 0,
        stdout=tuple(stdout.decode().splitlines()),
        stderr=tuple(stderr.decode().splitlines()),
    )


def run_git(repository: Path, *args: str) -> None:
    identity = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
    command = (GIT, '-C', str(repository), *identity, '-c', 'commit.gpgsign=false', *args)
    assert asyncio.run(run_process(command, repository)).exit_code == 0


def create_repository(directory: Path) -> Path:
    files = {'envs/prod/main.tf': BASE_ROOT, 'modules/network/main.tf': MODULE}
    for name, text in files.items():
        directory.joinpath(name).parent.mkdir(parents=True, exist_ok=True)
        directory.joinpath(name).write_text(text, encoding='utf-8')
    run_git(directory, 'init', '--quiet')
    run_git(directory, 'add', '.')
    run_git(directory, 'commit', '--quiet', '--message', 'base')
    return directory.joinpath('envs', 'prod')


@dataclass(slots=True, kw_only=True, frozen=True)
class MovedCoverageHarness:
    script: Path
    roots: tuple[Path, ...]
    arguments: tuple[str, ...] = ()

    def check(self) -> MovedCoverageRun:
        command = (sys.executable, str(self.script), *self.arguments, *map(str, self.roots))
        return asyncio.run(run_process(command, self.script.parent))


def read_hits(run: MovedCoverageRun) -> list[tuple[str, int, str]]:
    matches = [HIT_LINE.match(line) for line in run.stdout]
    return [(match['path'], int(match['line']), match['rule']) for match in matches if match]


def create_scenario(name: str, moved: str, *hits: tuple[str, int, str]) -> MoveScenario:
    return MoveScenario(name=name, moved=moved, hits=hits)


def create_scenario_cases(scenarios: list[MoveScenario]) -> pytest.MarkDecorator:
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def moved_coverage_clean_cases() -> pytest.MarkDecorator:
    instances = ''.join(
        write_moved(f'{SUBNET}[{index}]', f'module.network.{SUBNET}[{index}]') for index in (0, 1)
    )
    return create_scenario_cases([
        create_scenario('every-address-moved', VPC_MOVED + SUBNET_MOVED),
        create_scenario('each-instance-moved', VPC_MOVED + instances),
        create_scenario('address-removed-from-state', VPC_MOVED + SUBNET_REMOVED),
        MoveScenario(name='nothing-removed', root=BASE_ROOT, moved=''),
    ])


def moved_coverage_finding_cases() -> pytest.MarkDecorator:
    misspelled = write_moved('aws_vpc.main', 'module.netwrk.aws_vpc.this')
    renamed = write_moved('aws_vpc.main', 'aws_vpc.primary')
    missing = write_moved('aws_vpc.main', 'module.network.aws_vpc.missing')
    return create_scenario_cases([
        create_scenario('address-without-move', VPC_MOVED, ('', 1, 'MC1')),
        create_scenario('undeclared-module', misspelled + SUBNET_MOVED, ('moved.tf', 1, 'MC2')),
        create_scenario('undeclared-resource', renamed + SUBNET_MOVED, ('moved.tf', 1, 'MC2')),
        create_scenario(
            'resource-missing-in-module', missing + SUBNET_MOVED, ('moved.tf', 1, 'MC3')
        ),
        create_scenario(
            'duplicate-from', VPC_MOVED + SUBNET_MOVED + VPC_MOVED, ('moved.tf', 11, 'MC4')
        ),
    ])


@pytest.fixture
def moved_coverage(repository_root: Path) -> Path:
    return repository_root.joinpath('skills', 'create-module', 'scripts', 'moved_coverage.py')


@pytest.mark.integration
@pytest.mark.skipif(shutil.which('git') is None, reason='git is not on PATH')
class TestMovedCoverageRules:
    @pytest.fixture
    def harness(
        self, moved_coverage: Path, tmp_path: Path, scenario: MoveScenario
    ) -> MovedCoverageHarness:
        root = create_repository(tmp_path)
        root.joinpath('main.tf').write_text(scenario.root, encoding='utf-8')
        root.joinpath('moved.tf').write_text(scenario.moved, encoding='utf-8')
        return MovedCoverageHarness(script=moved_coverage, roots=(root,))

    def assert_reports_exactly(self, harness: MovedCoverageHarness, scenario: MoveScenario) -> None:
        run = harness.check()
        root = harness.roots[0]
        expected = [(str(root.joinpath(name)), line, rule) for name, line, rule in scenario.hits]
        assert read_hits(run) == expected
        assert run.exit_code == (1 if scenario.hits else 0)

    @moved_coverage_clean_cases()
    def test_covered_refactor_is_not_reported(
        self, harness: MovedCoverageHarness, scenario: MoveScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @moved_coverage_finding_cases()
    def test_uncovered_or_broken_move_is_reported(
        self, harness: MovedCoverageHarness, scenario: MoveScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)


@pytest.mark.integration
class TestMovedCoverageCommandLine:
    @pytest.fixture
    def absent_root(self, moved_coverage: Path, tmp_path: Path) -> MovedCoverageHarness:
        return MovedCoverageHarness(script=moved_coverage, roots=(tmp_path.joinpath('absent'),))

    @pytest.fixture
    def unknown_ref(self, moved_coverage: Path, tmp_path: Path) -> MovedCoverageHarness:
        root = create_repository(tmp_path)
        return MovedCoverageHarness(
            script=moved_coverage, roots=(root,), arguments=('--base', 'no-such-ref')
        )

    def assert_usage_error(self, harness: MovedCoverageHarness, named: str) -> None:
        run = harness.check()
        assert run.exit_code == 2
        assert run.stdout == ()
        assert named in run.stderr[0]

    def test_missing_root_is_a_usage_error(self, absent_root: MovedCoverageHarness) -> None:
        self.assert_usage_error(absent_root, 'absent')

    @pytest.mark.skipif(shutil.which('git') is None, reason='git is not on PATH')
    def test_unresolvable_ref_is_a_usage_error(self, unknown_ref: MovedCoverageHarness) -> None:
        self.assert_usage_error(unknown_ref, 'no-such-ref')
