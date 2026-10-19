"""Problems the structure layer reports as values instead of raising."""

from typing import TYPE_CHECKING

from tf_harness_mcp.errors import HarnessError

if TYPE_CHECKING:
    from pathlib import Path


class HclSyntaxError(HarnessError):
    def __init__(self, *, path: Path) -> None:
        self.path = path
        super().__init__(f'{path} does not parse as HCL')


class UnreadableFileError(HarnessError):
    def __init__(self, *, path: Path) -> None:
        self.path = path
        super().__init__(f'{path} cannot be read as a file')


type FileProblem = HclSyntaxError | UnreadableFileError


class SourceNotLocalError(HarnessError):
    def __init__(self, *, source: str) -> None:
        self.source = source
        super().__init__(f'module source is not a literal local path: {source}')


class SourceOutsideRootError(HarnessError):
    def __init__(self, *, source: str, root: Path) -> None:
        self.source = source
        self.root = root
        super().__init__(f'module source {source} leaves the project root {root}')
