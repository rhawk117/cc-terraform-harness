"""Report the Terraform blocks a diff changed, their interface changes and the roots they reach."""

from collections import defaultdict
from dataclasses import asdict, dataclass
from operator import attrgetter
from typing import TYPE_CHECKING, Any

from tf_harness_mcp.policies import containment
from tf_harness_mcp.policies.budget import create_output_budget
from tf_harness_mcp.structure.services import (
    FileIndex,
    build_module_graph,
    create_block_indexer,
)
from tf_harness_mcp.tools.change_impact.domain import (
    AffectedRoot,
    ChangeImpact,
    GitOptions,
    ModuleInterface,
    ProblemEntry,
    Variable,
)
from tf_harness_mcp.tools.change_impact.errors import ChangedFileOutsideRootError
from tf_harness_mcp.tools.change_impact.policy import (
    BlockChangePolicy,
    InterfacePolicy,
    normalize_expression,
)
from tf_harness_mcp.tools.change_impact.repository import GitRepository
from tf_harness_mcp.tools.diagnostics.errors import DirectoryNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from tf_harness_mcp.errors import HarnessError
    from tf_harness_mcp.policies.budget import OutputBudget
    from tf_harness_mcp.runner.domain import CommandRunner
    from tf_harness_mcp.settings import Settings
    from tf_harness_mcp.structure.domain import BlockEntry, ModuleGraph
    from tf_harness_mcp.structure.errors import FileProblem
    from tf_harness_mcp.structure.services import BlockIndexer
    from tf_harness_mcp.tools.change_impact.domain import (
        ChangedBlock,
        ChangedFile,
        InterfaceChange,
    )

NO_BLOCKS = FileIndex(problem=None)


def read_expression(entry: BlockEntry, name: str) -> str | None:
    attribute = entry.get_attribute(name)
    return normalize_expression(attribute.expression) if attribute else None


def read_variable(entry: BlockEntry) -> Variable:
    return Variable(type=read_expression(entry, 'type'), default=read_expression(entry, 'default'))


def read_interface(indexes: Iterable[FileIndex]) -> ModuleInterface:
    entries = [entry for index in indexes for entry in index.entries if entry.block.labels]
    return ModuleInterface(
        variables={
            entry.block.labels[0]: read_variable(entry)
            for entry in entries
            if entry.block.kind == 'variable'
        },
        outputs=frozenset(
            entry.block.labels[0] for entry in entries if entry.block.kind == 'output'
        ),
    )


def make_problem(problem: FileProblem | ChangedFileOutsideRootError) -> ProblemEntry:
    return ProblemEntry(path=str(problem.path), message=str(problem))


def list_affected_roots(graph: ModuleGraph, directories: Iterable[Path]) -> list[AffectedRoot]:
    return [
        AffectedRoot(root=str(path[0]), module=str(directory), path=list(map(str, path)))
        for directory in directories
        for path in graph.find_root_paths(directory)
    ]


