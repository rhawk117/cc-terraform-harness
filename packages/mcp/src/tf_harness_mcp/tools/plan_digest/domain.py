"""Values the plan digest is built from."""

from dataclasses import dataclass, field
from enum import StrEnum

REPLACEMENT_ACTIONS = (('delete', 'create'), ('create', 'delete'))
NO_OP = 'no-op'


class ActionKind(StrEnum):
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
    REPLACE_DELETE_FIRST = 'replace-delete-first'
    REPLACE_CREATE_FIRST = 'replace-create-first'
    READ = 'read'
    NOOP = 'no-op'
    FORGET = 'forget'
    UNSUPPORTED = 'unsupported'


class Flag(StrEnum):
    DESTROY_STATEFUL = 'destroy-stateful'
    MASS_DESTROY = 'mass-destroy'
    IMPORT = 'import'
    DRIFT = 'drift'
    OPEN_CIDR = 'open-cidr'
    PUBLIC_FLAG = 'public-flag'
    DELETION_PROTECTION_OFF = 'deletion-protection-off'
    ENCRYPTION_OFF = 'encryption-off'
    IAM_CHANGE = 'iam-change'
    SECURITY_RULE_CHANGE = 'security-rule-change'
    UNSUPPORTED_ACTION = 'unsupported-action'


@dataclass(slots=True, kw_only=True, frozen=True)
class ResourceChange:
    address: str
    actions: list[str]
    replacement: bool
    forced_by: list[str] = field(default_factory=list)
    sensitive_attributes: list[str] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)


@dataclass(slots=True, kw_only=True, frozen=True)
class Move:
    from_address: str
    to_address: str
    with_change: bool
