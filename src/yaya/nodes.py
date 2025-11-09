"""
Clean AST node types for lossless YAML representation.

This module defines a simple, immutable AST where every formatting detail
is captured as part of the node structure. Unlike ruamel.yaml's approach
of storing comments as attributes on nearby nodes, we treat all content
(including whitespace and comments) as first-class nodes.
"""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Node:
    """Base class for all AST nodes."""
    pass


@dataclass(frozen=True)
class Scalar(Node):
    """
    A scalar value (string, number, boolean, null).

    Attributes:
        value: The actual value as a string
        style: How the scalar is quoted/formatted
        indent: Number of spaces before this scalar (for block context)
    """
    value: str
    style: Literal['plain', 'single', 'double', 'literal', 'folded']
    indent: int = 0


@dataclass(frozen=True)
class KeyValue(Node):
    """
    A key-value pair in a mapping.

    Attributes:
        key: Key node (usually a Scalar)
        value: Value node (any Node type)
    """
    key: Node
    value: Node


@dataclass(frozen=True)
class Mapping(Node):
    """
    A YAML mapping (dictionary).

    Attributes:
        items: List of nodes (KeyValue, BlankLines, Comment)
        style: Flow {k: v} vs block style
        indent: Base indentation for this mapping
    """
    items: tuple[Node, ...]
    style: Literal['block', 'flow'] = 'block'
    indent: int = 0


@dataclass(frozen=True)
class Sequence(Node):
    """
    A YAML sequence (list).

    Attributes:
        items: List of nodes
        style: Flow [a, b] vs block style
        indent: Base indentation for this sequence
        offset: For block style, offset of dash from parent (0=aligned, 2=indented)
    """
    items: tuple[Node, ...]
    style: Literal['block', 'flow'] = 'block'
    indent: int = 0
    offset: int = 2


@dataclass(frozen=True)
class Comment(Node):
    """
    A comment line.

    Attributes:
        text: Comment text without the '#' prefix
        indent: Number of spaces before the '#'
    """
    text: str
    indent: int = 0


@dataclass(frozen=True)
class InlineCommented(Node):
    """
    Wrapper for a node with an inline comment.

    Attributes:
        node: The actual node (Scalar, Mapping, etc.)
        comment: Comment text without the '#' prefix
    """
    node: Node
    comment: str


@dataclass(frozen=True)
class BlankLines(Node):
    """
    One or more blank lines.

    Attributes:
        count: Number of blank lines
    """
    count: int = 1


@dataclass(frozen=True)
class Document(Node):
    """
    Top-level document node.

    A document is a sequence of nodes, which may include the main content
    plus leading/trailing comments and blank lines.

    Attributes:
        nodes: All nodes in the document (comments, blank lines, content)
    """
    nodes: tuple[Node, ...]
