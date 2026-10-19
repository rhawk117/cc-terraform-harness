"""Risk heuristics over plan changes; each flag is a prompt to look, not a verdict."""

import re
from typing import TYPE_CHECKING, Any

from tf_harness_mcp.tools.plan_digest.domain import ActionKind, Flag

if TYPE_CHECKING:
    from collections.abc import Iterator

RECOGNIZED_ACTIONS: dict[tuple[str, ...], ActionKind] = {
    ('no-op',): ActionKind.NOOP,
    ('create',): ActionKind.CREATE,
    ('read',): ActionKind.READ,
    ('update',): ActionKind.UPDATE,
    ('delete',): ActionKind.DELETE,
    ('forget',): ActionKind.FORGET,
    ('delete', 'create'): ActionKind.REPLACE_DELETE_FIRST,
    ('create', 'delete'): ActionKind.REPLACE_CREATE_FIRST,
}
STATEFUL_TYPE_MARKERS = (
    'db_instance', 'rds_cluster', 'dynamodb_table', 'sql_database_instance', 'cosmosdb',
    'elasticache', 'redis', 'memorystore', 'documentdb', 'neptune', 'spanner', 'bigtable',
    'mssql', 'postgresql', 'mysql', 'mariadb', 'redshift', 's3_bucket', 'storage_bucket',
    'storage_account', 'storage_container', 'ebs_volume', 'compute_disk', 'managed_disk',
    'persistent_volume', 'efs_file_system', 'fsx', 'filestore', 'kms_key', 'kms_crypto_key',
    'key_vault', 'secretsmanager_secret', 'secret_manager_secret', 'ssm_parameter',
    'tls_private_key', 'acm_certificate', 'certificate', 'sqs_queue', 'kinesis_stream',
    'pubsub_topic', 'pubsub_subscription', 'servicebus', 'eventhub', 'msk_cluster', 'kafka',
    'iam_user', 'iam_role', 'service_account', 'cognito_user_pool', 'identity_pool',
    'eks_cluster', 'container_cluster', 'kubernetes_cluster', 'gke', 'aks',
)  # fmt: skip
IAM_TYPE_MARKERS = (
    'iam',
    'policy',
    'role_binding',
    'role_assignment',
    'permission',
    'access_control',
)
SECURITY_RULE_TYPE_MARKERS = ('security_group', 'firewall', 'network_acl', 'nsg', 'network_policy')
OPEN_CIDRS = frozenset({'0.0.0.0/0', '::/0'})
PUBLIC_FLAG_KEYS = frozenset({
    'publicly_accessible',
    'public_network_access_enabled',
    'map_public_ip_on_launch',
    'assign_public_ip',
})
PUBLIC_ACL_VALUES = frozenset({'public-read', 'public-read-write'})
PROTECTION_KEYS = frozenset({
    'deletion_protection',
    'prevent_destroy',
    'enable_deletion_protection',
    'purge_protection_enabled',
})
ENCRYPTION_KEYS = frozenset({'storage_encrypted', 'encrypted', 'encryption_enabled', 'kms_key_id'})
DESTRUCTIVE_ACTIONS = frozenset({
    ActionKind.DELETE,
    ActionKind.REPLACE_DELETE_FIRST,
    ActionKind.REPLACE_CREATE_FIRST,
})
LOSSY_ACTIONS = frozenset({ActionKind.DELETE, ActionKind.REPLACE_DELETE_FIRST})
QUIET_ACTIONS = frozenset({ActionKind.NOOP, ActionKind.READ, ActionKind.FORGET})
MASS_DESTROY_ABSOLUTE = 10
MASS_DESTROY_RATIO = 0.3
MASS_DESTROY_MINIMUM = 3
LEAF_INDEX = re.compile(r'\[\d+\]$')
PATH_SEGMENT_SPLIT = re.compile(r'[.\[]')


def classify(actions: list[str]) -> ActionKind:
    return RECOGNIZED_ACTIONS.get(tuple(actions), ActionKind.UNSUPPORTED)


def matches_any(resource_type: str, markers: tuple[str, ...]) -> bool:
    return any(marker in resource_type for marker in markers)


def type_flags(resource_type: str, action: ActionKind) -> Iterator[Flag]:
    if action in QUIET_ACTIONS:
        return

    if action in LOSSY_ACTIONS and matches_any(resource_type, STATEFUL_TYPE_MARKERS):
        yield Flag.DESTROY_STATEFUL

    if matches_any(resource_type, IAM_TYPE_MARKERS):
        yield Flag.IAM_CHANGE

    if matches_any(resource_type, SECURITY_RULE_TYPE_MARKERS):
        yield Flag.SECURITY_RULE_CHANGE


def walk_values(value: Any, path: str = '') -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_values(child, f'{path}.{key}' if path else str(key))
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_values(child, f'{path}[{index}]')
        return

    yield path, value


def leaf_key(path: str) -> str:
    return LEAF_INDEX.sub('', path).rsplit('.', 1)[-1]


def is_egress_path(path: str) -> bool:
    return any(segment.startswith('egress') for segment in PATH_SEGMENT_SPLIT.split(path))


def is_public_value(key: str, value: object) -> bool:
    if key in PUBLIC_FLAG_KEYS:
        return value is True

    return key == 'acl' and value in PUBLIC_ACL_VALUES


def exposure_flags(after: dict[str, Any] | None) -> set[Flag]:
    found: set[Flag] = set()
    for path, value in walk_values(after or {}):
        if isinstance(value, str) and value in OPEN_CIDRS and not is_egress_path(path):
            found.add(Flag.OPEN_CIDR)

        if is_public_value(leaf_key(path), value):
            found.add(Flag.PUBLIC_FLAG)

    return found


def transition_flags(before: dict[str, Any] | None, after: dict[str, Any] | None) -> set[Flag]:
    if before is None or after is None:
        return set()

    found: set[Flag] = set()
    if any(before.get(key) is True and after.get(key) is False for key in PROTECTION_KEYS):
        found.add(Flag.DELETION_PROTECTION_OFF)

    if any(before.get(key) and not after.get(key) for key in ENCRYPTION_KEYS):
        found.add(Flag.ENCRYPTION_OFF)

    return found


def mass_destroy(actions: list[ActionKind], total: int) -> bool:
    destructive = sum(1 for action in actions if action in DESTRUCTIVE_ACTIONS)
    ratio = destructive / total if total else 0
    hits_ratio = destructive >= MASS_DESTROY_MINIMUM and ratio >= MASS_DESTROY_RATIO
    return destructive >= MASS_DESTROY_ABSOLUTE or hits_ratio


def is_marked(value: object) -> bool:
    return any(leaf is True for _, leaf in walk_values(value))
