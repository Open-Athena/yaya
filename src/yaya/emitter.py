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


def _serialize_node(node: Node, in_flow_context: bool = False) -> bytes:
    """
    Serialize any node to bytes.

    Args:
        node: The node to serialize
        in_flow_context: True if inside a flow-style collection
    """
    if isinstance(node, InlineCommented):
        return _serialize_inline_commented(node, in_flow_context=in_flow_context)
    elif isinstance(node, KeyValue):
        return _serialize_keyvalue(node, in_flow_context=in_flow_context)
    elif isinstance(node, Scalar):
        return _serialize_scalar(node, in_flow_context=in_flow_context)
    elif isinstance(node, Mapping):
        return _serialize_mapping(node, in_flow_context=in_flow_context)
    elif isinstance(node, Sequence):
        return _serialize_sequence(node, in_flow_context=in_flow_context)
    elif isinstance(node, Comment):
        return _serialize_comment(node)
    elif isinstance(node, BlankLines):
        return _serialize_blank_lines(node)
    else:
        raise ValueError(f"Unknown node type: {type(node)}")


def _needs_quotes(value: str, in_flow_context: bool = False) -> bool:
    """
    Determine if a string value needs quotes in YAML.

    Returns True if the value looks like a float (but not an int), boolean, null,
    or has special chars. Integers don't need quotes.

    Args:
        value: The string value to check
        in_flow_context: True if inside a flow-style collection [...] or {...}
    """
    if not value:
        return False

    # Check if it looks like an integer - integers don't need quotes
    try:
        int(value)
        return False  # It's an integer, no quotes needed
    except ValueError:
        pass

    # Check if it looks like a float - floats need quotes to preserve as string
    try:
        float(value)
        return True  # Looks like a float (e.g., "3.11"), needs quotes
    except ValueError:
        pass

    # Check for YAML keywords - these should NOT be quoted
    # (they're valid YAML literals)
    if value.lower() in ('true', 'false', 'null', 'yes', 'no', 'on', 'off'):
        return False

    # Check for special characters that require quoting
    # Note: Some chars are only problematic in certain positions:
    # - { and [ only at start (could be flow collection)
    # - : anywhere (could be key-value separator)
    # - # at start or after space (could be comment)
    # - others need context-specific handling

    # Check first character
    first_char = value[0]
    if first_char in '{[':
        return True  # Flow collection indicators at start
    if first_char == '#':
        return True  # Comment indicator

    # Check for chars that are problematic anywhere
    problematic_anywhere = ':`'
    if any(c in value for c in problematic_anywhere):
        return True

    # Check for # after space (comment)
    if ' #' in value:
        return True

    # Hyphen at start requires quoting ONLY in block context
    # In flow context (inside [...] or {...}), hyphens are safe
    if value.startswith('-') and not in_flow_context:
        return True

    # Check if starts with quote or spaces
    if value[0] in ('"', "'", ' ') or value[-1] == ' ':
        return True

    return False


def _serialize_scalar(scalar: Scalar, in_flow_context: bool = False) -> bytes:
    """
    Serialize a Scalar node.

    Args:
        scalar: The scalar node to serialize
        in_flow_context: True if inside a flow-style collection
    """
    indent_str = b' ' * scalar.indent

    if scalar.style == 'numeric':
        # Numeric values (int/float) - never quoted
        return indent_str + scalar.value.encode('utf-8')
    elif scalar.style == 'double':
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
        # Smart quoting: auto-quote if value needs it
        if _needs_quotes(scalar.value, in_flow_context=in_flow_context):
            # Use single quotes (ruamel's default for auto-quoting)
            escaped = scalar.value.replace("'", "''")
            return indent_str + b"'" + escaped.encode('utf-8') + b"'"
        else:
            return indent_str + scalar.value.encode('utf-8')


def _serialize_mapping(mapping: Mapping, in_flow_context: bool = False) -> bytes:
    """Serialize a Mapping node."""
    if mapping.style == 'flow':
        return _serialize_flow_mapping(mapping)
    else:
        return _serialize_block_mapping(mapping, in_flow_context=in_flow_context)


