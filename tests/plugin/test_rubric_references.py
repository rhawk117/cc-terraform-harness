import re
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

RUBRIC_PATH = 'skills/review-module/references/rubric.md'
DECLARED_ID = re.compile(r'^- \*\*(?P<id>[A-Z]+\d+)\*\*', re.MULTILINE)


def rubric_citing_file_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'citing_path',
        [
            pytest.param('skills/writing-terraform/scripts/smell_grep.py', id='smell-grep'),
            pytest.param('skills/writing-terraform/SKILL.md', id='writing-terraform-skill'),
            pytest.param('skills/writing-terraform/references/good-vs-bad.md', id='good-vs-bad'),
            pytest.param('skills/check-module/SKILL.md', id='check-module-skill'),
        ],
    )


@pytest.mark.unit
class TestRubricReferences:
    @pytest.fixture
    def declared_ids(self, repository_root: Path) -> set[str]:
        rubric = repository_root.joinpath(RUBRIC_PATH).read_text('utf-8')
        return set(DECLARED_ID.findall(rubric))

    def find_cited_ids(self, declared_ids: set[str], text: str) -> set[str]:
        prefixes = {re.sub(r'\d+$', '', rule_id) for rule_id in declared_ids}
        alternatives = '|'.join(sorted(prefixes))
        cited = re.compile(rf'(?<![\w-])(?:{alternatives})\d+\b(?!-)')
        return set(cited.findall(text))

    def test_rubric_declares_ids(self, declared_ids: set[str]) -> None:
        assert declared_ids

    @rubric_citing_file_cases()
    def test_cited_ids_are_declared_in_the_rubric(
        self, repository_root: Path, declared_ids: set[str], citing_path: str
    ) -> None:
        text = repository_root.joinpath(citing_path).read_text('utf-8')
        cited_ids = self.find_cited_ids(declared_ids, text)
        assert cited_ids, f'{citing_path} cites no rubric ID'
        assert cited_ids <= declared_ids, (
            f'{citing_path} cites IDs missing from {RUBRIC_PATH}: '
            f'{sorted(cited_ids - declared_ids)}'
        )
