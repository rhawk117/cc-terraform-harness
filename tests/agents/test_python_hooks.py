import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import msgspec
import pytest

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from _pytest.mark import ParameterSet

type HookCommand = Literal['format', 'diagnose', 'suppressions']
type ToolName = Literal['Write', 'Edit', 'Read']
type FormatOutcome = Literal['formatted', 'failed']


class ToolInput(msgspec.Struct, frozen=True, kw_only=True, omit_defaults=True):
    file_path: str
    content: str = ''
    old_string: str = ''
    new_string: str = ''


class HookPayload(msgspec.Struct, frozen=True, kw_only=True):
    tool_name: ToolName
    tool_input: ToolInput
    cwd: str


class SpecificOutput(msgspec.Struct, frozen=True, kw_only=True, rename='camel'):
    additional_context: str | None = None
    permission_decision: str | None = None
    permission_decision_reason: str | None = None


class HookReply(msgspec.Struct, frozen=True, kw_only=True, rename='camel'):
    hook_specific_output: SpecificOutput = msgspec.field(default_factory=SpecificOutput)


@dataclass(slots=True, kw_only=True, frozen=True)
class HookHarness:
    script: Path
    project: Path

    async def invoke(self, command: HookCommand, payload: HookPayload) -> str:
        process = await asyncio.create_subprocess_exec(
            'uv',
            'run',
            '--quiet',
            '--script',
            str(self.script),
            command,
            cwd=self.project,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        output, _ = await process.communicate(msgspec.json.encode(payload))
        return output.decode()

    def run_hook(self, command: HookCommand, payload: HookPayload) -> SpecificOutput:
        output = asyncio.run(self.invoke(command, payload))
        return msgspec.json.decode(output or '{}', type=HookReply).hook_specific_output

    def create_payload(self, tool_name: ToolName, tool_input: ToolInput) -> HookPayload:
        return HookPayload(tool_name=tool_name, tool_input=tool_input, cwd=str(self.project))


@dataclass(slots=True, kw_only=True, frozen=True)
class FormatCase:
    name: str
    filename: str
    source: str
    outcome: FormatOutcome | None
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


@dataclass(slots=True, kw_only=True, frozen=True)
class DiagnoseCase:
    name: str
    filename: str
    source: str
    reported: tuple[str, ...]
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


@dataclass(slots=True, kw_only=True, frozen=True)
class SuppressionCase:
    name: str
    tool_name: Literal['Write', 'Edit']
    before: str
    after: str
    decision: Literal['ask'] | None
    marks: Sequence[pytest.MarkDecorator] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)

    def create_tool_input(self, path: Path) -> ToolInput:
        if self.tool_name == 'Edit':
            return ToolInput(
                file_path=str(path),
                old_string=self.before,
                new_string=self.after,
            )

        return ToolInput(file_path=str(path), content=self.after)


def format_hook_cases() -> pytest.MarkDecorator:
    unformatted = FormatCase(
        name='unformatted',
        filename='messy.py',
        source='x=1\n',
        outcome='formatted',
    )
    formatted = FormatCase(
        name='already-formatted',
        filename='tidy.py',
        source='x = 1\n',
        outcome=None,
    )
    syntax_error = FormatCase(
        name='syntax-error',
        filename='broken.py',
        source='def f(:\n',
        outcome='failed',
    )
    not_python = FormatCase(
        name='not-python',
        filename='notes.md',
        source='x=1\n',
        outcome=None,
    )
    return pytest.mark.parametrize(
        'case',
        [unformatted.param, formatted.param, syntax_error.param, not_python.param],
    )


def diagnose_hook_cases() -> pytest.MarkDecorator:
    broken = DiagnoseCase(
        name='lint-and-type-errors',
        filename='broken.py',
        source='import os\n\n\ndef f(x: int) -> int:\n    return x + "a"\n',
        reported=('unused-import', 'unsupported-operator'),
    )
    clean = DiagnoseCase(name='clean', filename='clean.py', source='x = 1\n', reported=())
    not_python = DiagnoseCase(
        name='not-python', filename='notes.md', source='import os\n', reported=()
    )
    return pytest.mark.parametrize('case', [broken.param, clean.param, not_python.param])


