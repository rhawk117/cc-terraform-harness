from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.structure.services import create_block_indexer

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.structure.services import BlockIndexer, FileIndex

pytestmark = pytest.mark.unit

VALID_SOURCE = 'variable "x" {}\nmodule "m" {\n  source = "./net"\n}\n'
BROKEN_SOURCE = 'variable "x" {\n'


def repr_problem(index: FileIndex) -> tuple[type, str] | None:
    problem = index.problem
    return (type(problem), str(problem)) if problem else None


def source_index_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'text',
        [
            pytest.param(VALID_SOURCE, id='valid'),
            pytest.param(BROKEN_SOURCE, id='syntax-error'),
            pytest.param('', id='empty'),
        ],
    )


class TestSourceIndex:
    @pytest.fixture
    def indexer(self, project_root: Path) -> BlockIndexer:
        return create_block_indexer(project_root)

    @source_index_cases()
    def test_text_yields_what_the_same_file_on_disk_yields(
        self, indexer: BlockIndexer, project_root: Path, text: str
    ) -> None:
        path = project_root.joinpath('main.tf')
        path.write_text(text)
        from_disk = indexer.index_file(path)
        from_text = indexer.index_text(text, path)

        assert from_text.blocks == from_disk.blocks
        assert repr_problem(from_text) == repr_problem(from_disk)

    def test_blocks_are_attributed_to_the_given_path(
        self, indexer: BlockIndexer, project_root: Path
    ) -> None:
        path = project_root.joinpath('absent.tf')

        blocks = indexer.index_text(VALID_SOURCE, path).blocks

        assert {block.file for block in blocks} == {path}
