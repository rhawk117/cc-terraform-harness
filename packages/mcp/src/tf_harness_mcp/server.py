"""MCP server factory and stdio entrypoint."""

import os
import sys
from typing import TYPE_CHECKING

from mcp.server.mcpserver import MCPServer

from tf_harness_mcp.settings import load_settings

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from tf_harness_mcp.settings import Settings

SERVER_NAME = 'tf-harness-mcp'


def create_server(settings: Settings) -> MCPServer:
    instructions = f'Terraform harness tools for the project at {settings.project_root}.'
    return MCPServer(SERVER_NAME, instructions=instructions)


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    server = create_server(load_settings(argv, environ))
    server.run('stdio')
    return 0