def _serialize_block_mapping(mapping: Mapping, in_flow_context: bool = False) -> bytes:
    """Serialize a block-style mapping."""
    parts = []

    for item in mapping.items:
        # Item can be KeyValue, BlankLines, or Comment
        if isinstance(item, KeyValue):
            key_node = item.key
            value_node = item.value

            # Serialize key
            key_bytes = _serialize_node(key_node, in_flow_context=in_flow_context)

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
                # Check if it's flow style (can be inline) or block style (new line)
                is_flow = actual_value_node.style == 'flow'
                if is_flow:
                    # Flow style - inline with key, child nodes ARE in flow context
                    value_bytes = _serialize_node(actual_value_node, in_flow_context=True).lstrip()
                    line = key_bytes + colon + b' ' + value_bytes
                    if inline_comment:
                        line += b'  # ' + inline_comment.encode('utf-8')
                    parts.append(line + b'\n')
                else:
                    # Block style - value goes on next line
                    parts.append(key_bytes + colon + b'\n')
                    parts.append(_serialize_node(actual_value_node, in_flow_context=in_flow_context))
            else:
                # Scalar value - goes on same line
                value_bytes = _serialize_node(actual_value_node, in_flow_context=in_flow_context)
                # Remove indent from value (it's on same line as key)
                value_str = value_bytes.lstrip()
                line = key_bytes + colon + b' ' + value_str
                # Add inline comment if present
                if inline_comment:
                    line += b'  # ' + inline_comment.encode('utf-8')
                parts.append(line + b'\n')
        else:
            # BlankLines, Comment, or other node
            parts.append(_serialize_node(item, in_flow_context=in_flow_context))

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
            # Pass in_flow_context=True so children know they're in flow context
            key_bytes = _serialize_node(item.key, in_flow_context=True).strip()
            value_bytes = _serialize_node(item.value, in_flow_context=True).strip()

            parts.append(key_bytes + b': ' + value_bytes)
            kv_count += 1

    parts.append(b'}')
    return b''.join(parts)


def _serialize_keyvalue(keyvalue: KeyValue, in_flow_context: bool = False) -> bytes:
    """
    Serialize a KeyValue node.

    Note: This is used when KeyValue appears standalone, not in a Mapping.
    Inside Mapping, the serializer handles KeyValue directly.
    """
    key_bytes = _serialize_node(keyvalue.key, in_flow_context=in_flow_context)
    value_bytes = _serialize_node(keyvalue.value, in_flow_context=in_flow_context).lstrip()
    return key_bytes + b': ' + value_bytes


def _serialize_sequence(sequence: Sequence, in_flow_context: bool = False) -> bytes:
    """Serialize a Sequence node."""
    if sequence.style == 'flow':
        return _serialize_flow_sequence(sequence)
    else:
        return _serialize_block_sequence(sequence, in_flow_context=in_flow_context)


def _serialize_block_sequence(sequence: Sequence, in_flow_context: bool = False) -> bytes:
    """Serialize a block-style sequence."""
    parts = []

    for item_node in sequence.items:
        # Calculate dash position: base indent + offset
        dash_indent = sequence.indent + sequence.offset
        dash_str = b' ' * dash_indent + b'- '

        # Serialize item
        if isinstance(item_node, (Mapping, Sequence)):
            # Complex item
            item_bytes = _serialize_node(item_node, in_flow_context=in_flow_context)

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
            item_bytes = _serialize_node(item_node, in_flow_context=in_flow_context).strip()
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
        # Pass in_flow_context=True so children know they're in flow context
        item_bytes = _serialize_node(item_node, in_flow_context=True).strip()
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


def _serialize_inline_commented(inline_commented: InlineCommented, in_flow_context: bool = False) -> bytes:
    """
    Serialize an InlineCommented node.

    Note: This returns the node content WITHOUT the inline comment.
    The comment is added by the parent (Mapping serializer) since it needs
    to be on the same line as the key-value pair.
    """
    # Just serialize the wrapped node
    return _serialize_node(inline_commented.node, in_flow_context=in_flow_context)
