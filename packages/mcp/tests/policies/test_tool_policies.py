from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from tf_harness_mcp.policies import containment
from tf_harness_mcp.policies.containment import PROJECT_PATH_MARKER
from tf_harness_mcp.policies.errors import PathOutsideRootError

if TYPE_CHECKING:
    from mcp.types import Tool

pytestmark = pytest.mark.unit

type Schema = dict[str, Any]
type PathShape = Literal['single', 'list']

SAMPLE_BY_TYPE: dict[str, object] = {
    'string': 'sample',
    'integer': 1,
    'number': 1,
    'boolean': True,
    'array': [],
    'object': {},
}


def follow_reference(schema: Schema, root: Schema) -> Schema:
    reference = schema.get('$ref')
    if not isinstance(reference, str):
        return schema

    definitions = root.get('$defs')
    assert isinstance(definitions, dict)
    return definitions[reference.removeprefix('#/$defs/')]


def create_path_value(shape: PathShape, path: str) -> object:
    if shape == 'list':
        return [path]

    return path


def find_path_shape(schema: Schema, root: Schema) -> PathShape | None:
    target = follow_reference(schema, root)
    if target.get(PROJECT_PATH_MARKER):
        return 'single'

    items = target.get('items')
    if isinstance(items, dict) and find_path_shape(items, root):
        return 'list'

    branches = [*target.get('anyOf', []), *target.get('oneOf', [])]
    shapes = (find_path_shape(branch, root) for branch in branches)
    return next(filter(None, shapes), None)


def list_properties(tool: Tool) -> dict[str, Schema]:
    return tool.input_schema.get('properties', {})


def list_project_paths(tool: Tool) -> dict[str, PathShape]:
    shapes = {
        name: find_path_shape(schema, tool.input_schema)
        for name, schema in list_properties(tool).items()
    }
    return {name: shape for name, shape in shapes.items() if shape}


def list_project_path_names(tool: Tool) -> list[str]:
    return list(list_project_paths(tool))


def fill_arguments(tool: Tool, path: str) -> dict[str, object]:
    properties = list_properties(tool)
    marked = list_project_paths(tool)
    required = [name for name in tool.input_schema.get('required', []) if name not in marked]
    samples = {name: SAMPLE_BY_TYPE[properties[name]['type']] for name in required}
    return samples | {name: create_path_value(shape, path) for name, shape in marked.items()}


@dataclass(slots=True, kw_only=True, frozen=True)
class OutsidePath:
    path: str
    root: Path

    @property
    def expected_message(self) -> str:
        return str(PathOutsideRootError(path=Path(self.path), root=self.root))


class TestToolPathContainment:
    @pytest.fixture
    def outside(self, project_root: Path) -> OutsidePath:
        outside_path = str(project_root.parent.joinpath('outside-the-root'))
        return OutsidePath(path=outside_path, root=project_root)

    async def assert_refuses_outside_paths(self, client: Client, outside: OutsidePath) -> None:
        listed = await client.list_tools()

        for tool in listed.tools:
            for name in list_project_path_names(tool):
                arguments = fill_arguments(tool, outside.path)
                result = await client.call_tool(tool.name, arguments)
                text = ''.join(getattr(block, 'text', '') for block in result.content)

                assert result.is_error, f'{tool.name} accepted a path outside the root via {name}'
                assert outside.expected_message in text

    async def test_every_registered_tool_refuses_paths_outside_the_root(
        self, client: Client, outside: OutsidePath
    ) -> None:
        await self.assert_refuses_outside_paths(client, outside)

    async def test_the_check_catches_a_tool_that_reads_outside_the_root(
        self, project_root: Path, outside: OutsidePath
    ) -> None:
        server = MCPServer('probe')

        @server.tool()
        def read_file(path: containment.ProjectPath, label: str) -> str:
            return f'{label}:{containment.resolve_project_path(project_root, path)}'

        @server.tool()
        def read_optional(path: containment.ProjectPath | None) -> str:
            return str(path and containment.resolve_project_path(project_root, path))

        @server.tool()
        def read_many(paths: list[containment.ProjectPath]) -> str:
            return str([containment.resolve_project_path(project_root, path) for path in paths])

        @server.tool()
        def read_anything(path: containment.ProjectPath) -> str:
            return str(path)

        @server.tool()
        def read_anything_optional(path: containment.ProjectPath | None) -> str:
            return str(path)

        @server.tool()
        def read_anything_many(paths: list[containment.ProjectPath]) -> str:
            return str(paths)

        async with Client(server) as client:
            listed = await client.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            names = {name: list_project_path_names(tool) for name, tool in tools.items()}
            results = {
                name: await client.call_tool(name, fill_arguments(tool, outside.path))
                for name, tool in tools.items()
            }

        guarded = ['read_file', 'read_optional', 'read_many']
        unguarded = ['read_anything', 'read_anything_optional', 'read_anything_many']
        assert all(names[name] for name in tools)
        assert [name for name in guarded if results[name].is_error] == guarded
        assert [name for name in unguarded if not results[name].is_error] == unguarded
