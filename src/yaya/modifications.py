"""
Modification tracking for byte-level YAML edits.

Tracks changes to scalar values and applies them during document save.
"""
from typing import Any
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from .byte_ops import find_scalar_value_range


class ModificationTracker:
    """
    Tracks byte-level modifications to a YAML document.

    Modifications are stored as byte ranges to replace, allowing the
    original document bytes to be preserved except where explicitly modified.
    """

    def __init__(self, original_bytes: bytes):
        """
        Initialize modification tracker.

        Args:
            original_bytes: The original document bytes
        """
        self.original_bytes = original_bytes
        self.modifications: dict[tuple[int, int], bytes] = {}

    def record_scalar_modification(self, obj: Any, key: Any, value: str):
        """
        Record a modification to a scalar value.

        Args:
            obj: Parent object (CommentedMap or CommentedSeq)
            key: Key or index in parent
            value: New string value to replace with

        Note:
            Only records modifications for objects with line/column info.
            Silently skips objects without position data.
        """
        if isinstance(obj, CommentedMap) and hasattr(obj, 'lc') and key in obj.lc.data:
            lc_info = obj.lc.data[key]
            if len(lc_info) >= 4:
                val_line, val_col = lc_info[2], lc_info[3]
                start, end = find_scalar_value_range(
                    self.original_bytes, val_line, val_col
                )
                new_bytes = self._format_replacement(start, end, value)
                self.modifications[(start, end)] = new_bytes
        elif isinstance(obj, CommentedSeq) and hasattr(obj, 'lc') and key in obj.lc.data:
            lc_info = obj.lc.data[key]
            if len(lc_info) >= 2:
                val_line, val_col = lc_info[0], lc_info[1]
                start, end = find_scalar_value_range(
                    self.original_bytes, val_line, val_col
                )
                new_bytes = self._format_replacement(start, end, value)
                self.modifications[(start, end)] = new_bytes

    def _format_replacement(self, start: int, end: int, value: str) -> bytes:
        """
        Format a replacement value, preserving indentation for block scalars.

        Args:
            start: Start byte offset of original value
            end: End byte offset of original value
            value: New string value

        Returns:
            Formatted bytes to replace the original range with
        """
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
                for line in new_lines:
                    if not line.strip():
                        # Empty lines - preserve as-is
                        indented_lines.append(line)
                    else:
                        # Add indent to all non-empty lines
                        indented_lines.append(' ' * indent + line)

                return '\n'.join(indented_lines).encode('utf-8')

        return value.encode('utf-8')

    def record_insertion(self, position: int, content: bytes):
        """
        Record an insertion at a specific byte position.

        Args:
            position: Byte offset where content should be inserted
            content: Bytes to insert
        """
        self.modifications[(position, position)] = content

    def apply_modifications(self) -> bytes:
        """
        Apply all tracked modifications to the original bytes.

        Modifications are applied in reverse order to preserve byte offsets.

        Returns:
            Final document bytes with all modifications applied
        """
        result = bytearray(self.original_bytes)
        for (start, end), new_bytes in sorted(self.modifications.items(), reverse=True):
            result[start:end] = new_bytes
        return bytes(result)

    def clear(self):
        """Clear all tracked modifications."""
        self.modifications.clear()

    def has_modifications(self) -> bool:
        """Check if any modifications are tracked."""
        return len(self.modifications) > 0
