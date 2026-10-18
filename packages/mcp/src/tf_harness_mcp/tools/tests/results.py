from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.types import CallToolResult


def read_tool_text(result: CallToolResult) -> str:
    return ''.join(getattr(block, 'text', '') for block in result.content)
