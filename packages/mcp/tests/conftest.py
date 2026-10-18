from typing import TYPE_CHECKING

import pytest
from mcp import Client
from tf_harness_mcp.server import create_server
from tf_harness_mcp.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from mcp.server.mcpserver import MCPServer


pytest_plugins = ['tf_harness_mcp.runner.tests.recording']


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def settings(project_root: Path) -> Settings:
    return Settings(project_root=project_root)


@pytest.fixture
def server(settings: Settings) -> MCPServer:
    return create_server(settings)


@pytest.fixture
async def client(server: MCPServer) -> AsyncIterator[Client]:
    async with Client(server) as connected:
        yield connected
