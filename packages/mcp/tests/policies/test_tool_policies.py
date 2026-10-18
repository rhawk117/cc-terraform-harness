from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from tf_harness_mcp.policies import containment
from tf_harness_mcp.policies.containment import PROJECT_PATH_MARKER
from tf_harness_mcp.policies.errors import AbsolutePathError

if TYPE_CHECKING:
    from mcp.types import Tool

pytestmark = pytest.mark.unit

type Schema = dict[str, Any]

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


def list_properties(tool: Tool) -> dict[str, Schema]:
    properties = tool.input_schema.get('properties', {})
    return {
        name: follow_reference(schema, tool.input_schema) for name, schema in properties.items()
    }


def list_project_path_names(tool: Tool) -> list[str]:
    properties = list_properties(tool)
    return [name for name, schema in properties.items() if schema.get(PROJECT_PATH_MARKER)]


def fill_arguments(tool: Tool, path: str) -> dict[str, object]:
    properties = list_properties(tool)
    required = tool.input_schema.get('required', [])
    marked = list_project_path_names(tool)
    samples = {name: SAMPLE_BY_TYPE[properties[name]['type']] for name in required}
    return samples | dict.fromkeys(marked, path)


@dataclass(slots=True, kw_only=True, frozen=True)
class OutsidePath:
    path: str

    @property
    def expected_message(self) -> str:
        return str(AbsolutePathError(path=Path(self.path)))


class TestToolPathContainment:
    @pytest.fixture
    def outside(self, project_root: Path) -> OutsidePath:
        return OutsidePath(path=str(project_root.parent.joinpath('outside-the-root')))

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
        def read_anything(path: containment.ProjectPath) -> str:
            return str(path)

        async with Client(server) as client:
            listed = await client.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            names = {name: list_project_path_names(tool) for name, tool in tools.items()}
            arguments = fill_arguments(tools['read_file'], outside.path)
            refused = await client.call_tool('read_file', arguments)
            accepted = await client.call_tool('read_anything', {'path': outside.path})

        assert names == {'read_file': ['path'], 'read_anything': ['path']}
        assert refused.is_error
        assert not accepted.is_error
