import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.provider_schemas.domain import (
    ProviderRelease,
    SchemaCacheOptions,
    SchemaRequest,
    StoredSchema,
)
from tf_harness_mcp.provider_schemas.errors import (
    InvalidProviderAddressError,
    InvalidProviderVersionError,
    InvalidTypeNameError,
    LockFileMissingError,
    ProviderNotInSchemaOutputError,
    ProviderNotLockedError,
    SchemaCacheWriteError,
    SchemaOutputInvalidError,
    SchemaRunFailedError,
    SchemaTypeNotFoundError,
)
from tf_harness_mcp.provider_schemas.services import (
    SCHEMA_ARGV,
    create_provider_schema_service,
)
from tf_harness_mcp.provider_schemas.store import SchemaStore
from tf_harness_mcp.runner.domain import CommandResult
from tf_harness_mcp.runner.errors import CommandNotFoundError
from tf_harness_mcp.structure.errors import HclSyntaxError

if TYPE_CHECKING:
    from tf_harness_mcp.provider_schemas.domain import JsonObject, SchemaKind
    from tf_harness_mcp.provider_schemas.services import ProviderSchemaService
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).with_name('schema.json')
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
SCHEMA_RESULT = CommandResult(returncode=0, stdout=FIXTURE.read_text(), stderr='')


def lock_text(**versions: str) -> str:
    blocks = [
        f'provider "registry.terraform.io/hashicorp/{name}" {{\n'
        f'  version     = "{version}"\n'
        f'  constraints = ">= 3.0"\n'
        f'  hashes = [\n    "h1:abc=",\n  ]\n}}\n'
        for name, version in versions.items()
    ]
    return '\n'.join(blocks)


def fixture_output() -> JsonObject:
    return json.loads(FIXTURE.read_text())


def request_for(module: Path, kind: SchemaKind, type_name: str | None) -> SchemaRequest:
    return SchemaRequest(module=module, address=AWS, kind=kind, type_name=type_name)


def stored_files(directory: Path) -> set[str]:
    paths = (path for path in directory.rglob('*') if path.is_file())
    return {path.relative_to(directory).as_posix() for path in paths}


@dataclass(slots=True, kw_only=True, frozen=True)
class CacheHarness:
    module: Path
    cache_dir: Path
    runner: RecordingCommandRunner
    service: ProviderSchemaService

    def lock(self, text: str) -> None:
        self.module.joinpath('.terraform.lock.hcl').write_text(text)

    def script_output(self, output: JsonObject) -> None:
        stdout = json.dumps(output)
        self.runner.script(SCHEMA_ARGV, CommandResult(returncode=0, stdout=stdout, stderr=''))

    def release_dir(self, address: str, version: str) -> Path:
        return self.cache_dir.joinpath(*address.split('/'), version)


@pytest.fixture
def module(tmp_path: Path) -> Path:
    directory = tmp_path.joinpath('module')
    directory.mkdir()
    return directory


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path.joinpath('cache')


@pytest.fixture
def harness(
    module: Path, cache_dir: Path, recording_runner: RecordingCommandRunner
) -> CacheHarness:
    options = SchemaCacheOptions(cache_dir=cache_dir, timeout_seconds=7.5)
    service = create_provider_schema_service(recording_runner, options)
    harness = CacheHarness(
        module=module, cache_dir=cache_dir, runner=recording_runner, service=service
    )
    harness.lock(lock_text(aws='6.69.1', null='3.3.2'))
    recording_runner.script(SCHEMA_ARGV, SCHEMA_RESULT)
    return harness


