from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

    from plugin.conftest import PluginInventory

TOOL_PREFIX = 'mcp__plugin_terraform-harness_terraform__'
MCP_TOOLS = frozenset({
    'describe',
    'diagnostics',
    'plan_digest',
    'change_impact',
    'provider_schema',
})
SKILLS = frozenset({
    'check-module',
    'explain-plan',
    'review-module',
    'look-up-schema',
    'trace-change-impact',
})
AGENT_MODELS = {
    'terraform-author': 'sonnet',
    'terraform-researcher': 'haiku',
    'terraform-advisor': 'sonnet',
    'terraform-edit-reviewer': 'haiku',
}
AGENT_SKILLS = {
    'terraform-author': ['review-module'],
    'terraform-researcher': [],
    'terraform-advisor': ['review-module', 'explain-plan'],
    'terraform-edit-reviewer': ['review-module'],
}
IGNORED_PLUGIN_KEYS = (
    'hooks',
    'mcpServers',
    'permissionMode',
    'initialPrompt',
    'disable-model-invocation',
    'user-invocable',
)
WRITE_TOOLS = frozenset({'Write', 'Edit'})


def agent_tools(frontmatter: Mapping[str, Any]) -> list[str]:
    raw = frontmatter['tools']
    return [tool.strip() for tool in raw.split(',')] if isinstance(raw, str) else list(raw)


def mcp_tool_names(frontmatter: Mapping[str, Any]) -> list[str]:
    return [tool for tool in agent_tools(frontmatter) if tool.startswith('mcp__')]


def agent_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('agent', AGENT_MODELS)


@pytest.mark.unit
class TestPluginAgents:
    def test_plugin_defines_the_four_terraform_agents(self, claude_plugin: PluginInventory) -> None:
        assert claude_plugin.subagents.agent_names() == set(AGENT_MODELS)

    @agent_cases()
    def test_agent_names_itself_and_says_when_to_use_it(
        self, claude_plugin: PluginInventory, agent: str
    ) -> None:
        frontmatter = claude_plugin.subagents.given_frontmatters()[agent]
        assert frontmatter['name'] == agent
        assert frontmatter['description'].strip()

    @agent_cases()
    def test_agent_runs_on_its_model(self, claude_plugin: PluginInventory, agent: str) -> None:
        frontmatter = claude_plugin.subagents.given_frontmatters()[agent]
        assert frontmatter['model'] == AGENT_MODELS[agent]

    @agent_cases()
    def test_agent_carries_no_key_a_plugin_agent_ignores(
        self, claude_plugin: PluginInventory, agent: str
    ) -> None:
        frontmatter = claude_plugin.subagents.given_frontmatters()[agent]
        assert not set(IGNORED_PLUGIN_KEYS) & set(frontmatter)

    def test_only_terraform_author_can_write_files(self, claude_plugin: PluginInventory) -> None:
        frontmatters = claude_plugin.subagents.given_frontmatters()
        writers = {
            agent
            for agent, frontmatter in frontmatters.items()
            if WRITE_TOOLS & set(agent_tools(frontmatter))
        }
        assert writers == {'terraform-author'}

    @agent_cases()
    def test_agent_mcp_tools_are_terraform_harness_tools(
        self, claude_plugin: PluginInventory, agent: str
    ) -> None:
        frontmatter = claude_plugin.subagents.given_frontmatters()[agent]
        tools = mcp_tool_names(frontmatter)
        assert tools
        assert {tool.removeprefix(TOOL_PREFIX) for tool in tools} <= MCP_TOOLS
        assert all(tool.startswith(TOOL_PREFIX) for tool in tools)

    def test_terraform_author_has_all_five_mcp_tools(self, claude_plugin: PluginInventory) -> None:
        frontmatter = claude_plugin.subagents.given_frontmatters()['terraform-author']
        tools = {tool.removeprefix(TOOL_PREFIX) for tool in mcp_tool_names(frontmatter)}
        assert tools == MCP_TOOLS

    @agent_cases()
    def test_agent_preloads_the_skills_its_body_uses(
        self, claude_plugin: PluginInventory, agent: str
    ) -> None:
        frontmatter = claude_plugin.subagents.given_frontmatters()[agent]
        preloaded = frontmatter.get('skills', [])
        assert preloaded == AGENT_SKILLS[agent]
        assert set(preloaded) <= SKILLS
