from pathlib import Path

import pytest
from pydantic import ValidationError
from tf_harness_mcp.settings import ENV_PREFIX, Settings, load_settings

pytestmark = pytest.mark.unit


class TestLoadSettings:
    def test_defaults_budget_maximum_and_plan_cap(self, project_root: Path) -> None:
        loaded = load_settings(['--project-root', str(project_root)], {})

        assert loaded.output_budget_bytes == 16 * 1024
        assert loaded.output_budget_max_bytes == 64 * 1024
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

    def test_ignores_unknown_prefixed_environment(self, project_root: Path) -> None:
        environ = {f'{ENV_PREFIX}TYPO': '1', f'{ENV_PREFIX}SHOW_TIMEOUT_SECONDS': '7'}

        loaded = load_settings(['--project-root', str(project_root)], environ)

        assert loaded.show_timeout_seconds == 7

    def test_maximum_is_a_setting_the_budget_is_checked_against(self, project_root: Path) -> None:
        environ = {
            f'{ENV_PREFIX}PROJECT_ROOT': str(project_root),
            f'{ENV_PREFIX}OUTPUT_BUDGET_MAX_BYTES': '100000',
            f'{ENV_PREFIX}OUTPUT_BUDGET_BYTES': '90000',
        }

        loaded = load_settings([], environ)

        assert loaded.output_budget_bytes == 90000

    def test_rejects_output_budget_over_a_lowered_maximum(self, project_root: Path) -> None:
        environ = {
            f'{ENV_PREFIX}PROJECT_ROOT': str(project_root),
            f'{ENV_PREFIX}OUTPUT_BUDGET_MAX_BYTES': '1000',
        }

        with pytest.raises(ValidationError):
            load_settings([], environ)

    def test_rejects_missing_project_root(self) -> None:
        with pytest.raises(ValidationError):
            load_settings([], {})

    def test_rejects_project_root_that_is_not_a_directory(self, project_root: Path) -> None:
        missing = project_root.joinpath('absent')

        with pytest.raises(ValidationError):
            load_settings(['--project-root', str(missing)], {})


class TestSchemaSettings:
    xdg_cache_home = Path('/xdg/cache')
    home = Path('/home/someone')

    def load_cache_dir(self, project_root: Path, environ: dict[str, str], *args: str) -> Path:
        argv = ['--project-root', str(project_root), *args]
        return load_settings(argv, environ).schema_cache_dir

    def test_defaults_schema_timeout(self, project_root: Path) -> None:
        loaded = load_settings(['--project-root', str(project_root)], {})

        assert loaded.schema_timeout_seconds == 60.0

    def test_defaults_under_xdg_cache_home(self, project_root: Path) -> None:
        environ = {'XDG_CACHE_HOME': str(self.xdg_cache_home), 'HOME': str(self.home)}

        cache_dir = self.load_cache_dir(project_root, environ)

        assert cache_dir == self.xdg_cache_home.joinpath('tf-harness', 'provider-schemas')

    @pytest.mark.parametrize('xdg_cache_home', ['', 'relative/cache'])
    def test_defaults_under_home_when_xdg_cache_home_is_empty_or_relative(
        self, project_root: Path, xdg_cache_home: str
    ) -> None:
        environ = {'XDG_CACHE_HOME': xdg_cache_home, 'HOME': str(self.home)}

        cache_dir = self.load_cache_dir(project_root, environ)

        assert cache_dir == self.home.joinpath('.cache', 'tf-harness', 'provider-schemas')

    def test_defaults_under_home_when_xdg_cache_home_is_unset(self, project_root: Path) -> None:
        cache_dir = self.load_cache_dir(project_root, {'HOME': str(self.home)})

        assert cache_dir == self.home.joinpath('.cache', 'tf-harness', 'provider-schemas')

    def test_environment_overrides_the_default(self, project_root: Path) -> None:
        environ = {
            'XDG_CACHE_HOME': str(self.xdg_cache_home),
            f'{ENV_PREFIX}SCHEMA_CACHE_DIR': '/set/by/env',
        }

        assert self.load_cache_dir(project_root, environ) == Path('/set/by/env')

    def test_command_line_overrides_the_environment(self, project_root: Path) -> None:
        environ = {f'{ENV_PREFIX}SCHEMA_CACHE_DIR': '/set/by/env'}

        cache_dir = self.load_cache_dir(project_root, environ, '--schema-cache-dir', '/set/by/cli')

        assert cache_dir == Path('/set/by/cli')

    def test_accepts_a_directory_that_does_not_exist(self, project_root: Path) -> None:
        missing = project_root.joinpath('not', 'yet')

        cache_dir = self.load_cache_dir(project_root, {}, '--schema-cache-dir', str(missing))

        assert cache_dir == missing
        assert not missing.exists()

    def test_settings_built_with_only_project_root_validate(self, project_root: Path) -> None:
        assert Settings(project_root=project_root).schema_cache_dir.is_absolute()
