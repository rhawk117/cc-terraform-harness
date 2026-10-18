import json
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import anyio
import pytest
from tf_harness_mcp.runner.domain import CommandResult
from tf_harness_mcp.runner.process import create_command_runner
from tf_harness_mcp.server import create_server
from tf_harness_mcp.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path

    from mcp import Client
    from mcp.server.mcpserver import MCPServer
    from mcp.types import CallToolResult
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

type Report = dict[str, Any]

FMT_ARGV = ('terraform', 'fmt', '-check', '-list=true', '-no-color')
VALIDATE_ARGV = ('terraform', 'validate', '-json', '-no-color')
TFLINT_ARGV = ('tflint', '--format=json', '--no-color')


def succeed(stdout: str = '') -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr='')


def fail(returncode: int, stdout: str) -> CommandResult:
    return CommandResult(returncode=returncode, stdout=stdout, stderr='')


def create_validate_json(*diagnostics: dict[str, Any]) -> str:
    return json.dumps({'valid': not diagnostics, 'diagnostics': list(diagnostics)})


def create_range(filename: str, line: int) -> dict[str, Any]:
    return {'filename': filename, 'start': {'line': line, 'column': 1, 'byte': 0}}


def create_undeclared_diagnostic() -> dict[str, Any]:
    return {
        'severity': 'error',
        'summary': 'Reference to undeclared input variable',
        'detail': 'An input variable with the name "x" has not been declared.',
        'range': create_range('main.tf', 3),
    }


def create_missing_provider_diagnostic() -> dict[str, Any]:
    return {
        'severity': 'error',
        'summary': 'Missing required provider',
        'detail': 'This configuration requires provider "hashicorp/null"; run terraform init.',
    }


def read_report(result: CallToolResult) -> Report:
    assert not result.is_error
    assert result.structured_content is not None
    return result.structured_content


async def call_diagnostics(client: Client, directory: Path) -> CallToolResult:
    return await client.call_tool('diagnostics', {'directory': str(directory)})


@dataclass(slots=True, kw_only=True, frozen=True)
class Scripted:
    runner: RecordingCommandRunner
    module: Path


@pytest.fixture
def module(project_root: Path) -> Path:
    directory = project_root.joinpath('module')
    directory.mkdir()
    return directory


@pytest.mark.unit
class TestDiagnosticsWithFindings:
    tflint_output = json.dumps({
        'issues': [
            {
                'rule': {'name': 'terraform_unused_declarations', 'severity': 'warning'},
                'message': 'variable "y" is declared but not used',
                'range': create_range('variables.tf', 7),
            }
        ],
        'errors': [],
    })

    @pytest.fixture
    def scripted(self, recording_runner: RecordingCommandRunner, module: Path) -> Scripted:
        recording_runner.script(FMT_ARGV, fail(3, 'main.tf\n'))
        recording_runner.script(
            VALIDATE_ARGV, fail(1, create_validate_json(create_undeclared_diagnostic()))
        )
        recording_runner.script(TFLINT_ARGV, fail(2, self.tflint_output))
        return Scripted(runner=recording_runner, module=module)

    @pytest.fixture
    async def report(self, client: Client, scripted: Scripted) -> Report:
        return read_report(await call_diagnostics(client, scripted.module))

    async def test_fmt_names_each_unformatted_file(self, report: Report) -> None:
        fmt = report['checks']['fmt']

        assert fmt['status'] == 'failed'
        assert [finding['file'] for finding in fmt['findings']] == ['main.tf']

    async def test_validate_findings_carry_file_and_line(self, report: Report) -> None:
        finding = report['checks']['validate']['findings'][0]

        assert report['checks']['validate']['status'] == 'failed'
        assert (finding['file'], finding['line']) == ('main.tf', 3)
        assert finding['summary'] == 'Reference to undeclared input variable'

    async def test_tflint_findings_carry_file_and_line(self, report: Report) -> None:
        finding = report['checks']['tflint']['findings'][0]

        assert report['checks']['tflint']['status'] == 'failed'
        assert (finding['file'], finding['line']) == ('variables.tf', 7)
        assert finding['severity'] == 'warning'

    async def test_every_check_runs_in_the_module_directory(
        self, report: Report, scripted: Scripted
    ) -> None:
        calls = scripted.runner.calls

        assert report['directory'] == str(scripted.module.resolve())
        assert [call.command.argv for call in calls] == [FMT_ARGV, VALIDATE_ARGV, TFLINT_ARGV]
        assert {call.command.cwd for call in calls} == {scripted.module.resolve()}


@pytest.mark.unit
class TestDiagnosticsOnCleanModule:
    @pytest.fixture
    def scripted(self, recording_runner: RecordingCommandRunner, module: Path) -> Scripted:
        recording_runner.script(FMT_ARGV, succeed())
        recording_runner.script(VALIDATE_ARGV, succeed(create_validate_json()))
        recording_runner.script(TFLINT_ARGV, succeed(json.dumps({'issues': [], 'errors': []})))
        return Scripted(runner=recording_runner, module=module)

    async def test_every_check_passes_without_findings(
        self, client: Client, scripted: Scripted
    ) -> None:
        report = read_report(await call_diagnostics(client, scripted.module))

        assert {name: check['status'] for name, check in report['checks'].items()} == {
            'fmt': 'passed',
            'validate': 'passed',
            'tflint': 'passed',
        }
        assert [check['findings'] for check in report['checks'].values()] == [[], [], []]


