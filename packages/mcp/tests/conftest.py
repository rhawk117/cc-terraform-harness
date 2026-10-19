from typing import TYPE_CHECKING

import pytest
from mcp import Client
from tf_harness_mcp.server import create_server
from tf_harness_mcp.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from mcp.server.mcpserver import MCPServer
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner


pytest_plugins = [
    'tf_harness_mcp.runner.tests.recording',
    'tf_harness_mcp.tools.diagnostics.tests.scripting',
]


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def schema_cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('schema-cache')


@pytest.fixture
def settings(project_root: Path, schema_cache_dir: Path) -> Settings:
    return Settings(project_root=project_root, schema_cache_dir=schema_cache_dir)


@pytest.fixture
def server(settings: Settings, recording_runner: RecordingCommandRunner) -> MCPServer:
    return create_server(settings, recording_runner)


@pytest.fixture
async def client(server: MCPServer) -> AsyncIterator[Client]:
    async with Client(server) as connected:
        yield connected
