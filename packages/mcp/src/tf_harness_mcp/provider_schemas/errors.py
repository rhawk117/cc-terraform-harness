"""Problems the provider schema layer reports as values instead of raising."""

from typing import TYPE_CHECKING

from tf_harness_mcp.errors import HarnessError
from tf_harness_mcp.runner.errors import CommandNotFoundError, CommandTimeoutError
from tf_harness_mcp.structure.errors import FileProblem

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.provider_schemas.domain import ProviderRelease, SchemaKind


class InvalidProviderAddressError(HarnessError):
    def __init__(self, *, address: str) -> None:
        self.address = address
        super().__init__(f'provider address is not hostname/namespace/type: {address!r}')


class InvalidProviderVersionError(HarnessError):
    def __init__(self, *, version: str) -> None:
        self.version = version
        super().__init__(f'provider version is not a release version: {version!r}')


class InvalidTypeNameError(HarnessError):
    def __init__(self, *, kind: SchemaKind, type_name: str | None) -> None:
        self.kind = kind
        self.type_name = type_name
        super().__init__(f'type name {type_name!r} is not valid for a {kind} schema')


class LockFileMissingError(HarnessError):
    def __init__(self, *, path: Path) -> None:
        self.path = path
        super().__init__(f'{path} is missing; run terraform init in the module')


class ProviderNotLockedError(HarnessError):
    def __init__(self, *, address: str, path: Path) -> None:
        self.address = address
        self.path = path
        super().__init__(f'{address} has no entry in {path}')


class SchemaRunFailedError(HarnessError):
    def __init__(self, *, returncode: int, stderr: str) -> None:
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f'terraform providers schema exited {returncode}: {stderr}')


class SchemaOutputInvalidError(HarnessError):
    def __init__(self) -> None:
        super().__init__('terraform providers schema did not print the expected JSON')


class ProviderNotInSchemaOutputError(HarnessError):
    def __init__(self, *, address: str) -> None:
        self.address = address
        super().__init__(f'terraform providers schema printed no schema for {address}')


class SchemaTypeNotFoundError(HarnessError):
    def __init__(
        self, *, release: ProviderRelease, kind: SchemaKind, type_name: str | None
    ) -> None:
        self.release = release
        self.kind = kind
        self.type_name = type_name
        super().__init__(
            f'{release.address} {release.version} has no {kind} schema named {type_name}'
        )


class SchemaCacheWriteError(HarnessError):
    def __init__(self, *, path: Path) -> None:
        self.path = path
        super().__init__(f'the schema cache could not write {path}')


type LockFileProblem = FileProblem | LockFileMissingError

type SchemaProblem = (
    InvalidProviderAddressError
    | InvalidProviderVersionError
    | InvalidTypeNameError
    | LockFileProblem
    | ProviderNotLockedError
    | SchemaRunFailedError
    | SchemaOutputInvalidError
    | ProviderNotInSchemaOutputError
    | SchemaTypeNotFoundError
    | SchemaCacheWriteError
    | CommandNotFoundError
    | CommandTimeoutError
)
