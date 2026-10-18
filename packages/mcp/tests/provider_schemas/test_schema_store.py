import json
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.provider_schemas.domain import ProviderRelease, SchemaRequest, StoredSchema
from tf_harness_mcp.provider_schemas.errors import (
    InvalidProviderAddressError,
    InvalidProviderVersionError,
    InvalidTypeNameError,
    SchemaCacheWriteError,
)
from tf_harness_mcp.provider_schemas.store import SchemaStore

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import CacheHarness

pytestmark = pytest.mark.unit

AWS = 'registry.terraform.io/hashicorp/aws'
AWS_FILES = {
    'provider.json',
    'resource/aws_instance.json',
    'resource/aws_db_instance.json',
    'resource/aws_globalaccelerator_custom_routing_listener.json',
    'data_source/aws_ami.json',
}


class TestPathGuard:
    @pytest.mark.parametrize('address', ['../x/y', '../../../etc/passwd', f'{AWS}/..', 'a/b'])
    async def test_address_outside_the_form_builds_no_path(
        self, harness: CacheHarness, address: str
    ) -> None:
        request = SchemaRequest(module=harness.module, address=address, kind='provider')

        with pytest.raises(InvalidProviderAddressError):
            await harness.service.lookup(request)
        assert harness.runner.calls == []
        assert not harness.cache_dir.exists()

    @pytest.mark.parametrize('type_name', ['../evil', '..', 'a/b', ''])
    async def test_type_name_outside_the_form_builds_no_path(
        self, harness: CacheHarness, type_name: str
    ) -> None:
        with pytest.raises(InvalidTypeNameError):
            await harness.service.lookup(harness.request_for('resource', type_name))
        assert harness.runner.calls == []
        assert not harness.cache_dir.exists()

    async def test_locked_version_outside_the_form_builds_no_path(
        self, harness: CacheHarness
    ) -> None:
        harness.lock(harness.lock_text(aws='../../escape'))

        with pytest.raises(InvalidProviderVersionError):
            await harness.service.lookup(harness.request_for('provider', None))
        assert harness.runner.calls == []
        assert not harness.cache_dir.exists()

    async def test_names_in_terraform_output_outside_the_form_become_no_file(
        self, harness: CacheHarness, tmp_path: Path
    ) -> None:
        output = harness.fixture_output()
        aws = output['provider_schemas'][AWS]
        aws['resource_schemas']['../../../escaped'] = {'version': 0, 'block': {}}
        output['provider_schemas']['../../escaped/host/x'] = aws
        harness.lock(
            harness.lock_text(aws='6.69.1')
            + 'provider "../../escaped/host/x" {\n  version = "1.0.0"\n}\n'
        )
        harness.script_output(output)

        await harness.service.lookup(harness.request_for('provider', None))

        assert harness.stored_files(harness.release_dir(AWS, '6.69.1')) == AWS_FILES
        assert not [name for name in harness.stored_files(tmp_path) if 'escaped' in name]


class TestAtomicPublish:
    release = ProviderRelease(address=AWS, version='6.69.1')
    schema = StoredSchema(kind='provider', type_name=None, document={'version': 0})

    @pytest.fixture
    def store(self, cache_dir: Path) -> SchemaStore:
        return SchemaStore(cache_dir=cache_dir)

    def test_a_writer_that_loses_the_race_keeps_the_winners_files(
        self, store: SchemaStore, cache_dir: Path
    ) -> None:
        winner = store.release_dir(self.release)
        winner.mkdir(parents=True)
        winner.joinpath('provider.json').write_text('{"winner": true}')

        problem = store.write_release(self.release, [self.schema])

        assert problem is None
        assert json.loads(winner.joinpath('provider.json').read_text()) == {'winner': True}
        assert [path.name for path in cache_dir.iterdir()] == ['registry.terraform.io']

    def test_a_failed_write_leaves_no_partial_version(
        self, store: SchemaStore, cache_dir: Path
    ) -> None:
        too_long = StoredSchema(kind='resource', type_name='x' * 300, document={})

        problem = store.write_release(self.release, [self.schema, too_long])

        assert isinstance(problem, SchemaCacheWriteError)
        assert not store.has_release(self.release)
        assert not [path for path in cache_dir.iterdir() if path.name.startswith('.')]

    def test_a_version_appears_complete_or_not_at_all(self, store: SchemaStore) -> None:
        assert not store.has_release(self.release)

        store.write_release(self.release, [self.schema])

        assert store.has_release(self.release)
        assert store.read_schema(self.release, 'provider', None) == {'version': 0}
