"""
Convert ruamel.yaml AST to clean yaya AST.

This module handles the conversion from ruamel.yaml's CommentedMap/CommentedSeq
to our clean immutable AST nodes, extracting formatting information from the
original bytes along the way.
"""
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from .nodes import (
    Node, Scalar, Mapping, Sequence, Comment, BlankLines, Document
)
from .extract import (
    extract_quote_style,
    extract_indentation,
    extract_mapping_style,
    extract_sequence_style,
    extract_sequence_offset,
)


def convert_to_clean_ast(
    ruamel_data: any,
    original_bytes: bytes,
) -> Document:
    """
    Convert ruamel.yaml AST to clean yaya AST.

    Args:
        ruamel_data: Parsed data from ruamel.yaml
        original_bytes: Original file bytes (for extracting formatting)

    Returns:
        Document node containing the clean AST
    """
    nodes = []

    # Extract leading comments (in ca.comment[1])
    if hasattr(ruamel_data, 'ca') and ruamel_data.ca.comment:
        # ca.comment is [before, after] where before/after can be None or list of CommentToken
        if ruamel_data.ca.comment[1]:  # Leading comments are in position [1]
            leading_comments = ruamel_data.ca.comment[1]
            for comment_token in (leading_comments if isinstance(leading_comments, list) else [leading_comments]):
                if comment_token:
                    comment_text = comment_token.value.lstrip('#').rstrip('\n').lstrip()
                    line = comment_token.start_mark.line
                    indent = extract_indentation(original_bytes, line)
                    nodes.append(Comment(text=comment_text, indent=indent))

    # Convert main content
    main_node = _convert_node(ruamel_data, original_bytes, parent_col=0)
    nodes.append(main_node)

    return Document(nodes=tuple(nodes))


def _convert_node(
    node: any,
    original_bytes: bytes,
    parent_col: int = 0,
    line: int | None = None,
    col: int | None = None,
) -> Node:
    """
    Convert a single ruamel node to clean AST.

    Args:
        node: ruamel.yaml node (CommentedMap, CommentedSeq, or scalar)
        original_bytes: Original file bytes
        parent_col: Column position of parent (for indentation calculation)
        line: Line position of this node (for scalars)
        col: Column position of this node (for scalars)

    Returns:
        Clean AST node
    """
    if isinstance(node, CommentedMap):
        return _convert_mapping(node, original_bytes, parent_col)
    elif isinstance(node, CommentedSeq):
        return _convert_sequence(node, original_bytes, parent_col)
    else:
        return _convert_scalar(node, original_bytes, parent_col, line=line, col=col)


def _convert_mapping(
    mapping: CommentedMap,
    original_bytes: bytes,
    parent_col: int,
) -> Mapping:
    """Convert a CommentedMap to Mapping node."""
    pairs = []

    # Get position of first key to determine style and indent
    if hasattr(mapping, 'lc') and mapping.lc.data and len(mapping) > 0:
        first_key = list(mapping.keys())[0]
        key_line, key_col, val_line, val_col = mapping.lc.data[first_key][:4]

        style = extract_mapping_style(original_bytes, val_line, val_col)
        indent = extract_indentation(original_bytes, key_line)
    else:
        style = 'block'
        indent = parent_col

    for key, value in mapping.items():
        # Get position info for this key-value pair
        if hasattr(mapping, 'lc') and key in mapping.lc.data:
            key_line, key_col, val_line, val_col = mapping.lc.data[key][:4]

            # Convert key
            key_node = _convert_scalar(key, original_bytes, key_col, line=key_line, col=key_col)

            # Convert value (pass position info for scalars)
            value_node = _convert_node(value, original_bytes, parent_col=key_col, line=val_line, col=val_col)

            pairs.append((key_node, value_node))
        else:
            # No position info - use defaults
            key_node = Scalar(value=str(key), style='plain', indent=indent)
            value_node = _convert_node(value, original_bytes, parent_col=indent)
            pairs.append((key_node, value_node))

    return Mapping(pairs=tuple(pairs), style=style, indent=indent)


def _convert_sequence(
    sequence: CommentedSeq,
    original_bytes: bytes,
    parent_col: int,
) -> Sequence:
    """Convert a CommentedSeq to Sequence node."""
    items = []

    # Get position of first item to determine style and indent
    if hasattr(sequence, 'lc') and sequence.lc.data and len(sequence) > 0:
        first_item_line, first_item_col = sequence.lc.data[0][:2]

        style = extract_sequence_style(original_bytes, first_item_line, first_item_col)
        # Indent is the parent's column, not the dash position
        indent = parent_col

        # For block style, extract offset (relative to parent)
        if style == 'block':
            offset = extract_sequence_offset(original_bytes, parent_col, first_item_line)
        else:
            offset = 0
    else:
        style = 'block'
        indent = parent_col
        offset = 2

    for i, item in enumerate(sequence):
        if hasattr(sequence, 'lc') and i in sequence.lc.data:
            item_line, item_col = sequence.lc.data[i][:2]
            item_node = _convert_node(item, original_bytes, parent_col=item_col)
        else:
            item_node = _convert_node(item, original_bytes, parent_col=indent)

        items.append(item_node)

    return Sequence(items=tuple(items), style=style, indent=indent, offset=offset)


def _convert_scalar(
    value: any,
    original_bytes: bytes,
    indent: int,
    line: int | None = None,
    col: int | None = None,
) -> Scalar:
    """Convert a scalar value to Scalar node."""
    # Convert value to string
    if value is None:
        str_value = ''
        style = 'plain'
    elif isinstance(value, bool):
        str_value = 'true' if value else 'false'
        style = 'plain'
    elif isinstance(value, (int, float)):
        str_value = str(value)
        style = 'plain'
    else:
        str_value = str(value)
        # Extract quote style if we have position info
        if line is not None and col is not None:
            style = extract_quote_style(original_bytes, line, col)
        else:
            style = 'plain'

    return Scalar(value=str_value, style=style, indent=indent)
