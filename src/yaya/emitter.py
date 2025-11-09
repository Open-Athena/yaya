"""
Lossless YAML serializer for clean AST.

This module serializes our clean AST back to YAML bytes, preserving all
formatting details (quotes, indentation, comments, blank lines).
"""
from .nodes import Node, Scalar, Mapping, Sequence, Comment, BlankLines, Document, InlineCommented, KeyValue


def serialize(node: Node) -> bytes:
    """
    Serialize a clean AST node to YAML bytes.

    Args:
        node: Root node (usually a Document)

    Returns:
        YAML bytes preserving all formatting
    """
    if isinstance(node, Document):
        return _serialize_document(node)
    else:
        raise ValueError(f"serialize() expects Document node, got {type(node)}")


def _serialize_document(doc: Document) -> bytes:
    """Serialize a Document node."""
    parts = []

    for node in doc.nodes:
        parts.append(_serialize_node(node))

    result = b''.join(parts)

    # Ensure file ends with exactly one newline
    if result and not result.endswith(b'\n'):
        result += b'\n'

    return result


def _serialize_node(node: Node) -> bytes:
    """Serialize any node to bytes."""
    if isinstance(node, InlineCommented):
        return _serialize_inline_commented(node)
    elif isinstance(node, KeyValue):
        return _serialize_keyvalue(node)
    elif isinstance(node, Scalar):
        return _serialize_scalar(node)
    elif isinstance(node, Mapping):
        return _serialize_mapping(node)
    elif isinstance(node, Sequence):
        return _serialize_sequence(node)
    elif isinstance(node, Comment):
        return _serialize_comment(node)
    elif isinstance(node, BlankLines):
        return _serialize_blank_lines(node)
    else:
        raise ValueError(f"Unknown node type: {type(node)}")


def _serialize_scalar(scalar: Scalar) -> bytes:
    """Serialize a Scalar node."""
    indent_str = b' ' * scalar.indent

    if scalar.style == 'double':
        # Escape special characters for double-quoted strings
        escaped = scalar.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return indent_str + b'"' + escaped.encode('utf-8') + b'"'
    elif scalar.style == 'single':
        # Single quotes - escape single quotes by doubling
        escaped = scalar.value.replace("'", "''")
        return indent_str + b"'" + escaped.encode('utf-8') + b"'"
    elif scalar.style == 'literal':
        # Block scalar with |
        lines = scalar.value.split('\n')
        result = indent_str + b'|\n'
        for line in lines:
            if line:  # Only add indentation for non-empty lines
                result += indent_str + b'  ' + line.encode('utf-8') + b'\n'
            else:
                result += b'\n'
        return result
    elif scalar.style == 'folded':
        # Block scalar with >
        lines = scalar.value.split('\n')
        result = indent_str + b'>\n'
        for line in lines:
            if line:
                result += indent_str + b'  ' + line.encode('utf-8') + b'\n'
            else:
                result += b'\n'
        return result
    else:  # plain
        return indent_str + scalar.value.encode('utf-8')


def _serialize_mapping(mapping: Mapping) -> bytes:
    """Serialize a Mapping node."""
    if mapping.style == 'flow':
        return _serialize_flow_mapping(mapping)
    else:
        return _serialize_block_mapping(mapping)


def _serialize_block_mapping(mapping: Mapping) -> bytes:
    """Serialize a block-style mapping."""
    parts = []

    for item in mapping.items:
        # Item can be KeyValue, BlankLines, or Comment
        if isinstance(item, KeyValue):
            key_node = item.key
            value_node = item.value

            # Serialize key
            key_bytes = _serialize_node(key_node)

            # Add colon
            colon = b':'

            # Check if value has inline comment
            inline_comment = None
            actual_value_node = value_node
            if isinstance(value_node, InlineCommented):
                inline_comment = value_node.comment
                actual_value_node = value_node.node

            # Serialize value
            if isinstance(actual_value_node, (Mapping, Sequence)):
                # Complex value - goes on next line
                parts.append(key_bytes + colon + b'\n')
                parts.append(_serialize_node(actual_value_node))
            else:
                # Scalar value - goes on same line
                value_bytes = _serialize_node(actual_value_node)
                # Remove indent from value (it's on same line as key)
                value_str = value_bytes.lstrip()
                line = key_bytes + colon + b' ' + value_str
                # Add inline comment if present
                if inline_comment:
                    line += b'  # ' + inline_comment.encode('utf-8')
                parts.append(line + b'\n')
        else:
            # BlankLines, Comment, or other node
            parts.append(_serialize_node(item))

    return b''.join(parts)


