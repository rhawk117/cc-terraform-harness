"""Pydantic models for the parts of a terraform show -json plan the digest reads."""

from typing import Any

from pydantic import BaseModel, Field

type JsonObject = dict[str, Any]


class Change(BaseModel):
    actions: list[str]
    before: JsonObject | None = None
    after: JsonObject | None = None
    after_sensitive: JsonObject | bool | None = None
    after_unknown: JsonObject | bool | None = None
    replace_paths: list[list[str | int]] | None = None
    importing: JsonObject | None = None


class PlannedResourceChange(BaseModel):
    address: str
    previous_address: str | None = None
    type: str = ''
    change: Change


class DriftedResource(BaseModel):
    address: str


class PlannedOutputChange(BaseModel):
    actions: list[str]


class PlanDocument(BaseModel):
    planned_values: dict[str, object]
    resource_changes: list[PlannedResourceChange] = Field(default_factory=list)
    resource_drift: list[DriftedResource] = Field(default_factory=list)
    output_changes: dict[str, PlannedOutputChange] = Field(default_factory=dict)
