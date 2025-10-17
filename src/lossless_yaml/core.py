"""
Lossless YAML Editor - Core implementation.

Provides byte-for-byte preservation of YAML files while allowing
programmatic modifications to values.
"""
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from typing import Any
from io import BytesIO


def line_col_to_index(text: bytes, line: int, col: int) -> int:
    """Convert (line, col) to byte index."""
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
    Returns (start_idx, end_idx) where text[start:end] is the value.
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
    idx = start_idx
    while idx < len(text) and text[idx] not in b'\n\r#,:{}[]':
        idx += 1

    # Trim trailing whitespace
    while idx > start_idx and text[idx-1] in b' \t':
        idx -= 1

    return (start_idx, idx)


class LosslessYAML:
    """Lossless YAML editor that preserves exact bytes."""

    def __init__(self, original_bytes: bytes, data: Any, file_path: Path | None = None):
        self.original_bytes = original_bytes
        self.data = data
        self.file_path = file_path
        self.modifications: dict[tuple[int, int], bytes] = {}

    @classmethod
    def load(cls, file_path: str | Path) -> 'LosslessYAML':
        """Load a YAML file for lossless editing."""
        path = Path(file_path)
        original_bytes = path.read_bytes()

        yaml = YAML()
        data = yaml.load(BytesIO(original_bytes))

        doc = cls(original_bytes, data, path)
        doc._wrap_data(data)
        return doc

    def _record_modification(self, obj: Any, key: Any, value: Any):
        """Record a modification to track byte position changes."""
        if isinstance(obj, CommentedMap) and hasattr(obj, 'lc') and key in obj.lc.data:
            lc_info = obj.lc.data[key]
            if len(lc_info) >= 4:
                val_line, val_col = lc_info[2], lc_info[3]
                start, end = find_scalar_value_range(
                    self.original_bytes, val_line, val_col
                )
                if isinstance(value, str):
                    # For block scalars, preserve indentation
                    new_bytes = self._format_replacement(start, end, value)
                    self.modifications[(start, end)] = new_bytes
        elif isinstance(obj, CommentedSeq) and hasattr(obj, 'lc') and key in obj.lc.data:
            lc_info = obj.lc.data[key]
            if len(lc_info) >= 2:
                val_line, val_col = lc_info[0], lc_info[1]
                start, end = find_scalar_value_range(
                    self.original_bytes, val_line, val_col
                )
                if isinstance(value, str):
                    new_bytes = self._format_replacement(start, end, value)
                    self.modifications[(start, end)] = new_bytes

    def _format_replacement(self, start: int, end: int, value: str) -> bytes:
        """Format a replacement value, preserving indentation for block scalars."""
        original = self.original_bytes[start:end]

        # Check if this is a block scalar by looking for consistent indentation
        if b'\n' in original:
            lines = original.split(b'\n')
            if len(lines) > 1:
                # Determine indent level from first line
                first_line = lines[0] if lines[0].strip() else lines[1] if len(lines) > 1 else b''
                indent = 0
                for byte in first_line:
                    if byte in b' \t':
                        indent += 1
                    else:
                        break

                # Apply same indent to new value
                new_lines = value.split('\n')
                indented_lines = []
                for i, line in enumerate(new_lines):
                    if i == 0 or not line.strip():
                        # First line or empty lines
                        indented_lines.append(line)
                    else:
                        # Add indent
                        indented_lines.append(' ' * indent + line)

                return '\n'.join(indented_lines).encode('utf-8')

        return value.encode('utf-8')

    def _wrap_data(self, obj: Any, path: list[str | int] = []):
        """Recursively wrap CommentedMap/CommentedSeq to track modifications."""
        # No wrapping needed - we'll handle it in replace_in_values
        pass

    def replace_in_values(self, old: str, new: str):
        """Replace all occurrences of `old` with `new` in all string values."""
        def replace_recursive(obj):
            if isinstance(obj, CommentedMap):
                for key, value in obj.items():
                    if isinstance(value, str) and old in value:
                        new_value = value.replace(old, new)
                        self._record_modification(obj, key, new_value)
                        obj[key] = new_value
                    else:
                        replace_recursive(value)
            elif isinstance(obj, CommentedSeq):
                for i, item in enumerate(obj):
                    if isinstance(item, str) and old in item:
                        new_value = item.replace(old, new)
                        self._record_modification(obj, i, new_value)
                        obj[i] = new_value
                    else:
                        replace_recursive(item)

        replace_recursive(self.data)

    def save(self, file_path: Path | str | None = None) -> bytes:
        """Save the modified YAML, preserving all formatting."""
        target_path = Path(file_path) if file_path else self.file_path

        # Apply modifications in reverse order to preserve byte offsets
        result = bytearray(self.original_bytes)
        for (start, end), new_bytes in sorted(self.modifications.items(), reverse=True):
            result[start:end] = new_bytes

        final_bytes = bytes(result)

        if target_path:
            target_path.write_bytes(final_bytes)

        return final_bytes
