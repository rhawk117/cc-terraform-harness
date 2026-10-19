"""Read one plan JSON document and digest it; no subprocess is started."""

from collections import Counter
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from tf_harness_mcp.policies import containment
from tf_harness_mcp.policies.budget import create_output_budget
from tf_harness_mcp.tools.plan_digest.domain import (
    NO_OP,
    REPLACEMENT_ACTIONS,
    ActionKind,
    Flag,
    Move,
    ResourceChange,
)
from tf_harness_mcp.tools.plan_digest.errors import (
    NotAPlanError,
    PlanFileNotFoundError,
    PlanNotJsonError,
    PlanTooLargeError,
)
from tf_harness_mcp.tools.plan_digest.policy import (
    classify,
    exposure_flags,
    is_marked,
    mass_destroy,
    transition_flags,
    type_flags,
)
from tf_harness_mcp.tools.plan_digest.schemas import PlanDocument

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.policies.budget import OutputBudget
    from tf_harness_mcp.settings import Settings
    from tf_harness_mcp.tools.plan_digest.schemas import PlannedResourceChange


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


def change_flags(item: PlannedResourceChange) -> list[Flag]:
    change = item.change
    action = classify(change.actions)
    flags = set(type_flags(item.type, action))
    if action is not ActionKind.DELETE:
        flags |= exposure_flags(change.after)

    flags |= transition_flags(change.before, change.after)
    if change.importing is not None:
        flags.add(Flag.IMPORT)

    if action is ActionKind.UNSUPPORTED:
        flags.add(Flag.UNSUPPORTED_ACTION)

    return sorted(flags)


def sensitive_keys(item: PlannedResourceChange) -> list[str]:
    marks = item.change.after_sensitive
    if not isinstance(marks, dict):
        return []

    return sorted(key for key, marked in marks.items() if is_marked(marked))


def to_resource_change(item: PlannedResourceChange) -> ResourceChange:
    return ResourceChange(
        address=item.address,
        actions=item.change.actions,
        replacement=is_replacement(item.change.actions),
        forced_by=[
            '.'.join(str(segment) for segment in path) for path in item.change.replace_paths or []
        ],
        sensitive_attributes=sensitive_keys(item),
        flags=change_flags(item),
    )


def find_moves(plan: PlanDocument) -> list[Move]:
    return [
        Move(
            from_address=item.previous_address,
            to_address=item.address,
            with_change=item.change.actions != [NO_OP],
        )
        for item in plan.resource_changes
        if item.previous_address not in {None, item.address}
    ]


def find_plan_flags(plan: PlanDocument) -> list[Flag]:
    actions = [classify(item.change.actions) for item in plan.resource_changes]
    flags: list[Flag] = []
    if mass_destroy(actions, len(actions)):
        flags.append(Flag.MASS_DESTROY)

    if plan.resource_drift:
        flags.append(Flag.DRIFT)

    if ActionKind.UNSUPPORTED in actions:
        flags.append(Flag.UNSUPPORTED_ACTION)

    return flags


def digest_plan(path: Path, plan: PlanDocument) -> dict[str, Any]:
    changes = [to_resource_change(item) for item in plan.resource_changes]
    counts = Counter(get_action_label(change) for change in changes)
    return {
        'path': str(path),
        'counts': dict(counts),
        'resource_changes': [asdict(change) for change in changes if change.actions != [NO_OP]],
        'output_changes': [
            {'name': name, 'actions': out.actions} for name, out in plan.output_changes.items()
        ],
        'moves': [asdict(move) for move in find_moves(plan)],
        'imports': [change.address for change in changes if Flag.IMPORT in change.flags],
        'drifted': [item.address for item in plan.resource_drift],
        'plan_flags': find_plan_flags(plan),
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
        changes, plus risk facts: per resource `forced_by` (attributes forcing a replacement),
        `sensitive_attributes` (names only) and `flags`, and top level `moves`, `imports`,
        `drifted` addresses and `plan_flags`. The path is relative to the project root or absolute
        inside it.
        A binary plan file or state JSON is refused; render it with `terraform show -json` first.
        """
        resolved, raw = self.read_plan(path)
        return self.budget.apply(digest_plan(resolved, parse_plan(resolved, raw)))


def create_plan_digest_tool(settings: Settings) -> PlanDigestTool:
    return PlanDigestTool(
        root=settings.project_root,
        budget=create_output_budget(settings),
        read_cap_bytes=settings.plan_read_cap_bytes,
    )
