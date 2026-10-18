import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.provider_schemas.domain import SchemaCacheOptions, SchemaRequest
from tf_harness_mcp.provider_schemas.services import SCHEMA_ARGV, create_provider_schema_service
from tf_harness_mcp.runner.domain import CommandResult

if TYPE_CHECKING:
    from tf_harness_mcp.provider_schemas.domain import JsonObject, SchemaKind
    from tf_harness_mcp.provider_schemas.services import ProviderSchemaService
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

FIXTURE = Path(__file__).with_name('schema.json')
AWS = 'registry.terraform.io/hashicorp/aws'
SCHEMA_RESULT = CommandResult(returncode=0, stdout=FIXTURE.read_text(), stderr='')


@dataclass(slots=True, kw_only=True, frozen=True)
class CacheHarness:
    module: Path
    cache_dir: Path
    runner: RecordingCommandRunner
    service: ProviderSchemaService

    def lock(self, text: str) -> None:
        self.module.joinpath('.terraform.lock.hcl').write_text(text)

    def lock_text(self, **versions: str) -> str:
        blocks = [
            f'provider "registry.terraform.io/hashicorp/{name}" {{\n'
            f'  version     = "{version}"\n'
            f'  constraints = ">= 3.0"\n'
            f'  hashes = [\n    "h1:abc=",\n  ]\n}}\n'
            for name, version in versions.items()
        ]
        return '\n'.join(blocks)

    def fixture_output(self) -> JsonObject:
        return json.loads(FIXTURE.read_text())

    def request_for(
        self, kind: SchemaKind, type_name: str | None, module: Path | None = None
    ) -> SchemaRequest:
        return SchemaRequest(
            module=module or self.module, address=AWS, kind=kind, type_name=type_name
        )

    def stored_files(self, directory: Path) -> set[str]:
        paths = (path for path in directory.rglob('*') if path.is_file())
        return {path.relative_to(directory).as_posix() for path in paths}

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
    harness.lock(harness.lock_text(aws='6.69.1', null='3.3.2'))
    recording_runner.script(SCHEMA_ARGV, SCHEMA_RESULT)
    return harness