@pytest.mark.unit
class TestDiagnosticsWithoutTflint:
    @pytest.fixture
    def scripted(self, recording_runner: RecordingCommandRunner, module: Path) -> Scripted:
        recording_runner.script(FMT_ARGV, succeed())
        recording_runner.script(VALIDATE_ARGV, succeed(create_validate_json()))
        recording_runner.script_missing_binary(TFLINT_ARGV)
        return Scripted(runner=recording_runner, module=module)

    async def test_tflint_is_skipped_with_the_reason(
        self, client: Client, scripted: Scripted
    ) -> None:
        report = read_report(await call_diagnostics(client, scripted.module))

        tflint = report['checks']['tflint']
        assert tflint['status'] == 'skipped'
        assert 'tflint' in tflint['reason']
        assert report['checks']['fmt']['status'] == 'passed'


@pytest.mark.unit
class TestDiagnosticsOnUninitializedDirectory:
    @pytest.fixture
    def scripted(self, recording_runner: RecordingCommandRunner, module: Path) -> Scripted:
        recording_runner.script(FMT_ARGV, succeed())
        recording_runner.script(
            VALIDATE_ARGV, fail(1, create_validate_json(create_missing_provider_diagnostic()))
        )
        recording_runner.script(TFLINT_ARGV, succeed(json.dumps({'issues': [], 'errors': []})))
        return Scripted(runner=recording_runner, module=module)

    async def test_it_is_a_validate_finding_and_init_never_runs(
        self, client: Client, scripted: Scripted
    ) -> None:
        report = read_report(await call_diagnostics(client, scripted.module))

        validate = report['checks']['validate']
        assert validate['status'] == 'failed'
        assert validate['findings'][0]['summary'] == 'Missing required provider'
        assert validate['findings'][0]['file'] is None
        assert all('init' not in call.command.argv for call in scripted.runner.calls)


@pytest.mark.unit
class TestDiagnosticsOutputBudget:
    ceiling = 1_000
    unformatted_count = 200

    @pytest.fixture
    def settings(self, project_root: Path) -> Settings:
        return Settings(
            project_root=project_root,
            output_budget_bytes=self.ceiling,
            output_budget_max_bytes=self.ceiling,
        )

    @pytest.fixture
    def scripted(self, recording_runner: RecordingCommandRunner, module: Path) -> Scripted:
        names = ''.join(f'module_{number}.tf\n' for number in range(self.unformatted_count))
        recording_runner.script(FMT_ARGV, fail(3, names))
        recording_runner.script(VALIDATE_ARGV, succeed(create_validate_json()))
        recording_runner.script(TFLINT_ARGV, succeed(json.dumps({'issues': [], 'errors': []})))
        return Scripted(runner=recording_runner, module=module)

    async def test_findings_are_cut_to_fit_and_the_cut_is_reported(
        self, client: Client, scripted: Scripted
    ) -> None:
        result = await call_diagnostics(client, scripted.module)

        fmt = read_report(result)['checks']['fmt']
        assert len(json.dumps(read_report(result), separators=(',', ':'))) <= self.ceiling
        assert fmt['status'] == 'failed'
        assert 0 < len(fmt['findings']) < self.unformatted_count
        assert fmt['findings_omitted'] == self.unformatted_count - len(fmt['findings'])


@pytest.mark.integration
@pytest.mark.skipif(shutil.which('terraform') is None, reason='terraform is not on PATH')
class TestDiagnosticsWithTerraform:
    broken_module = 'resource   "terraform_data" "broken" {\n  input = var.undeclared\n}\n'

    @pytest.fixture
    def server(self, settings: Settings) -> MCPServer:
        return create_server(settings, create_command_runner())

    @pytest.fixture
    def broken(self, module: Path) -> Path:
        module.joinpath('main.tf').write_text(self.broken_module)
        return module

    @pytest.fixture
    async def report(self, client: Client, broken: Path) -> Report:
        return read_report(await call_diagnostics(client, broken))

    async def test_formatting_error_is_reported(self, report: Report) -> None:
        fmt = report['checks']['fmt']

        assert fmt['status'] == 'failed'
        assert [finding['file'] for finding in fmt['findings']] == ['main.tf']

    async def test_undeclared_reference_is_reported_with_its_line(self, report: Report) -> None:
        validate = report['checks']['validate']

        assert validate['status'] == 'failed'
        assert [(finding['file'], finding['line']) for finding in validate['findings']] == [
            ('main.tf', 2)
        ]

    async def test_nothing_is_written(self, report: Report, broken: Path) -> None:
        names = [path.name async for path in anyio.Path(broken).iterdir()]

        assert report['checks']['fmt']['status'] == 'failed'
        assert names == ['main.tf']
        assert await anyio.Path(broken, 'main.tf').read_text() == self.broken_module
