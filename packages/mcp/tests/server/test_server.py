from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.server import SERVER_NAME

if TYPE_CHECKING:
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
