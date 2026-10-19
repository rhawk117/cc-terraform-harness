from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from plugin.conftest import PluginInventory

COMMAND_PREFIX = (
    'UV_PROJECT_ENVIRONMENT="${CLAUDE_PLUGIN_DATA}/hooks-venv" '
    'uv run --project "${CLAUDE_PLUGIN_ROOT}/packages/hooks" tf-harness-hooks '
)


@dataclass(slots=True, kw_only=True, frozen=True)
class HookRegistration:
    event: str
    matcher: str
    subcommand: str
    timeout: int

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.subcommand)


def hook_registration_cases() -> pytest.MarkDecorator:
    fmt = HookRegistration(event='PostToolUse', matcher='Write|Edit', subcommand='fmt', timeout=30)
    read = HookRegistration(event='PostToolUse', matcher='Read', subcommand='read', timeout=90)
    session_start = HookRegistration(
        event='SessionStart',
        matcher='startup|clear|compact',
        subcommand='session-start',
        timeout=45,
    )
    return pytest.mark.parametrize('registration', [fmt.param, read.param, session_start.param])


@pytest.mark.unit
class TestPluginHooks:
    @pytest.fixture
    def hook_events(self, claude_plugin: PluginInventory) -> dict[str, list[dict[str, Any]]]:
        return claude_plugin.hooks.required_key('hooks')

    def find_commands(
        self, hook_events: dict[str, list[dict[str, Any]]], registration: HookRegistration
    ) -> list[dict[str, Any]]:
        groups = hook_events[registration.event]
        matching = [group for group in groups if group['matcher'] == registration.matcher]
        return [hook for group in matching for hook in group['hooks']]

    @hook_registration_cases()
    def test_registration_runs_its_subcommand_through_uv(
        self, hook_events: dict[str, list[dict[str, Any]]], registration: HookRegistration
    ) -> None:
        commands = self.find_commands(hook_events, registration)
        assert [hook['type'] for hook in commands] == ['command']
        assert commands[0]['command'] == COMMAND_PREFIX + registration.subcommand

    @hook_registration_cases()
    def test_registration_sets_its_timeout(
        self, hook_events: dict[str, list[dict[str, Any]]], registration: HookRegistration
    ) -> None:
        commands = self.find_commands(hook_events, registration)
        assert commands[0]['timeout'] == registration.timeout

    def test_plugin_registers_only_the_three_hooks(
        self, hook_events: dict[str, list[dict[str, Any]]]
    ) -> None:
        registered = [
            hook for groups in hook_events.values() for group in groups for hook in group['hooks']
        ]
        assert len(registered) == 3
