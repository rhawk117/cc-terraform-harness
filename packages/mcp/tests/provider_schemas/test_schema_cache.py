from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.provider_schemas.domain import ProviderRelease
from tf_harness_mcp.provider_schemas.errors import (
    LockFileMissingError,
    ProviderNotInSchemaOutputError,
    ProviderNotLockedError,
    SchemaCacheWriteError,
    SchemaOutputInvalidError,
    SchemaRunFailedError,
    SchemaTypeNotFoundError,
)
from tf_harness_mcp.provider_schemas.services import SCHEMA_ARGV
from tf_harness_mcp.runner.domain import CommandResult
from tf_harness_mcp.runner.errors import CommandNotFoundError
from tf_harness_mcp.structure.errors import HclSyntaxError

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.provider_schemas.domain import SchemaKind

    from conftest import CacheHarness

pytestmark = pytest.mark.unit

AWS = 'registry.terraform.io/hashicorp/aws'
NULL = 'registry.terraform.io/hashicorp/null'
BUILTIN = 'terraform.io/builtin/terraform'
AWS_FILES = {
    'provider.json',
    'resource/aws_instance.json',
    'resource/aws_db_instance.json',
    'resource/aws_globalaccelerator_custom_routing_listener.json',
    'data_source/aws_ami.json',
}
NULL_FILES = {'provider.json', 'resource/null_resource.json', 'data_source/null_data_source.json'}


class TestMiss:
    async def test_runs_terraform_once_in_the_module_directory(self, harness: CacheHarness) -> None:
        await harness.service.lookup(harness.request_for('resource', 'aws_instance'))

        assert len(harness.runner.calls) == 1
        call = harness.runner.calls[0]
        assert call.command.argv == ('terraform', 'providers', 'schema', '-json', '-no-color')
        assert call.command.cwd == harness.module
        assert call.timeout_seconds == 7.5

    async def test_stores_one_file_per_block_keyed_by_address_and_locked_version(
        self, harness: CacheHarness
    ) -> None:
        await harness.service.lookup(harness.request_for('provider', None))

        assert harness.stored_files(harness.release_dir(AWS, '6.69.1')) == AWS_FILES
        assert harness.stored_files(harness.release_dir(NULL, '3.3.2')) == NULL_FILES

    async def test_returns_the_requested_schema(self, harness: CacheHarness) -> None:
        expected = harness.fixture_output()['provider_schemas'][AWS]['resource_schemas'][
            'aws_instance'
        ]

        schema = await harness.service.lookup(harness.request_for('resource', 'aws_instance'))

        assert schema == expected

    async def test_returns_data_source_and_provider_schemas(self, harness: CacheHarness) -> None:
        aws = harness.fixture_output()['provider_schemas'][AWS]

        data_source = await harness.service.lookup(harness.request_for('data_source', 'aws_ami'))
        provider = await harness.service.lookup(harness.request_for('provider', None))

        assert data_source == aws['data_source_schemas']['aws_ami']
        assert provider == aws['provider']

    async def test_leaves_no_staging_directory_behind(self, harness: CacheHarness) -> None:
        await harness.service.lookup(harness.request_for('provider', None))

        assert not [path for path in harness.cache_dir.iterdir() if path.name.startswith('.')]

    async def test_skips_a_provider_without_a_locked_version(self, harness: CacheHarness) -> None:
        output = harness.fixture_output()
        output['provider_schemas'][BUILTIN] = {'provider': {'version': 0, 'block': {}}}
        harness.script_output(output)

        await harness.service.lookup(harness.request_for('provider', None))

        assert not harness.cache_dir.joinpath('terraform.io').exists()


