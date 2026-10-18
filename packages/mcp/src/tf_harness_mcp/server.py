"""MCP server factory and stdio entrypoint."""

import os
import sys
from typing import TYPE_CHECKING

from mcp.server.mcpserver import MCPServer

from tf_harness_mcp.runner.process import create_command_runner
from tf_harness_mcp.settings import load_settings
from tf_harness_mcp.tools import register_tools

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from tf_harness_mcp.runner.domain import CommandRunner
    from tf_harness_mcp.settings import Settings

SERVER_NAME = 'tf-harness-mcp'


def create_server(settings: Settings, runner: CommandRunner) -> MCPServer:
    instructions = f'Terraform harness tools for the project at {settings.project_root}.'
    server = MCPServer(SERVER_NAME, instructions=instructions)
    register_tools(server, runner, settings)
    return server


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    server = create_server(load_settings(argv, environ), create_command_runner())
    server.run('stdio')
    return 0
