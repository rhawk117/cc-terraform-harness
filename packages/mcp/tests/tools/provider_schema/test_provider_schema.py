import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tf_harness_mcp.provider_schemas.services import SCHEMA_ARGV
from tf_harness_mcp.runner.domain import CommandResult
from tf_harness_mcp.runner.process import create_command_runner
from tf_harness_mcp.server import create_server
from tf_harness_mcp.settings import Settings

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mcp import Client
    from mcp.server.mcpserver import MCPServer
    from mcp.types import CallToolResult
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

FIXTURE = Path(__file__).parents[2].joinpath('provider_schemas', 'schema.json')
MAIN_TF = """\
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
"""
LOCK_TEXT = (
    'provider "registry.terraform.io/hashicorp/aws" {\n'
    '  version     = "6.69.1"\n'
    '  constraints = "~> 6.0"\n'
    '  hashes = [\n    "h1:abc=",\n  ]\n}\n'
)
NULL_LOCK_TEXT = LOCK_TEXT.replace('aws', 'null').replace('6.69.1', '3.3.2')


def read_text(result: CallToolResult) -> str:
    return ''.join(getattr(block, 'text', '') for block in result.content)


async def read_level(client: Client, module: Path, **arguments: str) -> dict[str, Any]:
    result = await client.call_tool('provider_schema', {'path': str(module)} | arguments)
    assert not result.is_error, read_text(result)
    assert result.structured_content is not None
    return result.structured_content


async def read_error(client: Client, module: Path, **arguments: str) -> str:
    result = await client.call_tool('provider_schema', {'path': str(module)} | arguments)
    assert result.is_error
    return read_text(result)


def names(entries: list[dict[str, Any]]) -> list[str]:
    return [entry['name'] for entry in entries]


@pytest.fixture
def module(project_root: Path) -> Path:
    directory = project_root.joinpath('stack')
    directory.mkdir()
    directory.joinpath('main.tf').write_text(MAIN_TF)
    directory.joinpath('.terraform.lock.hcl').write_text(LOCK_TEXT)
    return directory


@pytest.fixture
def scripted(recording_runner: RecordingCommandRunner) -> RecordingCommandRunner:
    output = CommandResult(returncode=0, stdout=FIXTURE.read_text(), stderr='')
    recording_runner.script(SCHEMA_ARGV, output)
    return recording_runner


@pytest.mark.unit
@pytest.mark.usefixtures('scripted')
class TestProviderSchemaLevels:
    async def test_resource_level_lists_attributes_and_one_summary_per_block(
        self, client: Client, module: Path
    ) -> None:
        level = await read_level(client, module, type='aws_instance', kind='resource')

        ami = next(entry for entry in level['attributes'] if entry['name'] == 'ami')
        tags = next(entry for entry in level['attributes'] if entry['name'] == 'tags')
        cpu = next(entry for entry in level['blocks'] if entry['name'] == 'cpu_options')
        assert (ami['type'], ami['optional'], ami['computed'], ami['required']) == (
            'string',
            True,
            True,
            False,
        )
        assert tags['type'] == 'map(string)'
        assert cpu == {
            'name': 'cpu_options',
            'nesting_mode': 'list',
            'min_items': None,
            'max_items': 1,
            'attribute_count': 4,
            'block_count': 0,
        }

    async def test_locked_version_sits_beside_the_configuration_constraint(
        self, client: Client, module: Path
    ) -> None:
        level = await read_level(client, module, type='aws_instance', kind='resource')

        assert level['version'] == '6.69.1'
        assert level['constraint'] == '~> 6.0'
        assert level['provider'] == 'registry.terraform.io/hashicorp/aws'

    async def test_undeclared_provider_has_no_constraint(
        self, client: Client, module: Path
    ) -> None:
        module.joinpath('main.tf').write_text('resource "aws_instance" "web" {}\n')

        level = await read_level(client, module, type='aws_instance', kind='resource')

        assert level['constraint'] is None
        assert level['version'] == '6.69.1'

    async def test_block_path_selects_a_nested_level(self, client: Client, module: Path) -> None:
        level = await read_level(
            client,
            module,
            type='aws_instance',
            kind='resource',
            block='capacity_reservation_specification.capacity_reservation_target',
        )

        assert names(level['attributes']) == [
            'capacity_reservation_id',
            'capacity_reservation_resource_group_arn',
        ]
        assert level['blocks'] == []
        assert level['block'] == 'capacity_reservation_specification.capacity_reservation_target'

    async def test_data_source_and_provider_kinds(self, client: Client, module: Path) -> None:
        data = await read_level(client, module, type='aws_ami', kind='data_source')
        provider = await read_level(client, module, type='aws', kind='provider')

        assert 'owners' in names(data['attributes'])
        assert 'region' in names(provider['attributes'])
        assert provider['type'] == 'aws'

    async def test_second_call_reads_the_cache_without_running_terraform(
        self, client: Client, module: Path, scripted: RecordingCommandRunner
    ) -> None:
        await read_level(client, module, type='aws_instance', kind='resource')
        await read_level(client, module, type='aws_ami', kind='data_source')

        assert len(scripted.calls) == 1

    async def test_cache_is_filled_under_the_test_cache_directory(
        self, client: Client, module: Path, settings: Settings
    ) -> None:
        await read_level(client, module, type='aws_instance', kind='resource')

        assert settings.schema_cache_dir.joinpath('registry.terraform.io').is_dir()
        assert settings.schema_cache_dir.is_relative_to(settings.project_root.parent)


