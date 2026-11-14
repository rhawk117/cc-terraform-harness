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
VERSIONS = (
    'terraform {\n'
    '  required_version = ">= 1.9"\n'
    '  required_providers {\n'
    '    aws = {\n'
    '      source  = "hashicorp/aws"\n'
    '      version = "~> 5.0"\n'
    '    }\n'
    '  }\n'
    '}\n'
)
INTERFACE = (
    'variable "name" {\n'
    '  type        = string\n'
    '  description = "Name."\n'
    '}\n'
    'output "id" {\n'
    '  value       = aws_vpc.this.id\n'
    '  description = "ID."\n'
    '}\n'
)
MODULE = VERSIONS + INTERFACE


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleScenario:
    name: str
    source: str
    readme: bool = True
    hits: tuple[tuple[str, int, str], ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleLintRun:
    exit_code: int
    stdout: tuple[str, ...]
    stderr: tuple[str, ...]


async def run_module_lint(script: Path, targets: tuple[Path, ...]) -> ModuleLintRun:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script),
        *map(str, targets),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return ModuleLintRun(
        exit_code=process.returncode or 0,
        stdout=tuple(stdout.decode().splitlines()),
        stderr=tuple(stderr.decode().splitlines()),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleLintHarness:
    script: Path
    targets: tuple[Path, ...]

    def scan(self) -> ModuleLintRun:
        return asyncio.run(run_module_lint(self.script, self.targets))


def read_hits(run: ModuleLintRun) -> list[tuple[str, int, str]]:
    matches = [HIT_LINE.match(line) for line in run.stdout]
    return [(match['path'], int(match['line']), match['rule']) for match in matches if match]


def write_module(directory: Path, scenario: ModuleScenario) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    directory.joinpath('main.tf').write_text(scenario.source, encoding='utf-8')
    if scenario.readme:
        directory.joinpath('README.md').write_text('# Module\n', encoding='utf-8')

    return directory


def create_scenario(name: str, source: str, *hits: tuple[str, int, str]) -> ModuleScenario:
    return ModuleScenario(name=name, source=source, hits=hits)


def create_scenario_cases(scenarios: list[ModuleScenario]) -> pytest.MarkDecorator:
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def module_lint_settings_cases() -> pytest.MarkDecorator:
    backend = VERSIONS.replace('  required_providers', '  backend "s3" {}\n  required_providers')
    cloud = VERSIONS.replace(
        '  required_providers', '  cloud {\n    organization = "acme"\n  }\n  required_providers'
    )
    unpinned = VERSIONS.replace('      version = "~> 5.0"\n', '')
    no_core = VERSIONS.replace('  required_version = ">= 1.9"\n', '')
    provider = 'provider "aws" {\n  region = var.region\n}\n'
    return create_scenario_cases([
        create_scenario('provider-block', MODULE + provider, ('main.tf', 18, 'ML1')),
        create_scenario('backend-block', backend + INTERFACE, ('main.tf', 3, 'ML2')),
        create_scenario('cloud-block', cloud + INTERFACE, ('main.tf', 3, 'ML2')),
        create_scenario(
            'no-required-providers',
            'terraform {\n  required_version = ">= 1.9"\n}\n' + INTERFACE,
            ('', 1, 'ML3'),
        ),
        create_scenario('unpinned-provider', unpinned + INTERFACE, ('main.tf', 4, 'ML3')),
        create_scenario('no-required-version', no_core + INTERFACE, ('', 1, 'ML4')),
        ModuleScenario(name='no-readme', source=MODULE, readme=False, hits=(('', 1, 'ML9'),)),
    ])


def module_lint_interface_cases() -> pytest.MarkDecorator:
    untyped = 'variable "size" {\n  description = "Size."\n}\n'
    loose = 'variable "tags" {\n  type        = any\n  description = "Tags."\n}\n'
    undocumented = 'variable "size" {\n  type = number\n}\n'
    output = 'output "arn" {\n  value = aws_vpc.this.arn\n}\n'
    return create_scenario_cases([
        create_scenario('untyped-variable', MODULE + untyped, ('main.tf', 18, 'ML5')),
        create_scenario('any-typed-variable', MODULE + loose, ('main.tf', 18, 'ML5')),
        create_scenario('undocumented-variable', MODULE + undocumented, ('main.tf', 18, 'ML6')),
        create_scenario('undocumented-output', MODULE + output, ('main.tf', 18, 'ML7')),
    ])


def module_lint_literal_cases() -> pytest.MarkDecorator:
    environment = 'resource "aws_vpc" "this" {\n  tags = { Environment = "prod" }\n}\n'
    region = 'locals {\n  region = "us-east-1"\n}\n'
    account = 'module "peer" {\n  source  = "./peer"\n  account = "123456789012"\n}\n'
    return create_scenario_cases([
        create_scenario('environment-name', MODULE + environment, ('main.tf', 19, 'ML8')),
        create_scenario('region', MODULE + region, ('main.tf', 19, 'ML8')),
        create_scenario('account-id', MODULE + account, ('main.tf', 20, 'ML8')),
    ])


def module_lint_clean_cases() -> pytest.MarkDecorator:
    validation = (
        'variable "env" {\n'
        '  type        = string\n'
        '  description = "Env."\n'
        '  validation {\n'
        '    condition     = contains(["dev", "prod"], var.env)\n'
        '    error_message = "Bad."\n'
        '  }\n'
        '}\n'
    )
    heredoc = (
        'resource "aws_iam_policy" "p" {\n'
        '  # deployed to us-east-1 in prod\n'
        '  policy = <<EOT\n'
        '{"Region": "us-east-1"}\n'
        'EOT\n'
        '}\n'
    )
    return create_scenario_cases([
        create_scenario('complete-module', MODULE),
        create_scenario('literal-in-variable-validation', MODULE + validation),
        create_scenario('literal-in-comment-or-heredoc', MODULE + heredoc),
    ])


@pytest.fixture
def module_lint(repository_root: Path) -> Path:
    return repository_root.joinpath('skills', 'create-module', 'scripts', 'module_lint.py')


@pytest.mark.integration
class TestModuleLintRules:
    @pytest.fixture
    def harness(
        self, module_lint: Path, tmp_path: Path, scenario: ModuleScenario
    ) -> ModuleLintHarness:
        module = write_module(tmp_path.joinpath('module'), scenario)
        return ModuleLintHarness(script=module_lint, targets=(module,))

    def assert_reports_exactly(self, harness: ModuleLintHarness, scenario: ModuleScenario) -> None:
        run = harness.scan()
        module = harness.targets[0]
        expected = [(str(module.joinpath(name)), line, rule) for name, line, rule in scenario.hits]
        assert read_hits(run) == expected
        assert run.exit_code == (1 if scenario.hits else 0)

    @module_lint_settings_cases()
    def test_provider_state_or_version_setting_is_reported(
        self, harness: ModuleLintHarness, scenario: ModuleScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @module_lint_interface_cases()
    def test_loose_or_undocumented_interface_is_reported(
        self, harness: ModuleLintHarness, scenario: ModuleScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @module_lint_literal_cases()
    def test_hardcoded_literal_is_reported(
        self, harness: ModuleLintHarness, scenario: ModuleScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)

    @module_lint_clean_cases()
    def test_reusable_module_is_not_reported(
        self, harness: ModuleLintHarness, scenario: ModuleScenario
    ) -> None:
        self.assert_reports_exactly(harness, scenario)


@pytest.mark.integration
class TestModuleLintCommandLine:
    provider = 'provider "aws" {\n  region = "us-east-1"\n}\n'

    @pytest.fixture
    def nested_example(self, module_lint: Path, tmp_path: Path) -> ModuleLintHarness:
        module = write_module(tmp_path, create_scenario('module', MODULE))
        for nested in ('examples/basic', 'tests', '.terraform/modules/x'):
            directory = module.joinpath(nested)
            directory.mkdir(parents=True)
            directory.joinpath('main.tf').write_text(self.provider, encoding='utf-8')
        return ModuleLintHarness(script=module_lint, targets=(module,))

    @pytest.fixture
    def two_modules(self, module_lint: Path, tmp_path: Path) -> ModuleLintHarness:
        scenario = create_scenario('provider', MODULE + self.provider)
        beta, alpha = (
            write_module(tmp_path.joinpath(name), scenario) for name in ('beta', 'alpha')
        )
        return ModuleLintHarness(script=module_lint, targets=(beta, alpha))

    @pytest.fixture
    def absent_path(self, module_lint: Path, tmp_path: Path) -> ModuleLintHarness:
        return ModuleLintHarness(script=module_lint, targets=(tmp_path.joinpath('absent'),))

    def test_nested_directories_are_not_scanned(self, nested_example: ModuleLintHarness) -> None:
        run = nested_example.scan()
        assert (run.exit_code, run.stdout) == (0, ())

    def test_hits_are_ordered_by_path(self, two_modules: ModuleLintHarness) -> None:
        paths = [path for path, _, _ in read_hits(two_modules.scan())]
        assert paths == sorted(paths)
        assert len(paths) == 2

    def test_missing_directory_is_a_usage_error(self, absent_path: ModuleLintHarness) -> None:
        run = absent_path.scan()
        assert run.exit_code == 2
        assert run.stdout == ()
        assert 'absent' in run.stderr[0]
