"""Values describing one level of a provider schema as the provider_schema tool returns it."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.provider_schemas.domain import SchemaKind


@dataclass(slots=True, kw_only=True, frozen=True)
class LevelRequest:
    module: Path
    kind: SchemaKind
    type_name: str
    block: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ProviderReference:
    address: str
    constraint: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class BlockSummary:
    name: str
    nesting_mode: str
    min_items: int | None
    max_items: int | None
    attribute_count: int
    block_count: int


@dataclass(slots=True, kw_only=True, frozen=True)
class AttributeEntry:
    name: str
    type: str
    required: bool
    optional: bool
    computed: bool
    sensitive: bool
    deprecated: bool
    description: str | None
    nested: BlockSummary | None


@dataclass(slots=True, kw_only=True, frozen=True)
class SchemaLevel:
    type: str
    kind: SchemaKind
    block: str
    provider: str
    version: str
    constraint: str | None
    attributes: list[AttributeEntry]
    blocks: list[BlockSummary]
