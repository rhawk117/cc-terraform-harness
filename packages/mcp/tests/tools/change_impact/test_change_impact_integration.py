import asyncio
import shutil
from typing import TYPE_CHECKING, Any

import pytest
from tf_harness_mcp.runner.process import create_command_runner
from tf_harness_mcp.server import create_server
from tf_harness_mcp.tools.tests.results import read_tool_text

if TYPE_CHECKING:
    from pathlib import Path

    from mcp import Client
    from mcp.server.mcpserver import MCPServer
    from tf_harness_mcp.settings import Settings

GIT = shutil.which('git') or 'git'
GIT_CONFIG = (
    '-c',
    'user.name=Test',
    '-c',
    'user.email=test@example.com',
    '-c',
    'commit.gpgsign=false',
    '-c',
    'diff.mnemonicPrefix=true',
)
BASE_SHARED = """\
variable "region" {
  default = "a"
}

variable "zone" {
  default = "z"
}

variable "shape" {
  type = object({
    a = string
  })
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
EDITED_SHARED = """\
variable "region" {
  default = "b"
}

variable "zone" {
}

variable "shape" {
  type = object({ a = string })
}

variable "fresh" {}

output "id" {
  value = 1
}

output "extra" {
  value = 3
}

resource "null_resource" "a" {
  triggers = {}
}

resource "null_resource" "c" {}
"""
CALL = 'module "shared" {{\n  source = "{source}"\n}}\n'


async def run_git(repository: Path, *arguments: str) -> None:
    process = await asyncio.create_subprocess_exec(
        GIT, *GIT_CONFIG, *arguments, cwd=repository, stdout=asyncio.subprocess.DEVNULL
    )
    assert await process.wait() == 0


def write(root: Path, relative: str, text: str) -> None:
    path = root.joinpath(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


async def read_impact(client: Client, path: Path, **arguments: str) -> dict[str, Any]:
    result = await client.call_tool('change_impact', {'path': str(path)} | arguments)
    text = read_tool_text(result)
    assert not result.is_error, text
    assert result.structured_content is not None
    return result.structured_content


@pytest.mark.integration
@pytest.mark.skipif(shutil.which('git') is None, reason='git is not on PATH')
class TestChangeImpactWithGit:
    @pytest.fixture
    def server(self, settings: Settings) -> MCPServer:
        return create_server(settings, create_command_runner())

    @pytest.fixture
    async def shared(self, project_root: Path) -> Path:
        write(project_root, 'modules/shared/main.tf', BASE_SHARED)
        write(project_root, 'modules/mid/main.tf', CALL.format(source='../shared'))
        write(project_root, 'stacks/prod/main.tf', CALL.format(source='../../modules/shared'))
        write(project_root, 'stacks/dev/main.tf', CALL.format(source='../../modules/mid'))
        await run_git(project_root, 'init', '--quiet')
        await run_git(project_root, 'add', '.')
        await run_git(project_root, 'commit', '--quiet', '--message', 'base')
        write(project_root, 'modules/shared/main.tf', EDITED_SHARED)
        return project_root.joinpath('modules', 'shared')

    async def test_edit_to_a_shared_module_reports_blocks_roots_and_interface(
        self, client: Client, shared: Path, project_root: Path
    ) -> None:
        impact = await read_impact(client, shared)

        found = {
            (b['labels'][-1], b['status']): b['location']['start_line'] for b in impact['blocks']
        }
        assert found == {
            ('region', 'modified'): 1,
            ('zone', 'modified'): 5,
            ('shape', 'modified'): 8,
            ('gone', 'removed'): 15,
            ('fresh', 'added'): 12,
            ('old', 'removed'): 21,
            ('extra', 'added'): 18,
            ('a', 'modified'): 22,
            ('b', 'removed'): 28,
            ('c', 'added'): 26,
        }
        changes = {
            (c['kind'], c['name'], c['change'], c['before'], c['after'])
            for c in impact['interface']
        }
        assert changes == {
            ('variable', 'region', 'default_changed', '"a"', '"b"'),
            ('variable', 'zone', 'default_changed', '"z"', None),
            ('variable', 'gone', 'removed', None, None),
            ('variable', 'fresh', 'added', None, None),
            ('output', 'old', 'removed', None, None),
            ('output', 'extra', 'added', None, None),
        }
        stacks = project_root.joinpath('stacks')
        modules = project_root.joinpath('modules')
        assert {root['root']: root['path'] for root in impact['roots']} == {
            str(stacks.joinpath('dev')): [
                str(stacks.joinpath('dev')),
                str(modules.joinpath('mid')),
                str(shared),
            ],
            str(stacks.joinpath('prod')): [str(stacks.joinpath('prod')), str(shared)],
        }

    async def test_unchanged_tree_reports_nothing(
        self, client: Client, shared: Path, project_root: Path
    ) -> None:
        await run_git(project_root, 'commit', '--quiet', '--all', '--message', 'edit')

        impact = await read_impact(client, shared)

        assert impact['blocks'] == []
        assert impact['interface'] == []
        assert impact['roots'] == []

    async def test_base_ref_compares_against_an_earlier_commit(
        self, client: Client, shared: Path, project_root: Path
    ) -> None:
        await run_git(project_root, 'commit', '--quiet', '--all', '--message', 'edit')

        impact = await read_impact(client, shared, base_ref='HEAD~1')

        assert {b['status'] for b in impact['blocks']} == {'added', 'modified', 'removed'}
        assert len(impact['roots']) == 2
