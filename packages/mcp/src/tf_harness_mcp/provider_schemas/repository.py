"""Reads the provider versions a module's lock file pins."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tf_harness_mcp.provider_schemas.errors import LockFileMissingError
from tf_harness_mcp.structure.services import create_block_indexer

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.provider_schemas.domain import LockedVersions
    from tf_harness_mcp.provider_schemas.errors import LockFileProblem
    from tf_harness_mcp.structure.services import FileIndex

LOCK_FILE_NAME = '.terraform.lock.hcl'


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
