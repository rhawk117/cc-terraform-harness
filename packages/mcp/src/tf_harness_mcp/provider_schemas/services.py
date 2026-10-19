"""Looks up one provider schema, filling the cache with one terraform run on a miss."""

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tf_harness_mcp.provider_schemas.domain import LockedSchema, ProviderRelease, StoredSchema
from tf_harness_mcp.provider_schemas.errors import (
    ProviderNotInSchemaOutputError,
    ProviderNotLockedError,
    SchemaOutputInvalidError,
    SchemaRunFailedError,
    SchemaTypeNotFoundError,
)
from tf_harness_mcp.provider_schemas.policy import (
    ProviderAddressPolicy,
    ProviderVersionPolicy,
    SchemaRequestPolicy,
    TypeNamePolicy,
)
from tf_harness_mcp.provider_schemas.repository import lock_file_path, read_lock_file
from tf_harness_mcp.provider_schemas.store import SchemaStore
from tf_harness_mcp.runner.domain import Command

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from tf_harness_mcp.provider_schemas.domain import (
        JsonObject,
        LockedVersions,
        SchemaCacheOptions,
        SchemaKind,
        SchemaRequest,
    )
    from tf_harness_mcp.runner.domain import CommandRunner

SCHEMA_ARGV = ('terraform', 'providers', 'schema', '-json', '-no-color')
STDERR_TAIL_CHARS = 500


def parse_provider_schemas(stdout: str) -> JsonObject | None:
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        return None

    providers = output.get('provider_schemas') if isinstance(output, dict) else None
    if not isinstance(providers, dict):
        return None

    return {address: entry for address, entry in providers.items() if isinstance(entry, dict)}


def select_named_schemas(entry: JsonObject, kind: SchemaKind) -> Iterator[StoredSchema]:
    section = entry.get(f'{kind}_schemas')
    named = section.items() if isinstance(section, dict) else ()
    for type_name, document in named:
        if TypeNamePolicy(type_name=type_name).is_valid and isinstance(document, dict):
            yield StoredSchema(kind=kind, type_name=type_name, document=document)


def select_provider_block(entry: JsonObject) -> list[StoredSchema]:
    provider = entry.get('provider')
    if not isinstance(provider, dict):
        return []

    return [StoredSchema(kind='provider', type_name=None, document=provider)]


def select_provider_schemas(entry: JsonObject) -> list[StoredSchema]:
    return [
        *select_provider_block(entry),
        *select_named_schemas(entry, 'resource'),
        *select_named_schemas(entry, 'data_source'),
    ]


def select_releases(providers: JsonObject, versions: LockedVersions) -> list[ProviderRelease]:
    locked = (
        ProviderRelease(address=address, version=versions[address])
        for address in providers
        if address in versions
    )
    return [
        release
        for release in locked
        if ProviderAddressPolicy(address=release.address).is_valid
        and ProviderVersionPolicy(version=release.version).is_valid
    ]


def read_locked_versions(module: Path) -> LockedVersions:
    locked = read_lock_file(module)
    if locked.problem:
        raise locked.problem

    return locked.versions


def resolve_release(request: SchemaRequest, versions: LockedVersions) -> ProviderRelease:
    version = versions.get(request.address)
    if version is None:
        raise ProviderNotLockedError(address=request.address, path=lock_file_path(request.module))

    if problem := ProviderVersionPolicy(version=version).get_version_problem():
        raise problem

    return ProviderRelease(address=request.address, version=version)


@dataclass(slots=True, kw_only=True, frozen=True)
class ProviderSchemaService:
    runner: CommandRunner
    store: SchemaStore
    timeout_seconds: float

    async def lookup(self, request: SchemaRequest) -> LockedSchema:
        if problem := SchemaRequestPolicy(request=request).get_request_problem():
            raise problem

        versions = read_locked_versions(request.module)
        release = resolve_release(request, versions)
        if not self.store.has_release(release):
            await self.fill(request.module, versions)

        return LockedSchema(release=release, document=self.read(release, request))

    async def fill(self, module: Path, versions: LockedVersions) -> None:
        command = Command(argv=SCHEMA_ARGV, cwd=module)
        result = await self.runner.run(command, self.timeout_seconds)
        if result.returncode != 0:
            stderr = result.stderr.strip()[-STDERR_TAIL_CHARS:]
            raise SchemaRunFailedError(returncode=result.returncode, stderr=stderr)

        providers = parse_provider_schemas(result.stdout)
        if providers is None:
            raise SchemaOutputInvalidError

        self.store_releases(providers, versions)

    def store_releases(self, providers: JsonObject, versions: LockedVersions) -> None:
        releases = select_releases(providers, versions)
        for release in releases:
            if self.store.has_release(release):
                continue

            schemas = select_provider_schemas(providers[release.address])
            if problem := self.store.write_release(release, schemas):
                raise problem

    def read(self, release: ProviderRelease, request: SchemaRequest) -> JsonObject:
        if not self.store.has_release(release):
            raise ProviderNotInSchemaOutputError(address=release.address)

        schema = self.store.read_schema(release, request.kind, request.type_name)
        if schema is None:
            raise SchemaTypeNotFoundError(
                release=release, kind=request.kind, type_name=request.type_name
            )

        return schema


def create_provider_schema_service(
    runner: CommandRunner, options: SchemaCacheOptions
) -> ProviderSchemaService:
    return ProviderSchemaService(
        runner=runner,
        store=SchemaStore(cache_dir=options.cache_dir),
        timeout_seconds=options.timeout_seconds,
    )
