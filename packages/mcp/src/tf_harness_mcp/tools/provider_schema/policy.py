"""Rules that turn a type name and a declared source into a provider address and a block path."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tf_harness_mcp.tools.provider_schema.errors import InvalidBlockPathError

if TYPE_CHECKING:
    from tf_harness_mcp.provider_schemas.domain import SchemaKind

REGISTRY_HOST = 'registry.terraform.io'
DEFAULT_NAMESPACE = 'hashicorp'
HOSTED_SOURCE_PARTS = 3
SEGMENT_FORM = re.compile(r'[A-Za-z0-9_-]+', re.ASCII)


@dataclass(slots=True, kw_only=True, frozen=True)
class ProviderTypePolicy:
    kind: SchemaKind
    type_name: str

    @property
    def local_name(self) -> str:
        if self.kind == 'provider':
            return self.type_name

        return self.type_name.partition('_')[0]


@dataclass(slots=True, kw_only=True, frozen=True)
class ProviderSourcePolicy:
    local_name: str
    source: str | None

    @property
    def parts(self) -> list[str]:
        return (self.source or '').lower().split('/')

    @property
    def address(self) -> str:
        if self.source is None:
            return f'{REGISTRY_HOST}/{DEFAULT_NAMESPACE}/{self.local_name}'

        if len(self.parts) == HOSTED_SOURCE_PARTS:
            return '/'.join(self.parts)

        return '/'.join((REGISTRY_HOST, *self.parts))


@dataclass(slots=True, kw_only=True, frozen=True)
class BlockPathPolicy:
    block: str

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(self.block.split('.')) if self.block else ()

    @property
    def is_valid(self) -> bool:
        return all(SEGMENT_FORM.fullmatch(segment) for segment in self.segments)

    def get_block_path_problem(self) -> InvalidBlockPathError | None:
        if not self.is_valid:
            return InvalidBlockPathError(block=self.block)

        return None
