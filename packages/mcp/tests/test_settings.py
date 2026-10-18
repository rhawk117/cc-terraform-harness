from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from tf_harness_mcp.settings import ENV_PREFIX, load_settings

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit


class TestLoadSettings:
    def test_defaults_budget_and_plan_cap(self, project_root: Path) -> None:
        loaded = load_settings(['--project-root', str(project_root)], {})

        assert loaded.output_budget_bytes == 16 * 1024
        assert loaded.plan_read_cap_bytes == 50 * 1024 * 1024

    def test_reads_values_from_environment(self, project_root: Path) -> None:
        environ = {
            f'{ENV_PREFIX}PROJECT_ROOT': str(project_root),
            f'{ENV_PREFIX}VALIDATE_TIMEOUT_SECONDS': '5',
            f'{ENV_PREFIX}OUTPUT_BUDGET_BYTES': '2048',
        }

        loaded = load_settings([], environ)

        assert loaded.project_root == project_root
        assert loaded.validate_timeout_seconds == 5
        assert loaded.output_budget_bytes == 2048

    def test_command_line_wins_over_environment(self, project_root: Path) -> None:
        environ = {
            f'{ENV_PREFIX}PROJECT_ROOT': str(project_root),
            f'{ENV_PREFIX}SHOW_TIMEOUT_SECONDS': '5',
        }

        loaded = load_settings(['--show-timeout-seconds', '9'], environ)

        assert loaded.show_timeout_seconds == 9

    def test_ignores_unprefixed_environment(self, project_root: Path) -> None:
        loaded = load_settings(['--project-root', str(project_root)], {'SHOW_TIMEOUT_SECONDS': '1'})

        assert loaded.show_timeout_seconds == 60.0

    def test_rejects_output_budget_over_the_hard_maximum(self, project_root: Path) -> None:
        argv = ['--project-root', str(project_root), '--output-budget-bytes', '65537']

        with pytest.raises(ValidationError):
            load_settings(argv, {})

    def test_rejects_missing_project_root(self) -> None:
        with pytest.raises(ValidationError):
            load_settings([], {})

    def test_rejects_project_root_that_is_not_a_directory(self, project_root: Path) -> None:
        missing = project_root.joinpath('absent')

        with pytest.raises(ValidationError):
            load_settings(['--project-root', str(missing)], {})
