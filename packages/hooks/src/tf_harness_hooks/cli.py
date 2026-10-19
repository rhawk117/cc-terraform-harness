"""The tf-harness-hooks entry point: read one hook event, run a subcommand, print its output."""

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
from pydantic import ValidationError
from tf_harness_mcp.runner.process import create_command_runner

from tf_harness_hooks.domain import (
    FILE_SUBCOMMANDS,
    SUBCOMMANDS,
    HookIo,
    HookRequest,
    HookSession,
    default_handlers,
)
from tf_harness_hooks.policy import HookFilePolicy
from tf_harness_hooks.schemas import HookEvent

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from tf_harness_hooks.domain import Subcommand

PROJECT_DIR_VARIABLE = 'CLAUDE_PROJECT_DIR'
INVALID_EVENT = 1
USAGE_ERROR = 2


def find_subcommand(argv: Sequence[str]) -> Subcommand | None:
    if len(argv) != 1:
        return None

    return next((name for name in SUBCOMMANDS if name == argv[0]), None)


def gate_file(session: HookSession, event: HookEvent, project_root: Path) -> int | None:
    """Return the exit code that ends the hook before any handler runs, or None to go on."""
    if session.subcommand not in FILE_SUBCOMMANDS:
        return None

    if event.file_path is None:
        return 0

    policy = HookFilePolicy(project_root=project_root, file_path=event.file_path)
    if not policy.is_terraform_file:
        return 0

    if policy.get_file_problem():
        return 0

    return None


def run_hook(session: HookSession) -> int:
    project_dir = session.environ.get(PROJECT_DIR_VARIABLE)
    if project_dir is None or project_dir == '':
        return 0

    try:
        event = HookEvent.model_validate_json(session.io.stdin.read())
    except ValidationError as err:
        session.io.stderr.write(f'invalid hook event: {err}\n')
        return INVALID_EVENT

    project_root = Path(project_dir)
    if (exit_code := gate_file(session, event, project_root)) is not None:
        return exit_code

    request = HookRequest(
        event_name=event.hook_event_name,
        project_root=project_root,
        runner=session.runner,
        file_path=event.file_path,
    )
    output = anyio.run(session.handlers[session.subcommand], request)
    if output is not None:
        session.io.stdout.write(json.dumps(output.to_wire()))

    return 0


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    env = os.environ if environ is None else environ
    subcommand = find_subcommand(args)
    if subcommand is None:
        sys.stderr.write(f'usage: tf-harness-hooks {{{"|".join(SUBCOMMANDS)}}}\n')
        return USAGE_ERROR

    session = HookSession(
        subcommand=subcommand,
        environ=env,
        io=HookIo(stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr),
        runner=create_command_runner(env),
        handlers=default_handlers(),
    )
    return run_hook(session)
