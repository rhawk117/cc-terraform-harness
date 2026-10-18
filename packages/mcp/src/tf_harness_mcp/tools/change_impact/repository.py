"""Reads changed Terraform files, their hunks and their base content through the runner."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tf_harness_mcp.runner.domain import Command
from tf_harness_mcp.tools.change_impact.domain import ChangedFile, ChangeSet, GitOptions
from tf_harness_mcp.tools.change_impact.errors import BaseRefNotFoundError
from tf_harness_mcp.tools.change_impact.policy import (
    BaseRefPolicy,
    GitResultPolicy,
    parse_hunk_ranges,
    split_nul,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.runner.domain import CommandResult, CommandRunner
    from tf_harness_mcp.tools.change_impact.domain import ChangeStatus, LineRange

TF_PATHSPEC = '*.tf'
DIFF_ARGV = (
    'diff',
    '--no-ext-diff',
    '--no-textconv',
    '--no-color',
    '--no-prefix',
    '--no-renames',
    '--relative',
)
STATUSES: dict[str, ChangeStatus] = {'A': 'added', 'D': 'deleted'}


@dataclass(slots=True, kw_only=True, frozen=True)
class GitRepository:
    runner: CommandRunner
    directory: Path
    options: GitOptions = field(default_factory=GitOptions)

    async def run(self, argv: tuple[str, ...]) -> CommandResult:
        command = Command(argv=('git', *argv), cwd=self.directory)
        return await self.runner.run(command, self.options.timeout_seconds)

    async def read_stdout(self, argv: tuple[str, ...]) -> str:
        result = await self.run(argv)
        if problem := GitResultPolicy(argv=argv, result=result).get_git_problem():
            raise problem

        return result.stdout

    async def resolve_commit(self, base_ref: str) -> str:
        if problem := BaseRefPolicy(base_ref=base_ref).get_base_ref_problem():
            raise problem

        argv = ('rev-parse', '--verify', '--quiet', '--end-of-options', f'{base_ref}^{{commit}}')
        result = await self.run(argv)
        if result.returncode == 1:
            raise BaseRefNotFoundError(base_ref=base_ref)

        if problem := GitResultPolicy(argv=argv, result=result).get_git_problem():
            raise problem

        return result.stdout.strip()

    async def read_merge_base(self, commit: str) -> str:
        output = await self.read_stdout(('merge-base', commit, 'HEAD'))
        return output.strip()

    async def read_hunks(self, base_commit: str, path: str) -> tuple[LineRange, ...]:
        argv = (*DIFF_ARGV, '--unified=0', base_commit, '--', f':(literal){path}')
        return parse_hunk_ranges(await self.read_stdout(argv))

    async def read_tracked_changes(self, base_commit: str) -> tuple[ChangedFile, ...]:
        argv = (*DIFF_ARGV, '--name-status', '-z', base_commit, '--', TF_PATHSPEC)
        tokens = split_nul(await self.read_stdout(argv))
        changes = []
        for code, path in zip(tokens[::2], tokens[1::2], strict=True):
            status = STATUSES.get(code, 'modified')
            ranges = await self.read_hunks(base_commit, path)
            changes.append(ChangedFile(path=path, status=status, ranges=ranges))

        return tuple(changes)

    async def read_untracked_changes(self) -> tuple[ChangedFile, ...]:
        argv = ('ls-files', '--others', '--exclude-standard', '-z', '--', TF_PATHSPEC)
        paths = split_nul(await self.read_stdout(argv))
        return tuple(ChangedFile(path=path, status='added') for path in paths)

    async def read_changes(self, base_ref: str) -> ChangeSet:
        commit = await self.resolve_commit(base_ref)
        base_commit = await self.read_merge_base(commit)
        tracked = await self.read_tracked_changes(base_commit)
        untracked = await self.read_untracked_changes()
        return ChangeSet(base_commit=base_commit, files=(*tracked, *untracked))

    async def read_base_content(self, base_commit: str, path: str) -> str:
        return await self.read_stdout(('cat-file', 'blob', f'{base_commit}:./{path}'))
