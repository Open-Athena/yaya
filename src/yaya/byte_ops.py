"""
Byte-level operations for YAML document manipulation.

Provides utilities for converting between line/column positions and byte offsets,
and finding byte ranges of scalar values in the original YAML bytes.
"""


def line_col_to_index(text: bytes, line: int, col: int) -> int:
    """
    Convert (line, col) position to byte index in text.

    Args:
        text: The original bytes of the document
        line: Line number (0-indexed)
        col: Column number (0-indexed)

    Returns:
        Byte offset in text corresponding to (line, col)
    """
    current_line = 0
    current_col = 0

    for idx in range(len(text)):
        if current_line == line and current_col == col:
            return idx
        if text[idx] == ord('\n'):
            current_line += 1
            current_col = 0
        else:
            current_col += 1

    return len(text)


def find_scalar_value_range(text: bytes, line: int, col: int) -> tuple[int, int]:
    """
    Find the byte range of a scalar value starting at (line, col).

    Handles quoted strings (single and double), block scalars (| and >),
    and plain scalars.

    Args:
        text: The original bytes of the document
        line: Starting line number (0-indexed)
        col: Starting column number (0-indexed)

    Returns:
        Tuple of (start_idx, end_idx) where text[start:end] is the value content.
        For quoted strings, the quotes are excluded from the range.
    """
    start_idx = line_col_to_index(text, line, col)

    if start_idx >= len(text):
        return (start_idx, start_idx)

    ch = chr(text[start_idx])

    # Handle quoted strings
    if ch == '"':
        idx = start_idx + 1
        while idx < len(text):
            if text[idx] == ord('"') and (idx == start_idx + 1 or text[idx-1] != ord('\\')):
                return (start_idx + 1, idx)  # Exclude quotes
            idx += 1
        return (start_idx + 1, len(text))

    elif ch == "'":
        idx = start_idx + 1
        while idx < len(text):
            if text[idx] == ord("'"):
                if idx + 1 < len(text) and text[idx+1] == ord("'"):
                    idx += 2
                    continue
                return (start_idx + 1, idx)  # Exclude quotes
            idx += 1
        return (start_idx + 1, len(text))

    elif ch in ('|', '>'):
        # Block scalar - find all indented lines after the indicator
        # Skip the indicator line
        idx = start_idx
        while idx < len(text) and text[idx] != ord('\n'):
            idx += 1
        if idx < len(text):
            idx += 1  # Skip newline

        # Determine indent of first content line
        content_start = idx
        while idx < len(text) and text[idx] in b' \t':
            idx += 1
        indent_level = idx - content_start

        # Find end of block (dedent or end of file)
        while idx < len(text):
            if text[idx] == ord('\n'):
                # Check next line's indent
                next_line_start = idx + 1
                spaces = 0
                check_idx = next_line_start
                while check_idx < len(text) and text[check_idx] in b' \t':
                    spaces += 1
                    check_idx += 1

                # Empty line or dedented line ends the block
                if check_idx < len(text) and text[check_idx] == ord('\n'):
                    # Empty line, continue
                    idx = check_idx
                elif spaces < indent_level and check_idx < len(text):
                    # Dedented, end block
                    return (content_start, idx)
                else:
                    idx = check_idx
            else:
                idx += 1

        return (content_start, idx)

    # Plain scalar - until newline, comment, or flow indicator
    # Special handling for GitHub Actions jinja2 expressions: ${{ ... }}
    idx = start_idx
    while idx < len(text):
        ch = text[idx]

        # Check for end conditions
        if ch in b'\n\r#,:[]':
            break

        # Special case: Check for ${{ pattern (GitHub Actions/jinja2)
        if ch == ord('$') and idx + 2 < len(text):
            if text[idx+1] == ord('{') and text[idx+2] == ord('{'):
                # Found ${{ - scan until we find matching }}
                idx += 3  # Skip past ${{'
                depth = 2  # We need to find 2 closing braces
                while idx < len(text) and depth > 0:
                    if text[idx] == ord('}'):
                        depth -= 1
                    elif text[idx] == ord('{'):
                        depth += 1
                    idx += 1
                continue

        # Regular flow indicators end the scalar
        if ch in b'{}':
            break

        idx += 1

    # Trim trailing whitespace
    while idx > start_idx and text[idx-1] in b' \t':
        idx -= 1

    return (start_idx, idx)
