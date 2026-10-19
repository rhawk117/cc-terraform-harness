"""Which hook file paths may reach a handler."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from tf_harness_mcp.policies.containment import PathContainmentPolicy

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.policies.errors import PathOutsideRootError

TERRAFORM_SUFFIXES: Final[frozenset[str]] = frozenset({'.tf', '.tfvars'})


@dataclass(slots=True, kw_only=True, frozen=True)
class HookFilePolicy:
    project_root: Path
    file_path: Path

    @property
    def is_terraform_file(self) -> bool:
        return self.file_path.suffix in TERRAFORM_SUFFIXES

    def get_file_problem(self) -> PathOutsideRootError | None:
        containment = PathContainmentPolicy(root=self.project_root, path=self.file_path)
        return containment.get_path_problem()
