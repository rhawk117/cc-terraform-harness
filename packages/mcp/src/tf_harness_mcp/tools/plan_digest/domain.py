"""Values the plan digest is built from."""

from dataclasses import dataclass

REPLACEMENT_ACTIONS = (('delete', 'create'), ('create', 'delete'))
NO_OP = 'no-op'


@dataclass(slots=True, kw_only=True, frozen=True)
class ResourceChange:
    address: str
    actions: list[str]
    replacement: bool