class TestMiss:
    async def test_runs_terraform_once_in_the_module_directory(self, harness: CacheHarness) -> None:
        await harness.service.lookup(request_for(harness.module, 'resource', 'aws_instance'))

        assert len(harness.runner.calls) == 1
        call = harness.runner.calls[0]
        assert call.command.argv == SCHEMA_ARGV
        assert call.command.cwd == harness.module
        assert call.timeout_seconds == 7.5

    async def test_stores_one_file_per_block_keyed_by_address_and_locked_version(
        self, harness: CacheHarness
    ) -> None:
        await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert stored_files(harness.release_dir(AWS, '6.69.1')) == AWS_FILES
        assert stored_files(harness.release_dir(NULL, '3.3.2')) == NULL_FILES

    async def test_returns_the_requested_schema(self, harness: CacheHarness) -> None:
        expected = fixture_output()['provider_schemas'][AWS]['resource_schemas']['aws_instance']

        schema = await harness.service.lookup(
            request_for(harness.module, 'resource', 'aws_instance')
        )

        assert schema == expected

    async def test_returns_data_source_and_provider_schemas(self, harness: CacheHarness) -> None:
        aws = fixture_output()['provider_schemas'][AWS]

        data_source = await harness.service.lookup(
            request_for(harness.module, 'data_source', 'aws_ami')
        )
        provider = await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert data_source == aws['data_source_schemas']['aws_ami']
        assert provider == aws['provider']

    async def test_leaves_no_staging_directory_behind(self, harness: CacheHarness) -> None:
        await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert not [path for path in harness.cache_dir.iterdir() if path.name.startswith('.')]

    async def test_skips_a_provider_without_a_locked_version(self, harness: CacheHarness) -> None:
        output = fixture_output()
        output['provider_schemas'][BUILTIN] = {'provider': {'version': 0, 'block': {}}}
        harness.script_output(output)

        await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert not harness.cache_dir.joinpath('terraform.io').exists()


class TestHit:
    async def test_every_type_at_a_cached_version_runs_nothing(self, harness: CacheHarness) -> None:
        await harness.service.lookup(request_for(harness.module, 'provider', None))
        cached: list[tuple[SchemaKind, str | None]] = [
            ('resource', 'aws_instance'),
            ('resource', 'aws_db_instance'),
            ('resource', 'aws_globalaccelerator_custom_routing_listener'),
            ('data_source', 'aws_ami'),
            ('provider', None),
        ]

        for kind, type_name in cached:
            schema = await harness.service.lookup(request_for(harness.module, kind, type_name))
            assert isinstance(schema, dict)

        assert len(harness.runner.calls) == 1

    async def test_a_second_module_at_the_same_version_runs_nothing(
        self, harness: CacheHarness, tmp_path: Path
    ) -> None:
        await harness.service.lookup(request_for(harness.module, 'provider', None))
        other = tmp_path.joinpath('other')
        other.mkdir()
        other.joinpath('.terraform.lock.hcl').write_text(lock_text(aws='6.69.1'))

        schema = await harness.service.lookup(request_for(other, 'resource', 'aws_instance'))

        assert isinstance(schema, dict)
        assert len(harness.runner.calls) == 1

    async def test_another_version_is_a_miss(self, harness: CacheHarness) -> None:
        await harness.service.lookup(request_for(harness.module, 'provider', None))
        harness.lock(lock_text(aws='6.70.0', null='3.3.2'))

        schema = await harness.service.lookup(
            request_for(harness.module, 'resource', 'aws_instance')
        )

        assert isinstance(schema, dict)
        assert len(harness.runner.calls) == 2
        assert stored_files(harness.release_dir(AWS, '6.70.0')) == AWS_FILES

    async def test_an_unknown_type_at_a_cached_version_is_reported(
        self, harness: CacheHarness
    ) -> None:
        await harness.service.lookup(request_for(harness.module, 'provider', None))

        problem = await harness.service.lookup(request_for(harness.module, 'resource', 'aws_nope'))

        assert isinstance(problem, SchemaTypeNotFoundError)
        assert problem.release == ProviderRelease(address=AWS, version='6.69.1')
        assert len(harness.runner.calls) == 1


