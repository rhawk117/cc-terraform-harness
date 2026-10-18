"""Read one plan JSON document and digest it; no subprocess is started."""

from collections import Counter
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from tf_harness_mcp.policies import containment
from tf_harness_mcp.policies.budget import create_output_budget
from tf_harness_mcp.tools.plan_digest.domain import NO_OP, REPLACEMENT_ACTIONS, ResourceChange
from tf_harness_mcp.tools.plan_digest.errors import (
    NotAPlanError,
    PlanFileNotFoundError,
    PlanNotJsonError,
    PlanTooLargeError,
)
from tf_harness_mcp.tools.plan_digest.schemas import PlanDocument

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.policies.budget import OutputBudget
    from tf_harness_mcp.settings import Settings


def is_replacement(actions: list[str]) -> bool:
    return tuple(actions) in REPLACEMENT_ACTIONS


def get_action_label(change: ResourceChange) -> str:
    return 'replace' if change.replacement else '+'.join(change.actions)


def parse_plan(path: Path, raw: bytes) -> PlanDocument:
    try:
        document = PlanDocument.model_validate_json(raw)
    except ValidationError as err:
        if any(problem['type'] == 'json_invalid' for problem in err.errors()):
            raise PlanNotJsonError(path=path) from err

        raise NotAPlanError(path=path) from err

    return document


def digest_plan(path: Path, plan: PlanDocument) -> dict[str, Any]:
    changes = [
        ResourceChange(
            address=item.address,
            actions=item.change.actions,
            replacement=is_replacement(item.change.actions),
        )
        for item in plan.resource_changes
    ]
    counts = Counter(get_action_label(change) for change in changes)
    return {
        'path': str(path),
        'counts': dict(counts),
        'resource_changes': [asdict(change) for change in changes if change.actions != [NO_OP]],
        'output_changes': [
            {'name': name, 'actions': out.actions} for name, out in plan.output_changes.items()
        ],
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class PlanDigestTool:
    root: Path
    budget: OutputBudget
    read_cap_bytes: int

    def read_plan(self, path: containment.ProjectPath) -> tuple[Path, bytes]:
        resolved = containment.resolve_project_path(self.root, path)
        if not resolved.is_file():
            raise PlanFileNotFoundError(path=resolved)

        size = resolved.stat().st_size
        if size > self.read_cap_bytes:
            raise PlanTooLargeError(path=resolved, size=size, cap=self.read_cap_bytes)

        with resolved.open('rb') as handle:
            raw = handle.read(self.read_cap_bytes + 1)

        if len(raw) > self.read_cap_bytes:
            raise PlanTooLargeError(path=resolved, size=len(raw), cap=self.read_cap_bytes)

        return resolved, raw

    async def plan_digest(self, path: containment.ProjectPath) -> dict[str, Any]:
        """Summarize one plan JSON document without changing anything.

        Reads a plan rendered by `terraform show -json <planfile>` and returns the count of
        resources per action (a replacement counts as replace), each changed resource with its
        address and actions (replacements marked, no-op resources left out) and the output
        changes. The path is relative to the project root or absolute inside it. A binary plan
        file or state JSON is refused; render it with `terraform show -json` first.
        """
        resolved, raw = self.read_plan(path)
        return self.budget.apply(digest_plan(resolved, parse_plan(resolved, raw)))


def create_plan_digest_tool(settings: Settings) -> PlanDigestTool:
    return PlanDigestTool(
        root=settings.project_root,
        budget=create_output_budget(settings),
        read_cap_bytes=settings.plan_read_cap_bytes,
    )
