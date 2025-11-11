"""
Convert ruamel.yaml AST to clean yaya AST.

This module handles the conversion from ruamel.yaml's CommentedMap/CommentedSeq
to our clean immutable AST nodes, extracting formatting information from the
original bytes along the way.
"""
from ruamel.yaml.comments import CommentedMap, CommentedSeq

# Thread-local storage for default list offset during conversion
_default_list_offset = 2
from ruamel.yaml.scalarstring import (
    DoubleQuotedScalarString,
    SingleQuotedScalarString,
    PlainScalarString,
)
from .nodes import (
    Node, Scalar, Mapping, Sequence, Comment, BlankLines, Document, InlineCommented, KeyValue
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
    default_list_offset: int = 2,
) -> Document:
    """
    Convert ruamel.yaml AST to clean yaya AST.

    Args:
        ruamel_data: Parsed data from ruamel.yaml
        original_bytes: Original file bytes (for extracting formatting)
        default_list_offset: Default offset for programmatically-created lists (default: 2)

    Returns:
        Document node containing the clean AST
    """
    global _default_list_offset
    _default_list_offset = default_list_offset

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

    # Extract trailing comments from the root mapping
    if isinstance(ruamel_data, CommentedMap) and hasattr(ruamel_data, 'ca'):
        # Check each key for trailing comments
        for key in ruamel_data.keys():
            if key in ruamel_data.ca.items:
                ca_item = ruamel_data.ca.items[key]
                if len(ca_item) > 2 and ca_item[2]:
                    comment_token = ca_item[2]
                    comment_lines = comment_token.value.split('\n')
                    # Skip first line (inline comment, already handled)
                    for i, line in enumerate(comment_lines[1:]):
                        if line.strip():
                            comment_text = line.lstrip('#').lstrip()
                            comment_line = comment_token.start_mark.line + 1 + i
                            indent = extract_indentation(original_bytes, comment_line)
                            nodes.append(Comment(text=comment_text, indent=indent))

    return Document(nodes=tuple(nodes))