def _serialize_flow_mapping(mapping: Mapping) -> bytes:
    """Serialize a flow-style mapping {k: v}."""
    indent_str = b' ' * mapping.indent
    parts = [indent_str + b'{']

    kv_count = 0
    for item in mapping.items:
        if isinstance(item, KeyValue):
            if kv_count > 0:
                parts.append(b', ')

            # Serialize key and value (strip indents - they're in flow style)
            key_bytes = _serialize_node(item.key).strip()
            value_bytes = _serialize_node(item.value).strip()

            parts.append(key_bytes + b': ' + value_bytes)
            kv_count += 1

    parts.append(b'}')
    return b''.join(parts)


def _serialize_keyvalue(keyvalue: KeyValue) -> bytes:
    """
    Serialize a KeyValue node.

    Note: This is used when KeyValue appears standalone, not in a Mapping.
    Inside Mapping, the serializer handles KeyValue directly.
    """
    key_bytes = _serialize_node(keyvalue.key)
    value_bytes = _serialize_node(keyvalue.value).lstrip()
    return key_bytes + b': ' + value_bytes


def _serialize_sequence(sequence: Sequence) -> bytes:
    """Serialize a Sequence node."""
    if sequence.style == 'flow':
        return _serialize_flow_sequence(sequence)
    else:
        return _serialize_block_sequence(sequence)


def _serialize_block_sequence(sequence: Sequence) -> bytes:
    """Serialize a block-style sequence."""
    parts = []

    for item_node in sequence.items:
        # Calculate dash position: base indent + offset
        dash_indent = sequence.indent + sequence.offset
        dash_str = b' ' * dash_indent + b'- '

        # Serialize item
        if isinstance(item_node, (Mapping, Sequence)):
            # Complex item
            item_bytes = _serialize_node(item_node)

            # For mappings, we need to inline the first key-value on the same line as the dash
            if isinstance(item_node, Mapping) and item_node.items:
                # Split item into lines
                item_lines = item_bytes.split(b'\n')
                if item_lines and item_lines[0]:
                    # First line goes after dash
                    first_line = item_lines[0].lstrip()
                    parts.append(dash_str + first_line + b'\n')

                    # Remaining lines keep their indentation
                    for line in item_lines[1:]:
                        if line:  # Skip empty lines at end
                            parts.append(line + b'\n')
                else:
                    parts.append(dash_str + b'\n' + item_bytes)
            else:
                parts.append(dash_str + b'\n' + item_bytes)
        else:
            # Scalar item - goes on same line as dash
            item_bytes = _serialize_node(item_node).strip()
            parts.append(dash_str + item_bytes + b'\n')

    return b''.join(parts)


def _serialize_flow_sequence(sequence: Sequence) -> bytes:
    """Serialize a flow-style sequence [a, b, c]."""
    indent_str = b' ' * sequence.indent
    parts = [indent_str + b'[']

    for i, item_node in enumerate(sequence.items):
        if i > 0:
            parts.append(b', ')

        # Serialize item (strip indent - it's in flow style)
        item_bytes = _serialize_node(item_node).strip()
        parts.append(item_bytes)

    parts.append(b']')
    return b''.join(parts)


def _serialize_comment(comment: Comment) -> bytes:
    """Serialize a Comment node."""
    indent_str = b' ' * comment.indent
    return indent_str + b'#' + (b' ' + comment.text.encode('utf-8') if comment.text else b'') + b'\n'


def _serialize_blank_lines(blank_lines: BlankLines) -> bytes:
    """Serialize blank lines."""
    return b'\n' * blank_lines.count


def _serialize_inline_commented(inline_commented: InlineCommented) -> bytes:
    """
    Serialize an InlineCommented node.

    Note: This returns the node content WITHOUT the inline comment.
    The comment is added by the parent (Mapping serializer) since it needs
    to be on the same line as the key-value pair.
    """
    # Just serialize the wrapped node
    return _serialize_node(inline_commented.node)
