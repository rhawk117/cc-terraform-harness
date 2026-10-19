"""Settings for the tf-harness MCP server, read from the environment and the command line."""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, override

from pydantic import DirectoryPath, Field, PositiveFloat, PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pydantic_settings import PydanticBaseSettingsSource

ENV_PREFIX = 'TF_HARNESS_'


def default_output_budget() -> int:
    return 16 * 1024


def default_output_budget_max() -> int:
    return 64 * 1024


def default_plan_read_cap() -> int:
    return 50 * 1024 * 1024


def derive_schema_cache_dir(environ: Mapping[str, str]) -> Path:
    xdg_cache_home = Path(environ.get('XDG_CACHE_HOME', ''))
    if xdg_cache_home.is_absolute():
        return xdg_cache_home.joinpath('tf-harness', 'provider-schemas')

    home = Path(environ.get('HOME') or Path.home())
    return home.joinpath('.cache', 'tf-harness', 'provider-schemas')


def default_schema_cache_dir() -> Path:
    return derive_schema_cache_dir(os.environ)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        cli_parse_args=False,
        cli_kebab_case=True,
        cli_exit_on_error=False,
        frozen=True,
    )

    project_root: DirectoryPath
    validate_timeout_seconds: PositiveFloat = 120.0
    lint_timeout_seconds: PositiveFloat = 120.0
    schema_timeout_seconds: PositiveFloat = 60.0
    git_timeout_seconds: PositiveFloat = 30.0
    schema_cache_dir: Path = Field(default_factory=default_schema_cache_dir)
    output_budget_bytes: PositiveInt = Field(default_factory=default_output_budget)
    output_budget_max_bytes: PositiveInt = Field(default_factory=default_output_budget_max)
    plan_read_cap_bytes: PositiveInt = Field(default_factory=default_plan_read_cap)

    @model_validator(mode='after')
    def check_output_budget_within_maximum(self) -> Self:
        if self.output_budget_bytes > self.output_budget_max_bytes:
            message = 'output_budget_bytes must not exceed output_budget_max_bytes'
            raise ValueError(message)

        return self

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
    named = {name.removeprefix(ENV_PREFIX).lower(): value for name, value in prefixed.items()}
    return {name: value for name, value in named.items() if name in Settings.model_fields}


def load_settings(argv: Sequence[str], environ: Mapping[str, str]) -> Settings:
    from_environment: dict[str, Any] = {
        'schema_cache_dir': derive_schema_cache_dir(environ),
        **read_prefixed_environment(environ),
    }
    return Settings(_cli_parse_args=list(argv), **from_environment)
