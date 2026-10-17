from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plugin.conftest import PluginInventory


def test_plugin_manifest_version_matches_pyproject(
    pyproject_file: dict[str, Any],
    claude_plugin: PluginInventory,
) -> None:
    claude_plugin_version = claude_plugin.manifest.required_key('version')
    pyproject_version = pyproject_file['project']['version']
    assert pyproject_version == claude_plugin_version, (
        f'The pyproject version ({pyproject_version}) has drifted from the '
        f'plugin manifest version ({claude_plugin_version})'
    )
