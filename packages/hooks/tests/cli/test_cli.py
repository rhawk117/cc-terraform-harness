import json
from typing import TYPE_CHECKING

import pytest
from tf_harness_hooks.cli import main

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_hooks.domain import HookOutput, HookRequest

    from tests.conftest import HookHarness, PermissionDeniedRunner


pytestmark = pytest.mark.unit


async def ignore_event(_request: HookRequest) -> HookOutput | None:
    return None


class TestHookOutput:
    @pytest.mark.parametrize('suffix', ['main.tf', 'prod.tfvars'])
    def test_terraform_file_reaches_the_handler_and_prints_the_envelope(
        self, hook_harness: HookHarness, suffix: str
    ) -> None:
        run = hook_harness.run(
            'read',
            hook_harness.event(hook_harness.project_root / suffix),
            project_dir=str(hook_harness.project_root),
        )

        assert run.exit_code == 0
        assert json.loads(run.stdout) == {
            'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': 'probed'}
        }
        assert len(hook_harness.runner.calls) == 1

    def test_handler_receives_the_resolved_path(
        self, hook_harness: HookHarness, project_root: Path
    ) -> None:
        (project_root / 'sub').mkdir()
        hook_harness.run(
            'read',
            hook_harness.event(project_root / 'sub' / '..' / 'main.tf'),
            project_dir=str(project_root),
        )

        assert [request.file_path for request in hook_harness.requests] == [
            project_root.resolve() / 'main.tf'
        ]

    def test_session_start_needs_no_file_path(self, hook_harness: HookHarness) -> None:
        run = hook_harness.run(
            'session-start',
            hook_harness.event(None, event_name='SessionStart'),
            project_dir=str(hook_harness.project_root),
        )

        assert run.exit_code == 0
        assert json.loads(run.stdout)['hookSpecificOutput']['hookEventName'] == 'SessionStart'

    def test_default_handler_prints_nothing(
        self, hook_harness: HookHarness, project_root: Path
    ) -> None:
        run = hook_harness.run(
            'fmt',
            hook_harness.event(project_root / 'main.tf'),
            project_dir=str(project_root),
            handler=ignore_event,
        )

        assert (run.exit_code, run.stdout) == (0, '')


class TestRunnerOsError:
    def test_permission_error_exits_zero_with_one_stderr_line(
        self,
        hook_harness: HookHarness,
        project_root: Path,
        permission_denied_runner: PermissionDeniedRunner,
    ) -> None:
        run = hook_harness.run(
            'read',
            hook_harness.event(project_root / 'main.tf'),
            project_dir=str(project_root),
            runner=permission_denied_runner,
        )

        assert (run.exit_code, run.stdout) == (0, '')
        assert len(run.stderr.splitlines()) == 1
        assert 'Permission denied' in run.stderr


class TestInvalidInput:
    def test_malformed_event_is_a_non_blocking_error(self, hook_harness: HookHarness) -> None:
        run = hook_harness.run(
            'fmt', '{"tool_input": 3}', project_dir=str(hook_harness.project_root)
        )

        assert run.exit_code == 1
        assert 'invalid hook event' in run.stderr

    def test_unknown_subcommand_is_a_usage_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(['bogus'], {})

        assert exit_code == 2
        assert 'usage' in capsys.readouterr().err
