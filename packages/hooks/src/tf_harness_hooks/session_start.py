"""The session-start subcommand: report the terraform, tflint and terraform-ls versions."""

from typing import TYPE_CHECKING, Final

from tf_harness_mcp.runner.domain import Command
from tf_harness_mcp.runner.errors import CommandNotFoundError, CommandTimeoutError

from tf_harness_hooks.domain import HookOutput
from tf_harness_hooks.policy import TOOL_PROBES

if TYPE_CHECKING:
    from tf_harness_hooks.domain import HookRequest
    from tf_harness_hooks.policy import ToolProbe

PROBE_TIMEOUT_SECONDS: Final = 10.0


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

    version = probe.parser.parse(result.stdout)
    if version is None:
        return f'{probe.name}: installed, version not readable'

    return f'{probe.name}: {version}'


async def report_tool_versions(request: HookRequest) -> HookOutput | None:
    lines = [await describe_tool(request, probe) for probe in TOOL_PROBES]
    return HookOutput(event_name=request.event_name, additional_context='\n'.join(lines))
