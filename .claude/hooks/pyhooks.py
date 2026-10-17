# /// script
# requires-python = ">=3.14"
# dependencies = ["msgspec"]
# ///
"""Claude Code hooks: format writes, diagnose reads, ask before new suppressions."""

import argparse
import asyncio
import os
import re
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, Self, get_args, runtime_checkable

import msgspec

type HookCommand = Literal['format', 'diagnose', 'suppressions']


class ToolInput(msgspec.Struct, frozen=True, kw_only=True):
    file_path: str = ''
    content: str = ''
    old_string: str = ''
    new_string: str = ''


class HookInput(msgspec.Struct, frozen=True, kw_only=True):
    tool_name: str
    tool_input: ToolInput
    cwd: str = ''


class HookOutput(msgspec.Struct, frozen=True, kw_only=True, rename="camel"): ...


class ContextOutput(HookOutput, frozen=True, kw_only=True):
    additional_context: str
    hook_event_name: Literal['PostToolUse'] = 'PostToolUse'


class PermissionOutput(HookOutput, frozen=True, kw_only=True):
    permission_decision_reason: str
    hook_event_name: Literal['PreToolUse'] = 'PreToolUse'
    permission_decision: Literal['ask'] = 'ask'


class HookResponse(HookOutput, frozen=True, kw_only=True):
    hook_specific_output: ContextOutput | PermissionOutput


@dataclass(slots=True, kw_only=True, frozen=True)
class HookOptions:
    python_suffixes: tuple[str, ...] = ('.py', '.pyi')
    formatted_notice: str = 'This file was automatically formatted.'
    suppression_pattern: str = r'(?i)#\s*(?:ruff:\s*)?noqa\b|#\s*(?:type|ty):\s*ignore\b'
    diagnostic_pattern: str = r'^\S+:\d+:\d+: '

    def is_python_file(self, path: Path) -> bool:
        return path.suffix in self.python_suffixes

    def is_suppressed(self, line: str) -> bool:
        return bool(re.search(self.suppression_pattern, line))

    def is_diagnostic(self, line: str) -> bool:
        return bool(re.match(self.diagnostic_pattern, line))

    def select_diagnostics(self, output: str) -> tuple[str, ...]:
        return tuple(filter(self.is_diagnostic, output.splitlines()))


@dataclass(slots=True, kw_only=True, frozen=True)
class TextChange:
    before: str
    after: str


@dataclass(slots=True, kw_only=True, frozen=True)
class AddedSuppressions:
    lines: Sequence[str]

    @property
    def reason(self) -> str:
        listed = '\n'.join(self.lines)
        return f'This change adds lint or type suppressions:\n{listed}'


@dataclass(slots=True, kw_only=True, frozen=True)
class SuppressionPolicy:
    change: TextChange
    options: HookOptions = field(default_factory=HookOptions)

    def select_suppressed_lines(self, text: str) -> Iterator[str]:
        lines = map(str.strip, text.splitlines())
        return filter(self.options.is_suppressed, lines)

    @property
    def added_suppressions(self) -> tuple[str, ...]:
        before = Counter(self.select_suppressed_lines(self.change.before))
        after = Counter(self.select_suppressed_lines(self.change.after))
        return tuple((after - before).elements())

    def get_suppression_issues(self) -> AddedSuppressions | None:
        if suppressions := self.added_suppressions:
            return AddedSuppressions(lines=suppressions)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class CompletedRun:
    command: str
    exit_code: int
    output: str
    errors: str
    failure_exit_code: int

    @property
    def failed(self) -> bool:
        return self.exit_code >= self.failure_exit_code

    @property
    def flagged(self) -> bool:
        return 0 < self.exit_code < self.failure_exit_code

    @property
    def failure(self) -> str:
        detail = next(iter(self.errors.splitlines()), 'no error output')
        return f'{self.command} exited {self.exit_code}: {detail}'


