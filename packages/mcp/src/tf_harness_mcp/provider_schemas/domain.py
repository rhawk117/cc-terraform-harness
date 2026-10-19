"""Values describing a schema request, a locked provider release and the cache options."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Self

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.settings import Settings

type SchemaKind = Literal['resource', 'data_source', 'provider']
type JsonObject = dict[str, Any]
type LockedVersions = dict[str, str]


@dataclass(slots=True, kw_only=True, frozen=True)
class SchemaRequest:
    module: Path
    address: str
    kind: SchemaKind
    type_name: str | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class ProviderRelease:
    address: str
    version: str


@dataclass(slots=True, kw_only=True, frozen=True)
class LockedSchema:
    release: ProviderRelease
    document: JsonObject


@dataclass(slots=True, kw_only=True, frozen=True)
class StoredSchema:
    kind: SchemaKind
    type_name: str | None
    document: JsonObject


@dataclass(slots=True, kw_only=True, frozen=True)
class SchemaCacheOptions:
    cache_dir: Path
    timeout_seconds: float

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            cache_dir=settings.schema_cache_dir,
            timeout_seconds=settings.schema_timeout_seconds,
        )
