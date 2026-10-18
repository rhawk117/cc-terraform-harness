from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.structure.services import (
    create_block_indexer,
    first_child_of_type,
    get_children,
    node_text,
    read_attributes,
    read_flag,
    read_object_fields,
    read_required_providers,
    read_string,
    read_value,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.structure.domain import RequiredProvider
    from tree_sitter import Node

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
def root(project_root: Path, tf_file: Path) -> Node:
    indexed = create_block_indexer(project_root).index_file(tf_file)
    assert indexed.root is not None
    return indexed.root


def find_block(root: Node, kind: str) -> Node:
    blocks = get_children(first_child_of_type(root, 'body'), 'block')
    return next(block for block in blocks if node_text(block.children[0]) == kind)


def find_variable_value(root: Node, name: str) -> Node | None:
    attributes = read_attributes(find_block(root, 'variable'))
    return read_value(attributes.get(name))


class TestValueReaders:
    def test_attributes_are_keyed_by_name(self, root: Node) -> None:
        attributes = read_attributes(find_block(root, 'variable'))

        assert list(attributes) == [
            'description',
            'sensitive',
            'default',
            'settings',
            'count_hint',
        ]

    def test_attributes_of_nothing_are_empty(self) -> None:
        assert read_attributes(None) == {}

    def test_quoted_string_is_read(self, root: Node) -> None:
        value = find_variable_value(root, 'description')

        assert read_string(value) == 'Where to deploy'

    def test_heredoc_is_read_and_stripped(self, root: Node) -> None:
        value = find_variable_value(root, 'default')

        assert read_string(value) == 'hello'

    def test_number_is_not_a_string(self, root: Node) -> None:
        value = find_variable_value(root, 'count_hint')

        assert read_string(value) is None

    def test_flag_reads_true(self, root: Node) -> None:
        assert read_flag(find_variable_value(root, 'sensitive'))

    def test_flag_of_a_string_is_false(self, root: Node) -> None:
        assert not read_flag(find_variable_value(root, 'description'))

    def test_object_fields_are_keyed_by_name(self, root: Node) -> None:
        fields = read_object_fields(find_variable_value(root, 'settings'))

        assert {name: read_string(node) for name, node in fields.items()} == {
            'first': 'one',
            'second': None,
        }

    def test_object_fields_of_a_string_are_empty(self, root: Node) -> None:
        assert read_object_fields(find_variable_value(root, 'description')) == {}


class TestRequiredProviders:
    def test_required_providers_carry_name_source_version_and_location(
        self, root: Node, tf_file: Path
    ) -> None:
        providers = read_required_providers(find_block(root, 'terraform'), tf_file)

        summary = [(p.local_name, p.source, p.version, p.start_line, p.end_line) for p in providers]
        assert summary == [
            ('aws', 'hashicorp/aws', '~> 5.0', 3, 6),
            ('legacy', None, '~> 1.0', 7, 7),
            ('bare', None, None, 8, 8),
        ]

    def test_required_providers_record_their_file(self, root: Node, tf_file: Path) -> None:
        providers: tuple[RequiredProvider, ...] = read_required_providers(
            find_block(root, 'terraform'), tf_file
        )

        assert {provider.file for provider in providers} == {tf_file}
