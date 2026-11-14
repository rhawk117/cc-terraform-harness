import sys
from importlib.metadata import version
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest
from mcp.types import TextContent
from tf_harness_mcp import app
from tf_harness_mcp.app import SERVER_DESCRIPTION, SERVER_NAME, SERVER_TITLE, SERVER_WEBSITE
from tf_harness_mcp.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path

    from mcp import Client
    from mcp.server.mcpserver import MCPServer

pytestmark = pytest.mark.unit


class TestCreateServer:
    input_properties = MappingProxyType({
        'diagnostics': frozenset({'directory'}),
        'plan_digest': frozenset({'path'}),
        'describe': frozenset({'path'}),
        'provider_schema': frozenset({'path', 'type', 'kind', 'block'}),
        'change_impact': frozenset({'path', 'base_ref'}),
    })
    read_only_hints = MappingProxyType({
        'diagnostics': True,
        'plan_digest': True,
        'describe': True,
        'provider_schema': False,
        'change_impact': True,
    })

    async def test_in_process_client_initializes(self, client: Client) -> None:
        tools = await client.list_tools()

        assert {tool.name for tool in tools.tools} == self.input_properties.keys()

    def test_server_is_named_for_the_package(self, server: MCPServer) -> None:
        assert server.name == SERVER_NAME

    async def test_server_reports_its_identity(self, client: Client) -> None:
        info = client.server_info

        assert info is not None
        assert info.name == SERVER_NAME
        assert info.version == version(SERVER_NAME)
        assert (info.title, info.description, info.website_url) == (
            SERVER_TITLE,
            SERVER_DESCRIPTION,
            SERVER_WEBSITE,
        )

    async def test_only_provider_schema_is_declared_as_writing(self, client: Client) -> None:
        tools = await client.list_tools()

        hints = {
            tool.name: tool.annotations and tool.annotations.read_only_hint for tool in tools.tools
        }
        assert hints == self.read_only_hints

    async def test_every_tool_is_titled_and_declared_safe(self, client: Client) -> None:
        tools = await client.list_tools()

        for tool in tools.tools:
            assert tool.title is not None
            assert tool.description is not None
            assert tool.annotations is not None
            assert tool.annotations.destructive_hint is False
            assert tool.annotations.idempotent_hint is True
            assert tool.annotations.open_world_hint is False

    async def test_input_schema_holds_only_the_tool_arguments(self, client: Client) -> None:
        tools = await client.list_tools()

        properties = {tool.name: set(tool.input_schema['properties']) for tool in tools.tools}
        assert properties == self.input_properties


class TestRealLifespan:
    @pytest.fixture
    def server(self, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> MCPServer:
        monkeypatch.setattr(sys, 'argv', [SERVER_NAME, '--project-root', str(project_root)])
        return app.mcp

    async def test_services_load_from_the_command_line(
        self, client: Client, project_root: Path
    ) -> None:
        result = await client.call_tool('describe', {'path': '.'})

        assert not result.is_error
        assert str(project_root) in str(result.structured_content)


class TestRegisterTools:
    @pytest.fixture
    def settings(self, project_root: Path, schema_cache_dir: Path) -> Settings:
        return Settings(
            project_root=project_root,
            schema_cache_dir=schema_cache_dir,
            output_budget_bytes=1,
            output_budget_max_bytes=1,
        )

    async def test_over_budget_result_reaches_the_client_as_an_error(self, client: Client) -> None:
        result = await client.call_tool('describe', {'path': '.'})

        message = result.content[0]
        assert result.is_error
        assert isinstance(message, TextContent)
        assert 'cannot be cut to 1 bytes' in message.text
