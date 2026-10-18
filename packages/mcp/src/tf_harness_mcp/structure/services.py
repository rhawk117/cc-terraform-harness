"""Block index over tree-sitter-hcl and the local module graph built from it."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter_hcl
from tree_sitter import Language, Parser

from tf_harness_mcp.policies.containment import PathContainmentPolicy
from tf_harness_mcp.structure.domain import (
    Attribute,
    Block,
    BlockEntry,
    ModuleGraph,
    ModuleIndex,
    ModuleNode,
    RequiredProvider,
)
from tf_harness_mcp.structure.errors import HclSyntaxError, UnreadableFileError
from tf_harness_mcp.structure.policy import LocalSourcePolicy

if TYPE_CHECKING:
    from tree_sitter import Node

    from tf_harness_mcp.structure.errors import FileProblem

LABEL_TYPES = frozenset({'string_lit', 'identifier'})
OBJECT_ELEMENT_EXPRESSIONS = 2


def node_text(node: Node) -> str:
    return (node.text or b'').decode()


def first_child_of_type(node: Node | None, type_name: str) -> Node | None:
    if node is None:
        return None

    return next((child for child in node.children if child.type == type_name), None)


def get_children(node: Node | None, type_name: str) -> list[Node]:
    return [child for child in (node.children if node else ()) if child.type == type_name]


def read_attributes(container: Node | None) -> dict[str, Node]:
    body = first_child_of_type(container, 'body')
    return {node_text(node.children[0]): node for node in get_children(body, 'attribute')}


def read_value(attribute: Node | None) -> Node | None:
    return first_child_of_type(attribute, 'expression')


def read_string(expression: Node | None) -> str | None:
    literal = first_child_of_type(expression, 'literal_value')
    quoted = first_child_of_type(literal, 'string_lit')
    template = first_child_of_type(expression, 'template_expr')
    heredoc = first_child_of_type(template, 'heredoc_template')
    text = quoted or heredoc
    if text is None:
        return None

    return ''.join(map(node_text, get_children(text, 'template_literal'))).strip()


def read_flag(expression: Node | None) -> bool:
    literal = first_child_of_type(expression, 'literal_value')
    flag = first_child_of_type(literal, 'bool_lit')
    return flag is not None and node_text(flag) == 'true'


def read_object_fields(expression: Node | None) -> dict[str, Node]:
    collection = first_child_of_type(expression, 'collection_value')
    elements = get_children(first_child_of_type(collection, 'object'), 'object_elem')
    pairs = [get_children(element, 'expression') for element in elements]
    return {
        node_text(pair[0]): pair[1] for pair in pairs if len(pair) == OBJECT_ELEMENT_EXPRESSIONS
    }


def read_required_provider(name: str, attribute: Node, file: Path) -> RequiredProvider:
    expression = read_value(attribute)
    fields = read_object_fields(expression)
    legacy_version = None if fields else read_string(expression)
    return RequiredProvider(
        local_name=name,
        source=read_string(fields.get('source')),
        version=read_string(fields.get('version')) or legacy_version,
        file=file,
        start_line=attribute.start_point.row + 1,
        end_line=attribute.end_point.row + 1,
    )


def read_required_providers(terraform: Node, file: Path) -> tuple[RequiredProvider, ...]:
    nested = get_children(first_child_of_type(terraform, 'body'), 'block')
    declarations = [node for node in nested if node_text(node.children[0]) == 'required_providers']
    return tuple(
        read_required_provider(name, attribute, file)
        for declaration in declarations
        for name, attribute in read_attributes(declaration).items()
    )


def read_label(node: Node) -> str:
    text = node_text(node)
    return text.strip('"') if node.type == 'string_lit' else text


def read_attribute(name: str, attribute: Node) -> Attribute:
    expression = read_value(attribute)
    return Attribute(
        name=name,
        expression=node_text(expression) if expression else '',
        string=read_string(expression),
        flag=read_flag(expression),
        start_line=attribute.start_point.row + 1,
        end_line=attribute.end_point.row + 1,
    )


def read_attribute_values(container: Node | None) -> tuple[Attribute, ...]:
    return tuple(read_attribute(name, node) for name, node in read_attributes(container).items())


def read_block(block: Node, file: Path, attributes: tuple[Attribute, ...]) -> Block:
    kind = node_text(block.children[0])
    labels = tuple(read_label(child) for child in block.children[1:] if child.type in LABEL_TYPES)
    source = next((a.string for a in attributes if a.name == 'source'), None)
    return Block(
        kind=kind,
        labels=labels,
        file=file,
        start_line=block.start_point.row + 1,
        end_line=block.end_point.row + 1,
        source=source if kind == 'module' else None,
    )


def read_block_entry(node: Node, file: Path) -> BlockEntry:
    attributes = read_attribute_values(node)
    block = read_block(node, file, attributes)
    providers = read_required_providers(node, file) if block.kind == 'terraform' else ()
    return BlockEntry(block=block, attributes=attributes, required_providers=providers)


@dataclass(slots=True, kw_only=True, frozen=True)
class FileIndex:
    problem: FileProblem | None
    entries: tuple[BlockEntry, ...] = ()
    attributes: tuple[Attribute, ...] = ()

    @property
    def blocks(self) -> tuple[Block, ...]:
        return tuple(entry.block for entry in self.entries)


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
            return FileIndex(problem=UnreadableFileError(path=path))

        return self.index_content(content, path)

    def index_text(self, text: str, path: Path) -> FileIndex:
        return self.index_content(text.encode(), path)

    def index_content(self, content: bytes, path: Path) -> FileIndex:
        tree = self.parser.parse(content)
        if tree.root_node.has_error:
            return FileIndex(problem=HclSyntaxError(path=path))

        body = first_child_of_type(tree.root_node, 'body')
        nodes = (child for child in (body.children if body else ()) if child.type == 'block')
        entries = tuple(read_block_entry(node, path) for node in nodes)
        attributes = read_attribute_values(tree.root_node)
        return FileIndex(entries=entries, attributes=attributes, problem=None)

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
