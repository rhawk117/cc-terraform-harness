from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

    from plugin.conftest import PluginInventory

TOOL_PREFIX = 'mcp__plugin_terraform-harness_terraform__'
SKILL_TOOLS = {
    'check-module': 'diagnostics',
    'explain-plan': 'plan_digest',
    'review-module': 'describe',
    'look-up-schema': 'provider_schema',
    'onboard-toolchain': 'describe',
    'trace-change-impact': 'change_impact',
    'writing-terraform': 'provider_schema',
}


def allowed_tools(frontmatter: Mapping[str, Any]) -> list[str]:
    raw = frontmatter['allowed-tools']
    return raw.split() if isinstance(raw, str) else list(raw)


@pytest.mark.unit
class TestPluginSkills:
    def test_plugin_defines_the_terraform_skills(self, claude_plugin: PluginInventory) -> None:
        assert claude_plugin.skills.defined_skill_names() == set(SKILL_TOOLS)

    @pytest.mark.parametrize(('skill', 'tool'), SKILL_TOOLS.items())
    def test_skill_allows_its_mcp_tool(
        self, claude_plugin: PluginInventory, skill: str, tool: str
    ) -> None:
        frontmatter = claude_plugin.skills.given_frontmatters()[skill]
        assert TOOL_PREFIX + tool in allowed_tools(frontmatter)

    @pytest.mark.parametrize('skill', SKILL_TOOLS)
    def test_skill_names_itself_and_says_when_to_use_it(
        self, claude_plugin: PluginInventory, skill: str
    ) -> None:
        frontmatter = claude_plugin.skills.given_frontmatters()[skill]
        assert frontmatter['name'] == skill
        assert frontmatter['description'].strip()
