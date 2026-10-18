"""Disk cache of provider schemas, one file per block, and the lock file that keys it."""

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from tf_harness_mcp.provider_schemas.errors import LockFileMissingError, SchemaCacheWriteError
from tf_harness_mcp.structure.services import create_block_indexer

if TYPE_CHECKING:
    from collections.abc import Iterable

    from tf_harness_mcp.provider_schemas.domain import (
        JsonObject,
        LockedVersions,
        ProviderRelease,
        SchemaKind,
        StoredSchema,
    )
    from tf_harness_mcp.provider_schemas.errors import LockFileProblem
    from tf_harness_mcp.structure.services import FileIndex

LOCK_FILE_NAME = '.terraform.lock.hcl'
STAGING_PREFIX = '.partial-'
PROVIDER_FILE_NAME = 'provider.json'


def lock_file_path(module: Path) -> Path:
    return module.joinpath(LOCK_FILE_NAME)


def read_provider_versions(index: FileIndex) -> LockedVersions:
    entries = [
        entry for entry in index.entries if entry.block.kind == 'provider' and entry.block.labels
    ]
    versions = {entry.block.labels[0]: entry.get_attribute('version') for entry in entries}
    return {
        address: attribute.string
        for address, attribute in versions.items()
        if attribute and attribute.string is not None
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class LockFileRead:
    versions: LockedVersions
    problem: LockFileProblem | None = None


def read_lock_file(module: Path) -> LockFileRead:
    path = lock_file_path(module)
    if not path.is_file():
        return LockFileRead(versions={}, problem=LockFileMissingError(path=path))

    indexed = create_block_indexer(module).index_file(path)
    if indexed.problem:
        return LockFileRead(versions={}, problem=indexed.problem)

    return LockFileRead(versions=read_provider_versions(indexed))


def schema_relative_path(kind: SchemaKind, type_name: str | None) -> Path:
    if kind == 'provider' or type_name is None:
        return Path(PROVIDER_FILE_NAME)

    return Path(kind, f'{type_name}.json')


@dataclass(slots=True, kw_only=True, frozen=True)
class SchemaStore:
    cache_dir: Path

    def release_dir(self, release: ProviderRelease) -> Path:
        return self.cache_dir.joinpath(*release.address.split('/'), release.version)

    def has_release(self, release: ProviderRelease) -> bool:
        return self.release_dir(release).is_dir()

    def read_schema(
        self, release: ProviderRelease, kind: SchemaKind, type_name: str | None
    ) -> JsonObject | None:
        path = self.release_dir(release).joinpath(schema_relative_path(kind, type_name))
        if not path.is_file():
            return None

        return json.loads(path.read_text())

    def write_release(
        self, release: ProviderRelease, schemas: Iterable[StoredSchema]
    ) -> SchemaCacheWriteError | None:
        target = self.release_dir(release)
        try:
            self.stage_and_publish(target, schemas)
        except OSError:
            return SchemaCacheWriteError(path=target)

        return None

    def stage_and_publish(self, target: Path, schemas: Iterable[StoredSchema]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=self.cache_dir, prefix=STAGING_PREFIX) as staging:
            staged = Path(staging)
            for schema in schemas:
                write_schema(staged, schema)

            publish(staged, target)


def write_schema(directory: Path, schema: StoredSchema) -> None:
    path = directory.joinpath(schema_relative_path(schema.kind, schema.type_name))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema.document))


def publish(staged: Path, target: Path) -> None:
    try:
        staged.rename(target)
    except OSError:
        if not target.is_dir():
            raise
