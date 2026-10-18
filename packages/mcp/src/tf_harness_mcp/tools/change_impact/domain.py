"""Values the change_impact git layer reads from a repository."""

from dataclasses import dataclass
from typing import Literal

type ChangeStatus = Literal['added', 'modified', 'deleted']


@dataclass(slots=True, kw_only=True, frozen=True)
class GitOptions:
    timeout_seconds: float = 30.0


@dataclass(slots=True, kw_only=True, frozen=True)
class LineRange:
    start: int
    count: int


@dataclass(slots=True, kw_only=True, frozen=True)
class ChangedFile:
    path: str
    status: ChangeStatus
    ranges: tuple[LineRange, ...] = ()


@dataclass(slots=True, kw_only=True, frozen=True)
class ChangeSet:
    base_commit: str
    files: tuple[ChangedFile, ...]
