import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet

    from plugin.conftest import PluginInventory

COMMAND_PREFIX = '"${CLAUDE_PLUGIN_ROOT}/bin/tf-harness-hooks" '


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


def find_commands(
    hook_events: dict[str, list[dict[str, Any]]], registration: HookRegistration
) -> list[dict[str, Any]]:
    groups = hook_events[registration.event]
    matching = [group for group in groups if group['matcher'] == registration.matcher]
    return [hook for group in matching for hook in group['hooks']]


async def run_shim_without_uv(shim: Path, empty_path: Path) -> tuple[int, list[str]]:
    process = await asyncio.create_subprocess_exec(
        str(shim),
        'fmt',
        env={'PATH': str(empty_path)},
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    return process.returncode or 0, stderr.decode().splitlines()


@pytest.mark.integration
class TestHooksShim:
    def test_shim_without_uv_exits_zero_with_one_stderr_line(
        self, repository_root: Path, tmp_path: Path
    ) -> None:
        shim = repository_root.joinpath('bin', 'tf-harness-hooks')
        exit_code, stderr_lines = asyncio.run(run_shim_without_uv(shim, tmp_path))
        assert exit_code == 0
        assert len(stderr_lines) == 1


@pytest.mark.unit
class TestPluginHooks:
    @pytest.fixture
    def hook_events(self, claude_plugin: PluginInventory) -> dict[str, list[dict[str, Any]]]:
        return claude_plugin.hooks.required_key('hooks')

    @hook_registration_cases()
    def test_registration_runs_its_subcommand_through_the_shim(
        self, hook_events: dict[str, list[dict[str, Any]]], registration: HookRegistration
    ) -> None:
        commands = find_commands(hook_events, registration)
        assert [hook['type'] for hook in commands] == ['command']
        assert commands[0]['command'] == COMMAND_PREFIX + registration.subcommand

    @hook_registration_cases()
    def test_registration_sets_its_timeout(
        self, hook_events: dict[str, list[dict[str, Any]]], registration: HookRegistration
    ) -> None:
        commands = find_commands(hook_events, registration)
        assert commands[0]['timeout'] == registration.timeout

    def test_plugin_registers_only_the_three_hooks(
        self, hook_events: dict[str, list[dict[str, Any]]]
    ) -> None:
        registered = [
            hook for groups in hook_events.values() for group in groups for hook in group['hooks']
        ]
        assert len(registered) == 3
