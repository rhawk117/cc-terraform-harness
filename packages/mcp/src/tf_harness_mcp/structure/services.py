"""Block index over tree-sitter-hcl and the local module graph built from it."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter_hcl
from tree_sitter import Language, Parser

from tf_harness_mcp.policies.containment import PathContainmentPolicy
from tf_harness_mcp.structure.domain import Block, ModuleGraph, ModuleIndex, ModuleNode
from tf_harness_mcp.structure.errors import HclSyntaxError, UnreadableFileError
from tf_harness_mcp.structure.policy import LocalSourcePolicy

if TYPE_CHECKING:
    from tree_sitter import Node

    from tf_harness_mcp.structure.errors import FileProblem

LABEL_TYPES = frozenset({'string_lit', 'identifier'})


def node_text(node: Node) -> str:
    return (node.text or b'').decode()


def first_child_of_type(node: Node | None, type_name: str) -> Node | None:
    if node is None:
        return None

    return next((child for child in node.children if child.type == type_name), None)


def read_label(node: Node) -> str:
    text = node_text(node)
    return text.strip('"') if node.type == 'string_lit' else text


def read_literal_source(block: Node) -> str | None:
    body = first_child_of_type(block, 'body')
    attributes = (child for child in (body.children if body else ()) if child.type == 'attribute')
    attribute = next((a for a in attributes if node_text(a.children[0]) == 'source'), None)
    expression = first_child_of_type(attribute, 'expression')
    literal = first_child_of_type(expression, 'literal_value')
    string = first_child_of_type(literal, 'string_lit')
    return read_label(string) if string else None


def read_block(block: Node, file: Path) -> Block:
    kind = node_text(block.children[0])
    labels = tuple(read_label(child) for child in block.children[1:] if child.type in LABEL_TYPES)
    return Block(
        kind=kind,
        labels=labels,
        file=file,
        start_line=block.start_point.row + 1,
        end_line=block.end_point.row + 1,
        source=read_literal_source(block) if kind == 'module' else None,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class FileIndex:
    blocks: tuple[Block, ...]
    problem: FileProblem | None


@dataclass(slots=True, kw_only=True, frozen=True)
class BlockIndexer:
    root: Path
    parser: Parser

    def is_inside_root(self, path: Path) -> bool:
        return PathContainmentPolicy(root=self.root, path=path).is_inside_root

    def select_files(self, directory: Path) -> tuple[Path, ...]:
        return tuple(path for path in sorted(directory.glob('*.tf')) if self.is_inside_root(path))

    def index_file(self, path: Path) -> FileIndex:
        try:
            content = path.read_bytes()
        except OSError:
            return FileIndex(blocks=(), problem=UnreadableFileError(path=path))

        tree = self.parser.parse(content)
        if tree.root_node.has_error:
            return FileIndex(blocks=(), problem=HclSyntaxError(path=path))

        body = first_child_of_type(tree.root_node, 'body')
        nodes = (child for child in (body.children if body else ()) if child.type == 'block')
        return FileIndex(blocks=tuple(read_block(node, path) for node in nodes), problem=None)

    def index_module(self, directory: Path) -> ModuleIndex:
        files = tuple(map(self.index_file, self.select_files(directory)))
        return ModuleIndex(
            directory=directory,
            blocks=tuple(block for file in files for block in file.blocks),
            problems=tuple(file.problem for file in files if file.problem),
        )


def create_block_indexer(root: Path) -> BlockIndexer:
    return BlockIndexer(root=root, parser=Parser(Language(tree_sitter_hcl.language())))


def index_module(root: Path, directory: Path) -> ModuleIndex:
    return create_block_indexer(root).index_module(directory)


def find_module_directories(root: Path) -> tuple[Path, ...]:
    found: list[Path] = []
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not name.startswith('.'))
        if any(name.endswith('.tf') for name in filenames):
            found.append(Path(current))

    return tuple(found)


@dataclass(slots=True, kw_only=True, frozen=True)
class ModuleGraphBuilder:
    root: Path
    indexer: BlockIndexer

    def select_calls(self, index: ModuleIndex) -> tuple[Path, ...]:
        sources = (block.source for block in index.blocks if block.kind == 'module')
        policies = (
            LocalSourcePolicy(root=self.root, module_dir=index.directory, source=source)
            for source in sources
            if source is not None
        )
        return tuple(policy.target for policy in policies if not policy.get_source_problem())

    def build_node(self, directory: Path) -> ModuleNode:
        index = self.indexer.index_module(directory)
        return ModuleNode(index=index, calls=self.select_calls(index))

    def build(self) -> ModuleGraph:
        directories = find_module_directories(self.root)
        return ModuleGraph(root=self.root, modules=tuple(map(self.build_node, directories)))


def build_module_graph(root: Path) -> ModuleGraph:
    resolved_root = root.resolve()
    indexer = create_block_indexer(resolved_root)
    builder = ModuleGraphBuilder(root=resolved_root, indexer=indexer)
    return builder.build()
