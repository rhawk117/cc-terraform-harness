"""Pydantic models for the JSON that terraform validate and tflint print."""

from pydantic import BaseModel, Field


class Position(BaseModel):
    line: int


class SourceRange(BaseModel):
    filename: str
    start: Position


class LocatedModel(BaseModel):
    range: SourceRange | None = None

    @property
    def file(self) -> str | None:
        return self.range.filename if self.range else None

    @property
    def line(self) -> int | None:
        return self.range.start.line if self.range else None


class ValidateDiagnostic(LocatedModel):
    severity: str
    summary: str
    detail: str = ''


class ValidateOutput(BaseModel):
    valid: bool
    diagnostics: list[ValidateDiagnostic] = Field(default_factory=list)


class TflintRule(BaseModel):
    name: str
    severity: str


class TflintIssue(LocatedModel):
    rule: TflintRule
    message: str


class TflintError(BaseModel):
    message: str
    severity: str = 'error'


class TflintOutput(BaseModel):
    issues: list[TflintIssue] = Field(default_factory=list)
    errors: list[TflintError] = Field(default_factory=list)