def suppression_hook_cases() -> pytest.MarkDecorator:
    cases = (
        SuppressionCase(
            name='edit-adds-noqa',
            tool_name='Edit',
            before='x = 1',
            after='x = 1  # noqa: E501',
            decision='ask',
        ),
        SuppressionCase(
            name='edit-adds-file-noqa',
            tool_name='Edit',
            before='',
            after='# ruff: noqa',
            decision='ask',
        ),
        SuppressionCase(
            name='edit-adds-type-ignore',
            tool_name='Edit',
            before='x = f()',
            after='x = f()  # type: ignore[misc]',
            decision='ask',
        ),
        SuppressionCase(
            name='edit-adds-ty-ignore',
            tool_name='Edit',
            before='x = f()',
            after='x = f()  # ty: ignore[unresolved-reference]',
            decision='ask',
        ),
        SuppressionCase(
            name='edit-without-suppression',
            tool_name='Edit',
            before='x = 1',
            after='x = 2',
            decision=None,
        ),
        SuppressionCase(
            name='write-keeps-existing-noqa',
            tool_name='Write',
            before='x = 1  # noqa: E501\n',
            after='x = 1  # noqa: E501\ny = 2\n',
            decision=None,
        ),
        SuppressionCase(
            name='write-adds-noqa',
            tool_name='Write',
            before='x = 1\n',
            after='x = 1  # noqa: E501\n',
            decision='ask',
        ),
    )
    return pytest.mark.parametrize('case', [case.param for case in cases])


@pytest.fixture
def harness(pytestconfig: pytest.Config) -> HookHarness:
    root = pytestconfig.rootpath
    script = root.joinpath('.claude', 'hooks', 'pyhooks.py')
    return HookHarness(script=script, project=root)


@pytest.mark.integration
class TestFormatHook:
    outcome_prefixes: tuple[tuple[FormatOutcome, str], ...] = (
        ('formatted', 'This file was automatically formatted.'),
        ('failed', 'ruff format exited 2: '),
    )

    def classify(self, reply: SpecificOutput) -> FormatOutcome | None:
        context = reply.additional_context or ''
        matches = (
            outcome for outcome, prefix in self.outcome_prefixes if context.startswith(prefix)
        )
        return next(matches, None)

    @pytest.fixture
    def payload(self, harness: HookHarness, case: FormatCase, tmp_path: Path) -> HookPayload:
        path = tmp_path.joinpath(case.filename)
        path.write_text(case.source, encoding='utf-8')
        return harness.create_payload('Write', ToolInput(file_path=str(path)))

    @format_hook_cases()
    def test_notice_only_when_the_file_changed(
        self, harness: HookHarness, payload: HookPayload, case: FormatCase
    ) -> None:
        assert self.classify(harness.run_hook('format', payload)) == case.outcome


@pytest.mark.integration
class TestDiagnoseHook:
    candidates = ('unused-import', 'unsupported-operator')

    @pytest.fixture
    def inspected(self, case: DiagnoseCase, tmp_path: Path) -> Path:
        path = tmp_path.joinpath(case.filename)
        path.write_text(case.source, encoding='utf-8')
        return path

    @pytest.fixture
    def payload(self, harness: HookHarness, inspected: Path) -> HookPayload:
        return harness.create_payload('Read', ToolInput(file_path=str(inspected)))

    def find_reported(self, reply: SpecificOutput) -> tuple[str, ...]:
        context = reply.additional_context or ''
        return tuple(code for code in self.candidates if code in context)

    @diagnose_hook_cases()
    def test_reports_ruff_and_ty_findings(
        self, harness: HookHarness, payload: HookPayload, case: DiagnoseCase
    ) -> None:
        assert self.find_reported(harness.run_hook('diagnose', payload)) == case.reported

    @diagnose_hook_cases()
    def test_leaves_the_inspected_file_unchanged(
        self, harness: HookHarness, payload: HookPayload, inspected: Path, case: DiagnoseCase
    ) -> None:
        harness.run_hook('diagnose', payload)
        assert inspected.read_text(encoding='utf-8') == case.source


@pytest.mark.integration
class TestSuppressionHook:
    @pytest.fixture
    def payload(self, harness: HookHarness, case: SuppressionCase, tmp_path: Path) -> HookPayload:
        path = tmp_path.joinpath('module.py')
        path.write_text(case.before, encoding='utf-8')
        return harness.create_payload(case.tool_name, case.create_tool_input(path))

    @suppression_hook_cases()
    def test_asks_only_for_added_suppressions(
        self,
        harness: HookHarness,
        payload: HookPayload,
        case: SuppressionCase,
    ) -> None:
        reply = harness.run_hook('suppressions', payload)
        assert reply.permission_decision == case.decision
