import shutil
from typing import TYPE_CHECKING

import pytest
from tf_harness_hooks.domain import HookRequest
from tf_harness_hooks.fmt import format_file
from tf_harness_hooks.policy import runner_options
from tf_harness_mcp.runner.process import create_command_runner

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which('terraform') is None, reason='terraform is not installed'),
]


class TestRealTerraformFmt:
    unformatted = 'variable   "name" {\ntype=string\n}\n'
    formatted = 'variable "name" {\n  type = string\n}\n'

    def request(self, project_root: Path, name: str) -> HookRequest:
        return HookRequest(
            event_name='PostToolUse',
            project_root=project_root,
            runner=create_command_runner(options=runner_options('fmt')),
            file_path=project_root / name,
        )

    async def test_badly_formatted_file_is_rewritten(self, project_root: Path) -> None:
        target = project_root / 'main.tf'
        target.write_text(self.unformatted)

        output = await format_file(self.request(project_root, 'main.tf'))

        assert target.read_text() == self.formatted
        assert output is not None
        assert output.additional_context == f'terraform fmt rewrote {target}'

    async def test_formatted_file_gives_no_output(self, project_root: Path) -> None:
        (project_root / 'main.tf').write_text(self.formatted)

        assert await format_file(self.request(project_root, 'main.tf')) is None

    async def test_parse_error_is_reported(self, project_root: Path) -> None:
        (project_root / 'main.tf').write_text('variable "name" {\n')

        output = await format_file(self.request(project_root, 'main.tf'))

        assert output is not None
        assert output.additional_context.startswith('Error:')
