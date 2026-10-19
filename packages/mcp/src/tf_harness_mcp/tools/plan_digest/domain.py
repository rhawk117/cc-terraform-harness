"""Values the plan digest is built from."""

from dataclasses import dataclass, field
from typing import Literal

type ActionKind = Literal[
    'create',
    'update',
    'delete',
    'replace-delete-first',
    'replace-create-first',
    'read',
    'no-op',
    'forget',
    'unsupported',
]
type Flag = Literal[
    'destroy-stateful',
    'mass-destroy',
    'import',
    'drift',
    'open-cidr',
    'public-flag',
    'deletion-protection-off',
    'encryption-off',
    'iam-change',
    'security-rule-change',
    'unsupported-action',
]


@dataclass(slots=True, kw_only=True, frozen=True)
class ResourceChange:
    address: str
    actions: list[str]
    kind: ActionKind
    forced_by: list[str] = field(default_factory=list)
    sensitive_attributes: list[str] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)

    @property
    def replacement(self) -> bool:
        return self.kind in {'replace-delete-first', 'replace-create-first'}


@dataclass(slots=True, kw_only=True, frozen=True)
class Move:
    from_address: str
    to_address: str
    with_change: bool
