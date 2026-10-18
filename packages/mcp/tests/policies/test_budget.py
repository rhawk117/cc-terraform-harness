import json
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.policies.budget import OutputBudget, create_output_budget, measure
from tf_harness_mcp.policies.errors import OutputOverBudgetError

if TYPE_CHECKING:
    from tf_harness_mcp.policies.budget import Payload
    from tf_harness_mcp.settings import Settings

pytestmark = pytest.mark.unit


class TestOutputBudget:
    budget = OutputBudget(default_bytes=400, max_bytes=1_000)
    item_count = 200

    @pytest.fixture
    def oversized(self) -> Payload:
        resources = [
            {'address': f'aws_instance.web_{i}', 'index': i} for i in range(self.item_count)
        ]
        warnings = [f'warning number {i}' for i in range(self.item_count)]
        return {'summary': 'plan', 'resources': resources, 'nested': {'warnings': warnings}}

    def test_result_under_the_ceiling_is_returned_unchanged(self) -> None:
        small: Payload = {'resources': [1, 2, 3]}

        assert self.budget.apply(small) == small

    def test_every_list_is_cut_with_its_omitted_count(self, oversized: Payload) -> None:
        cut = self.budget.apply(oversized)
        nested = cut['nested']

        assert isinstance(nested, dict)
        assert len(cut['resources']) + cut['resources_omitted'] == self.item_count
        assert len(nested['warnings']) + nested['warnings_omitted'] == self.item_count
        assert cut['summary'] == 'plan'

    def test_cut_result_fits_the_ceiling(self, oversized: Payload) -> None:
        cut = self.budget.apply(oversized)

        assert measure(cut) <= self.budget.default_bytes
        assert len(json.dumps(cut, separators=(',', ':'))) == measure(cut)

    def test_cut_keeps_the_most_items_that_fit(self, oversized: Payload) -> None:
        cut = self.budget.apply(oversized)
        kept = len(cut['resources'])
        one_more = {
            'summary': 'plan',
            'resources': oversized['resources'][: kept + 1],
            'resources_omitted': self.item_count - kept - 1,
            'nested': {
                'warnings': oversized['nested']['warnings'][: kept + 1],
                'warnings_omitted': self.item_count - kept - 1,
            },
        }

        assert measure(one_more) > self.budget.default_bytes

    def test_limit_raises_the_ceiling(self, oversized: Payload) -> None:
        cut = self.budget.apply(oversized, limit=900)

        assert self.budget.default_bytes < measure(cut) <= 900

    def test_limit_never_passes_the_maximum(self, oversized: Payload) -> None:
        cut = self.budget.apply(oversized, limit=50_000)

        assert measure(cut) <= self.budget.max_bytes

    def test_result_that_lists_cannot_shrink_is_an_error(self) -> None:
        stubborn: Payload = {'text': 'x' * 2_000, 'items': [1, 2, 3]}

        with pytest.raises(OutputOverBudgetError):
            self.budget.apply(stubborn)

    def test_budget_from_settings_uses_the_settings_default_and_maximum(
        self, settings: Settings
    ) -> None:
        budget = create_output_budget(settings)

        assert budget.get_ceiling(None) == settings.output_budget_bytes
        assert budget.get_ceiling(10**9) == settings.output_budget_max_bytes
