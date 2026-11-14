"""Stdio entrypoint for the tf-harness MCP server."""

from tf_harness_mcp.app import mcp


def main() -> int:
    mcp.run('stdio')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
