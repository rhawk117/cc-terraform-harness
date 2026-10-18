from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tf_harness_mcp.structure.domain import Block
from tf_harness_mcp.tools.change_impact.domain import LineRange
from tf_harness_mcp.tools.change_impact.policy import RangeTouchPolicy, normalize_expression

from .conftest import BASE

if TYPE_CHECKING:
    from mcp import Client

    from .conftest import GitHarness

pytestmark = pytest.mark.unit

BASE_SHARED = """\
variable "name" {
  type = string
}

variable "gone" {}

output "id" {
  value = 1
}

output "old" {
  value = 2
}

resource "null_resource" "a" {
}

resource "null_resource" "b" {}
"""
CURRENT_SHARED = """\
variable "name" {
  type = list(string)
}

variable "added" {
  default = "x"
}

output "id" {
  value = 1
}

resource "null_resource" "a" {
  triggers = {}
}

resource "null_resource" "c" {}
"""
SHARED_DIFF = '@@ -2 +2 @@\n@@ -16,0 +14 @@\n'
CALL = 'module "shared" {{\n  source = "{source}"\n}}\n'


def write(root: Path, relative: str, text: str) -> None:
    path = root.joinpath(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def block_at(start_line: int, end_line: int) -> Block:
    return Block(
        kind='resource', labels=(), file=Path('main.tf'), start_line=start_line, end_line=end_line
    )


async def read_impact(client: Client, path: Path, **arguments: str) -> dict[str, Any]:
    result = await client.call_tool('change_impact', {'path': str(path)} | arguments)
    text = ''.join(getattr(block, 'text', '') for block in result.content)
    assert not result.is_error, text
    assert result.structured_content is not None
    return result.structured_content


async def read_failure(client: Client, path: Path, **arguments: str) -> str:
    result = await client.call_tool('change_impact', {'path': str(path)} | arguments)
    assert result.is_error
    return ''.join(getattr(block, 'text', '') for block in result.content)


@pytest.fixture
def shared(project_root: Path) -> Path:
    write(project_root, 'modules/shared/main.tf', CURRENT_SHARED)
    write(project_root, 'modules/mid/main.tf', CALL.format(source='../shared'))
    write(project_root, 'stacks/prod/main.tf', CALL.format(source='../../modules/shared'))
    write(project_root, 'stacks/dev/main.tf', CALL.format(source='../../modules/mid'))
    return project_root.joinpath('modules', 'shared')


@pytest.fixture
def scripted(git_harness: GitHarness) -> GitHarness:
    git_harness.script_resolution('HEAD')
    git_harness.script_merge_base()
    git_harness.script_name_status('M', 'main.tf')
    git_harness.script_hunks('main.tf', SHARED_DIFF)
    git_harness.script_base_content('main.tf', BASE_SHARED)
    git_harness.script_untracked()
    return git_harness


def touch_cases() -> pytest.MarkDecorator:
    cases = [
        pytest.param(LineRange(start=3, count=1), 3, 5, True, id='first-line'),
        pytest.param(LineRange(start=5, count=2), 3, 5, True, id='last-line'),
        pytest.param(LineRange(start=6, count=1), 3, 5, False, id='after'),
        pytest.param(LineRange(start=1, count=2), 3, 5, False, id='before'),
        pytest.param(LineRange(start=3, count=0), 3, 5, True, id='removal-after-first-line'),
        pytest.param(LineRange(start=5, count=0), 3, 5, False, id='removal-after-last-line'),
        pytest.param(LineRange(start=2, count=0), 3, 5, False, id='removal-before'),
    ]
    return pytest.mark.parametrize(('lines', 'start', 'end', 'touches'), cases)


class TestPolicies:
    @touch_cases()
    def test_range_touches_a_block_by_overlap_or_removal(
        self, lines: LineRange, start: int, end: int, *, touches: bool
    ) -> None:
        policy = RangeTouchPolicy(lines=lines, block=block_at(start, end))

        assert policy.touches is touches

    def test_expression_whitespace_runs_collapse(self) -> None:
        assert normalize_expression('object({\n    a = string\n  })') == 'object({ a = string })'


@pytest.mark.usefixtures('scripted')
class TestChangeImpact:
    async def test_blocks_carry_status_and_location(self, client: Client, shared: Path) -> None:
        impact = await read_impact(client, shared)

        file = str(shared.joinpath('main.tf'))
        found = {
            (block['labels'][-1], block['status']): (
                block['location']['file'],
                block['location']['start_line'],
                block['location']['end_line'],
            )
            for block in impact['blocks']
        }
        assert impact['base_commit'] == BASE
        assert found == {
            ('name', 'modified'): (file, 1, 3),
            ('gone', 'removed'): (file, 5, 5),
            ('added', 'added'): (file, 5, 7),
            ('old', 'removed'): (file, 11, 13),
            ('a', 'modified'): (file, 13, 15),
            ('b', 'removed'): (file, 18, 18),
            ('c', 'added'): (file, 17, 17),
        }

    async def test_interface_changes_compare_the_base_with_the_working_tree(
        self, client: Client, shared: Path
    ) -> None:
        impact = await read_impact(client, shared)

        found = {
            (change['kind'], change['name'], change['change'], change['before'], change['after'])
            for change in impact['interface']
        }
        assert found == {
            ('variable', 'added', 'added', None, None),
            ('variable', 'gone', 'removed', None, None),
            ('variable', 'name', 'type_changed', 'string', 'list(string)'),
            ('output', 'old', 'removed', None, None),
        }
        assert {change['module'] for change in impact['interface']} == {str(shared)}

    async def test_every_reaching_root_reports_its_shortest_path(
        self, client: Client, shared: Path, project_root: Path
    ) -> None:
        impact = await read_impact(client, shared)

        found = {root['root']: root['path'] for root in impact['roots']}
        stacks = project_root.joinpath('stacks')
        modules = project_root.joinpath('modules')
        assert found == {
            str(stacks.joinpath('dev')): [
                str(stacks.joinpath('dev')),
                str(modules.joinpath('mid')),
                str(shared),
            ],
            str(stacks.joinpath('prod')): [str(stacks.joinpath('prod')), str(shared)],
        }

    async def test_git_runs_in_the_given_path_not_the_project_root(
        self, client: Client, shared: Path, scripted: GitHarness
    ) -> None:
        await read_impact(client, shared)

        assert {call.command.cwd for call in scripted.runner.calls} == {shared}

    async def test_base_ref_reaches_git_as_resolved(
        self, client: Client, shared: Path, scripted: GitHarness
    ) -> None:
        scripted.script_resolution('main')

        impact = await read_impact(client, shared, base_ref='main')

        assert impact['base_commit'] == BASE


class TestChangeImpactProblems:
    async def test_option_like_base_ref_is_refused_before_git(
        self, client: Client, project_root: Path, git_harness: GitHarness
    ) -> None:
        text = await read_failure(client, project_root, base_ref='--output=x')

        assert 'starts with a dash' in text
        assert not git_harness.runner.calls

    async def test_syntax_error_in_a_changed_file_is_reported(
        self, client: Client, project_root: Path, git_harness: GitHarness
    ) -> None:
        write(project_root, 'main.tf', 'variable "x" {\n')
        git_harness.script_resolution('HEAD')
        git_harness.script_merge_base()
        git_harness.script_name_status('M', 'main.tf')
        git_harness.script_hunks('main.tf', '@@ -1 +1 @@\n')
        git_harness.script_base_content('main.tf', 'variable "x" {}\n')
        git_harness.script_untracked()

        text = await read_failure(client, project_root)

        assert 'does not parse as HCL' in text
