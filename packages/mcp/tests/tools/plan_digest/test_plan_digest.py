import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.settings import Settings

if TYPE_CHECKING:
    from mcp import Client
    from mcp.types import CallToolResult
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

FIXTURE_PLAN = Path(__file__).with_name('plan.json')
LOWERED_CAP = 100


def error_text(result: CallToolResult) -> str:
    assert result.is_error
    return ''.join(getattr(block, 'text', '') for block in result.content)


@pytest.fixture
def plan_file(project_root: Path) -> Path:
    return Path(shutil.copy(FIXTURE_PLAN, project_root.joinpath('plan.json')))


@pytest.fixture
async def digest(client: Client, plan_file: Path) -> dict[str, object]:
    result = await client.call_tool('plan_digest', {'path': str(plan_file)})
    assert not result.is_error
    assert result.structured_content is not None
    return result.structured_content


@pytest.mark.unit
class TestPlanDigest:
    async def test_counts_resources_per_action(self, digest: dict[str, object]) -> None:
        assert digest['counts'] == {'no-op': 1, 'delete': 1, 'replace': 1, 'update': 1}

    async def test_lists_changes_with_replacements_marked_and_no_ops_left_out(
        self, digest: dict[str, object]
    ) -> None:
        assert digest['resource_changes'] == [
            {'address': 'terraform_data.removed[0]', 'actions': ['delete'], 'replacement': False},
            {
                'address': 'terraform_data.replaced',
                'actions': ['delete', 'create'],
                'replacement': True,
            },
            {'address': 'terraform_data.updated', 'actions': ['update'], 'replacement': False},
        ]

    async def test_lists_output_changes_by_name(self, digest: dict[str, object]) -> None:
        assert digest['output_changes'] == {'gen': ['update']}

    async def test_marks_a_create_before_destroy_replacement(
        self, client: Client, project_root: Path
    ) -> None:
        plan = {
            'planned_values': {},
            'resource_changes': [{'address': 'a.b', 'change': {'actions': ['create', 'delete']}}],
        }
        path = project_root.joinpath('cbd.json')
        path.write_text(json.dumps(plan))

        result = await client.call_tool('plan_digest', {'path': str(path)})

        assert result.structured_content is not None
        assert result.structured_content['counts'] == {'replace': 1}
        assert result.structured_content['resource_changes'][0]['replacement']

    async def test_digests_a_plan_without_resource_changes(
        self, client: Client, project_root: Path
    ) -> None:
        path = project_root.joinpath('empty.json')
        path.write_text(json.dumps({'planned_values': {}}))

        result = await client.call_tool('plan_digest', {'path': str(path)})

        assert result.structured_content is not None
        assert result.structured_content['counts'] == {}
        assert result.structured_content['resource_changes'] == []

    async def test_starts_no_subprocess(
        self, digest: dict[str, object], recording_runner: RecordingCommandRunner
    ) -> None:
        assert digest
        assert not recording_runner.calls


@pytest.mark.unit
class TestPlanDigestWithinBudget:
    @pytest.fixture
    def settings(self, project_root: Path) -> Settings:
        return Settings(project_root=project_root, output_budget_bytes=1500)

    async def test_cuts_the_resource_list_to_the_budget(
        self, client: Client, project_root: Path
    ) -> None:
        changes = [
            {'address': f'null_resource.r{index}', 'change': {'actions': ['create']}}
            for index in range(200)
        ]
        path = project_root.joinpath('big.json')
        path.write_text(json.dumps({'planned_values': {}, 'resource_changes': changes}))

        result = await client.call_tool('plan_digest', {'path': str(path)})

        assert result.structured_content is not None
        assert len(json.dumps(result.structured_content, separators=(',', ':'))) <= 1500
        assert result.structured_content['counts'] == {'create': 200}
        assert result.structured_content['resource_changes_omitted'] > 0


@pytest.mark.unit
class TestPlanDigestRefusals:
    @pytest.fixture
    def settings(self, project_root: Path) -> Settings:
        return Settings(project_root=project_root, plan_read_cap_bytes=LOWERED_CAP)

    async def call(self, client: Client, path: Path) -> str:
        return error_text(await client.call_tool('plan_digest', {'path': str(path)}))

    async def test_refuses_a_file_over_the_cap_before_reading_it(
        self, client: Client, project_root: Path
    ) -> None:
        path = project_root.joinpath('huge.json')
        path.write_text('x' * (LOWERED_CAP + 1))

        text = await self.call(client, path)

        assert f'over the {LOWERED_CAP} byte read cap' in text
        assert 'terraform show -json' not in text

    async def test_refuses_a_binary_plan_naming_terraform_show(
        self, client: Client, project_root: Path
    ) -> None:
        path = project_root.joinpath('tfplan')
        path.write_bytes(b'PK\x03\x04' + b'\x00' * 20)

        assert 'is not JSON' in await self.call(client, path)
        assert 'terraform show -json' in await self.call(client, path)

    @pytest.mark.parametrize('content', ['{}', '[]', '{"format_version": "1.0", "values": {}}'])
    async def test_refuses_json_that_is_not_a_plan(
        self, client: Client, project_root: Path, content: str
    ) -> None:
        path = project_root.joinpath('state.json')
        path.write_text(content)

        text = await self.call(client, path)

        assert 'not a plan' in text
        assert 'terraform show -json' in text

    async def test_refuses_a_missing_path(self, client: Client, project_root: Path) -> None:
        text = await self.call(client, project_root.joinpath('absent.json'))

        assert 'not an existing file' in text

    async def test_refuses_a_directory(self, client: Client, project_root: Path) -> None:
        assert 'not an existing file' in await self.call(client, project_root)

    async def test_refusals_start_no_subprocess(
        self, client: Client, project_root: Path, recording_runner: RecordingCommandRunner
    ) -> None:
        await self.call(client, project_root.joinpath('absent.json'))

        assert not recording_runner.calls
