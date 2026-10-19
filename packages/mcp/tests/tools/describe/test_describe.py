import json
from typing import TYPE_CHECKING, Any

import pytest
from tf_harness_mcp.settings import Settings
from tf_harness_mcp.tools.tests.results import read_tool_text

if TYPE_CHECKING:
    from pathlib import Path

    from mcp import Client
    from mcp.types import CallToolResult
    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

MAIN_TF = """\
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    legacy = "~> 1.0"
  }
}

variable "region" {
  type        = string
  description = "Deployment region"
  default     = null
}

variable "names" {
  type        = list(string)
  description = <<-EOT
    Names to create
  EOT
  sensitive   = true
}

resource "aws_s3_bucket" "logs" {
  bucket = "logs"
}

data "aws_caller_identity" "current" {}

module "network" {
  source = "./network"
}

output "bucket" {
  value       = aws_s3_bucket.logs.id
  description = "The bucket"
}
"""
TFVARS = 'region = "eu-west-1"\nextra = 1\n'
BROKEN_TF = 'variable "oops" {\n'


def error_text(result: CallToolResult) -> str:
    assert result.is_error
    return read_tool_text(result)


async def describe(client: Client, path: Path) -> dict[str, Any]:
    result = await client.call_tool('describe', {'path': str(path)})
    assert not result.is_error
    assert result.structured_content is not None
    return result.structured_content


@pytest.fixture
def module_dir(project_root: Path) -> Path:
    directory = project_root.joinpath('stack')
    directory.mkdir()
    directory.joinpath('main.tf').write_text(MAIN_TF)
    directory.joinpath('prod.tfvars').write_text(TFVARS)
    return directory


@pytest.fixture
async def module_summary(client: Client, module_dir: Path) -> dict[str, Any]:
    return await describe(client, module_dir)


@pytest.fixture
def broken_module_file(module_dir: Path) -> Path:
    broken = module_dir.joinpath('broken.tf')
    broken.write_text(BROKEN_TF)
    return broken


@pytest.mark.unit
class TestDescribeModule:
    async def test_lists_variables_with_type_default_description_and_sensitivity(
        self, module_summary: dict[str, Any], module_dir: Path
    ) -> None:
        location = {'file': str(module_dir.joinpath('main.tf'))}

        assert module_summary['kind'] == 'module'
        assert [
            {key: value for key, value in entry.items() if key != 'location'}
            for entry in module_summary['variables']
        ] == [
            {
                'name': 'region',
                'type': 'string',
                'has_default': True,
                'description': 'Deployment region',
                'sensitive': False,
            },
            {
                'name': 'names',
                'type': 'list(string)',
                'has_default': False,
                'description': 'Names to create',
                'sensitive': True,
            },
        ]
        assert module_summary['variables'][0]['location'] == {
            **location,
            'start_line': 11,
            'end_line': 15,
        }

    async def test_lists_outputs_resources_data_sources_and_module_calls(
        self, module_summary: dict[str, Any]
    ) -> None:
        assert [entry['name'] for entry in module_summary['outputs']] == ['bucket']
        assert module_summary['outputs'][0]['description'] == 'The bucket'
        assert [(e['type'], e['name']) for e in module_summary['resources']] == [
            ('aws_s3_bucket', 'logs')
        ]
        assert [(e['type'], e['name']) for e in module_summary['data_sources']] == [
            ('aws_caller_identity', 'current')
        ]
        assert [(e['name'], e['source']) for e in module_summary['module_calls']] == [
            ('network', './network')
        ]

    async def test_locates_each_entry_kind_in_main_tf(
        self, module_summary: dict[str, Any], module_dir: Path
    ) -> None:
        main_tf = str(module_dir.joinpath('main.tf'))

        assert {
            kind: module_summary[kind][0]['location']
            for kind in ('outputs', 'resources', 'data_sources', 'module_calls')
        } == {
            'outputs': {'file': main_tf, 'start_line': 35, 'end_line': 38},
            'resources': {'file': main_tf, 'start_line': 25, 'end_line': 27},
            'data_sources': {'file': main_tf, 'start_line': 29, 'end_line': 29},
            'module_calls': {'file': main_tf, 'start_line': 31, 'end_line': 33},
        }

    async def test_lists_required_providers_with_constraints_and_local_names(
        self, module_summary: dict[str, Any]
    ) -> None:
        providers = [
            (e['local_name'], e['source'], e['version'])
            for e in module_summary['required_providers']
        ]

        assert providers == [('aws', 'hashicorp/aws', '~> 5.0'), ('legacy', None, '~> 1.0')]
        assert module_summary['required_providers'][0]['location']['start_line'] == 3

    async def test_describes_a_single_tf_file(self, client: Client, module_dir: Path) -> None:
        summary = await describe(client, module_dir.joinpath('main.tf'))

        assert summary['kind'] == 'file'
        assert len(summary['variables']) == 2

    async def test_reports_a_file_that_does_not_parse_as_a_problem(
        self, client: Client, module_dir: Path, broken_module_file: Path
    ) -> None:
        summary = await describe(client, module_dir)

        assert [entry['path'] for entry in summary['problems']] == [str(broken_module_file)]
        assert len(summary['variables']) == 2

    async def test_starts_no_subprocess(
        self, module_summary: dict[str, Any], recording_runner: RecordingCommandRunner
    ) -> None:
        assert module_summary
        assert not recording_runner.calls


