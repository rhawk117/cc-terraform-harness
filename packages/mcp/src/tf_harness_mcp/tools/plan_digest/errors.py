from typing import TYPE_CHECKING

from tf_harness_mcp.errors import HarnessError

if TYPE_CHECKING:
    from pathlib import Path


class PlanFileNotFoundError(HarnessError):
    def __init__(self, *, path: Path) -> None:
        self.path = path
        super().__init__(f'not an existing file: {path}')


class PlanTooLargeError(HarnessError):
    def __init__(self, *, path: Path, size: int, cap: int) -> None:
        self.path = path
        self.size = size
        self.cap = cap
        super().__init__(f'plan file {path} is {size} bytes, over the {cap} byte read cap')


class PlanNotJsonError(HarnessError):
    def __init__(self, *, path: Path) -> None:
        self.path = path
        super().__init__(
            f'{path} is not JSON; render a plan file with `terraform show -json <planfile>`'
        )


class NotAPlanError(HarnessError):
    def __init__(self, *, path: Path) -> None:
        self.path = path
        super().__init__(
            f'{path} is JSON but not a plan (no planned_values); '
            'render a plan file with `terraform show -json <planfile>`'
        )