@dataclass(slots=True, kw_only=True, frozen=True)
class ChangeSnapshot:
    changed: ChangedFile
    path: Path
    base: FileIndex
    current: FileIndex
    escape: ChangedFileOutsideRootError | None = None

    @property
    def directory(self) -> Path:
        return self.path.parent

    @property
    def problem(self) -> HarnessError | None:
        return self.base.problem or self.current.problem


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotReader:
    indexer: BlockIndexer
    git: GitRepository
    base_commit: str

    async def read_base_index(self, changed: ChangedFile, path: Path) -> FileIndex:
        if changed.status == 'added':
            return NO_BLOCKS

        text = await self.git.read_base_content(self.base_commit, changed.path)
        return self.indexer.index_text(text, path)

    async def read(self, changed: ChangedFile) -> ChangeSnapshot:
        path = self.git.directory.joinpath(changed.path)
        if not self.indexer.is_inside_root(path):
            return ChangeSnapshot(
                changed=changed,
                path=path,
                base=NO_BLOCKS,
                current=NO_BLOCKS,
                escape=ChangedFileOutsideRootError(path=path),
            )

        current = NO_BLOCKS if changed.status == 'deleted' else self.indexer.index_file(path)
        return ChangeSnapshot(
            changed=changed,
            path=path,
            base=await self.read_base_index(changed, path),
            current=current,
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class InterfaceComparison:
    changes: list[InterfaceChange]
    problems: list[ProblemEntry]


@dataclass(slots=True, kw_only=True, frozen=True)
class InterfaceReader:
    indexer: BlockIndexer

    def compare(self, directory: Path, snapshots: list[ChangeSnapshot]) -> InterfaceComparison:
        changed_paths = {snapshot.path for snapshot in snapshots}
        unchanged = [
            self.indexer.index_file(path)
            for path in self.indexer.select_files(directory)
            if path not in changed_paths
        ]
        base = read_interface([*unchanged, *(snapshot.base for snapshot in snapshots)])
        current = read_interface([*unchanged, *(snapshot.current for snapshot in snapshots)])
        policy = InterfacePolicy(module=str(directory), base=base, current=current)
        return InterfaceComparison(
            changes=policy.list_changes(),
            problems=[make_problem(index.problem) for index in unchanged if index.problem],
        )


def group_by_module(snapshots: list[ChangeSnapshot]) -> dict[Path, list[ChangeSnapshot]]:
    modules: defaultdict[Path, list[ChangeSnapshot]] = defaultdict(list)
    for snapshot in sorted(snapshots, key=attrgetter('path')):
        modules[snapshot.directory].append(snapshot)

    return dict(modules)


def list_changed_blocks(snapshots: list[ChangeSnapshot]) -> list[ChangedBlock]:
    return [
        change
        for snapshot in snapshots
        for change in BlockChangePolicy(
            base=snapshot.base.blocks,
            current=snapshot.current.blocks,
            ranges=snapshot.changed.ranges,
        ).list_changes()
    ]


@dataclass(slots=True, kw_only=True, frozen=True)
class ChangeImpactTool:
    root: Path
    budget: OutputBudget
    indexer: BlockIndexer
    runner: CommandRunner
    git_options: GitOptions

    async def read_snapshots(
        self, git: GitRepository, base_ref: str
    ) -> tuple[str, list[ChangeSnapshot]]:
        changes = await git.read_changes(base_ref)
        reader = SnapshotReader(indexer=self.indexer, git=git, base_commit=changes.base_commit)
        return changes.base_commit, [await reader.read(changed) for changed in changes.files]

    def resolve_directory(self, path: containment.ProjectPath) -> Path:
        resolved = containment.resolve_project_path(self.root, path)
        if not resolved.is_dir():
            raise DirectoryNotFoundError(path=resolved)

        return resolved

    async def analyze(self, directory: Path, base_ref: str) -> ChangeImpact:
        git = GitRepository(runner=self.runner, directory=directory, options=self.git_options)
        base_commit, snapshots = await self.read_snapshots(git, base_ref)
        escaped = [snapshot.escape for snapshot in snapshots if snapshot.escape]
        readable = [snapshot for snapshot in snapshots if not snapshot.escape]
        if problem := next((snapshot.problem for snapshot in readable if snapshot.problem), None):
            raise problem

        modules = group_by_module(readable)
        reader = InterfaceReader(indexer=self.indexer)
        comparisons = [reader.compare(module, members) for module, members in modules.items()]
        graph = build_module_graph(self.root)
        return ChangeImpact(
            base_commit=base_commit,
            blocks=list_changed_blocks(readable),
            interface=[change for comparison in comparisons for change in comparison.changes],
            roots=list_affected_roots(graph, modules),
            problems=[
                *map(make_problem, escaped),
                *(problem for comparison in comparisons for problem in comparison.problems),
            ],
        )

    async def change_impact(
        self, path: containment.ProjectPath, base_ref: str = 'HEAD'
    ) -> dict[str, Any]:
        """Report what a git diff changed in Terraform and which root modules it reaches.

        Give a directory inside the project and a base ref (default HEAD). Changes are the
        working tree, staged and untracked .tf files under that directory against the merge base
        of the ref and HEAD. Returns the changed blocks (added, modified or removed, a removed
        block located at its base file and line), each changed module's variable and output
        changes (added, removed, type or default changed, as expression text with whitespace
        collapsed) and every root module in the whole project that reaches a changed module with
        its shortest module call path. Reads only git and the files; no plan or state.
        The path is relative to the project root or absolute inside it.
        """
        directory = self.resolve_directory(path)
        result = await self.analyze(directory, base_ref)
        return self.budget.apply(asdict(result))


def create_change_impact_tool(runner: CommandRunner, settings: Settings) -> ChangeImpactTool:
    return ChangeImpactTool(
        root=settings.project_root,
        budget=create_output_budget(settings),
        indexer=create_block_indexer(settings.project_root),
        runner=runner,
        git_options=GitOptions(timeout_seconds=settings.git_timeout_seconds),
    )
