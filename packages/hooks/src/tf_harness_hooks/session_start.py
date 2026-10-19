"""The session-start subcommand: report the terraform, tflint and terraform-ls versions."""

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from tf_harness_mcp.runner.domain import Command
from tf_harness_mcp.runner.errors import CommandNotFoundError, CommandTimeoutError

from tf_harness_hooks.domain import HookOutput
from tf_harness_hooks.policy import (
    TERRAFORM_LS_VERSION_ARGV,
    TERRAFORM_VERSION_ARGV,
    TFLINT_VERSION_ARGV,
)

if TYPE_CHECKING:
    from tf_harness_hooks.domain import HookRequest

PROBE_TIMEOUT_SECONDS: Final = 10.0


@dataclass(slots=True, kw_only=True, frozen=True)
class ToolProbe:
    name: str
    argv: tuple[str, ...]
    degrades: str


TOOL_PROBES: Final[tuple[ToolProbe, ...]] = (
    ToolProbe(
        name='terraform',
        argv=TERRAFORM_VERSION_ARGV,
        degrades='the fmt hook and the validate check of the read hook are skipped',
    ),
    ToolProbe(
        name='tflint',
        argv=TFLINT_VERSION_ARGV,
        degrades='the tflint check of the read hook is skipped',
    ),
    ToolProbe(
        name='terraform-ls',
        argv=TERRAFORM_LS_VERSION_ARGV,
        degrades='the code-intelligence language server (.lsp.json) cannot start',
    ),
)


def parse_version(probe: ToolProbe, stdout: str) -> str | None:
    if probe.name == 'terraform':
        try:
            version = json.loads(stdout).get('terraform_version')
        except json.JSONDecodeError, AttributeError:
            return None
        return version if isinstance(version, str) else None

    first_line = stdout.strip().splitlines()[:1]
    if not first_line:
        return None

    return first_line[0].removeprefix('TFLint version ').strip()


async def describe_tool(request: HookRequest, probe: ToolProbe) -> str:
    command = Command(argv=probe.argv, cwd=request.project_root)
    try:
        result = await request.runner.run(command, PROBE_TIMEOUT_SECONDS)
    except CommandNotFoundError:
        return f'{probe.name}: not found; {probe.degrades}'
    except CommandTimeoutError:
        return f'{probe.name}: version check timed out after {PROBE_TIMEOUT_SECONDS:g}s'
    except OSError as err:
        return f'{probe.name}: could not run ({err.strerror or type(err).__name__})'

    if result.returncode != 0:
        return f'{probe.name}: version check exited with code {result.returncode}'

    version = parse_version(probe, result.stdout)
    if version is None:
        return f'{probe.name}: installed, version not readable'

    return f'{probe.name}: {version}'


async def report_tool_versions(request: HookRequest) -> HookOutput | None:
    lines = [await describe_tool(request, probe) for probe in TOOL_PROBES]
    return HookOutput(event_name=request.event_name, additional_context='\n'.join(lines))