class TestHit:
    async def test_every_type_at_a_cached_version_runs_nothing(self, harness: CacheHarness) -> None:
        await harness.service.lookup(harness.request_for('provider', None))
        cached: list[tuple[SchemaKind, str | None]] = [
            ('resource', 'aws_instance'),
            ('resource', 'aws_db_instance'),
            ('resource', 'aws_globalaccelerator_custom_routing_listener'),
            ('data_source', 'aws_ami'),
            ('provider', None),
        ]

        for kind, type_name in cached:
            schema = await harness.service.lookup(harness.request_for(kind, type_name))
            assert isinstance(schema, dict)

        assert len(harness.runner.calls) == 1

    async def test_a_second_module_at_the_same_version_runs_nothing(
        self, harness: CacheHarness, tmp_path: Path
    ) -> None:
        await harness.service.lookup(harness.request_for('provider', None))
        other = tmp_path.joinpath('other')
        other.mkdir()
        other.joinpath('.terraform.lock.hcl').write_text(harness.lock_text(aws='6.69.1'))

        schema = await harness.service.lookup(
            harness.request_for('resource', 'aws_instance', module=other)
        )

        assert isinstance(schema, dict)
        assert len(harness.runner.calls) == 1

    async def test_another_version_is_a_miss(self, harness: CacheHarness) -> None:
        await harness.service.lookup(harness.request_for('provider', None))
        harness.lock(harness.lock_text(aws='6.70.0', null='3.3.2'))

        schema = await harness.service.lookup(harness.request_for('resource', 'aws_instance'))

        assert isinstance(schema, dict)
        assert len(harness.runner.calls) == 2
        assert harness.stored_files(harness.release_dir(AWS, '6.70.0')) == AWS_FILES

    async def test_an_unknown_type_at_a_cached_version_is_reported(
        self, harness: CacheHarness
    ) -> None:
        await harness.service.lookup(harness.request_for('provider', None))

        problem = await harness.service.lookup(harness.request_for('resource', 'aws_nope'))

        assert isinstance(problem, SchemaTypeNotFoundError)
        assert problem.release == ProviderRelease(address=AWS, version='6.69.1')
        assert len(harness.runner.calls) == 1


class TestReportedConditions:
    async def test_missing_lock_file(self, harness: CacheHarness) -> None:
        harness.module.joinpath('.terraform.lock.hcl').unlink()

        problem = await harness.service.lookup(harness.request_for('provider', None))

        assert isinstance(problem, LockFileMissingError)
        assert harness.runner.calls == []

    async def test_unparseable_lock_file(self, harness: CacheHarness) -> None:
        harness.lock('provider "x" {')

        problem = await harness.service.lookup(harness.request_for('provider', None))

        assert isinstance(problem, HclSyntaxError)
        assert harness.runner.calls == []

    async def test_provider_absent_from_the_lock_file(self, harness: CacheHarness) -> None:
        harness.lock(harness.lock_text(null='3.3.2'))

        problem = await harness.service.lookup(harness.request_for('provider', None))

        assert isinstance(problem, ProviderNotLockedError)
        assert problem.address == AWS
        assert harness.runner.calls == []

    async def test_failed_schema_run(self, harness: CacheHarness) -> None:
        stderr = 'Inconsistent dependency lock file\nrun: terraform init'
        harness.runner.script(SCHEMA_ARGV, CommandResult(returncode=1, stdout='', stderr=stderr))

        problem = await harness.service.lookup(harness.request_for('provider', None))

        assert isinstance(problem, SchemaRunFailedError)
        assert problem.returncode == 1
        assert 'terraform init' in problem.stderr
        assert not harness.cache_dir.exists()

    async def test_missing_terraform_binary(self, harness: CacheHarness) -> None:
        harness.runner.script_missing_binary(SCHEMA_ARGV)

        problem = await harness.service.lookup(harness.request_for('provider', None))

        assert isinstance(problem, CommandNotFoundError)

    async def test_output_that_is_not_the_expected_json(self, harness: CacheHarness) -> None:
        harness.runner.script(SCHEMA_ARGV, CommandResult(returncode=0, stdout='[1]', stderr=''))

        problem = await harness.service.lookup(harness.request_for('provider', None))

        assert isinstance(problem, SchemaOutputInvalidError)

    async def test_locked_provider_missing_from_the_output(self, harness: CacheHarness) -> None:
        output = harness.fixture_output()
        del output['provider_schemas'][AWS]
        harness.script_output(output)

        problem = await harness.service.lookup(harness.request_for('provider', None))

        assert isinstance(problem, ProviderNotInSchemaOutputError)

    async def test_cache_directory_that_cannot_be_written(self, harness: CacheHarness) -> None:
        harness.cache_dir.write_text('a file where the cache directory should be')

        problem = await harness.service.lookup(harness.request_for('provider', None))

        assert isinstance(problem, SchemaCacheWriteError)
