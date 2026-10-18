"""Problems the change_impact git layer reports."""

from typing import TYPE_CHECKING

from tf_harness_mcp.errors import HarnessError

if TYPE_CHECKING:
    from pathlib import Path


class InvalidBaseRefError(HarnessError):
    def __init__(self, *, base_ref: str) -> None:
        self.base_ref = base_ref
        super().__init__(f'base ref is empty or starts with a dash: {base_ref!r}')


class BaseRefNotFoundError(HarnessError):
    def __init__(self, *, base_ref: str) -> None:
        self.base_ref = base_ref
        super().__init__(f'base ref does not resolve to a commit: {base_ref!r}')


class GitCommandFailedError(HarnessError):
    def __init__(self, *, command: str, returncode: int, stderr: str) -> None:
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f'git exited with {returncode}: {command}: {stderr.strip()}')


class ChangedFileOutsideRootError(HarnessError):
    def __init__(self, *, path: Path) -> None:
        self.path = path
        super().__init__(f'{path} resolves outside the project root and was not read')


type ChangeSetProblem = InvalidBaseRefError | BaseRefNotFoundError | GitCommandFailedError
