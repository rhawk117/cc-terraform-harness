"""The MCP tools the server registers."""

from typing import TYPE_CHECKING

from tf_harness_mcp.tools.diagnostics.services import create_diagnostics_tool
from tf_harness_mcp.tools.plan_digest.services import create_plan_digest_tool

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from tf_harness_mcp.runner.domain import CommandRunner
    from tf_harness_mcp.settings import Settings


def register_tools(server: MCPServer, runner: CommandRunner, settings: Settings) -> None:
    server.add_tool(create_diagnostics_tool(runner, settings).diagnostics)
    server.add_tool(create_plan_digest_tool(settings).plan_digest)