@dataclass(slots=True, kw_only=True, frozen=True)
class Toolchain:
    project_dir: Path
    failure_exit_code: int = 2

    async def run(self, *arguments: str) -> CompletedRun:
        process = await asyncio.create_subprocess_exec(
            'uv',
            'run',
            '--quiet',
            *arguments,
            cwd=self.project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        output, errors = await process.communicate()
        return CompletedRun(
            command=' '.join(arguments[:2]),
            exit_code=process.returncode or 0,
            output=output.decode(),
            errors=errors.decode(),
            failure_exit_code=self.failure_exit_code,
        )


def create_context_response(text: str) -> HookResponse:
    return HookResponse(hook_specific_output=ContextOutput(additional_context=text))


def create_permission_response(reason: str) -> HookResponse:
    output = PermissionOutput(permission_decision_reason=reason)
    return HookResponse(hook_specific_output=output)


def describe_change(hook_input: HookInput) -> TextChange:
    tool_input = hook_input.tool_input
    if hook_input.tool_name == 'Edit':
        return TextChange(
            before=tool_input.old_string,
            after=tool_input.new_string,
        )

    path = Path(tool_input.file_path)
    before = path.read_text(encoding='utf-8') if path.exists() else ''
    return TextChange(before=before, after=tool_input.content)


@runtime_checkable
class HookHandler(Protocol):
    async def handle(self, hook_input: HookInput) -> HookResponse | None: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class FormatHandler:
    toolchain: Toolchain
    options: HookOptions

    async def handle(self, hook_input: HookInput) -> HookResponse | None:
        path = Path(hook_input.tool_input.file_path)
        if not self.options.is_python_file(path):
            return None

        formatting = await self.toolchain.run(
            'ruff',
            'format',
            '--exit-non-zero-on-format',
            str(path),
        )

        if formatting.failed:
            return create_context_response(formatting.failure)

        if formatting.flagged:
            return create_context_response(self.options.formatted_notice)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class DiagnoseHandler:
    toolchain: Toolchain
    options: HookOptions

    async def handle(self, hook_input: HookInput) -> HookResponse | None:
        path = Path(hook_input.tool_input.file_path)
        if not self.options.is_python_file(path):
            return None

        async with asyncio.TaskGroup() as group:
            ruff = group.create_task(self.run_checker('ruff', path))
            ty = group.create_task(self.run_checker('ty', path))

        if diagnostics := (*ruff.result(), *ty.result()):
            listed = '\n'.join(diagnostics)
            report = f'ruff and ty report for {path.name}:\n{listed}'
            return create_context_response(report)

        return None

    async def run_checker(self, checker: str, path: Path) -> tuple[str, ...]:
        fix_flags = ('--no-fix',) if checker == 'ruff' else ()
        arguments = (checker, 'check', *fix_flags, '--output-format', 'concise', str(path))
        checking = await self.toolchain.run(*arguments)
        if checking.failed:
            return (checking.failure,)

        return self.options.select_diagnostics(checking.output)


@dataclass(slots=True, kw_only=True, frozen=True)
class SuppressionHandler:
    options: HookOptions

    async def handle(self, hook_input: HookInput) -> HookResponse | None:
        if not self.options.is_python_file(Path(hook_input.tool_input.file_path)):
            return None

        change = await asyncio.to_thread(describe_change, hook_input)
        policy = SuppressionPolicy(change=change, options=self.options)

        if issues := policy.get_suppression_issues():
            return create_permission_response(issues.reason)

        return None


type HookHandlers = dict[HookCommand, HookHandler]


@dataclass(slots=True, kw_only=True, frozen=True)
class HookRouter:
    handlers: HookHandlers = field(default_factory=dict)

    def mount(self, handlers: HookHandlers) -> Self:
        self.handlers.update(handlers)
        return self

    async def dispatch(self, command: HookCommand, hook_input: HookInput) -> HookResponse | None:
        return await self.handlers[command].handle(hook_input)


def create_hook_router(project_dir: Path, options: HookOptions | None = None) -> HookRouter:
    options = options or HookOptions()
    toolchain = Toolchain(project_dir=project_dir)
    return HookRouter().mount({
        'format': FormatHandler(toolchain=toolchain, options=options),
        'diagnose': DiagnoseHandler(toolchain=toolchain, options=options),
        'suppressions': SuppressionHandler(options=options),
    })


def parse_command() -> HookCommand:
    parser = argparse.ArgumentParser(
        prog=__file__,
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'command',
        choices=get_args(HookCommand.__value__),
    )
    return parser.parse_args().command


async def main() -> int:
    command = parse_command()
    hook_input = msgspec.json.decode(sys.stdin.read(), type=HookInput)
    cwd = os.getenv("CLAUDE_PROJECT_DIR", hook_input.cwd)

    project_dir = Path(cwd)
    router = create_hook_router(project_dir)

    if response := await router.dispatch(command, hook_input):
        sys.stdout.buffer.write(msgspec.json.encode(response))

    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
