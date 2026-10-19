"""Which hook file paths may reach a handler."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from tf_harness_mcp.policies.containment import PathContainmentPolicy
from tf_harness_mcp.runner.policy import AllowedCommand, ReadOnlyOptions

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.policies.errors import PathOutsideRootError

    from tf_harness_hooks.domain import Subcommand

TERRAFORM_SUFFIXES: Final[frozenset[str]] = frozenset({'.tf', '.tfvars'})
FMT_WRITE_PREFIX: Final[tuple[str, ...]] = ('terraform', 'fmt', '-list=true', '-no-color')


def runner_options(subcommand: Subcommand) -> ReadOnlyOptions:
    if subcommand == 'fmt':
        return ReadOnlyOptions(commands=(AllowedCommand(prefix=FMT_WRITE_PREFIX),))

    return ReadOnlyOptions()


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
