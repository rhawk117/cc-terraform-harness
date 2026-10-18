from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.runner.domain import Command, CommandResult, CommandRunner
from tf_harness_mcp.runner.errors import CommandNotAllowedError
from tf_harness_mcp.runner.tests.recording import RecordedCall, UnscriptedCommandError

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

VERSION = Command(argv=('terraform', 'version'))
VERSION_RESULT = CommandResult(returncode=0, stdout='Terraform v1.9.0', stderr='')


@pytest.mark.unit
class TestRecordingCommandRunner:
    @pytest.fixture
    def scripted(self, recording_runner: RecordingCommandRunner) -> RecordingCommandRunner:
        recording_runner.script(VERSION.argv, VERSION_RESULT)
        return recording_runner

    def test_fixture_provides_a_command_runner(
        self, recording_runner: RecordingCommandRunner
    ) -> None:
        assert isinstance(recording_runner, CommandRunner)

    async def test_scripted_command_returns_its_result(
        self, scripted: RecordingCommandRunner
    ) -> None:
        assert await scripted.run(VERSION, 5.0) == VERSION_RESULT

    async def test_each_call_is_recorded_with_its_timeout(
        self, scripted: RecordingCommandRunner
    ) -> None:
        await scripted.run(VERSION, 5.0)
        await scripted.run(VERSION, 7.5)
        assert scripted.calls == [
            RecordedCall(command=VERSION, timeout_seconds=5.0),
            RecordedCall(command=VERSION, timeout_seconds=7.5),
        ]

    async def test_each_call_records_the_working_directory(
        self, scripted: RecordingCommandRunner, tmp_path: Path
    ) -> None:
        in_directory = Command(argv=VERSION.argv, cwd=tmp_path)
        scripted.script(in_directory.argv, VERSION_RESULT)

        await scripted.run(in_directory, 5.0)

        assert [call.command.cwd for call in scripted.calls] == [tmp_path]

    async def test_command_outside_the_read_only_set_is_refused(
        self, scripted: RecordingCommandRunner
    ) -> None:
        with pytest.raises(CommandNotAllowedError):
            await scripted.run(Command(argv=('terraform', 'apply')), 5.0)
        assert scripted.calls == []

    async def test_allowed_command_without_a_script_fails_loudly(
        self, recording_runner: RecordingCommandRunner
    ) -> None:
        with pytest.raises(UnscriptedCommandError, match='terraform version'):
            await recording_runner.run(VERSION, 5.0)
