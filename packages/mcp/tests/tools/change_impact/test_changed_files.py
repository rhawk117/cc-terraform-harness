from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.runner.errors import CommandNotFoundError
from tf_harness_mcp.tools.change_impact.domain import ChangedFile, LineRange
from tf_harness_mcp.tools.change_impact.errors import (
    BaseRefNotFoundError,
    GitCommandFailedError,
    InvalidBaseRefError,
)

from .conftest import BASE, COMMIT, fail, succeed

if TYPE_CHECKING:
    from .conftest import GitHarness

pytestmark = pytest.mark.unit

MODIFIED_DIFF = (
    'diff --git main.tf main.tf\n'
    '--- main.tf\n'
    '+++ main.tf\n'
    '@@ -1,0 +2 @@\n'
    '+added\n'
    '@@ -5,2 +6,3 @@\n'
    '@@ -9 +0,0 @@\n'
)
RESOLVE = ('git', 'rev-parse', '--verify', '--quiet', '--end-of-options')


def option_like_ref_cases() -> pytest.MarkDecorator:
    refs = ['-', '--output=x', '-h', '--upload-pack=x', '-n1']
    return pytest.mark.parametrize('base_ref', [pytest.param(ref, id=ref) for ref in refs])


class TestBaseRef:
    @option_like_ref_cases()
    async def test_option_like_ref_never_reaches_git(
        self, git_harness: GitHarness, base_ref: str
    ) -> None:
        with pytest.raises(InvalidBaseRefError):
            await git_harness.repository.read_changes(base_ref)
        assert not git_harness.runner.calls

    async def test_empty_ref_never_reaches_git(self, git_harness: GitHarness) -> None:
        with pytest.raises(InvalidBaseRefError):
            await git_harness.repository.read_changes('')
        assert not git_harness.runner.calls

    async def test_unresolvable_ref_is_reported(self, git_harness: GitHarness) -> None:
        git_harness.runner.script((*RESOLVE, 'nope^{commit}'), fail(1))
        with pytest.raises(BaseRefNotFoundError) as caught:
            await git_harness.repository.read_changes('nope')
        assert caught.value.base_ref == 'nope'

    async def test_git_failure_carries_the_command(self, git_harness: GitHarness) -> None:
        git_harness.runner.script((*RESOLVE, 'main^{commit}'), fail(128, 'not a git repository'))
        with pytest.raises(GitCommandFailedError) as caught:
            await git_harness.repository.read_changes('main')
        assert caught.value.returncode == 128
        assert 'rev-parse' in caught.value.command

    async def test_missing_git_binary_propagates(self, git_harness: GitHarness) -> None:
        git_harness.runner.script_missing_binary((*RESOLVE, 'main^{commit}'))
        with pytest.raises(CommandNotFoundError):
            await git_harness.repository.read_changes('main')


class TestChangedFiles:
    @pytest.fixture
    def scripted(self, git_harness: GitHarness) -> GitHarness:
        git_harness.script_resolution('main')
        git_harness.script_merge_base()
        git_harness.script_name_status('M', 'main.tf', 'A', 'mod/new.tf', 'D', 'del.tf')
        git_harness.script_hunks('main.tf', MODIFIED_DIFF)
        git_harness.script_hunks('mod/new.tf', '@@ -0,0 +1,4 @@\n')
        git_harness.script_hunks('del.tf', '@@ -1,3 +0,0 @@\n')
        git_harness.script_untracked('scratch.tf')
        return git_harness

    async def test_changed_set_covers_tracked_and_untracked_files(
        self, scripted: GitHarness
    ) -> None:
        changes = await scripted.repository.read_changes('main')
        assert changes.base_commit == BASE
        assert changes.files == (
            ChangedFile(
                path='main.tf',
                status='modified',
                ranges=(
                    LineRange(start=2, count=1),
                    LineRange(start=6, count=3),
                    LineRange(start=0, count=0),
                ),
            ),
            ChangedFile(path='mod/new.tf', status='added', ranges=(LineRange(start=1, count=4),)),
            ChangedFile(path='del.tf', status='deleted', ranges=(LineRange(start=0, count=0),)),
            ChangedFile(path='scratch.tf', status='added'),
        )

    async def test_every_command_runs_in_the_module_directory(self, scripted: GitHarness) -> None:
        await scripted.repository.read_changes('main')
        assert {call.command.cwd for call in scripted.runner.calls} == {scripted.module}

    async def test_diff_runs_against_the_merge_base(self, scripted: GitHarness) -> None:
        await scripted.repository.read_changes('main')
        diffs = [
            call.command.argv for call in scripted.runner.calls if call.command.argv[1] == 'diff'
        ]
        assert diffs
        assert all(BASE in argv and COMMIT not in argv for argv in diffs)

    async def test_no_changes_gives_an_empty_set(self, git_harness: GitHarness) -> None:
        git_harness.script_resolution('HEAD')
        git_harness.script_merge_base()
        git_harness.script_name_status()
        git_harness.script_untracked()
        changes = await git_harness.repository.read_changes('HEAD')
        assert changes.files == ()


class TestBaseContent:
    async def test_content_is_read_at_the_base_commit(self, git_harness: GitHarness) -> None:
        argv = ('git', 'cat-file', 'blob', f'{BASE}:./mod/main.tf')
        git_harness.runner.script(argv, succeed('resource "x" "y" {}\n'))
        content = await git_harness.repository.read_base_content(BASE, 'mod/main.tf')
        assert content == 'resource "x" "y" {}\n'

    async def test_missing_blob_is_reported(self, git_harness: GitHarness) -> None:
        argv = ('git', 'cat-file', 'blob', f'{BASE}:./new.tf')
        git_harness.runner.script(argv, fail(128, 'path does not exist'))
        with pytest.raises(GitCommandFailedError):
            await git_harness.repository.read_base_content(BASE, 'new.tf')
