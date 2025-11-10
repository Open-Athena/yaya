"""
Build ruamel.yaml AST nodes with formatting metadata.

This module provides helpers to create CommentedMap/CommentedSeq objects
with explicit formatting control (flow vs block, quote styles, etc.)
"""

from typing import Any, Literal
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import (
    DoubleQuotedScalarString,
    SingleQuotedScalarString,
    PlainScalarString,
)


def build_yaml_node(
    value: Any,
    *,
    flow_style: bool | None = None,
    quote_style: Literal['auto', 'double', 'single', 'plain'] = 'auto',
    formatting: dict | None = None,
) -> Any:
    """
    Convert Python value to ruamel.yaml AST node with formatting metadata.

    Args:
        value: Python value (dict, list, str, int, etc.)
        flow_style: True=flow ([...]), False=block (- ...), None=auto
        quote_style: How to quote string scalars
        formatting: Nested formatting hints for sub-nodes
            {
                'key': {'flow_style': True, 'quote_style': 'double'},
                'other[0]': {'quote_style': 'single'},
            }

    Returns:
        CommentedMap, CommentedSeq, or scalar with formatting metadata

    Examples:
        >>> # Simple list with flow style
        >>> node = build_yaml_node(['a', 'b'], flow_style=True)
        >>> # When serialized: [a, b]

        >>> # Dict with mixed collection styles
        >>> node = build_yaml_node({
        ...     'inline': ['a', 'b'],
        ...     'block': ['c', 'd'],
        ... }, formatting={
        ...     'inline': {'flow_style': True},
        ...     'block': {'flow_style': False},
        ... })
        >>> # When serialized:
        >>> # inline: [a, b]
        >>> # block:
        >>> # - c
        >>> # - d

        >>> # List with mixed quotes per item
        >>> node = build_yaml_node(['a', 'b', 'c'], formatting={
        ...     '[0]': {'quote_style': 'double'},
        ...     '[1]': {'quote_style': 'single'},
        ...     '[2]': {'quote_style': 'plain'},
        ... })
        >>> # When serialized:
        >>> # - "a"
        >>> # - 'b'
        >>> # - c
    """
    if isinstance(value, dict):
        node = CommentedMap()
        for k, v in value.items():
            # Get formatting hints for this specific key
            key_format = (formatting or {}).get(k, {})

            # Separate direct formatting options from nested formatting
            direct_format = {}
            nested_format = {}
            for fmt_key, fmt_val in key_format.items():
                if fmt_key in ('flow_style', 'quote_style'):
                    direct_format[fmt_key] = fmt_val
                else:
                    nested_format[fmt_key] = fmt_val

            # Inherit parent flow_style if not overridden for this key
            if 'flow_style' not in direct_format and flow_style is not None:
                direct_format['flow_style'] = flow_style

            # Pass nested formatting as 'formatting' param
            if nested_format:
                direct_format['formatting'] = nested_format

            node[k] = build_yaml_node(v, **direct_format)

        # Apply collection-level flow/block style
        if flow_style is not None:
            if flow_style:
                node.fa.set_flow_style()
            else:
                node.fa.set_block_style()

        return node

    elif isinstance(value, list):
        # Build items with per-item formatting
        items = []
        for i, item in enumerate(value):
            # Get formatting hints for this specific index
            item_format = (formatting or {}).get(f'[{i}]', {})
            # Inherit parent quote_style if not overridden for this item
            if 'quote_style' not in item_format and quote_style != 'auto':
                item_format = {**item_format, 'quote_style': quote_style}
            # Inherit parent flow_style if not overridden for this item
            if 'flow_style' not in item_format and flow_style is not None:
                item_format = {**item_format, 'flow_style': flow_style}
            items.append(build_yaml_node(item, **item_format))

        node = CommentedSeq(items)

        # Apply collection-level flow/block style
        if flow_style is not None:
            if flow_style:
                node.fa.set_flow_style()
            else:
                node.fa.set_block_style()

        return node

    elif isinstance(value, str):
        # Apply scalar quote style
        if quote_style == 'double':
            return DoubleQuotedScalarString(value)
        elif quote_style == 'single':
            return SingleQuotedScalarString(value)
        elif quote_style == 'plain':
            return PlainScalarString(value)
        # else 'auto' - return plain string, let ruamel.yaml decide
        return value

    else:
        # Numbers, bools, None, etc - return as-is
        return value


def add_blank_lines(
    node: CommentedMap,
    blank_lines: dict[str, int],
) -> None:
    """
    Add blank lines before keys in a CommentedMap.

    Args:
        node: CommentedMap to modify in-place
        blank_lines: Mapping of {key: num_lines}

    Examples:
        >>> from ruamel.yaml.comments import CommentedMap
        >>> node = CommentedMap([
        ...     ('runs-on', 'ubuntu-latest'),
        ...     ('strategy', {'matrix': {'python-version': ['3.11']}}),
        ...     ('steps', [{'uses': 'actions/checkout@v3'}]),
        ... ])
        >>> add_blank_lines(node, {'strategy': 1, 'steps': 1})
        >>> # When serialized:
        >>> # runs-on: ubuntu-latest
        >>> #
        >>> # strategy:
        >>> #   matrix:
        >>> #     python-version:
        >>> #     - '3.11'
        >>> #
        >>> # steps:
        >>> # - uses: actions/checkout@v3
    """
    for key, num_lines in blank_lines.items():
        if key in node:
            # '\n' for each blank line
            before = '\n' * num_lines
            node.yaml_set_comment_before_after_key(key, before=before)
