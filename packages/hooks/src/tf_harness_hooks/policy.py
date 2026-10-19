"""Which hook file paths may reach a handler."""

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from tf_harness_mcp.policies.containment import PathContainmentPolicy
from tf_harness_mcp.runner.policy import AllowedCommand, ReadOnlyOptions

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.policies.errors import PathOutsideRootError
TERRAFORM_SUFFIXES: Final[frozenset[str]] = frozenset({'.tf', '.tfvars'})
FMT_WRITE_PREFIX: Final[tuple[str, ...]] = ('terraform', 'fmt', '-list=true', '-no-color')


@runtime_checkable
class VersionParser(Protocol):
    def parse(self, stdout: str) -> str | None: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class JsonVersionParser:
    key: str

    def parse(self, stdout: str) -> str | None:
        try:
            version = json.loads(stdout).get(self.key)
        except json.JSONDecodeError, AttributeError:
            return None
        return version if isinstance(version, str) else None


@dataclass(slots=True, kw_only=True, frozen=True)
class FirstLineParser:
    prefix: str = ''

    def parse(self, stdout: str) -> str | None:
        first_line = stdout.strip().splitlines()[:1]
        if not first_line:
            return None

        return first_line[0].removeprefix(self.prefix).strip()


@dataclass(slots=True, kw_only=True, frozen=True)
class ToolProbe:
    name: str
    argv: tuple[str, ...]
    parser: VersionParser
    degrades: str


TOOL_PROBES: Final[tuple[ToolProbe, ...]] = (
    ToolProbe(
        name='terraform',
        argv=('terraform', 'version', '-json'),
        parser=JsonVersionParser(key='terraform_version'),
        degrades='the fmt hook and the validate check of the read hook are skipped',
    ),
    ToolProbe(
        name='tflint',
        argv=('tflint', '--version'),
        parser=FirstLineParser(prefix='TFLint version '),
        degrades='the tflint check of the read hook is skipped',
    ),
    ToolProbe(
        name='terraform-ls',
        argv=('terraform-ls', 'version'),
        parser=FirstLineParser(),
        degrades='the code-intelligence language server (.lsp.json) cannot start',
    ),
)

FMT_OPTIONS: Final[ReadOnlyOptions] = ReadOnlyOptions(
    commands=(
        AllowedCommand(
            prefix=FMT_WRITE_PREFIX, forbidden_flags=('-recursive', '-write=false', '-check')
        ),
    )
)
SESSION_START_OPTIONS: Final[ReadOnlyOptions] = ReadOnlyOptions(
    commands=tuple(
        AllowedCommand(prefix=probe.argv, forbidden_flags=('--init', '--fix'))
        for probe in TOOL_PROBES
    )
)


@dataclass(slots=True, kw_only=True, frozen=True)
class HookFilePolicy:
    project_root: Path
    file_path: Path

    @property
    def is_terraform_file(self) -> bool:
        return self.file_path.suffix in TERRAFORM_SUFFIXES

    def get_file_problem(self) -> PathOutsideRootError | None:
        containment = PathContainmentPolicy(root=self.project_root, path=self.file_path)
        return containment.get_path_problem()
