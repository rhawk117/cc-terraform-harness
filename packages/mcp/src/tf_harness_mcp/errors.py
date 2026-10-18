"""Root of the exception hierarchy for the tf-harness MCP server."""


class HarnessError(Exception):
    """Base class for every failure the server raises on purpose."""
