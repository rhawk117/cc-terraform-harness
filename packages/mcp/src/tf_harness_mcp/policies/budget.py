"""Output budget: cut every list of an oversized result so its JSON stays under a ceiling."""

import json
from bisect import bisect_left
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tf_harness_mcp.policies.errors import OutputOverBudgetError

if TYPE_CHECKING:
    from tf_harness_mcp.settings import Settings

type Payload = dict[str, Any]


def measure(payload: Payload) -> int:
    return len(json.dumps(payload, separators=(',', ':')).encode())


def count_longest_list(payload: Payload) -> int:
    lengths = [
        count_longest_list(value) if isinstance(value, dict) else len(value)
        for value in payload.values()
        if isinstance(value, dict | list)
    ]
    return max(lengths, default=0)


def cut_lists(payload: Payload, keep: int) -> Payload:
    cut: Payload = {}
    for name, value in payload.items():
        if isinstance(value, dict):
            cut[name] = cut_lists(value, keep)
            continue

        if isinstance(value, list) and len(value) > keep:
            cut[name] = value[:keep]
            cut[f'{name}_omitted'] = len(value) - keep
            continue

        cut[name] = value

    return cut


@dataclass(slots=True, kw_only=True, frozen=True)
class ListCut:
    payload: Payload
    ceiling: int

    def exceeds_ceiling(self, keep: int) -> bool:
        return measure(cut_lists(self.payload, keep)) > self.ceiling

    def find_largest_keep(self) -> int:
        keeps = range(count_longest_list(self.payload) + 1)
        return bisect_left(keeps, x=True, key=self.exceeds_ceiling) - 1


@dataclass(slots=True, kw_only=True, frozen=True)
class OutputBudget:
    default_bytes: int
    max_bytes: int

    def get_ceiling(self, limit: int | None) -> int:
        return min(limit or self.default_bytes, self.max_bytes)

    def apply(self, payload: Payload, limit: int | None = None) -> Payload:
        ceiling = self.get_ceiling(limit)
        if measure(payload) <= ceiling:
            return payload

        keep = ListCut(payload=payload, ceiling=ceiling).find_largest_keep()
        if keep < 0:
            raise OutputOverBudgetError(size=measure(cut_lists(payload, 0)), ceiling=ceiling)

        return cut_lists(payload, keep)


def create_output_budget(settings: Settings) -> OutputBudget:
    return OutputBudget(
        default_bytes=settings.output_budget_bytes,
        max_bytes=settings.output_budget_max_bytes,
    )
