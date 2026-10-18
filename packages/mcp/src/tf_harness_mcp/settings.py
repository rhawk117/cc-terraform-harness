"""Settings for the tf-harness MCP server, read from the environment and the command line."""

from typing import TYPE_CHECKING, Annotated, Any, override

from pydantic import DirectoryPath, Field, PositiveFloat, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pydantic_settings import PydanticBaseSettingsSource

ENV_PREFIX = 'TF_HARNESS_'

type OutputBudget = Annotated[int, Field(gt=0, le=65_536)]


def default_output_budget() -> int:
    return 16 * 1024


def default_plan_read_cap() -> int:
    return 50 * 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        cli_parse_args=False,
        cli_kebab_case=True,
        cli_exit_on_error=False,
        frozen=True,
    )

    project_root: DirectoryPath
    validate_timeout_seconds: PositiveFloat = 120.0
    show_timeout_seconds: PositiveFloat = 60.0
    lint_timeout_seconds: PositiveFloat = 120.0
    output_budget_bytes: OutputBudget = Field(default_factory=default_output_budget)
    plan_read_cap_bytes: PositiveInt = Field(default_factory=default_plan_read_cap)

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def read_prefixed_environment(environ: Mapping[str, str]) -> dict[str, str]:
    prefixed = {name: value for name, value in environ.items() if name.startswith(ENV_PREFIX)}
    return {name.removeprefix(ENV_PREFIX).lower(): value for name, value in prefixed.items()}


def load_settings(argv: Sequence[str], environ: Mapping[str, str]) -> Settings:
    from_environment: dict[str, Any] = dict(read_prefixed_environment(environ))
    return Settings(_cli_parse_args=list(argv), **from_environment)
