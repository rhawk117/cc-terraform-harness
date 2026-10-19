from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from plugin.conftest import PluginInventory


class TestPluginManifest:
    expected_mcp_args = (
        'run',
        '--project',
        '${CLAUDE_PLUGIN_ROOT}/packages/mcp',
        'tf-harness-mcp',
        '--project-root',
        '${CLAUDE_PROJECT_DIR}',
    )

    @pytest.fixture
    def mcp_server(self, claude_plugin: PluginInventory) -> dict[str, Any]:
        return claude_plugin.mcp.required_key('mcpServers')['terraform']

    @pytest.fixture
    def lsp_server(self, claude_plugin: PluginInventory) -> dict[str, Any]:
        return claude_plugin.lsp.required_key('terraform')

    def test_mcp_server_runs_the_package_through_uv(self, mcp_server: dict[str, Any]) -> None:
        assert mcp_server['command'] == 'uv'
        assert tuple(mcp_server['args']) == self.expected_mcp_args

    def test_mcp_server_environment_lives_under_plugin_data(
        self, mcp_server: dict[str, Any]
    ) -> None:
        environment = mcp_server['env']['UV_PROJECT_ENVIRONMENT']
        assert environment.startswith('${CLAUDE_PLUGIN_DATA}/')

    def test_lsp_server_serves_terraform_files(self, lsp_server: dict[str, Any]) -> None:
        assert lsp_server['command'] == 'terraform-ls'
        assert lsp_server['args'] == ['serve']
        assert lsp_server['extensionToLanguage'] == {
            '.tf': 'terraform',
            '.tfvars': 'terraform-vars',
        }

    def test_manifest_declares_no_inline_servers(self, claude_plugin: PluginInventory) -> None:
        assert 'mcpServers' not in claude_plugin.manifest.contents
        assert 'lspServers' not in claude_plugin.manifest.contents
