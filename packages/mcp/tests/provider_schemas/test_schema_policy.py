from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.provider_schemas.domain import SchemaRequest
from tf_harness_mcp.provider_schemas.errors import (
    InvalidProviderAddressError,
    InvalidProviderVersionError,
    InvalidTypeNameError,
)
from tf_harness_mcp.provider_schemas.policy import (
    ProviderAddressPolicy,
    ProviderVersionPolicy,
    SchemaRequestPolicy,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from tf_harness_mcp.provider_schemas.domain import SchemaKind

pytestmark = pytest.mark.unit

MODULE = Path('module')
AWS = 'registry.terraform.io/hashicorp/aws'


@dataclass(slots=True, kw_only=True, frozen=True)
class FormCase:
    name: str
    value: str
    valid: bool

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def address_form_cases() -> pytest.MarkDecorator:
    cases = [
        FormCase(name='registry', value=AWS, valid=True),
        FormCase(name='dotted-host', value='example.com/team-a/web-app', valid=True),
        FormCase(name='two-parts', value='hashicorp/aws', valid=False),
        FormCase(name='four-parts', value=f'{AWS}/extra', valid=False),
        FormCase(name='dot-dot-host', value='../hashicorp/aws', valid=False),
        FormCase(name='dot-dot-namespace', value='registry.terraform.io/../aws', valid=False),
        FormCase(name='traversal', value='../../../etc/passwd', valid=False),
        FormCase(name='absolute', value='/registry.terraform.io/hashicorp/aws', valid=False),
        FormCase(name='uppercase', value='registry.terraform.io/HashiCorp/aws', valid=False),
        FormCase(name='trailing-newline', value=f'{AWS}\n', valid=False),
        FormCase(name='empty', value='', valid=False),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


def version_form_cases() -> pytest.MarkDecorator:
    cases = [
        FormCase(name='release', value='6.69.1', valid=True),
        FormCase(name='prerelease', value='1.0.0-beta.2', valid=True),
        FormCase(name='two-parts', value='6.69', valid=False),
        FormCase(name='traversal', value='../6.69.1', valid=False),
        FormCase(name='nested', value='6.69.1/../../x', valid=False),
        FormCase(name='non-ascii-digits', value='٦.٦٩.١', valid=False),
        FormCase(name='empty', value='', valid=False),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


def type_name_cases() -> pytest.MarkDecorator:
    cases = [
        FormCase(name='resource', value='aws_instance', valid=True),
        FormCase(name='traversal', value='../evil', valid=False),
        FormCase(name='slash', value='aws/instance', valid=False),
        FormCase(name='dot-dot', value='..', valid=False),
        FormCase(name='dash', value='aws-instance', valid=False),
        FormCase(name='empty', value='', valid=False),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


def request_for(kind: SchemaKind, type_name: str | None) -> SchemaRequest:
    return SchemaRequest(module=MODULE, address=AWS, kind=kind, type_name=type_name)


class TestSchemaPolicy:
    @address_form_cases()
    def test_address_must_be_hostname_namespace_type(self, case: FormCase) -> None:
        problem = ProviderAddressPolicy(address=case.value).get_address_problem()

        assert (problem is None) is case.valid
        assert case.valid or isinstance(problem, InvalidProviderAddressError)

    @version_form_cases()
    def test_version_must_be_a_release_version(self, case: FormCase) -> None:
        problem = ProviderVersionPolicy(version=case.value).get_version_problem()

        assert (problem is None) is case.valid
        assert case.valid or isinstance(problem, InvalidProviderVersionError)

    @type_name_cases()
    @pytest.mark.parametrize('kind', ['resource', 'data_source'])
    def test_named_kinds_need_an_identifier(self, kind: SchemaKind, case: FormCase) -> None:
        problem = SchemaRequestPolicy(request=request_for(kind, case.value)).get_request_problem()

        assert (problem is None) is case.valid
        assert case.valid or isinstance(problem, InvalidTypeNameError)

    @pytest.mark.parametrize('kind', ['resource', 'data_source'])
    def test_named_kinds_need_a_type_name(self, kind: SchemaKind) -> None:
        problem = SchemaRequestPolicy(request=request_for(kind, None)).get_request_problem()

        assert isinstance(problem, InvalidTypeNameError)

    def test_provider_kind_takes_no_type_name(self) -> None:
        accepted = SchemaRequestPolicy(request=request_for('provider', None))
        refused = SchemaRequestPolicy(request=request_for('provider', 'aws_instance'))

        assert accepted.get_request_problem() is None
        assert isinstance(refused.get_request_problem(), InvalidTypeNameError)

    def test_request_reports_the_address_before_the_type_name(self) -> None:
        request = SchemaRequest(module=MODULE, address='../x', kind='resource', type_name='../y')

        problem = SchemaRequestPolicy(request=request).get_request_problem()

        assert isinstance(problem, InvalidProviderAddressError)
