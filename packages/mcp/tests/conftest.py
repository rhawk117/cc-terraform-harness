from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def settings(project_root: Path) -> Settings:
    return Settings(project_root=project_root)
