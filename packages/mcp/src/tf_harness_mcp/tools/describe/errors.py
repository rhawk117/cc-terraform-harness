from typing import TYPE_CHECKING

from tf_harness_mcp.errors import HarnessError

if TYPE_CHECKING:
    from pathlib import Path


class DescribeTargetError(HarnessError):
    def __init__(self, *, path: Path) -> None:
        self.path = path
        super().__init__(f'not a directory, a .tf file or a .tfvars file: {path}')
