from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.structure.services import create_block_indexer

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.structure.domain import BlockEntry
    from tf_harness_mcp.structure.services import FileIndex

pytestmark = pytest.mark.unit

SAMPLE_TF = """\
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    legacy = "~> 1.0"
    bare   = {}
  }
}

variable "region" {
  description = "Where to deploy"
  sensitive   = true
  default     = <<-EOT
    hello
  EOT
  settings    = { first = "one", second = 2 }
  count_hint  = 3
}
"""


@pytest.fixture
def tf_file(project_root: Path) -> Path:
    path = project_root.joinpath('main.tf')
    path.write_text(SAMPLE_TF)
    return path


@pytest.fixture
def index(project_root: Path, tf_file: Path) -> FileIndex:
    return create_block_indexer(project_root).index_file(tf_file)


def find_entry(index: FileIndex, kind: str) -> BlockEntry:
    return next(entry for entry in index.entries if entry.block.kind == kind)


def test_undecodable_source_text_indexes_without_raising(project_root: Path) -> None:
    path = project_root.joinpath('bad.tf')
    path.write_bytes(b'variable "region" {\n  description = "caf\xe9 \xff"\n}\n')

    index = create_block_indexer(project_root).index_file(path)

    attribute = find_entry(index, 'variable').get_attribute('description')
    assert attribute is not None
    assert attribute.string is not None
    assert '\ufffd' in attribute.string


class TestAttributes:
    def test_attributes_are_listed_in_source_order(self, index: FileIndex) -> None:
        names = [attribute.name for attribute in find_entry(index, 'variable').attributes]

        assert names == ['description', 'sensitive', 'default', 'settings', 'count_hint']

    def test_attribute_carries_its_line_range(self, index: FileIndex) -> None:
        attribute = find_entry(index, 'variable').get_attribute('default')

        assert attribute is not None
        assert (attribute.start_line, attribute.end_line) == (15, 17)

    def test_missing_attribute_is_none(self, index: FileIndex) -> None:
        assert find_entry(index, 'variable').get_attribute('type') is None

    def test_expression_is_the_raw_source_text(self, index: FileIndex) -> None:
        attribute = find_entry(index, 'variable').get_attribute('settings')

        assert attribute is not None
        assert attribute.expression == '{ first = "one", second = 2 }'

    def test_quoted_string_is_read(self, index: FileIndex) -> None:
        attribute = find_entry(index, 'variable').get_attribute('description')

        assert attribute is not None
        assert attribute.string == 'Where to deploy'

    def test_heredoc_is_read_and_stripped(self, index: FileIndex) -> None:
        attribute = find_entry(index, 'variable').get_attribute('default')

        assert attribute is not None
        assert attribute.string == 'hello'

    def test_number_is_not_a_string(self, index: FileIndex) -> None:
        attribute = find_entry(index, 'variable').get_attribute('count_hint')

        assert attribute is not None
        assert attribute.string is None

    def test_flag_reads_true(self, index: FileIndex) -> None:
        attribute = find_entry(index, 'variable').get_attribute('sensitive')

        assert attribute is not None
        assert attribute.flag

    def test_flag_of_a_string_is_false(self, index: FileIndex) -> None:
        attribute = find_entry(index, 'variable').get_attribute('description')

        assert attribute is not None
        assert not attribute.flag

    def test_top_level_attributes_are_indexed(self, project_root: Path) -> None:
        indexer = create_block_indexer(project_root)

        index = indexer.index_text('region = "eu"\nzones = 3\n', project_root.joinpath('a.tfvars'))

        assert [(a.name, a.string) for a in index.attributes] == [('region', 'eu'), ('zones', None)]


class TestRequiredProviders:
    def test_required_providers_carry_name_source_version_and_location(
        self, index: FileIndex
    ) -> None:
        providers = find_entry(index, 'terraform').required_providers

        summary = [(p.local_name, p.source, p.version, p.start_line, p.end_line) for p in providers]
        assert summary == [
            ('aws', 'hashicorp/aws', '~> 5.0', 3, 6),
            ('legacy', None, '~> 1.0', 7, 7),
            ('bare', None, None, 8, 8),
        ]

    def test_required_providers_record_their_file(self, index: FileIndex, tf_file: Path) -> None:
        providers = find_entry(index, 'terraform').required_providers

        assert {provider.file for provider in providers} == {tf_file}

    def test_only_terraform_blocks_carry_required_providers(self, index: FileIndex) -> None:
        assert find_entry(index, 'variable').required_providers == ()
