"""Return one level of a cached provider schema, resolving the provider from the module."""

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver.exceptions import ToolError

from tf_harness_mcp.errors import HarnessError
from tf_harness_mcp.policies import containment
from tf_harness_mcp.policies.budget import create_output_budget
from tf_harness_mcp.provider_schemas.domain import (  # noqa: TC001 - the MCP SDK evaluates the tool annotations
    LockedSchema,
    SchemaCacheOptions,
    SchemaKind,
    SchemaRequest,
)
from tf_harness_mcp.provider_schemas.services import create_provider_schema_service
from tf_harness_mcp.structure.services import create_block_indexer
from tf_harness_mcp.tools.provider_schema.domain import (
    AttributeEntry,
    BlockSummary,
    LevelRequest,
    ProviderReference,
    SchemaLevel,
)
from tf_harness_mcp.tools.provider_schema.errors import BlockPathNotFoundError
from tf_harness_mcp.tools.provider_schema.policy import (
    BlockPathPolicy,
    ProviderSourcePolicy,
    ProviderTypePolicy,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.policies.budget import OutputBudget
    from tf_harness_mcp.provider_schemas.domain import JsonObject
    from tf_harness_mcp.provider_schemas.services import ProviderSchemaService
    from tf_harness_mcp.runner.domain import CommandRunner
    from tf_harness_mcp.settings import Settings
    from tf_harness_mcp.structure.domain import RequiredProvider
    from tf_harness_mcp.structure.services import BlockIndexer

type RequiredProviders = dict[str, RequiredProvider]


def render_member(name: str, cty: Any, optional_names: set[str]) -> str:
    rendered = render_type(cty)
    return f'{name} = optional({rendered})' if name in optional_names else f'{name} = {rendered}'


def render_object(fields: dict[str, Any], optional_names: set[str]) -> str:
    members = (render_member(name, cty, optional_names) for name, cty in fields.items())
    return f'object({{{", ".join(members)}}})'


def render_type(cty: Any) -> str:
    if isinstance(cty, str):
        return 'any' if cty == 'dynamic' else cty

    constructor, argument, *rest = cty
    if constructor == 'object':
        return render_object(argument, set(rest[0]) if rest else set())

    if constructor == 'tuple':
        return f'tuple([{", ".join(map(render_type, argument))}])'

    return f'{constructor}({render_type(argument)})'


def render_nested_type(nested: JsonObject) -> str:
    mode = nested.get('nesting_mode', 'single')
    return 'object' if mode == 'single' else f'{mode}(object)'


def summarize_nested_type(name: str, nested: JsonObject) -> BlockSummary:
    return BlockSummary(
        name=name,
        nesting_mode=nested.get('nesting_mode', 'single'),
        min_items=nested.get('min_items'),
        max_items=nested.get('max_items'),
        attribute_count=len(nested.get('attributes', {})),
        block_count=0,
    )


def summarize_block_type(name: str, block_type: JsonObject) -> BlockSummary:
    block = block_type['block']
    return BlockSummary(
        name=name,
        nesting_mode=block_type['nesting_mode'],
        min_items=block_type.get('min_items'),
        max_items=block_type.get('max_items'),
        attribute_count=len(block.get('attributes', {})),
        block_count=len(block.get('block_types', {})),
    )


def make_attribute(name: str, attribute: JsonObject) -> AttributeEntry:
    nested = attribute.get('nested_type')
    return AttributeEntry(
        name=name,
        type=render_nested_type(nested) if nested else render_type(attribute['type']),
        required=attribute.get('required', False),
        optional=attribute.get('optional', False),
        computed=attribute.get('computed', False),
        sensitive=attribute.get('sensitive', False),
        deprecated=attribute.get('deprecated', False),
        description=attribute.get('description'),
        nested=summarize_nested_type(name, nested) if nested else None,
    )


def descend(level: JsonObject, segment: str) -> JsonObject | None:
    block_type = level.get('block_types', {}).get(segment)
    if block_type:
        return block_type['block']

    return level.get('attributes', {}).get(segment, {}).get('nested_type')


def find_level(level: JsonObject, segments: tuple[str, ...]) -> JsonObject | None:
    if not segments:
        return level

    child = descend(level, segments[0])
    if child is None:
        return None

    return find_level(child, segments[1:])


def read_file_providers(indexer: BlockIndexer, path: Path) -> list[RequiredProvider]:
    index = indexer.index_file(path)
    return [provider for entry in index.entries for provider in entry.required_providers]


def read_declared_providers(indexer: BlockIndexer, module: Path) -> RequiredProviders:
    files = indexer.select_files(module)
    return {
        provider.local_name: provider
        for path in files
        for provider in read_file_providers(indexer, path)
    }


def read_attributes(level: JsonObject) -> list[AttributeEntry]:
    return [
        make_attribute(name, attribute) for name, attribute in level.get('attributes', {}).items()
    ]


def read_blocks(level: JsonObject) -> list[BlockSummary]:
    return [
        summarize_block_type(name, block_type)
        for name, block_type in level.get('block_types', {}).items()
    ]


def create_schema_level(
    request: LevelRequest, provider: ProviderReference, locked_level: LockedSchema
) -> SchemaLevel:
    level = locked_level.document
    return SchemaLevel(
        type=request.type_name,
        kind=request.kind,
        block=request.block,
        provider=provider.address,
        version=locked_level.release.version,
        constraint=provider.constraint,
        attributes=read_attributes(level),
        blocks=read_blocks(level),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ProviderSchemaTool:
    root: Path
    budget: OutputBudget
    indexer: BlockIndexer
    service: ProviderSchemaService

    def resolve_provider(self, request: LevelRequest) -> ProviderReference:
        policy = ProviderTypePolicy(kind=request.kind, type_name=request.type_name)
        declared = read_declared_providers(self.indexer, request.module).get(policy.local_name)
        source = ProviderSourcePolicy(
            local_name=policy.local_name, source=declared.source if declared else None
        )
        return ProviderReference(
            address=source.address, constraint=declared.version if declared else None
        )

    async def lookup_schema(
        self, request: LevelRequest, provider: ProviderReference
    ) -> LockedSchema:
        type_name = None if request.kind == 'provider' else request.type_name
        return await self.service.lookup(
            SchemaRequest(
                module=request.module,
                address=provider.address,
                kind=request.kind,
                type_name=type_name,
            )
        )

    async def read_level(self, request: LevelRequest) -> SchemaLevel:
        policy = BlockPathPolicy(block=request.block)
        if problem := policy.get_block_path_problem():
            raise problem

        provider = self.resolve_provider(request)
        locked = await self.lookup_schema(request, provider)
        level = find_level(locked.document['block'], policy.segments)
        if level is None:
            raise BlockPathNotFoundError(type_name=request.type_name, block=request.block)

        return create_schema_level(
            request, provider, LockedSchema(release=locked.release, document=level)
        )

    async def provider_schema(  # noqa: PLR0913, PLR0917 - the MCP tool arguments are its schema
        self,
        path: containment.ProjectPath,
        type: str,  # noqa: A002 - the MCP tool argument is named type
        kind: SchemaKind,
        block: str = '',
    ) -> dict[str, Any]:
        """Read one level of a provider, resource or data source schema without changing anything.

        Give the module directory, the type (a resource or data source type such as aws_instance,
        or the provider's local name such as aws when kind is provider) and the kind (resource,
        data_source or provider). The provider comes from the module's required_providers, or is
        hashicorp/<prefix> when undeclared. Returns the locked provider version beside the
        configuration's version constraint, the level's attributes (type, required, optional,
        computed, sensitive, deprecated, description) and one summary per nested block (nesting
        mode, min and max items, attribute and block counts). Pass block as a dotted path such
        as ebs_block_device or a.b to read a nested block or nested attribute instead of the top
        level. Needs the module initialized, with a .terraform.lock.hcl entry for the provider.
        The path is relative to the project root or absolute inside it.
        """
        try:
            module = containment.resolve_project_path(self.root, path)
        except HarnessError as err:
            raise ToolError(str(err)) from err

        try:
            result = await self.read_level(
                LevelRequest(module=module, kind=kind, type_name=type, block=block)
            )
        except HarnessError as err:
            raise ToolError(str(err)) from err

        return self.budget.apply(asdict(result))


def create_provider_schema_tool(runner: CommandRunner, settings: Settings) -> ProviderSchemaTool:
    options = SchemaCacheOptions.from_settings(settings)
    return ProviderSchemaTool(
        root=settings.project_root,
        budget=create_output_budget(settings),
        indexer=create_block_indexer(settings.project_root),
        service=create_provider_schema_service(runner, options),
    )
