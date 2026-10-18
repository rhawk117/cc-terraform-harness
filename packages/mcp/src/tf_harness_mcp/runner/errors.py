"""Failures raised while starting a command."""

from tf_harness_mcp.errors import HarnessError


class CommandNotAllowedError(HarnessError):
    def __init__(self, *, command: str) -> None:
        self.command = command
        super().__init__(f'command is not in the read-only set: {command}')


class CommandNotFoundError(HarnessError):
    def __init__(self, *, command: str) -> None:
        self.command = command
        super().__init__(f'command not found on PATH: {command}')


class CommandTimeoutError(HarnessError):
    def __init__(self, *, command: str, timeout_seconds: float) -> None:
        self.command = command
        self.timeout_seconds = timeout_seconds
        super().__init__(f'command timed out after {timeout_seconds} seconds: {command}')
