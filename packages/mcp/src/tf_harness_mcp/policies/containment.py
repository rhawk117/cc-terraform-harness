"""Path containment: a tool argument may only name a path inside the project root."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import Field

from tf_harness_mcp.policies.errors import PathOutsideRootError

PROJECT_PATH_MARKER = 'x-project-path'

type ProjectPath = Annotated[Path, Field(json_schema_extra={PROJECT_PATH_MARKER: True})]


@dataclass(slots=True, kw_only=True, frozen=True)
class PathContainmentPolicy:
    root: Path
    path: Path

    @property
    def resolved_root(self) -> Path:
        return self.root.resolve()

    @property
    def resolved(self) -> Path:
        return self.resolved_root.joinpath(self.path).resolve()

    @property
    def is_inside_root(self) -> bool:
        return self.resolved.is_relative_to(self.resolved_root)

    def get_path_problem(self) -> PathOutsideRootError | None:
        if not self.is_inside_root:
            return PathOutsideRootError(path=self.path, root=self.root)

        return None


def resolve_project_path(root: Path, path: Path) -> Path:
    policy = PathContainmentPolicy(root=root, path=path)
    if problem := policy.get_path_problem():
        raise problem

    return policy.resolved
