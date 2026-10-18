"""Forms a provider address, version and type name must take before they become cache paths."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tf_harness_mcp.provider_schemas.errors import (
    InvalidProviderAddressError,
    InvalidProviderVersionError,
    InvalidTypeNameError,
)

if TYPE_CHECKING:
    from tf_harness_mcp.provider_schemas.domain import SchemaRequest

HOSTNAME = r'[a-z0-9]([a-z0-9.-]*[a-z0-9])?'
DASHED_NAME = r'[a-z0-9]([a-z0-9-]*[a-z0-9])?'
ADDRESS_FORM = re.compile(f'{HOSTNAME}/{DASHED_NAME}/{DASHED_NAME}', re.ASCII)
VERSION_FORM = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?', re.ASCII)
TYPE_NAME_FORM = re.compile(r'[A-Za-z0-9_]+', re.ASCII)


@dataclass(slots=True, kw_only=True, frozen=True)
class ProviderAddressPolicy:
    address: str

    @property
    def is_valid(self) -> bool:
        return ADDRESS_FORM.fullmatch(self.address) is not None

    def get_address_problem(self) -> InvalidProviderAddressError | None:
        if not self.is_valid:
            return InvalidProviderAddressError(address=self.address)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class ProviderVersionPolicy:
    version: str

    @property
    def is_valid(self) -> bool:
        return VERSION_FORM.fullmatch(self.version) is not None

    def get_version_problem(self) -> InvalidProviderVersionError | None:
        if not self.is_valid:
            return InvalidProviderVersionError(version=self.version)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class TypeNamePolicy:
    type_name: str

    @property
    def is_valid(self) -> bool:
        return TYPE_NAME_FORM.fullmatch(self.type_name) is not None


@dataclass(slots=True, kw_only=True, frozen=True)
class SchemaRequestPolicy:
    request: SchemaRequest

    @property
    def has_fitting_type_name(self) -> bool:
        type_name = self.request.type_name
        if self.request.kind == 'provider':
            return type_name is None

        return type_name is not None and TypeNamePolicy(type_name=type_name).is_valid

    def get_request_problem(self) -> InvalidProviderAddressError | InvalidTypeNameError | None:
        address_policy = ProviderAddressPolicy(address=self.request.address)
        if problem := address_policy.get_address_problem():
            return problem

        if not self.has_fitting_type_name:
            return InvalidTypeNameError(kind=self.request.kind, type_name=self.request.type_name)

        return None
