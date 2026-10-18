"""Pydantic models for the parts of a terraform show -json plan the digest reads."""

from pydantic import BaseModel, Field


class Change(BaseModel):
    actions: list[str]


class PlannedResourceChange(BaseModel):
    address: str
    change: Change


class PlannedOutputChange(BaseModel):
    actions: list[str]


class PlanDocument(BaseModel):
    planned_values: dict[str, object]
    resource_changes: list[PlannedResourceChange] = Field(default_factory=list)
    output_changes: dict[str, PlannedOutputChange] = Field(default_factory=dict)
