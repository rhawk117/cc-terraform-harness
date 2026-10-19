from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from tests.conftest import HookHarness


pytestmark = pytest.mark.unit


class TestFilePathGate:
    @pytest.fixture
    def outside_file(self, tmp_path: Path) -> Path:
        outside = tmp_path / 'elsewhere'
        outside.mkdir()
        return outside / 'main.tf'

    @pytest.fixture
    def symlinked_file(self, project_root: Path, outside_file: Path) -> Path:
        link = project_root / 'linked'
        link.symlink_to(outside_file.parent, target_is_directory=True)
        return link / 'main.tf'

    def test_path_outside_root_is_a_silent_no_op_before_any_runner_call(
        self, hook_harness: HookHarness, outside_file: Path
    ) -> None:
        run = hook_harness.run(
            'fmt',
            hook_harness.event(outside_file),
            project_dir=str(hook_harness.project_root),
        )

        assert (run.exit_code, run.stdout, run.stderr) == (0, '', '')
        assert hook_harness.runner.calls == []

    def test_symlink_leaving_root_is_a_silent_no_op_before_any_runner_call(
        self, hook_harness: HookHarness, symlinked_file: Path
    ) -> None:
        run = hook_harness.run(
            'fmt',
            hook_harness.event(symlinked_file),
            project_dir=str(hook_harness.project_root),
        )

        assert (run.exit_code, run.stdout, run.stderr) == (0, '', '')
        assert hook_harness.runner.calls == []

    @pytest.mark.parametrize('name', ['main.py', 'README.md', 'main.tf.bak', 'tf'])
    def test_non_terraform_file_is_a_silent_no_op(
        self, hook_harness: HookHarness, name: str
    ) -> None:
        run = hook_harness.run(
            'fmt',
            hook_harness.event(hook_harness.project_root / name),
            project_dir=str(hook_harness.project_root),
        )

        assert (run.exit_code, run.stdout, run.stderr) == (0, '', '')
        assert hook_harness.runner.calls == []

    def test_unset_project_dir_is_a_silent_no_op(
        self, hook_harness: HookHarness, project_root: Path
    ) -> None:
        run = hook_harness.run(
            'fmt', hook_harness.event(project_root / 'main.tf'), project_dir=None
        )

        assert (run.exit_code, run.stdout, run.stderr) == (0, '', '')
        assert hook_harness.runner.calls == []