@pytest.fixture
def broken_tfvars_file(module_dir: Path) -> Path:
    broken = module_dir.joinpath('bad.tfvars')
    broken.write_text('region = \n')
    return broken


@pytest.mark.unit
class TestDescribeTfvars:
    async def test_splits_assigned_variables_into_declared_and_undeclared(
        self, client: Client, module_dir: Path
    ) -> None:
        summary = await describe(client, module_dir.joinpath('prod.tfvars'))

        assert summary['kind'] == 'tfvars'
        assert [entry['name'] for entry in summary['declared']] == ['region']
        assert [entry['name'] for entry in summary['undeclared']] == ['extra']
        assert summary['undeclared'][0]['location']['start_line'] == 2

    async def test_reports_a_tfvars_file_that_does_not_parse(
        self, client: Client, broken_tfvars_file: Path
    ) -> None:
        summary = await describe(client, broken_tfvars_file)

        assert [entry['path'] for entry in summary['problems']] == [str(broken_tfvars_file)]


@pytest.mark.unit
class TestDescribeRefusals:
    @pytest.fixture
    def notes_file(self, project_root: Path) -> Path:
        path = project_root.joinpath('notes.txt')
        path.write_text('x')
        return path

    async def call(self, client: Client, path: Path) -> str:
        return error_text(await client.call_tool('describe', {'path': str(path)}))

    async def test_refuses_a_file_that_is_neither_tf_nor_tfvars(
        self, client: Client, notes_file: Path
    ) -> None:
        assert f'not a directory, a .tf file or a .tfvars file: {notes_file}' in await self.call(
            client, notes_file
        )

    async def test_refuses_a_missing_path_without_starting_a_subprocess(
        self, client: Client, project_root: Path, recording_runner: RecordingCommandRunner
    ) -> None:
        path = project_root.joinpath('absent.tf')

        assert str(path) in await self.call(client, path)
        assert not recording_runner.calls


@pytest.mark.unit
class TestDescribeWithinBudget:
    @pytest.fixture
    def settings(self, project_root: Path) -> Settings:
        return Settings(project_root=project_root, output_budget_bytes=2000)

    @pytest.fixture
    def many_variables_file(self, project_root: Path) -> Path:
        blocks = [f'variable "v{index}" {{\n  type = string\n}}\n' for index in range(30)]
        path = project_root.joinpath('many.tf')
        path.write_text(''.join(blocks))
        return path

    async def test_cuts_the_variable_list_to_the_budget(
        self, client: Client, many_variables_file: Path
    ) -> None:
        summary = await describe(client, many_variables_file)

        assert len(json.dumps(summary, separators=(',', ':'))) <= 2000
        assert summary['variables_omitted'] > 0
        assert len(summary['variables']) + summary['variables_omitted'] == 30
