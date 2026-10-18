from typing import TYPE_CHECKING

import pytest
from mcp.types import TextContent
from tf_harness_mcp.server import SERVER_NAME
from tf_harness_mcp.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path

    from mcp import Client
    from mcp.server.mcpserver import MCPServer

pytestmark = pytest.mark.unit


class TestCreateServer:
    async def test_in_process_client_initializes(self, client: Client) -> None:
        tools = await client.list_tools()

        assert [tool.name for tool in tools.tools] == [
            'diagnostics',
            'plan_digest',
            'describe',
            'provider_schema',
            'change_impact',
        ]

    def test_server_is_named_for_the_package(self, server: MCPServer) -> None:
        assert server.name == SERVER_NAME


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
