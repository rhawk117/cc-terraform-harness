from typing import TYPE_CHECKING

import pytest
from mcp import Client
from tf_harness_mcp.server import SERVER_NAME, create_server

if TYPE_CHECKING:
    from tf_harness_mcp.settings import Settings

pytestmark = pytest.mark.unit


class TestCreateServer:
    async def test_in_process_client_initializes(self, settings: Settings) -> None:
        async with Client(create_server(settings)) as client:
            tools = await client.list_tools()

        assert tools.tools == []

    def test_server_is_named_for_the_package(self, settings: Settings) -> None:
        assert create_server(settings).name == SERVER_NAME
