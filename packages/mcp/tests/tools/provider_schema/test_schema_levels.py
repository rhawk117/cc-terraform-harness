from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from tf_harness_mcp.tools.provider_schema.domain import BlockSummary
from tf_harness_mcp.tools.provider_schema.policy import (
    BlockPathPolicy,
    ProviderSourcePolicy,
    ProviderTypePolicy,
)
from tf_harness_mcp.tools.provider_schema.services import (
    find_level,
    make_attribute,
    render_type,
    summarize_block_type,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from tf_harness_mcp.provider_schemas.domain import SchemaKind

pytestmark = pytest.mark.unit

NESTED_LEVEL: dict[str, Any] = {
    'attributes': {
        'rules': {
            'nested_type': {
                'nesting_mode': 'list',
                'attributes': {
                    'action': {'type': 'string', 'required': True},
                    'targets': {
                        'nested_type': {
                            'nesting_mode': 'set',
                            'attributes': {'arn': {'type': 'string', 'computed': True}},
                        }
                    },
                },
            }
        }
    },
    'block_types': {
        'timeouts': {
            'nesting_mode': 'single',
            'block': {'attributes': {'create': {'type': 'string', 'optional': True}}},
        },
        'rule': {
            'nesting_mode': 'list',
            'min_items': 1,
            'max_items': 4,
            'block': {
                'attributes': {'name': {'type': 'string', 'required': True}},
                'block_types': {
                    'condition': {
                        'nesting_mode': 'set',
                        'block': {'attributes': {'field': {'type': 'string'}}},
                    }
                },
            },
        },
    },
}


@dataclass(slots=True, kw_only=True, frozen=True)
class TypeRendering:
    name: str
    cty: Any
    expected: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def type_rendering_cases() -> pytest.MarkDecorator:
    cases = [
        TypeRendering(name='primitive', cty='string', expected='string'),
        TypeRendering(name='dynamic', cty='dynamic', expected='any'),
        TypeRendering(name='list', cty=['list', 'string'], expected='list(string)'),
        TypeRendering(
            name='map-of-set', cty=['map', ['set', 'number']], expected='map(set(number))'
        ),
        TypeRendering(
            name='object',
            cty=['object', {'id': 'string', 'tags': ['map', 'string']}],
            expected='object({id = string, tags = map(string)})',
        ),
        TypeRendering(
            name='object-with-optional',
            cty=['object', {'id': 'string', 'size': 'number'}, ['size']],
            expected='object({id = string, size = optional(number)})',
        ),
        TypeRendering(
            name='tuple',
            cty=['tuple', ['string', ['list', 'bool']]],
            expected='tuple([string, list(bool)])',
        ),
        TypeRendering(
            name='list-of-objects',
            cty=['list', ['object', {'a': 'dynamic'}]],
            expected='list(object({a = any}))',
        ),
    ]
    return pytest.mark.parametrize('rendering', [case.param for case in cases])


@dataclass(slots=True, kw_only=True, frozen=True)
class LevelWalk:
    name: str
    block: str
    expected_attributes: list[str] | None

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def level_walk_cases() -> pytest.MarkDecorator:
    cases = [
        LevelWalk(name='top', block='', expected_attributes=['rules']),
        LevelWalk(name='nested-block', block='rule', expected_attributes=['name']),
        LevelWalk(name='block-in-block', block='rule.condition', expected_attributes=['field']),
        LevelWalk(
            name='nested-attribute', block='rules', expected_attributes=['action', 'targets']
        ),
        LevelWalk(
            name='attribute-in-attribute', block='rules.targets', expected_attributes=['arn']
        ),
        LevelWalk(name='unknown', block='nope', expected_attributes=None),
        LevelWalk(name='plain-attribute', block='rules.action', expected_attributes=None),
        LevelWalk(name='unknown-below-known', block='rule.nope', expected_attributes=None),
    ]
    return pytest.mark.parametrize('walk', [case.param for case in cases])


@dataclass(slots=True, kw_only=True, frozen=True)
class AddressResolution:
    name: str
    kind: SchemaKind
    type_name: str
    source: str | None
    expected: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def address_resolution_cases() -> pytest.MarkDecorator:
    cases = [
        AddressResolution(
            name='undeclared-resource',
            kind='resource',
            type_name='aws_instance',
            source=None,
            expected='registry.terraform.io/hashicorp/aws',
        ),
        AddressResolution(
            name='undeclared-provider',
            kind='provider',
            type_name='google',
            source=None,
            expected='registry.terraform.io/hashicorp/google',
        ),
        AddressResolution(
            name='declared-namespace',
            kind='data_source',
            type_name='datadog_monitor',
            source='DataDog/datadog',
            expected='registry.terraform.io/datadog/datadog',
        ),
        AddressResolution(
            name='declared-hostname',
            kind='resource',
            type_name='acme_widget',
            source='Example.com/acme/acme',
            expected='example.com/acme/acme',
        ),
        AddressResolution(
            name='no-underscore',
            kind='resource',
            type_name='random',
            source=None,
            expected='registry.terraform.io/hashicorp/random',
        ),
    ]
    return pytest.mark.parametrize('resolution', [case.param for case in cases])


class TestRenderType:
    @type_rendering_cases()
    def test_cty_json_renders_as_an_hcl_type_expression(self, rendering: TypeRendering) -> None:
        assert render_type(rendering.cty) == rendering.expected


class TestFindLevel:
    @level_walk_cases()
    def test_dotted_path_walks_blocks_and_nested_attributes(self, walk: LevelWalk) -> None:
        segments = BlockPathPolicy(block=walk.block).segments

        level = find_level(NESTED_LEVEL, segments)

        found = None if level is None else list(level['attributes'])
        assert found == walk.expected_attributes


class TestSummaries:
    def test_block_summary_counts_attributes_and_blocks(self) -> None:
        summary = summarize_block_type('rule', NESTED_LEVEL['block_types']['rule'])

        assert summary == BlockSummary(
            name='rule',
            nesting_mode='list',
            min_items=1,
            max_items=4,
            attribute_count=1,
            block_count=1,
        )

    def test_block_summary_defaults_min_items_to_zero_and_max_to_unbounded(self) -> None:
        summary = summarize_block_type('timeouts', NESTED_LEVEL['block_types']['timeouts'])

        assert (summary.min_items, summary.max_items) == (0, None)

    def test_nested_type_attribute_summarizes_its_attributes(self) -> None:
        entry = make_attribute('rules', NESTED_LEVEL['attributes']['rules'])

        assert entry.type == 'list(object)'
        assert entry.nested == BlockSummary(
            name='rules',
            nesting_mode='list',
            min_items=None,
            max_items=None,
            attribute_count=2,
            block_count=0,
        )

    def test_attribute_flags_default_to_false(self) -> None:
        entry = make_attribute('name', {'type': 'string', 'required': True, 'description': 'x'})

        assert (entry.required, entry.optional, entry.computed) == (True, False, False)
        assert (entry.sensitive, entry.deprecated, entry.description) == (False, False, 'x')


class TestProviderResolution:
    @address_resolution_cases()
    def test_type_prefix_and_declared_source_give_the_address(
        self, resolution: AddressResolution
    ) -> None:
        local_name = ProviderTypePolicy(
            kind=resolution.kind, type_name=resolution.type_name
        ).local_name

        policy = ProviderSourcePolicy(local_name=local_name, source=resolution.source)

        assert policy.address == resolution.expected
