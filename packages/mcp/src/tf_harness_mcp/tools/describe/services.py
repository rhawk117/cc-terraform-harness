"""Summarize a module, a Terraform file or a tfvars file from the structure layer's parse."""

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver.exceptions import ToolError

from tf_harness_mcp.errors import HarnessError
from tf_harness_mcp.policies import containment
from tf_harness_mcp.policies.budget import create_output_budget
from tf_harness_mcp.structure.services import (
    create_block_indexer,
    first_child_of_type,
    get_children,
    node_text,
    read_attributes,
    read_flag,
    read_required_providers,
    read_string,
    read_value,
)
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

    from tree_sitter import Node

    from tf_harness_mcp.policies.budget import OutputBudget
    from tf_harness_mcp.settings import Settings
    from tf_harness_mcp.structure.domain import Block, RequiredProvider
    from tf_harness_mcp.structure.errors import FileProblem
    from tf_harness_mcp.structure.services import BlockIndexer, FileIndex
    from tf_harness_mcp.tools.describe.domain import (
        TargetKind,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class NamedBlock:
    node: Node
    block: Block


def read_named_blocks(index: FileIndex) -> list[NamedBlock]:
    body = first_child_of_type(index.root, 'body')
    nodes = get_children(body, 'block')
    pairs = zip(nodes, index.blocks, strict=True)
    return [NamedBlock(node=node, block=block) for node, block in pairs]


def get_label(block: Block, position: int) -> str:
    return block.labels[position] if len(block.labels) > position else ''


def locate_node(node: Node, file: Path) -> Location:
    return Location(
        file=str(file), start_line=node.start_point.row + 1, end_line=node.end_point.row + 1
    )


def locate_block(block: Block) -> Location:
    return Location(file=str(block.file), start_line=block.start_line, end_line=block.end_line)


def make_variable(item: NamedBlock) -> VariableEntry:
    attributes = read_attributes(item.node)
    type_expression = read_value(attributes.get('type'))
    return VariableEntry(
        name=get_label(item.block, 0),
        type=node_text(type_expression) if type_expression else None,
        has_default='default' in attributes,
        description=read_string(read_value(attributes.get('description'))),
        sensitive=read_flag(read_value(attributes.get('sensitive'))),
        location=locate_block(item.block),
    )


def make_output(item: NamedBlock) -> OutputEntry:
    attributes = read_attributes(item.node)
    return OutputEntry(
        name=get_label(item.block, 0),
        description=read_string(read_value(attributes.get('description'))),
        sensitive=read_flag(read_value(attributes.get('sensitive'))),
        location=locate_block(item.block),
    )


def make_object(item: NamedBlock) -> ObjectEntry:
    return ObjectEntry(
        type=get_label(item.block, 0),
        name=get_label(item.block, 1),
        location=locate_block(item.block),
    )


def make_module_call(item: NamedBlock) -> ModuleCallEntry:
    return ModuleCallEntry(
        name=get_label(item.block, 0),
        source=item.block.source,
        location=locate_block(item.block),
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


def select_required_providers(item: NamedBlock) -> list[ProviderEntry]:
    return list(map(make_provider, read_required_providers(item.node, item.block.file)))


def select_kind(items: list[NamedBlock], kind: str) -> list[NamedBlock]:
    return [item for item in items if item.block.kind == kind]


def make_problem(problem: FileProblem) -> ProblemEntry:
    return ProblemEntry(path=str(problem.path), message=str(problem))


def summarize_module(path: Path, kind: TargetKind, indexes: list[FileIndex]) -> ModuleSummary:
    items = [item for index in indexes for item in read_named_blocks(index)]
    terraform_blocks = select_kind(items, 'terraform')
    return ModuleSummary(
        path=str(path),
        kind=kind,
        variables=list(map(make_variable, select_kind(items, 'variable'))),
        outputs=list(map(make_output, select_kind(items, 'output'))),
        resources=list(map(make_object, select_kind(items, 'resource'))),
        data_sources=list(map(make_object, select_kind(items, 'data'))),
        module_calls=list(map(make_module_call, select_kind(items, 'module'))),
        required_providers=[
            provider for item in terraform_blocks for provider in select_required_providers(item)
        ],
        problems=[make_problem(index.problem) for index in indexes if index.problem],
    )


def read_assignments(path: Path, index: FileIndex) -> list[AssignmentEntry]:
    return [
        AssignmentEntry(name=name, location=locate_node(attribute, path))
        for name, attribute in read_attributes(index.root).items()
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
