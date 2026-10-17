import json
import tomllib
from pathlib import Path


def test_plugin_manifest_version_matches_pyproject(repository_root: Path) -> None:
    pyproject = tomllib.loads((repository_root / 'pyproject.toml').read_text('utf-8'))
    manifest = json.loads((repository_root / '.claude-plugin' / 'plugin.json').read_text('utf-8'))

    assert manifest['version'] == pyproject['project']['version']
