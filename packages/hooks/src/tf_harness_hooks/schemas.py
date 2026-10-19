"""Hook stdin: untrusted JSON that Claude Code writes for every hook event."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ToolInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra='ignore')

    file_path: Path | None = None


class HookEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra='ignore')

    hook_event_name: str
    cwd: Path | None = None
    tool_name: str | None = None
    tool_input: ToolInput = ToolInput()

    @property
    def file_path(self) -> Path | None:
        return self.tool_input.file_path
