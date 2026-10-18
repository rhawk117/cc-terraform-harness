"""Which module sources the graph follows: literal local paths that stay inside the root."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tf_harness_mcp.policies.containment import PathContainmentPolicy
from tf_harness_mcp.structure.errors import SourceNotLocalError, SourceOutsideRootError

if TYPE_CHECKING:
    from pathlib import Path

LOCAL_PREFIXES = ('./', '../')

type SourceIssue = SourceNotLocalError | SourceOutsideRootError


@dataclass(slots=True, kw_only=True, frozen=True)
class LocalSourcePolicy:
    root: Path
    module_dir: Path
    source: str

    @property
    def is_local(self) -> bool:
        return self.source.startswith(LOCAL_PREFIXES)

    @property
    def target(self) -> Path:
        return self.module_dir.joinpath(self.source).resolve()

    @property
    def is_inside_root(self) -> bool:
        return PathContainmentPolicy(root=self.root, path=self.target).is_inside_root

    def get_source_problem(self) -> SourceIssue | None:
        if not self.is_local:
            return SourceNotLocalError(source=self.source)

        if not self.is_inside_root:
            return SourceOutsideRootError(source=self.source, root=self.root)

        return None
