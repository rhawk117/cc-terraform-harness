from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mcp import Client
from tf_harness_mcp import app
from tf_harness_mcp.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from mcp.server.mcpserver import MCPServer
    from tf_harness_mcp.runner.domain import CommandRunner
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


@dataclass(slots=True, kw_only=True, frozen=True)
class FixedServices:
    services: app.AppServices

    def load(self) -> app.AppServices:
        return self.services


@pytest.fixture
def command_runner(recording_runner: RecordingCommandRunner) -> CommandRunner:
    return recording_runner


@pytest.fixture
def server(
    settings: Settings, command_runner: CommandRunner, monkeypatch: pytest.MonkeyPatch
) -> MCPServer[app.AppServices]:
    fixed = FixedServices(services=app.create_services(settings, command_runner))
    monkeypatch.setattr(app, 'load_services', fixed.load)
    return app.mcp


@pytest.fixture
async def client(server: MCPServer) -> AsyncIterator[Client]:
    async with Client(server) as connected:
        yield connected
