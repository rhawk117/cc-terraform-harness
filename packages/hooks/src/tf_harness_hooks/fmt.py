"""The fmt subcommand: format one written terraform file and report only a rewrite or a failure."""

from typing import TYPE_CHECKING, Final

from tf_harness_mcp.runner.domain import Command
from tf_harness_mcp.runner.errors import CommandNotFoundError, CommandTimeoutError

from tf_harness_hooks.domain import HookOutput
from tf_harness_hooks.policy import FMT_WRITE_PREFIX

if TYPE_CHECKING:
    from tf_harness_hooks.domain import HookRequest

FMT_TIMEOUT_SECONDS: Final = 15.0


async def format_file(request: HookRequest) -> HookOutput | None:
    if request.file_path is None:
        return None

    command = Command(argv=(*FMT_WRITE_PREFIX, str(request.file_path)), cwd=request.project_root)
    try:
        result = await request.runner.run(command, FMT_TIMEOUT_SECONDS)
    except CommandNotFoundError:
        return None
    except CommandTimeoutError:
        notice = f'terraform fmt timed out after {FMT_TIMEOUT_SECONDS:g}s on {request.file_path}'
        return HookOutput(event_name=request.event_name, additional_context=notice)

    if result.returncode != 0:
        failure = result.stderr.strip() or result.stdout.strip()
        return HookOutput(event_name=request.event_name, additional_context=failure)

    if result.stdout.strip():
        notice = f'terraform fmt rewrote {request.file_path}'
        return HookOutput(event_name=request.event_name, additional_context=notice)

    return None
