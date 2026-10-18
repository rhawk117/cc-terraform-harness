"""Rules for a base ref and for a git command's outcome."""

import re
import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tf_harness_mcp.tools.change_impact.domain import LineRange
from tf_harness_mcp.tools.change_impact.errors import GitCommandFailedError, InvalidBaseRefError

if TYPE_CHECKING:
    from tf_harness_mcp.runner.domain import CommandResult

HUNK_HEADER = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', re.ASCII)


@dataclass(slots=True, kw_only=True, frozen=True)
class BaseRefPolicy:
    base_ref: str

    @property
    def is_option_like(self) -> bool:
        return self.base_ref.startswith('-')

    def get_base_ref_problem(self) -> InvalidBaseRefError | None:
        if not self.base_ref or self.is_option_like:
            return InvalidBaseRefError(base_ref=self.base_ref)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class GitResultPolicy:
    argv: tuple[str, ...]
    result: CommandResult

    def get_git_problem(self) -> GitCommandFailedError | None:
        if self.result.returncode == 0:
            return None

        return GitCommandFailedError(
            command=shlex.join(('git', *self.argv)),
            returncode=self.result.returncode,
            stderr=self.result.stderr,
        )


def parse_hunk_ranges(diff: str) -> tuple[LineRange, ...]:
    matches = map(HUNK_HEADER.match, diff.splitlines())
    return tuple(
        LineRange(start=int(match[1]), count=int(match[2] or 1)) for match in matches if match
    )


def split_nul(output: str) -> list[str]:
    return [token for token in output.split('\0') if token]
