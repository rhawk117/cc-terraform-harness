"""The MCP tools the server registers."""

from functools import wraps
from typing import TYPE_CHECKING

from mcp.server.mcpserver.exceptions import ToolError

from tf_harness_mcp.errors import HarnessError
from tf_harness_mcp.tools.change_impact.services import create_change_impact_tool
from tf_harness_mcp.tools.describe.services import create_describe_tool
from tf_harness_mcp.tools.diagnostics.services import create_diagnostics_tool
from tf_harness_mcp.tools.plan_digest.services import create_plan_digest_tool
from tf_harness_mcp.tools.provider_schema.services import create_provider_schema_tool

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.mcpserver import MCPServer

    from tf_harness_mcp.runner.domain import CommandRunner
    from tf_harness_mcp.settings import Settings


def translate_harness_errors[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def translated(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except HarnessError as err:
            raise ToolError(str(err)) from err

    return translated


def register_tools(server: MCPServer, runner: CommandRunner, settings: Settings) -> None:
    server.add_tool(translate_harness_errors(create_diagnostics_tool(runner, settings).diagnostics))
    server.add_tool(translate_harness_errors(create_plan_digest_tool(settings).plan_digest))
    server.add_tool(translate_harness_errors(create_describe_tool(settings).describe))
    server.add_tool(
        translate_harness_errors(create_provider_schema_tool(runner, settings).provider_schema)
    )
    server.add_tool(
        translate_harness_errors(create_change_impact_tool(runner, settings).change_impact)
    )
