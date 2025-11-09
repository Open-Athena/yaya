"""
Extract formatting information from original YAML bytes.

This module provides functions to extract formatting details (quote styles,
indentation, etc.) from the original YAML bytes using position information
from ruamel.yaml's parser.
"""
from typing import Literal


def line_col_to_byte_offset(original_bytes: bytes, line: int, col: int) -> int:
    """
    Convert line/column position to byte offset.

    Args:
        original_bytes: Original YAML file bytes
        line: Line number (0-indexed)
        col: Column number (0-indexed)

    Returns:
        Byte offset in the original file
    """
    offset = 0
    current_line = 0

    while current_line < line and offset < len(original_bytes):
        if original_bytes[offset] == ord('\n'):
            current_line += 1
        offset += 1

    offset += col
    return min(offset, len(original_bytes))


def extract_quote_style(
    original_bytes: bytes,
    line: int,
    col: int
) -> Literal['plain', 'single', 'double', 'literal', 'folded']:
    """
    Extract the quote style of a scalar at given position.

    Args:
        original_bytes: Original YAML file bytes
        line: Line number where scalar starts
        col: Column number where scalar starts

    Returns:
        Quote style used in original file
    """
    offset = line_col_to_byte_offset(original_bytes, line, col)

    if offset >= len(original_bytes):
        return 'plain'

    first_char = chr(original_bytes[offset])

    if first_char == '"':
        return 'double'
    elif first_char == "'":
        return 'single'
    elif first_char == '|':
        # Check for chomping indicator
        if offset + 1 < len(original_bytes):
            next_char = chr(original_bytes[offset + 1])
            if next_char == '-':
                return 'literal'  # We'll use 'literal' for both | and |-
        return 'literal'
    elif first_char == '>':
        return 'folded'
    else:
        return 'plain'


def extract_indentation(original_bytes: bytes, line: int) -> int:
    """
    Extract the indentation (number of leading spaces) for a line.

    Args:
        original_bytes: Original YAML file bytes
        line: Line number (0-indexed)

    Returns:
        Number of spaces at start of line
    """
    offset = line_col_to_byte_offset(original_bytes, line, 0)
    indent = 0

    while offset + indent < len(original_bytes):
        char = original_bytes[offset + indent]
        if char == ord(' '):
            indent += 1
        else:
            break

    return indent


def extract_mapping_style(
    original_bytes: bytes,
    line: int,
    col: int
) -> Literal['block', 'flow']:
    """
    Determine if a mapping uses flow {k: v} or block style.

    Args:
        original_bytes: Original YAML file bytes
        line: Line number where mapping starts
        col: Column number where mapping starts

    Returns:
        'flow' if uses {}, 'block' otherwise
    """
    offset = line_col_to_byte_offset(original_bytes, line, col)

    # Look ahead to see if we find a '{' before newline
    search_offset = offset
    while search_offset < len(original_bytes):
        char = chr(original_bytes[search_offset])
        if char == '{':
            return 'flow'
        elif char == '\n':
            return 'block'
        elif char not in (' ', '\t'):
            # Hit non-whitespace that's not {
            return 'block'
        search_offset += 1

    return 'block'


def extract_sequence_style(
    original_bytes: bytes,
    line: int,
    col: int
) -> Literal['block', 'flow']:
    """
    Determine if a sequence uses flow [a, b] or block style.

    Args:
        original_bytes: Original YAML file bytes
        line: Line number where sequence starts
        col: Column number where sequence starts

    Returns:
        'flow' if uses [], 'block' otherwise
    """
    offset = line_col_to_byte_offset(original_bytes, line, col)

    # Look ahead to see if we find a '[' before newline
    search_offset = offset
    while search_offset < len(original_bytes):
        char = chr(original_bytes[search_offset])
        if char == '[':
            return 'flow'
        elif char == '\n':
            return 'block'
        elif char == '-':
            # Found list dash
            return 'block'
        search_offset += 1

    return 'block'


def extract_sequence_offset(
    original_bytes: bytes,
    parent_col: int,
    first_item_line: int
) -> int:
    """
    Extract the list offset (distance between parent key and dash).

    Args:
        original_bytes: Original YAML file bytes
        parent_col: Column where parent key starts
        first_item_line: Line where first list item appears

    Returns:
        Offset (0 for aligned, 2 for indented)
    """
    indent = extract_indentation(original_bytes, first_item_line)

    # Find the dash
    offset = line_col_to_byte_offset(original_bytes, first_item_line, 0)
    dash_col = 0

    while offset + dash_col < len(original_bytes):
        char = chr(original_bytes[offset + dash_col])
        if char == '-':
            break
        elif char == ' ':
            dash_col += 1
        else:
            # Unexpected
            return 2

    return dash_col - parent_col
