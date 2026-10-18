from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.runner.domain import CommandResult
from tf_harness_mcp.tools.change_impact.repository import GitRepository

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

COMMIT = 'a' * 40
BASE = 'b' * 40
DIFF_PINS = (
    'git',
    'diff',
    '--no-ext-diff',
    '--no-textconv',
    '--no-color',
    '--no-prefix',
    '--no-renames',
    '--relative',
)


def succeed(stdout: str = '') -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr='')


def fail(returncode: int, stderr: str = '') -> CommandResult:
    return CommandResult(returncode=returncode, stdout='', stderr=stderr)


@dataclass(slots=True, kw_only=True, frozen=True)
class GitHarness:
    runner: RecordingCommandRunner
    repository: GitRepository
    module: Path

    def script_resolution(self, base_ref: str) -> None:
        argv = ('git', 'rev-parse', '--verify', '--quiet', '--end-of-options')
        self.runner.script((*argv, f'{base_ref}^{{commit}}'), succeed(f'{COMMIT}\n'))

    def script_merge_base(self) -> None:
        self.runner.script(('git', 'merge-base', COMMIT, 'HEAD'), succeed(f'{BASE}\n'))

    def script_name_status(self, *entries: str) -> None:
        argv = (*DIFF_PINS, '--name-status', '-z', BASE, '--', '*.tf')
        self.runner.script(argv, succeed(''.join(f'{entry}\0' for entry in entries)))

    def script_hunks(self, path: str, diff: str) -> None:
        argv = (*DIFF_PINS, '--unified=0', BASE, '--', f':(literal){path}')
        self.runner.script(argv, succeed(diff))

    def script_base_content(self, path: str, text: str) -> None:
        self.runner.script(('git', 'cat-file', 'blob', f'{BASE}:./{path}'), succeed(text))

    def script_untracked(self, *paths: str) -> None:
        argv = ('git', 'ls-files', '--others', '--exclude-standard', '-z', '--', '*.tf')
        self.runner.script(argv, succeed(''.join(f'{path}\0' for path in paths)))


@pytest.fixture
def module(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def git_harness(recording_runner: RecordingCommandRunner, module: Path) -> GitHarness:
    repository = GitRepository(runner=recording_runner, directory=module)
    return GitHarness(runner=recording_runner, repository=repository, module=module)
