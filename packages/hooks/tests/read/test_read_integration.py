import shutil
from typing import TYPE_CHECKING

import pytest
from tf_harness_hooks.domain import HookRequest
from tf_harness_hooks.policy import runner_options
from tf_harness_hooks.read import report_file_findings
from tf_harness_mcp.runner.process import create_command_runner

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which('terraform') is None, reason='terraform is not installed'),
    pytest.mark.skipif(shutil.which('tflint') is None, reason='tflint is not installed'),
]


class TestRealReadChecks:
    broken = 'output "value" {\n  value = var.undeclared\n}\n'
    plugin_config = (
        'plugin "aws" {\n  enabled = true\n  version = "0.1.0"\n'
        '  source = "github.com/terraform-linters/tflint-ruleset-aws"\n}\n'
    )

    async def read(self, project_root: Path, name: str) -> str | None:
        request = HookRequest(
            event_name='PostToolUse',
            project_root=project_root,
            runner=create_command_runner(options=runner_options('read')),
            file_path=project_root / name,
        )
        output = await report_file_findings(request)
        return None if output is None else output.additional_context

    async def test_validate_error_in_the_read_file_is_reported(self, project_root: Path) -> None:
        (project_root / '.terraform').mkdir()
        (project_root / 'main.tf').write_text(self.broken)
        (project_root / 'other.tf').write_text('output "other" {\n  value = var.missing\n}\n')

        context = await self.read(project_root, 'main.tf')

        assert context is not None
        assert 'terraform validate:\n2: error Reference to undeclared input variable' in context
        assert 'missing' not in context

    async def test_clean_initialized_module_gives_no_output(self, project_root: Path) -> None:
        (project_root / '.terraform').mkdir()
        (project_root / 'main.tf').write_text(
            'terraform {\n  required_version = ">= 1.5"\n}\n\n'
            'variable "x" {\n  type = string\n}\n\n'
            'output "x" {\n  value = var.x\n}\n'
        )

        assert await self.read(project_root, 'main.tf') is None

    async def test_module_without_terraform_directory_asks_for_init(
        self, project_root: Path
    ) -> None:
        (project_root / 'main.tf').write_text(self.broken)

        context = await self.read(project_root, 'main.tf')

        assert context is not None
        assert context.startswith('terraform validate did not run: run terraform init in ')
        assert 'Reference to undeclared' not in context

    async def test_uninstalled_plugin_gives_the_tflint_init_hint(self, project_root: Path) -> None:
        (project_root / '.terraform').mkdir()
        (project_root / 'main.tf').write_text('variable "x" {\n  type = string\n}\n')
        (project_root / '.tflint.hcl').write_text(self.plugin_config)

        context = await self.read(project_root, 'main.tf')

        assert context == f'tflint plugins are missing: run tflint --init in {project_root}'
