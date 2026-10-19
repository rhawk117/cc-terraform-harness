"""Failures raised by the shared tool policies."""

from typing import TYPE_CHECKING

from tf_harness_mcp.errors import HarnessError

if TYPE_CHECKING:
    from pathlib import Path


class PathOutsideRootError(HarnessError):
    def __init__(self, *, path: Path, root: Path) -> None:
        self.path = path
        self.root = root
        super().__init__(f'path leaves the project root {root}: {path}')


class OutputOverBudgetError(HarnessError):
    def __init__(self, *, size: int, ceiling: int) -> None:
        self.size = size
        self.ceiling = ceiling
        super().__init__(f'output of {size} bytes cannot be cut to {ceiling} bytes')
