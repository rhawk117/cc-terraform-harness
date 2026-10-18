import shutil
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(shutil.which('uv') is None, reason='uv is not on PATH'),
]

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class TestStdioLaunch:
    async def test_launched_server_lists_tools(self, project_root: Path) -> None:
        launch = StdioServerParameters(
            command='uv',
            args=[
                'run',
                '--project',
                'packages/mcp',
                'tf-harness-mcp',
                '--project-root',
                str(project_root),
            ],
            cwd=REPOSITORY_ROOT,
        )

        async with Client(launch) as client:
            tools = await client.list_tools()

        assert [tool.name for tool in tools.tools] == ['diagnostics', 'plan_digest', 'describe']
