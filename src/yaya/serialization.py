"""
YAML serialization utilities with indentation detection and control.

Handles list indentation styles (aligned vs indented) and provides
automatic detection of the document's existing style.
"""
import os
import warnings
from typing import Any, Literal
from collections import Counter
from io import StringIO
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq


def detect_list_indentation(data: Any, original_bytes: bytes) -> int | None:
    """
    Detect the list indentation offset used in the document.

    Analyzes the relationship between list item positions and their parent
    key positions to determine if lists use aligned (0-offset) or indented
    (2-offset) style.

    Args:
        data: Parsed YAML data (CommentedMap/CommentedSeq)
        original_bytes: Original document bytes (unused but kept for API consistency)

    Returns:
        The detected offset (0 for aligned, 2 for indented), or None if:
        - No lists found in document
        - Mixed indentation detected (less than 70% consensus)

    Examples:
        Aligned style (offset=0):
            ```yaml
            jobs:
            - name: test
            ```

        Indented style (offset=2):
            ```yaml
            jobs:
              - name: test
            ```
    """
    offsets = []

    def scan_for_lists(obj, parent_obj=None, parent_key=None):
        if isinstance(obj, CommentedSeq):
            # Skip flow-style lists - they don't have block-style indentation
            if hasattr(obj, 'fa') and hasattr(obj.fa, 'flow_style'):
                is_flow = obj.fa.flow_style()
                if is_flow:
                    # Flow-style list - don't analyze indentation
                    for item in obj:
                        scan_for_lists(item, obj, None)
                    return

            # This is a block-style list - check its indentation
            if hasattr(obj, 'lc') and hasattr(obj.lc, 'data') and len(obj) > 0:
                # Get first item position
                if 0 in obj.lc.data:
                    item_line, item_col = obj.lc.data[0][0], obj.lc.data[0][1]
                    # Get parent key position if available
                    if parent_obj and hasattr(parent_obj, 'lc') and parent_key in parent_obj.lc.data:
                        parent_lc = parent_obj.lc.data[parent_key]
                        parent_col = parent_lc[1]
                        # item_col is the column of the scalar value, not the dash
                        # The dash is always 2 characters before (dash + space)
                        dash_col = item_col - 2
                        # Calculate offset: dash_col - parent_col
                        offset = dash_col - parent_col
                        offsets.append(offset)

            # Recurse into list items
            for item in obj:
                scan_for_lists(item, obj, None)

        elif isinstance(obj, CommentedMap):
            for key, value in obj.items():
                scan_for_lists(value, obj, key)

    scan_for_lists(data)

    if not offsets:
        return None

    # Return the most common offset
    counts = Counter(offsets)
    most_common_offset, count = counts.most_common(1)[0]

    # If there's disagreement, check if it's significant
    if len(counts) > 1:
        total = sum(counts.values())
        if count / total < 0.7:  # Less than 70% consensus
            # Mixed indentation - return None to signal ambiguity
            return None

    return most_common_offset


def serialize_to_yaml(
    value: Any,
    indent: int = 0,
    style: Literal['auto', 'block', 'flow'] = 'auto',
    list_offset: int | None = None
) -> str:
    """
    Serialize a Python value to YAML string with specific indentation.

    If value is a CommentedMap/CommentedSeq with formatting metadata
    (from build_yaml_node()), that formatting is preserved.

    Args:
        value: The value to serialize (dict, list, scalar, or CommentedMap/CommentedSeq)
        indent: Additional indentation to add to all lines (in spaces)
        style: How to format collections:
            - 'auto': Use ruamel.yaml's default (block for mappings, varies for sequences)
            - 'block': Force block style for collections
            - 'flow': Force inline/flow style for collections (e.g., [1, 2, 3])
            Note: Ignored if value is a pre-formatted CommentedMap/CommentedSeq
        list_offset: Offset for list items from parent key (0=aligned, 2=indented).
                    If None, uses YAYA_LIST_OFFSET environment variable or defaults to 2.

    Returns:
        YAML string representation with trailing newline stripped

    Examples:
        >>> serialize_to_yaml({'key': 'value'})
        'key: value'
        >>> serialize_to_yaml(['a', 'b'], list_offset=2)
        '- a\\n- b'
        >>> serialize_to_yaml(['a', 'b'], style='flow')
        '[a, b]'

        >>> # With pre-formatted node
        >>> from yaya.formatting import build_yaml_node
        >>> node = build_yaml_node(['a', 'b'], flow_style=True)
        >>> serialize_to_yaml(node)  # Respects flow_style setting
        '[a, b]'

    Environment Variables:
        YAYA_LIST_OFFSET: Default list offset if not specified (integer)
    """
    if list_offset is None:
        # Check environment variable for default
        env_default = os.environ.get('YAYA_LIST_OFFSET', '').strip()
        if env_default:
            try:
                list_offset = int(env_default)
            except ValueError:
                warnings.warn(f"Invalid YAYA_LIST_OFFSET value: {env_default!r}, using offset=2")
                list_offset = 2
        else:
            # Default to 2 (GitHub Actions style)
            list_offset = 2

    yaml = YAML()

    # Check if value is a pre-formatted node (has formatting metadata)
    is_formatted_node = isinstance(value, (CommentedMap, CommentedSeq))

    # Configure flow style ONLY if not a pre-formatted node
    # Pre-formatted nodes have their own .fa (format attribute) settings
    if not is_formatted_node:
        if style == 'flow':
            yaml.default_flow_style = True
        elif style == 'block':
            yaml.default_flow_style = False
        # else 'auto' - let ruamel.yaml decide (default_flow_style is None)

    yaml.width = 4096
    # mapping=2: indent nested mappings by 2 spaces
    # sequence=2: indent list items by 2 spaces
    # offset: indent the dash of list items from parent key (0=aligned, 2=indented)
    yaml.indent(mapping=2, sequence=2, offset=list_offset)

    stream = StringIO()
    yaml.dump(value, stream)
    result = stream.getvalue()

    # Add indentation to all lines if needed
    if indent > 0:
        lines = result.rstrip('\n').split('\n')
        indented_lines = [(' ' * indent) + line for line in lines]
        return '\n'.join(indented_lines)

    return result.rstrip('\n')
