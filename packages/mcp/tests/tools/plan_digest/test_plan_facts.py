import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tf_harness_mcp.settings import Settings

if TYPE_CHECKING:
    from mcp import Client

RISKY_PLAN = Path(__file__).with_name('risky_plan.json')
type Digest = dict[str, Any]


def resource_flag_cases() -> pytest.MarkDecorator:
    cases = {
        'destroy-stateful': 'aws_db_instance.retired',
        'import': 'terraform_data.adopted',
        'open-cidr': 'aws_security_group.open',
        'public-flag': 'aws_s3_bucket.exposed',
        'deletion-protection-off': 'aws_rds_cluster.unguarded',
        'encryption-off': 'aws_rds_cluster.unguarded',
        'iam-change': 'aws_iam_role_policy.grant',
        'security-rule-change': 'aws_security_group.open',
        'unsupported-action': 'terraform_data.odd',
    }
    return pytest.mark.parametrize(
        ('flag', 'address'), [pytest.param(*case, id=case[0]) for case in cases.items()]
    )


@pytest.fixture
def risky_plan(project_root: Path) -> Path:
    return Path(shutil.copy(RISKY_PLAN, project_root.joinpath('risky.json')))


@pytest.fixture
async def risky_digest(client: Client, risky_plan: Path) -> Digest:
    result = await client.call_tool('plan_digest', {'path': str(risky_plan)})
    assert not result.is_error
    assert result.structured_content is not None
    return result.structured_content


def find_resource(digest: Digest, address: str) -> Digest:
    return next(item for item in digest['resource_changes'] if item['address'] == address)


@pytest.mark.unit
class TestPlanFacts:
    async def test_lists_forced_by_attribute_paths(self, risky_digest: Digest) -> None:
        replaced = find_resource(risky_digest, 'aws_db_instance.replaced')

        assert replaced['forced_by'] == ['engine', 'tags.0']

    async def test_lists_sensitive_attributes_by_name_only(self, risky_digest: Digest) -> None:
        replaced = find_resource(risky_digest, 'aws_db_instance.replaced')

        assert replaced['sensitive_attributes'] == ['password']
        assert find_resource(risky_digest, 'aws_db_instance.retired')['sensitive_attributes'] == []

    async def test_lists_moves_with_whether_the_resource_also_changes(
        self, risky_digest: Digest
    ) -> None:
        assert risky_digest['moves'] == [
            {
                'from_address': 'terraform_data.original',
                'to_address': 'terraform_data.renamed',
                'with_change': False,
            }
        ]

    async def test_lists_imports_by_address(self, risky_digest: Digest) -> None:
        assert risky_digest['imports'] == ['terraform_data.adopted']

    async def test_lists_drifted_addresses(self, risky_digest: Digest) -> None:
        assert risky_digest['drifted'] == ['aws_instance.drifted']

    @resource_flag_cases()
    async def test_flags_a_risky_resource(
        self, risky_digest: Digest, flag: str, address: str
    ) -> None:
        assert flag in find_resource(risky_digest, address)['flags']

    async def test_does_not_flag_an_open_cidr_under_egress(self, risky_digest: Digest) -> None:
        flags = find_resource(risky_digest, 'aws_security_group.egress_only')['flags']

        assert 'open-cidr' not in flags

    async def test_does_not_flag_an_encryption_key_that_became_unknown(
        self, risky_digest: Digest
    ) -> None:
        flags = find_resource(risky_digest, 'aws_rds_cluster.rekeyed')['flags']

        assert 'encryption-off' not in flags

    @pytest.mark.parametrize('flag', ['mass-destroy', 'drift', 'unsupported-action'])
    async def test_plan_flags_name_the_plan_wide_risk(
        self, risky_digest: Digest, flag: str
    ) -> None:
        assert flag in risky_digest['plan_flags']

    async def test_flags_nothing_on_a_quiet_resource(
        self, client: Client, project_root: Path
    ) -> None:
        path = project_root.joinpath('quiet.json')
        change = {
            'address': 'null_resource.a',
            'type': 'null_resource',
            'change': {'actions': ['create']},
        }
        path.write_text(json.dumps({'planned_values': {}, 'resource_changes': [change]}))

        result = await client.call_tool('plan_digest', {'path': str(path)})

        content = result.structured_content
        assert content is not None
        assert content['resource_changes'][0]['flags'] == []
        assert content['plan_flags'] == []
        assert content['moves'] == content['imports'] == content['drifted'] == []


@pytest.mark.unit
class TestPlanFactsWithinBudget:
    @pytest.fixture
    def settings(self, project_root: Path) -> Settings:
        return Settings(project_root=project_root, output_budget_bytes=1500)

    async def test_cuts_the_drifted_list_and_counts_the_omitted(
        self, client: Client, project_root: Path
    ) -> None:
        drift = [{'address': f'null_resource.drifted{index}'} for index in range(200)]
        path = project_root.joinpath('drift.json')
        path.write_text(json.dumps({'planned_values': {}, 'resource_drift': drift}))

        result = await client.call_tool('plan_digest', {'path': str(path)})

        content = result.structured_content
        assert content is not None
        assert content['drifted_omitted'] > 0
        assert len(content['drifted']) + content['drifted_omitted'] == 200
