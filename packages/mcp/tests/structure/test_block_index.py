from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.structure.errors import HclSyntaxError, UnreadableFileError
from tf_harness_mcp.structure.services import index_module

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet
    from tf_harness_mcp.structure.domain import Block, ModuleIndex

pytestmark = pytest.mark.unit

MAIN_TF = """\
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "us-east-1"
}

locals {
  policy = <<-EOT
    {
      "closing": "}"
    }
  EOT
  names  = ["a", "b"]
}

resource "aws_security_group" "web" {
  name = "web"

  dynamic "ingress" {
    for_each = local.names
    content {
      from_port = 443
      to_port   = 443
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

data "aws_ami" "base" {
  most_recent = true
  filter {
    name   = "name"
    values = ["al2023-*"]
  }
}

module "network" {
  source = "./network"
  cidr   = "10.0.0.0/16"
}

output "script" {
  value = <<EOF2
#!/bin/sh
echo "}"
EOF2
}
"""

BROKEN_TF = """\
resource "aws_s3_bucket" "logs" {
  bucket = "logs"

variable "unclosed" {
"""


@dataclass(slots=True, kw_only=True, frozen=True)
class BlockCase:
    name: str
    kind: str
    labels: tuple[str, ...]
    start_line: int
    end_line: int

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def top_level_block_cases() -> pytest.MarkDecorator:
    cases = [
        BlockCase(name='terraform', kind='terraform', labels=(), start_line=1, end_line=8),
        BlockCase(name='provider', kind='provider', labels=('aws',), start_line=10, end_line=12),
        BlockCase(name='variable', kind='variable', labels=('region',), start_line=14, end_line=17),
        BlockCase(name='locals-heredoc', kind='locals', labels=(), start_line=19, end_line=26),
        BlockCase(
            name='resource-dynamic-nested',
            kind='resource',
            labels=('aws_security_group', 'web'),
            start_line=28,
            end_line=42,
        ),
        BlockCase(
            name='data-nested', kind='data', labels=('aws_ami', 'base'), start_line=44, end_line=50
        ),
        BlockCase(name='module', kind='module', labels=('network',), start_line=52, end_line=55),
        BlockCase(
            name='output-heredoc', kind='output', labels=('script',), start_line=57, end_line=62
        ),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


@pytest.fixture
def module_dir(project_root: Path) -> Path:
    project_root.joinpath('main.tf').write_text(MAIN_TF)
    return project_root


class TestBlockIndex:
    @pytest.fixture
    def index(self, project_root: Path, module_dir: Path) -> ModuleIndex:
        return index_module(project_root, module_dir)

    @pytest.fixture
    def broken_index(self, project_root: Path, module_dir: Path) -> ModuleIndex:
        module_dir.joinpath('broken.tf').write_text(BROKEN_TF)
        return index_module(project_root, module_dir)

    def find_block(self, index: ModuleIndex, case: BlockCase) -> Block | None:
        matches = (b for b in index.blocks if (b.kind, b.labels) == (case.kind, case.labels))
        return next(matches, None)

    def test_every_top_level_block_is_indexed_once(self, index: ModuleIndex) -> None:
        assert len(index.blocks) == 8
        assert not index.problems

    @top_level_block_cases()
    def test_block_maps_to_file_and_line_range(
        self, index: ModuleIndex, module_dir: Path, case: BlockCase
    ) -> None:
        block = self.find_block(index, case)

        assert block is not None
        assert block.file == module_dir.joinpath('main.tf')
        assert (block.start_line, block.end_line) == (case.start_line, case.end_line)

    def test_module_block_carries_its_literal_source(self, index: ModuleIndex) -> None:
        sources = {block.source for block in index.blocks}

        assert sources == {None, './network'}

    def test_file_that_does_not_parse_is_reported_with_its_path(
        self, broken_index: ModuleIndex, module_dir: Path
    ) -> None:
        problem = broken_index.problems[0]

        assert isinstance(problem, HclSyntaxError)
        assert problem.path == module_dir.joinpath('broken.tf')

    def test_file_that_does_not_parse_contributes_no_blocks(
        self, broken_index: ModuleIndex, module_dir: Path
    ) -> None:
        files = {block.file for block in broken_index.blocks}

        assert files == {module_dir.joinpath('main.tf')}


class TestUnreadableFiles:
    @pytest.fixture
    def directory_named_tf_index(self, project_root: Path, module_dir: Path) -> ModuleIndex:
        module_dir.joinpath('stray.tf').mkdir()
        return index_module(project_root, module_dir)

    @pytest.fixture
    def dangling_link_index(self, project_root: Path, module_dir: Path) -> ModuleIndex:
        module_dir.joinpath('dangling.tf').symlink_to(module_dir.joinpath('missing.tf'))
        return index_module(project_root, module_dir)

    @pytest.fixture
    def escaping_link_index(
        self, project_root: Path, module_dir: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> ModuleIndex:
        outside = tmp_path_factory.mktemp('outside').joinpath('leak.tf')
        outside.write_text(BROKEN_TF)
        module_dir.joinpath('leak.tf').symlink_to(outside)
        return index_module(project_root, module_dir)

    def test_directory_named_like_a_tf_file_is_reported_with_its_path(
        self, directory_named_tf_index: ModuleIndex, module_dir: Path
    ) -> None:
        problem = directory_named_tf_index.problems[0]

        assert isinstance(problem, UnreadableFileError)
        assert problem.path == module_dir.joinpath('stray.tf')

    def test_unreadable_file_is_reported_and_other_files_still_index(
        self, dangling_link_index: ModuleIndex, module_dir: Path
    ) -> None:
        problem = dangling_link_index.problems[0]

        assert isinstance(problem, UnreadableFileError)
        assert problem.path == module_dir.joinpath('dangling.tf')
        assert len(dangling_link_index.blocks) == 8

    def test_file_whose_real_path_leaves_the_root_is_skipped(
        self, escaping_link_index: ModuleIndex
    ) -> None:
        assert not escaping_link_index.problems
        assert len(escaping_link_index.blocks) == 8