def _convert_node(
    node: any,
    original_bytes: bytes,
    parent_col: int = 0,
    line: int | None = None,
    col: int | None = None,
    is_list_item: bool = False,
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
        return _convert_mapping(node, original_bytes, parent_col, is_list_item=is_list_item)
    elif isinstance(node, CommentedSeq):
        return _convert_sequence(node, original_bytes, parent_col, is_list_item=is_list_item)
    else:
        return _convert_scalar(node, original_bytes, parent_col, line=line, col=col)


def _convert_mapping(
    mapping: CommentedMap,
    original_bytes: bytes,
    parent_col: int,
    is_list_item: bool = False,
) -> Mapping:
    """Convert a CommentedMap to Mapping node."""
    items = []

    # First try to extract from original bytes (if mapping has position data)
    if hasattr(mapping, 'lc') and mapping.lc.data and len(mapping) > 0:
        # Extract style from original bytes
        first_key = list(mapping.keys())[0]
        # Only use first key if it has position data
        if first_key in mapping.lc.data:
            key_line, key_col, val_line, val_col = mapping.lc.data[first_key][:4]
            style = extract_mapping_style(original_bytes, val_line, val_col)
            indent = extract_indentation(original_bytes, key_line)
        else:
            # First key is programmatic, fall back to parent_col
            style = 'block'
            indent = parent_col
    # Check if style was set programmatically via .fa (for fully programmatic nodes)
    elif hasattr(mapping, 'fa') and hasattr(mapping.fa, 'flow_style') and mapping.fa.flow_style() is not None:
        # Use programmatically-set style (for nodes without any position data)
        style = 'flow' if mapping.fa.flow_style() else 'block'
        # List items: keys at parent_col. Mapping values: keys at parent_col + 2
        indent = parent_col if is_list_item else parent_col + 2
    else:
        # Default for programmatic mappings without explicit style
        style = 'block'
        # List items: keys at parent_col. Mapping values: keys at parent_col + 2
        indent = parent_col if is_list_item else parent_col + 2

    # Extract leading blank lines (blank lines after the mapping key, before first child)
    # These appear in mapping.ca.comment[1]
    if hasattr(mapping, 'ca') and mapping.ca.comment and mapping.ca.comment[1]:
        leading_tokens = mapping.ca.comment[1] if isinstance(mapping.ca.comment[1], list) else [mapping.ca.comment[1]]
        for token in leading_tokens:
            if hasattr(token, 'value') and token.value:
                # Check if it's blank lines (just newlines, no # character)
                if not token.value.lstrip('\n').strip():
                    blank_count = token.value.count('\n')
                    if blank_count > 0:
                        items.append(BlankLines(count=blank_count))

    for key, value in mapping.items():
        # Check for blank lines or comments BEFORE this key
        # ca_item structure: [before_key, between_key_value, after_value, end_of_block]
        # Blank lines before key can be in position [0] or [1] depending on how they were added
        if hasattr(mapping, 'ca') and key in mapping.ca.items:
            ca_item = mapping.ca.items[key]

            # Check position [1] (between_key_value) - used by yaml_set_comment_before_after_key
            if len(ca_item) > 1 and ca_item[1]:
                between_items = ca_item[1] if isinstance(ca_item[1], list) else [ca_item[1]]
                for token in between_items:
                    if hasattr(token, 'value') and token.value:
                        # Check if it's just newlines (blank lines)
                        if token.value == '\n' or (token.value.startswith('\n') and not token.value.lstrip('\n').strip()):
                            blank_count = token.value.count('\n')
                            if blank_count > 0:
                                items.append(BlankLines(count=blank_count))

            # Also check position [0] (before_key) for completeness
            if len(ca_item) > 0 and ca_item[0]:
                before_token = ca_item[0]
                if hasattr(before_token, 'value'):
                    before_value = before_token.value
                    # Check if it's blank lines
                    if before_value and not before_value.lstrip('\n').startswith('#'):
                        blank_count = before_value.count('\n')
                        if blank_count > 0:
                            items.append(BlankLines(count=blank_count))

        # Get position info for this key-value pair
        if hasattr(mapping, 'lc') and mapping.lc.data and key in mapping.lc.data:
            key_line, key_col, val_line, val_col = mapping.lc.data[key][:4]

            # Convert key
            key_node = _convert_scalar(key, original_bytes, key_col, line=key_line, col=key_col)

            # Convert value (pass position info for scalars)
            value_node = _convert_node(value, original_bytes, parent_col=key_col, line=val_line, col=val_col)

            # Check for inline comment
            if hasattr(mapping, 'ca') and key in mapping.ca.items:
                ca_item = mapping.ca.items[key]
                # ca_item is [before_key, between_key_value, after_value, end_of_block]
                if len(ca_item) > 2 and ca_item[2]:
                    comment_token = ca_item[2]
                    comment_value = comment_token.value

                    # Check if it's blank lines (just newlines, no # character)
                    if comment_value and not comment_value.lstrip('\n').startswith('#'):
                        # Count blank lines
                        blank_count = comment_value.count('\n')
                        if blank_count > 0:
                            # This is blank lines after the value
                            # We'll add them after creating the KeyValue
                            pass
                    else:
                        # It's a comment
                        comment_lines = comment_value.split('\n')
                        # First line is inline comment (on same line as value)
                        if comment_lines and comment_lines[0]:
                            inline_comment = comment_lines[0].lstrip('#').lstrip()
                            value_node = InlineCommented(node=value_node, comment=inline_comment)

            # Create KeyValue node
            items.append(KeyValue(key=key_node, value=value_node))

            # Add blank lines after this key-value pair
            if hasattr(mapping, 'ca') and key in mapping.ca.items:
                ca_item = mapping.ca.items[key]
                if len(ca_item) > 2 and ca_item[2]:
                    comment_token = ca_item[2]
                    comment_value = comment_token.value
                    # Check if it's blank lines
                    if comment_value and not comment_value.lstrip('\n').startswith('#'):
                        blank_count = comment_value.count('\n')
                        # Subtract 1 because the key-value line already has a newline
                        if blank_count > 1:
                            items.append(BlankLines(count=blank_count - 1))
        else:
            # No position info - use defaults
            key_node = Scalar(value=str(key), style='plain', indent=indent)
            value_node = _convert_node(value, original_bytes, parent_col=indent)
            items.append(KeyValue(key=key_node, value=value_node))

    return Mapping(items=tuple(items), style=style, indent=indent)


def _convert_sequence(
    sequence: CommentedSeq,
    original_bytes: bytes,
    parent_col: int,
    is_list_item: bool = False,
) -> Sequence:
    """Convert a CommentedSeq to Sequence node."""
    items = []

    # Determine style and formatting
    # Priority: .fa.flow_style() (works for both parsed and programmatic) > extract from bytes
    if hasattr(sequence, 'fa') and hasattr(sequence.fa, 'flow_style'):
        fa_style = sequence.fa.flow_style()
        if fa_style is True:
            style = 'flow'
        elif fa_style is False:
            style = 'block'
        else:
            style = None  # Will extract from bytes
    else:
        style = None

    # For parsed sequences with position data, extract indent/offset from bytes
    if hasattr(sequence, 'lc') and sequence.lc.data and len(sequence) > 0:
        first_item_line, first_item_col = sequence.lc.data[0][:2]

        # If style not determined from .fa, extract from bytes
        if style is None:
            style = extract_sequence_style(original_bytes, first_item_line, first_item_col)

        # Indent is the parent's column, not the dash position
        indent = parent_col

        # For block style, extract offset (relative to parent)
        if style == 'block':
            offset = extract_sequence_offset(original_bytes, parent_col, first_item_line)
        else:
            offset = 0
    else:
        # Programmatic sequence without position data
        if style is None:
            style = 'block'  # Default
        indent = parent_col
        offset = _default_list_offset  # Use detected offset from document

    # Extract leading comments (before first item)
    if hasattr(sequence, 'ca') and sequence.ca.comment and sequence.ca.comment[1]:
        leading_comments = sequence.ca.comment[1] if isinstance(sequence.ca.comment[1], list) else [sequence.ca.comment[1]]
        for comment_token in leading_comments:
            if comment_token:
                comment_text = comment_token.value.lstrip('#').rstrip('\n').lstrip()
                line = comment_token.start_mark.line
                indent_val = extract_indentation(original_bytes, line)
                items.append(Comment(text=comment_text, indent=indent_val))

    for i, item in enumerate(sequence):
        # Check for comments before this item
        if hasattr(sequence, 'ca') and sequence.ca.items and i in sequence.ca.items:
            ca_item = sequence.ca.items[i]
            if len(ca_item) > 0 and ca_item[0]:
                comment_token = ca_item[0]
                # This can contain comments (lines starting with #) and/or blank lines
                comment_value = comment_token.value if hasattr(comment_token, 'value') else str(comment_token)
                for line in comment_value.split('\n'):
                    line = line.strip()
                    if line.startswith('#'):
                        comment_text = line.lstrip('#').lstrip()
                        # Get indentation from token position
                        token_line = comment_token.start_mark.line if hasattr(comment_token, 'start_mark') else None
                        if token_line is not None:
                            indent_val = extract_indentation(original_bytes, token_line)
                        else:
                            indent_val = indent + offset
                        items.append(Comment(text=comment_text, indent=indent_val))
                    elif not line:
                        # Blank line
                        items.append(BlankLines(count=1))

        if hasattr(sequence, 'lc') and sequence.lc.data and i in sequence.lc.data:
            item_line, item_col = sequence.lc.data[i][:2]
            item_node = _convert_node(item, original_bytes, parent_col=item_col, is_list_item=True)
        else:
            item_node = _convert_node(item, original_bytes, parent_col=indent, is_list_item=True)

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
        style = 'numeric'  # Special style for actual numbers (never quoted)
    else:
        str_value = str(value)

        # Check if this is a programmatically-created scalar with explicit quote style
        if isinstance(value, DoubleQuotedScalarString):
            style = 'double'
        elif isinstance(value, SingleQuotedScalarString):
            style = 'single'
        elif isinstance(value, PlainScalarString):
            style = 'plain'
        # Extract quote style from original bytes if we have position info
        elif line is not None and col is not None:
            style = extract_quote_style(original_bytes, line, col)
        else:
            style = 'plain'

    return Scalar(value=str_value, style=style, indent=indent)
