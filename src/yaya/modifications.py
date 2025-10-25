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
                new_bytes, actual_start, actual_end = self._format_replacement(start, end, value)
                self.modifications[(actual_start, actual_end)] = new_bytes
        elif isinstance(obj, CommentedSeq) and hasattr(obj, 'lc') and key in obj.lc.data:
            lc_info = obj.lc.data[key]
            if len(lc_info) >= 2:
                val_line, val_col = lc_info[0], lc_info[1]
                start, end = find_scalar_value_range(
                    self.original_bytes, val_line, val_col
                )
                new_bytes, actual_start, actual_end = self._format_replacement(start, end, value)
                self.modifications[(actual_start, actual_end)] = new_bytes

    def _format_replacement(self, start: int, end: int, value: str) -> tuple[bytes, int, int]:
        """
        Format a replacement value, preserving indentation for block scalars
        and handling quote escaping intelligently.

        Args:
            start: Start byte offset of original value (inside quotes if quoted)
            end: End byte offset of original value (inside quotes if quoted)
            value: New string value

        Returns:
            Tuple of (new_bytes, actual_start, actual_end) where:
            - new_bytes: The formatted bytes to insert
            - actual_start: Actual start position (may include opening quote)
            - actual_end: Actual end position (may include closing quote)

        Note:
            The start/end range excludes the quotes (see find_scalar_value_range).
            This method detects the original quote style and applies smart escaping:
            - Preserves original quote style when possible
            - Switches quote styles to avoid escaping when beneficial
            - Only escapes when necessary
            - Expands the replacement range to include quotes if quote style changes
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

                return ('\n'.join(indented_lines).encode('utf-8'), start, end)

        # Detect original quote style by looking at the character before start
        original_quote = None
        if start > 0:
            char_before = chr(self.original_bytes[start - 1])
            if char_before in ('"', "'"):
                original_quote = char_before

        # Apply smart quoting/escaping
        formatted_value, needs_quote_change = self._apply_smart_quoting(value, original_quote)

        # If quote style needs to change, expand range to include quotes
        if needs_quote_change and original_quote:
            # Include opening and closing quotes in replacement
            actual_start = start - 1  # Include opening quote
            actual_end = end + 1      # Include closing quote
            return (formatted_value.encode('utf-8'), actual_start, actual_end)
        else:
            # No quote style change needed, just replace the content
            return (formatted_value.encode('utf-8'), start, end)

    def _apply_smart_quoting(self, value: str, original_quote: str | None) -> tuple[str, bool]:
        """
        Apply smart quoting to a value based on its content and original quote style.

        Strategy:
        1. If originally unquoted → keep unquoted (let YAML parser handle it)
        2. If originally quoted and no conflict → preserve quote style
        3. If originally quoted with conflict → switch to avoid escaping or escape
        4. Otherwise preserve original quote style

        Args:
            value: The new value to insert
            original_quote: The original quote character ('"', "'", or None for unquoted)

        Returns:
            Tuple of (formatted_value, needs_quote_change) where:
            - formatted_value: The value to insert (with quotes if changing style)
            - needs_quote_change: True if the quote style needs to change
                                  (meaning we need to include the quotes in replacement)
        """
        has_single = "'" in value
        has_double = '"' in value

        # If originally unquoted, keep it unquoted
        # YAML plain scalars can contain quotes without issue in most cases
        if original_quote is None:
            return (value, False)

        # Originally quoted - need to handle potential conflicts
        if not has_single and not has_double:
            # No conflicts - preserve original quote style
            return (value, False)

        # Value has quotes - choose best quote style
        if has_single and not has_double:
            # Prefer double quotes (no escaping needed)
            if original_quote == '"':
                # Already using double quotes - no change needed
                return (value, False)
            else:
                # Need to switch to double quotes
                return (f'"{value}"', True)

        elif has_double and not has_single:
            # Prefer single quotes (no escaping needed)
            if original_quote == "'":
                # Already using single quotes - no change needed
                return (value, False)
            else:
                # Need to switch to single quotes
                return (f"'{value}'", True)

        else:
            # Both types of quotes - use double quotes with escaping
            # Escape backslashes first, then double quotes
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            if original_quote == '"':
                # Already using double quotes - just need escaping, no quote change
                return (escaped, False)
            else:
                # Need to switch to double quotes AND escape
                return (f'"{escaped}"', True)

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
