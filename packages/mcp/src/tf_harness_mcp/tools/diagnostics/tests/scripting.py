"""Scripted command results, report readers and the module fixture for the diagnostics tests."""

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from tf_harness_mcp.runner.domain import CommandResult

if TYPE_CHECKING:
    from pathlib import Path

    from mcp import Client
    from mcp.types import CallToolResult

    from tf_harness_mcp.runner.tests.recording import RecordingCommandRunner

type Report = dict[str, Any]

FMT_ARGV = ('terraform', 'fmt', '-check', '-list=true', '-no-color')
VALIDATE_ARGV = ('terraform', 'validate', '-json', '-no-color')
TFLINT_ARGV = ('tflint', '--format=json', '--no-color')


def succeed(stdout: str = '') -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr='')


def fail(returncode: int, stdout: str = '', stderr: str = '') -> CommandResult:
    return CommandResult(returncode=returncode, stdout=stdout, stderr=stderr)


def create_validate_json(*diagnostics: dict[str, Any]) -> str:
    return json.dumps({'valid': not diagnostics, 'diagnostics': list(diagnostics)})


def create_range(filename: str, line: int) -> dict[str, Any]:
    return {'filename': filename, 'start': {'line': line, 'column': 1, 'byte': 0}}


def create_undeclared_diagnostic() -> dict[str, Any]:
    return {
        'severity': 'error',
        'summary': 'Reference to undeclared input variable',
        'detail': 'An input variable with the name "x" has not been declared.',
        'range': create_range('main.tf', 3),
    }


def create_missing_provider_diagnostic() -> dict[str, Any]:
    return {
        'severity': 'error',
        'summary': 'Missing required provider',
        'detail': 'This configuration requires provider "hashicorp/null"; run terraform init.',
    }


def read_report(result: CallToolResult) -> Report:
    assert not result.is_error
    assert result.structured_content is not None
    return result.structured_content


async def call_diagnostics(client: Client, directory: Path) -> CallToolResult:
    return await client.call_tool('diagnostics', {'directory': str(directory)})


@dataclass(slots=True, kw_only=True, frozen=True)
class Scripted:
    runner: RecordingCommandRunner
    module: Path


@pytest.fixture
def module(project_root: Path) -> Path:
    directory = project_root.joinpath('module')
    directory.mkdir()
    return directory
