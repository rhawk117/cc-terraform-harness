import asyncio
import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet

HIT_LINE = re.compile(r'^(?P<path>.+):(?P<line>\d+): (?P<rule>[A-Z]+\d+) ')


@dataclass(slots=True, kw_only=True, frozen=True)
class SmellScenario:
    name: str
    source: str
    filename: str = 'main.tf'
    hits: tuple[tuple[int, str], ...] = ()
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


@dataclass(slots=True, kw_only=True, frozen=True)
class SmellGrepRun:
    exit_code: int
    stdout: tuple[str, ...]
    stderr: tuple[str, ...]


async def run_smell_grep(script: Path, target: Path) -> SmellGrepRun:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script),
        str(target),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return SmellGrepRun(
        exit_code=process.returncode or 0,
        stdout=tuple(stdout.decode().splitlines()),
        stderr=tuple(stderr.decode().splitlines()),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SmellGrepHarness:
    script: Path
    target: Path

    def scan(self) -> SmellGrepRun:
        return asyncio.run(run_smell_grep(self.script, self.target))


def read_hits(run: SmellGrepRun) -> list[tuple[str, int, str]]:
    matches = [HIT_LINE.match(line) for line in run.stdout]
    return [(match['path'], int(match['line']), match['rule']) for match in matches if match]


def create_scenario(name: str, source: str, *hits: tuple[int, str]) -> SmellScenario:
    return SmellScenario(name=name, source=source, hits=hits)


def create_scenario_cases(scenarios: list[SmellScenario]) -> pytest.MarkDecorator:
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def smell_grep_secret_cases() -> pytest.MarkDecorator:
    return create_scenario_cases([
        create_scenario('literal-password', 'password = "hunter2"\n', (1, 'SE1')),
        create_scenario('access-key-id', 'bootstrap = "AKIAIOSFODNN7EXAMPLE"\n', (1, 'SE1')),
        create_scenario('private-key', 'cert = "-----BEGIN RSA PRIVATE KEY-----"\n', (1, 'SE1')),
        create_scenario('static-access-key', 'resource "aws_iam_access_key" "ci" {}\n', (1, 'SE4')),
        create_scenario(
            'secret-default', 'variable "db_password" {\n  default = "x"\n}\n', (2, 'SE1')
        ),
        SmellScenario(
            name='tfvars-token',
            source='api_token = "abc123"\n',
            filename='prod.tfvars',
            hits=((1, 'SE1'),),
        ),
    ])


def smell_grep_iam_cases() -> pytest.MarkDecorator:
    return create_scenario_cases([
        create_scenario('wildcard-action', 'actions = ["*"]\n', (1, 'SE6')),
        create_scenario('wildcard-resource', 'resources = ["*"]\n', (1, 'SE6')),
        create_scenario('wildcard-principal', 'identifiers = ["*"]\n', (1, 'SE6')),
        create_scenario('service-wide-action', 'actions = ["dynamodb:*"]\n', (1, 'SE6')),
        create_scenario(
            'jsonencode', 'Action   = "s3:*"\nResource = "*"\n', (1, 'SE6'), (2, 'SE6')
        ),
    ])


def smell_grep_safety_cases() -> pytest.MarkDecorator:
    return create_scenario_cases([
        create_scenario('force-destroy', 'force_destroy = true\n', (1, 'BR10')),
        create_scenario('skip-final-snapshot', 'skip_final_snapshot = true\n', (1, 'BR10')),
        create_scenario('deletion-protection-off', 'deletion_protection = false\n', (1, 'BR10')),
        create_scenario(
            'table-protection-off', 'deletion_protection_enabled = false\n', (1, 'BR10')
        ),
        create_scenario('prevent-destroy-off', 'prevent_destroy = false\n', (1, 'BR10')),
    ])


def smell_grep_idiom_cases() -> pytest.MarkDecorator:
    git_module = 'module "net" {\n  source = "git::https://example.com/net.git"\n}\n'
    registry_module = 'module "vpc" {\n  source = "terraform-aws-modules/vpc/aws"\n}\n'
    return create_scenario_cases([
        create_scenario(
            'account-in-arn', 'role = "arn:aws:iam::123456789012:role/job"\n', (1, 'DE3')
        ),
        create_scenario('bare-account-id', 'account_number = "123456789012"\n', (1, 'DE3')),
        create_scenario('ami-literal', 'ami = "ami-0abcdef1234567890"\n', (1, 'DE3')),
        create_scenario(
            'inline-acl', 'resource "aws_s3_bucket" "b" {\n  acl = "private"\n}\n', (2, 'VE6')
        ),
        create_scenario('alb-resource', 'resource "aws_alb" "web" {}\n', (1, 'VE6')),
        create_scenario('unversioned-registry-module', registry_module, (2, 'VE4')),
        create_scenario('unpinned-git-module', git_module, (2, 'VE4')),
    ])


def smell_grep_regression_cases() -> pytest.MarkDecorator:
    regression = (pytest.mark.regression,)
    return create_scenario_cases([
        SmellScenario(name='http-tokens', source='http_tokens = "required"\n', marks=regression),
        SmellScenario(
            name='api-key-source', source='api_key_source = "HEADER"\n', marks=regression
        ),
    ])


def smell_grep_clean_cases() -> pytest.MarkDecorator:
    pinned_modules = (
        'module "vpc" {\n  source  = "terraform-aws-modules/vpc/aws"\n  version = "~> 5.0"\n}\n'
        'module "net" {\n  source = "git::https://example.com/net.git?ref=v1.2.0"\n}\n'
        'module "local" {\n  source = "../modules/local"\n}\n'
    )
    return create_scenario_cases([
        create_scenario('secret-name', 'secret_name = "ledger/db"\n'),
        create_scenario('secret-by-reference', 'password = random_password.db.result\n'),
        create_scenario('interpolated-secret', 'secret = "${random_password.db.result}"\n'),
        create_scenario('allowed-account-ids', 'allowed_account_ids = ["123456789012"]\n'),
        create_scenario('commented-out', '# password = "hunter2"\n// force_destroy = true\n'),
        create_scenario(
            'bucket-acl-resource', 'resource "aws_s3_bucket_acl" "b" {\n  acl = "x"\n}\n'
        ),
        create_scenario('pinned-modules', pinned_modules),
    ])


@pytest.fixture
def smell_grep(repository_root: Path) -> Path:
    return repository_root.joinpath('skills', 'writing-terraform', 'scripts', 'smell_grep.py')


@pytest.mark.integration
class TestSmellGrepRules:
    @pytest.fixture
    def harness(
        self, smell_grep: Path, tmp_path: Path, scenario: SmellScenario
    ) -> SmellGrepHarness:
        tmp_path.joinpath(scenario.filename).write_text(scenario.source, encoding='utf-8')
        return SmellGrepHarness(script=smell_grep, target=tmp_path)

    def assert_reports_exactly(self, harness: SmellGrepHarness, scenario: SmellScenario) -> None:
        run = harness.scan()
        target = str(harness.target.joinpath(scenario.filename))
        assert read_hits(run) == [(target, line, rule) for line, rule in scenario.hits]
        assert run.exit_code == (1 if scenario.hits else 0)

    @smell_grep_secret_cases()
    def test_secret_or_static_key_is_reported(
        self, harness: SmellGrepHarness, scenario: SmellScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @smell_grep_iam_cases()
    def test_wildcard_iam_is_reported(
        self, harness: SmellGrepHarness, scenario: SmellScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @smell_grep_safety_cases()
    def test_weakened_safety_setting_is_reported(
        self, harness: SmellGrepHarness, scenario: SmellScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @smell_grep_idiom_cases()
    def test_hardcoded_identifier_stale_idiom_or_unpinned_module_is_reported(
        self, harness: SmellGrepHarness, scenario: SmellScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @smell_grep_regression_cases()
    def test_past_false_positive_is_not_reported(
        self, harness: SmellGrepHarness, scenario: SmellScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @smell_grep_clean_cases()
    def test_safe_terraform_is_not_reported(
        self, harness: SmellGrepHarness, scenario: SmellScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)


@pytest.mark.integration
class TestSmellGrepCommandLine:
    force_destroy = 'resource "aws_s3_bucket" "logs" {\n  force_destroy = true\n}\n'
    readme = 'Set password = "hunter2" in the console.\n'

    @pytest.fixture
    def vendored_module(self, smell_grep: Path, tmp_path: Path) -> SmellGrepHarness:
        module = tmp_path.joinpath('.terraform', 'modules', 'logs')
        module.mkdir(parents=True)
        module.joinpath('main.tf').write_text(self.force_destroy, encoding='utf-8')
        return SmellGrepHarness(script=smell_grep, target=tmp_path)

    @pytest.fixture
    def readme_only(self, smell_grep: Path, tmp_path: Path) -> SmellGrepHarness:
        tmp_path.joinpath('README.md').write_text(self.readme, encoding='utf-8')
        return SmellGrepHarness(script=smell_grep, target=tmp_path)

    @pytest.fixture
    def two_modules(self, smell_grep: Path, tmp_path: Path) -> SmellGrepHarness:
        for name in ('beta', 'alpha'):
            module = tmp_path.joinpath(name)
            module.mkdir()
            module.joinpath('main.tf').write_text(self.force_destroy, encoding='utf-8')
        return SmellGrepHarness(script=smell_grep, target=tmp_path)

    @pytest.fixture
    def absent_path(self, smell_grep: Path, tmp_path: Path) -> SmellGrepHarness:
        return SmellGrepHarness(script=smell_grep, target=tmp_path.joinpath('absent'))

    def assert_reports_nothing(self, harness: SmellGrepHarness) -> None:
        run = harness.scan()
        assert (run.exit_code, run.stdout) == (0, ())

    def test_vendored_modules_are_skipped(self, vendored_module: SmellGrepHarness) -> None:
        self.assert_reports_nothing(vendored_module)

    def test_files_that_are_not_terraform_are_skipped(self, readme_only: SmellGrepHarness) -> None:
        self.assert_reports_nothing(readme_only)

    def test_hits_are_ordered_by_path(self, two_modules: SmellGrepHarness) -> None:
        paths = [path for path, _, _ in read_hits(two_modules.scan())]
        expected = [two_modules.target.joinpath(name, 'main.tf') for name in ('alpha', 'beta')]
        assert paths == list(map(str, expected))

    def test_missing_path_exits_two_and_names_it(self, absent_path: SmellGrepHarness) -> None:
        run = absent_path.scan()
        assert run.exit_code == 2
        assert run.stderr == (f'smell_grep: no such path: {absent_path.target}',)
