import os
import tomllib
from pathlib import Path
from typing import Any

import pytest
from hypothesis import settings


def resolve_hypothesis_profile() -> str:
    default_value = 'ci' if os.getenv('CI') == 'true' else 'dev'
    return os.getenv('HYPOTHESIS_PROFILE', default_value)


settings.register_profile('dev', max_examples=50, print_blob=True)
settings.register_profile('ci', parent=settings.get_profile('ci'), max_examples=300)
settings.register_profile('thorough', parent=settings.get_profile('ci'), max_examples=1000)
settings.load_profile(resolve_hypothesis_profile())


@pytest.fixture
def anyio_backend() -> str:
    return 'asyncio'


@pytest.fixture
def isolated_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path.joinpath('home')
    home.mkdir()

    isolated_environment: dict[str, str] = dict.fromkeys(('HOME', 'USERPROFILE'), str(home))
    isolated_environment.update({
        'XDG_CONFIG_HOME': str(home.joinpath('.config')),
        'XDG_CACHE_HOME': str(home.joinpath('.cache')),
        'XDG_DATA_HOME': str(home.joinpath('.local', 'share')),
    })

    for env_var, value in isolated_environment.items():
        monkeypatch.setenv(env_var, value)

    return home


@pytest.fixture
def repository_root() -> Path:
    return Path(__file__).parent.resolve()


@pytest.fixture
def pyproject_file(repository_root: Path) -> dict[str, Any]:
    contents = repository_root.joinpath('pyproject.toml').read_text('utf-8')
    return tomllib.loads(contents)
