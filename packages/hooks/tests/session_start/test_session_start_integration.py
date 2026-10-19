import shutil
from typing import TYPE_CHECKING

import pytest
from tf_harness_hooks.domain import HookRequest
from tf_harness_hooks.policy import runner_options
from tf_harness_hooks.session_start import report_tool_versions
from tf_harness_mcp.runner.process import create_command_runner

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


async def report_lines(project_root: Path) -> list[str]:
    request = HookRequest(
        event_name='SessionStart',
        project_root=project_root,
        runner=create_command_runner(options=runner_options('session-start')),
    )
    output = await report_tool_versions(request)
    assert output is not None
    return output.additional_context.splitlines()


class TestRealVersions:
    @pytest.mark.skipif(shutil.which('terraform') is None, reason='terraform is not installed')
    async def test_terraform_reports_a_version(self, project_root: Path) -> None:
        line = (await report_lines(project_root))[0]

        assert line.startswith('terraform: ')
        assert line.removeprefix('terraform: ')[0].isdigit()

    @pytest.mark.skipif(shutil.which('tflint') is None, reason='tflint is not installed')
    async def test_tflint_reports_a_version(self, project_root: Path) -> None:
        line = (await report_lines(project_root))[1]

        assert line.startswith('tflint: ')
        assert line.removeprefix('tflint: ')[0].isdigit()

    @pytest.mark.skipif(
        shutil.which('terraform-ls') is None, reason='terraform-ls is not installed'
    )
    async def test_terraform_ls_reports_a_version(self, project_root: Path) -> None:
        line = (await report_lines(project_root))[2]

        assert line.startswith('terraform-ls: ')
        assert line.removeprefix('terraform-ls: ')[0].isdigit()
