from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from tf_harness_mcp.errors import HarnessError
from tf_harness_mcp.policies import containment
from tf_harness_mcp.policies.containment import PROJECT_PATH_MARKER
from tf_harness_mcp.policies.errors import PathOutsideRootError
from tf_harness_mcp.tools.tests.results import read_tool_text

if TYPE_CHECKING:
    from mcp.types import Tool
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

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
    'null': None,
}


def follow_reference(schema: Schema, root: Schema) -> Schema:
    reference = schema.get('$ref')
    if not isinstance(reference, str):
        return schema

    definitions = root.get('$defs')
    assert isinstance(definitions, dict)
    return definitions[reference.removeprefix('#/$defs/')]


def sample_value(schema: Schema, root: Schema) -> object:
    target = follow_reference(schema, root)
    if 'enum' in target:
        return target['enum'][0]

    branches = [*target.get('anyOf', []), *target.get('oneOf', [])]
    if branches:
        return sample_value(branches[0], root)

    return SAMPLE_BY_TYPE[target['type']]


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
    samples = {name: sample_value(properties[name], tool.input_schema) for name in required}
    return samples | {name: create_path_value(shape, path) for name, shape in marked.items()}


@dataclass(slots=True, kw_only=True, frozen=True)
class OutsidePath:
    path: str
    root: Path

    @property
    def expected_message(self) -> str:
        return str(PathOutsideRootError(path=Path(self.path), root=self.root))


class Kind(StrEnum):
    RESOURCE = auto()
    DATA = auto()


@pytest.fixture
def outside(project_root: Path) -> OutsidePath:
    outside_path = str(project_root.parent.joinpath('outside-the-root'))
    return OutsidePath(path=outside_path, root=project_root)


async def assert_refuses_outside_paths(client: Client, outside: OutsidePath) -> None:
    listed = await client.list_tools()

    for tool in listed.tools:
        for name in list_project_path_names(tool):
            arguments = fill_arguments(tool, outside.path)
            result = await client.call_tool(tool.name, arguments)
            text = read_tool_text(result)

            assert result.is_error, f'{tool.name} accepted a path outside the root via {name}'
            assert outside.expected_message in text, f'{tool.name} failed before containment'


class TestToolPathContainment:
    async def test_every_registered_tool_refuses_paths_outside_the_root(
        self, client: Client, outside: OutsidePath, recording_runner: RecordingCommandRunner
    ) -> None:
        await assert_refuses_outside_paths(client, outside)

        assert not recording_runner.calls


class TestContainmentCheckProbes:
    @pytest.fixture
    def guarded_server(self, project_root: Path) -> MCPServer:
        def resolve(path: Path) -> Path:
            try:
                return containment.resolve_project_path(project_root, path)
            except HarnessError as err:
                raise ToolError(str(err)) from err

        def read_file(
            path: containment.ProjectPath,
            label: str,
            mode: Literal['resource', 'data'],
            kind: Kind,
            limit: int | str,
            cursor: int | None,
        ) -> str:
            return f'{label}{mode}{kind}{limit}{cursor}:{resolve(path)}'

        def read_optional(path: containment.ProjectPath | None) -> str:
            return str(path and resolve(path))

        def read_many(paths: list[containment.ProjectPath]) -> str:
            return str([resolve(path) for path in paths])

        server = MCPServer('guarded')
        for tool in (read_file, read_optional, read_many):
            server.add_tool(tool)
        return server

    @pytest.fixture(params=['read_anything', 'read_anything_optional', 'read_anything_many'])
    def unguarded_server(self, request: pytest.FixtureRequest) -> MCPServer:
        def read_anything(path: containment.ProjectPath) -> str:
            return str(path)

        def read_anything_optional(path: containment.ProjectPath | None) -> str:
            return str(path)

        def read_anything_many(paths: list[containment.ProjectPath]) -> str:
            return str(paths)

        tools = {
            fn.__name__: fn for fn in (read_anything, read_anything_optional, read_anything_many)
        }
        server = MCPServer('unguarded')
        server.add_tool(tools[request.param])
        return server

    async def test_the_check_passes_guarded_tools_with_enum_ref_and_union_arguments(
        self, guarded_server: MCPServer, outside: OutsidePath
    ) -> None:
        async with Client(guarded_server) as client:
            await assert_refuses_outside_paths(client, outside)

            listed = await client.list_tools()

        assert [tool.name for tool in listed.tools if list_project_path_names(tool)] == [
            'read_file',
            'read_optional',
            'read_many',
        ]

    async def test_the_check_fails_on_each_unguarded_tool(
        self, unguarded_server: MCPServer, outside: OutsidePath
    ) -> None:
        async with Client(unguarded_server) as client:
            with pytest.raises(AssertionError, match='accepted a path outside the root'):
                await assert_refuses_outside_paths(client, outside)