@dataclass(slots=True, kw_only=True, frozen=True)
class Condition:
    name: str
    arguments: dict[str, str]
    lock: str | None
    expected: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def condition_cases() -> pytest.MarkDecorator:
    resource = {'type': 'aws_instance', 'kind': 'resource'}
    cases = [
        Condition(
            name='unknown-type',
            arguments={'type': 'aws_nothing', 'kind': 'resource'},
            lock=LOCK_TEXT,
            expected='has no resource schema named aws_nothing',
        ),
        Condition(
            name='type-of-the-wrong-kind',
            arguments={'type': 'aws_instance', 'kind': 'data_source'},
            lock=LOCK_TEXT,
            expected='has no data_source schema named aws_instance',
        ),
        Condition(
            name='unknown-block-path',
            arguments=resource | {'block': 'cpu_options.nothing'},
            lock=LOCK_TEXT,
            expected="has no nested block or nested attribute at 'cpu_options.nothing'",
        ),
        Condition(
            name='malformed-block-path',
            arguments=resource | {'block': 'cpu_options..x'},
            lock=LOCK_TEXT,
            expected='block path is not dot separated',
        ),
        Condition(
            name='provider-missing-from-lock-file',
            arguments=resource,
            lock=NULL_LOCK_TEXT,
            expected='has no entry in',
        ),
        Condition(
            name='uninitialized-directory',
            arguments=resource,
            lock=None,
            expected='is missing; run terraform init',
        ),
    ]
    return pytest.mark.parametrize('condition', [case.param for case in cases])


@pytest.mark.unit
@pytest.mark.usefixtures('scripted')
class TestProviderSchemaConditions:
    @condition_cases()
    async def test_condition_is_reported(
        self, client: Client, module: Path, condition: Condition
    ) -> None:
        lock = module.joinpath('.terraform.lock.hcl')
        lock.unlink()
        if condition.lock is not None:
            lock.write_text(condition.lock)

        text = await read_error(client, module, **condition.arguments)

        assert condition.expected in text


@pytest.mark.unit
@pytest.mark.usefixtures('scripted')
class TestProviderSchemaBudget:
    ceiling = 3_000

    @pytest.fixture
    def settings(self, project_root: Path, schema_cache_dir: Path) -> Settings:
        return Settings(
            project_root=project_root,
            schema_cache_dir=schema_cache_dir,
            output_budget_bytes=self.ceiling,
            output_budget_max_bytes=self.ceiling,
        )

    async def test_oversized_level_is_cut_to_fit_and_the_cut_is_reported(
        self, client: Client, module: Path
    ) -> None:
        level = await read_level(client, module, type='aws_instance', kind='resource')

        assert len(json.dumps(level, separators=(',', ':'))) <= self.ceiling
        assert level['attributes']
        assert level['attributes_omitted'] > 0


@pytest.mark.integration
@pytest.mark.skipif(shutil.which('terraform') is None, reason='terraform is not on PATH')
class TestProviderSchemaWithTerraform:
    @pytest.fixture
    def server(self, settings: Settings) -> MCPServer:
        return create_server(settings, create_command_runner())

    async def test_uninitialized_module_reports_the_missing_provider(
        self, client: Client, module: Path, settings: Settings
    ) -> None:
        text = await read_error(client, module, type='aws_instance', kind='resource')

        assert 'terraform providers schema exited' in text
        assert 'registry.terraform.io/hashicorp/aws' in text
        assert not module.joinpath('.terraform').exists()
        assert not list(settings.schema_cache_dir.iterdir())
