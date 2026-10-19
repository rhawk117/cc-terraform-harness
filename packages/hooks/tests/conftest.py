import json
from dataclasses import dataclass, field
from io import StringIO
from typing import TYPE_CHECKING

import pytest
from tf_harness_hooks.cli import PROJECT_DIR_VARIABLE, run_hook
from tf_harness_hooks.domain import HookIo, HookOutput, HookSession, default_handlers
from tf_harness_mcp.runner.domain import Command, CommandResult

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_hooks.domain import Handler, HookRequest, Subcommand
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

pytest_plugins = ['tf_harness_mcp.runner.tests.recording']

PROBE = Command(argv=('terraform', 'version'))


@dataclass(slots=True, kw_only=True, frozen=True)
class HookRun:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(slots=True, kw_only=True, frozen=True)
class HookHarness:
    project_root: Path
    runner: RecordingCommandRunner
    requests: list[HookRequest] = field(default_factory=list)

    def event(self, file_path: Path | str | None, event_name: str = 'PostToolUse') -> str:
        tool_input = {} if file_path is None else {'file_path': str(file_path)}
        return json.dumps({
            'hook_event_name': event_name,
            'cwd': str(self.project_root),
            'tool_name': 'Write',
            'tool_input': tool_input,
        })

    async def probe_runner(self, request: HookRequest) -> HookOutput | None:
        self.requests.append(request)
        await request.runner.run(PROBE, 1.0)
        return HookOutput(event_name=request.event_name, additional_context='probed')

    def run(
        self,
        subcommand: Subcommand,
        stdin: str,
        *,
        project_dir: str | None,
        probe: bool = True,
    ) -> HookRun:
        environ = {} if project_dir is None else {PROJECT_DIR_VARIABLE: project_dir}
        handlers: dict[Subcommand, Handler] = default_handlers()
        if probe:
            handlers[subcommand] = self.probe_runner
        stdout, stderr = StringIO(), StringIO()
        io = HookIo(stdin=StringIO(stdin), stdout=stdout, stderr=stderr)
        session = HookSession(
            subcommand=subcommand,
            environ=environ,
            io=io,
            runner=self.runner,
            handlers=handlers,
        )
        exit_code = run_hook(session)
        return HookRun(exit_code=exit_code, stdout=stdout.getvalue(), stderr=stderr.getvalue())


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / 'project'
    root.mkdir()
    return root


@pytest.fixture
def hook_harness(project_root: Path, recording_runner: RecordingCommandRunner) -> HookHarness:
    recording_runner.script(PROBE.argv, CommandResult(returncode=0, stdout='', stderr=''))
    return HookHarness(project_root=project_root, runner=recording_runner)
