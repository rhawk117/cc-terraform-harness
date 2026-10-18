"""Summarize a module, a Terraform file or a tfvars file from the structure layer's parse."""

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver.exceptions import ToolError

from tf_harness_mcp.errors import HarnessError
from tf_harness_mcp.policies import containment
from tf_harness_mcp.policies.budget import create_output_budget
from tf_harness_mcp.structure.services import create_block_indexer
from tf_harness_mcp.tools.describe.domain import (
    AssignmentEntry,
    Location,
    ModuleCallEntry,
    ModuleSummary,
    ObjectEntry,
    OutputEntry,
    ProblemEntry,
    ProviderEntry,
    TfvarsSummary,
    VariableEntry,
)
from tf_harness_mcp.tools.describe.errors import DescribeTargetError

if TYPE_CHECKING:
    from pathlib import Path

    from tf_harness_mcp.policies.budget import OutputBudget
    from tf_harness_mcp.settings import Settings
    from tf_harness_mcp.structure.domain import Block, BlockEntry, RequiredProvider
    from tf_harness_mcp.structure.errors import FileProblem
    from tf_harness_mcp.structure.services import BlockIndexer, FileIndex
    from tf_harness_mcp.tools.describe.domain import (
        TargetKind,
    )


def get_label(block: Block, position: int) -> str:
    return block.labels[position] if len(block.labels) > position else ''


def locate_block(block: Block) -> Location:
    return Location(file=str(block.file), start_line=block.start_line, end_line=block.end_line)


def read_description(entry: BlockEntry) -> str | None:
    description = entry.get_attribute('description')
    return description.string if description else None


def read_sensitive(entry: BlockEntry) -> bool:
    sensitive = entry.get_attribute('sensitive')
    return sensitive.flag if sensitive else False


def make_variable(entry: BlockEntry) -> VariableEntry:
    type_attribute = entry.get_attribute('type')
    return VariableEntry(
        name=get_label(entry.block, 0),
        type=type_attribute.expression if type_attribute else None,
        has_default=entry.get_attribute('default') is not None,
        description=read_description(entry),
        sensitive=read_sensitive(entry),
        location=locate_block(entry.block),
    )


def make_output(entry: BlockEntry) -> OutputEntry:
    return OutputEntry(
        name=get_label(entry.block, 0),
        description=read_description(entry),
        sensitive=read_sensitive(entry),
        location=locate_block(entry.block),
    )


def make_object(entry: BlockEntry) -> ObjectEntry:
    return ObjectEntry(
        type=get_label(entry.block, 0),
        name=get_label(entry.block, 1),
        location=locate_block(entry.block),
    )


def make_module_call(entry: BlockEntry) -> ModuleCallEntry:
    return ModuleCallEntry(
        name=get_label(entry.block, 0),
        source=entry.block.source,
        location=locate_block(entry.block),
    )


def make_provider(provider: RequiredProvider) -> ProviderEntry:
    return ProviderEntry(
        local_name=provider.local_name,
        source=provider.source,
        version=provider.version,
        location=Location(
            file=str(provider.file), start_line=provider.start_line, end_line=provider.end_line
        ),
    )


def select_kind(entries: list[BlockEntry], kind: str) -> list[BlockEntry]:
    return [entry for entry in entries if entry.block.kind == kind]


def make_problem(problem: FileProblem) -> ProblemEntry:
    return ProblemEntry(path=str(problem.path), message=str(problem))


def summarize_module(path: Path, kind: TargetKind, indexes: list[FileIndex]) -> ModuleSummary:
    items = [entry for index in indexes for entry in index.entries]
    return ModuleSummary(
        path=str(path),
        kind=kind,
        variables=list(map(make_variable, select_kind(items, 'variable'))),
        outputs=list(map(make_output, select_kind(items, 'output'))),
        resources=list(map(make_object, select_kind(items, 'resource'))),
        data_sources=list(map(make_object, select_kind(items, 'data'))),
        module_calls=list(map(make_module_call, select_kind(items, 'module'))),
        required_providers=[
            make_provider(provider)
            for entry in select_kind(items, 'terraform')
            for provider in entry.required_providers
        ],
        problems=[make_problem(index.problem) for index in indexes if index.problem],
    )


def read_assignments(path: Path, index: FileIndex) -> list[AssignmentEntry]:
    return [
        AssignmentEntry(
            name=attribute.name,
            location=Location(
                file=str(path), start_line=attribute.start_line, end_line=attribute.end_line
            ),
        )
        for attribute in index.attributes
    ]


@dataclass(slots=True, kw_only=True, frozen=True)
class DescribeTool:
    root: Path
    budget: OutputBudget
    indexer: BlockIndexer

    def describe_files(
        self, path: Path, kind: TargetKind, files: tuple[Path, ...]
    ) -> ModuleSummary:
        return summarize_module(path, kind, list(map(self.indexer.index_file, files)))

    def describe_tfvars(self, path: Path) -> TfvarsSummary:
        module = self.indexer.index_module(path.parent)
        declared = {get_label(block, 0) for block in module.blocks if block.kind == 'variable'}
        index = self.indexer.index_file(path)
        assigned = read_assignments(path, index)
        problems = [index.problem, *module.problems]
        return TfvarsSummary(
            path=str(path),
            kind='tfvars',
            declared=[entry for entry in assigned if entry.name in declared],
            undeclared=[entry for entry in assigned if entry.name not in declared],
            problems=[make_problem(problem) for problem in problems if problem],
        )

    def describe_target(self, path: Path) -> ModuleSummary | TfvarsSummary:
        if path.is_dir():
            return self.describe_files(path, 'module', self.indexer.select_files(path))

        if path.is_file() and path.suffix == '.tf':
            return self.describe_files(path, 'file', (path,))

        if path.is_file() and path.suffix == '.tfvars':
            return self.describe_tfvars(path)

        raise DescribeTargetError(path=path)

    async def describe(self, path: containment.ProjectPath) -> dict[str, Any]:
        """Summarize one Terraform module, `.tf` file or `.tfvars` file without changing anything.

        For a module directory or a `.tf` file, lists the variables (type, whether a default
        exists, description, sensitive), outputs, resources, data sources, module calls with
        their sources and required providers with source and version constraint, each with its
        file and line range. For a `.tfvars` file, lists the variables it assigns, split into
        those declared by the module in the same directory and those that are not. Files that
        cannot be read or do not parse are reported under problems. The path is relative to the
        project root or absolute inside it.
        """
        try:
            resolved = containment.resolve_project_path(self.root, path)
            return self.budget.apply(asdict(self.describe_target(resolved)))
        except HarnessError as err:
            raise ToolError(str(err)) from err


def create_describe_tool(settings: Settings) -> DescribeTool:
    return DescribeTool(
        root=settings.project_root,
        budget=create_output_budget(settings),
        indexer=create_block_indexer(settings.project_root),
    )