class TestReportedConditions:
    async def test_missing_lock_file(self, harness: CacheHarness) -> None:
        harness.module.joinpath('.terraform.lock.hcl').unlink()

        problem = await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert isinstance(problem, LockFileMissingError)
        assert harness.runner.calls == []

    async def test_unparseable_lock_file(self, harness: CacheHarness) -> None:
        harness.lock('provider "x" {')

        problem = await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert isinstance(problem, HclSyntaxError)
        assert harness.runner.calls == []

    async def test_provider_absent_from_the_lock_file(self, harness: CacheHarness) -> None:
        harness.lock(lock_text(null='3.3.2'))

        problem = await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert isinstance(problem, ProviderNotLockedError)
        assert problem.address == AWS
        assert harness.runner.calls == []

    async def test_failed_schema_run(self, harness: CacheHarness) -> None:
        stderr = 'Inconsistent dependency lock file\nrun: terraform init'
        harness.runner.script(SCHEMA_ARGV, CommandResult(returncode=1, stdout='', stderr=stderr))

        problem = await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert isinstance(problem, SchemaRunFailedError)
        assert problem.returncode == 1
        assert 'terraform init' in problem.stderr
        assert not harness.cache_dir.exists()

    async def test_missing_terraform_binary(self, harness: CacheHarness) -> None:
        harness.runner.script_missing_binary(SCHEMA_ARGV)

        problem = await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert isinstance(problem, CommandNotFoundError)

    async def test_output_that_is_not_the_expected_json(self, harness: CacheHarness) -> None:
        harness.runner.script(SCHEMA_ARGV, CommandResult(returncode=0, stdout='[1]', stderr=''))

        problem = await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert isinstance(problem, SchemaOutputInvalidError)

    async def test_locked_provider_missing_from_the_output(self, harness: CacheHarness) -> None:
        output = fixture_output()
        del output['provider_schemas'][AWS]
        harness.script_output(output)

        problem = await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert isinstance(problem, ProviderNotInSchemaOutputError)

    async def test_cache_directory_that_cannot_be_written(self, harness: CacheHarness) -> None:
        harness.cache_dir.write_text('a file where the cache directory should be')

        problem = await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert isinstance(problem, SchemaCacheWriteError)


class TestPathGuard:
    @pytest.mark.parametrize('address', ['../x/y', '../../../etc/passwd', f'{AWS}/..', 'a/b'])
    async def test_address_outside_the_form_builds_no_path(
        self, harness: CacheHarness, address: str
    ) -> None:
        request = SchemaRequest(module=harness.module, address=address, kind='provider')

        problem = await harness.service.lookup(request)

        assert isinstance(problem, InvalidProviderAddressError)
        assert harness.runner.calls == []
        assert not harness.cache_dir.exists()

    @pytest.mark.parametrize('type_name', ['../evil', '..', 'a/b', ''])
    async def test_type_name_outside_the_form_builds_no_path(
        self, harness: CacheHarness, type_name: str
    ) -> None:
        problem = await harness.service.lookup(request_for(harness.module, 'resource', type_name))

        assert isinstance(problem, InvalidTypeNameError)
        assert harness.runner.calls == []
        assert not harness.cache_dir.exists()

    async def test_locked_version_outside_the_form_builds_no_path(
        self, harness: CacheHarness
    ) -> None:
        harness.lock(lock_text(aws='../../escape'))

        problem = await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert isinstance(problem, InvalidProviderVersionError)
        assert harness.runner.calls == []
        assert not harness.cache_dir.exists()

    async def test_names_in_terraform_output_outside_the_form_become_no_file(
        self, harness: CacheHarness, tmp_path: Path
    ) -> None:
        output = fixture_output()
        aws = output['provider_schemas'][AWS]
        aws['resource_schemas']['../../../escaped'] = {'version': 0, 'block': {}}
        output['provider_schemas']['../../escaped/host/x'] = aws
        harness.lock(
            lock_text(aws='6.69.1') + 'provider "../../escaped/host/x" {\n  version = "1.0.0"\n}\n'
        )
        harness.script_output(output)

        await harness.service.lookup(request_for(harness.module, 'provider', None))

        assert stored_files(harness.release_dir(AWS, '6.69.1')) == AWS_FILES
        assert not [name for name in stored_files(tmp_path) if 'escaped' in name]


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
