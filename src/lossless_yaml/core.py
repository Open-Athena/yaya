"""
Lossless YAML Editor - Core implementation.

Provides byte-for-byte preservation of YAML files while allowing
programmatic modifications to values.
"""
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from typing import Any, Callable, Literal
from io import BytesIO
import re
import os
import warnings


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


def parse_path(path: str) -> list[str | int]:
    """
    Parse a dotted path string into components.
    Supports: "jobs.test.steps[0].uses"
    Returns: ["jobs", "test", "steps", 0, "uses"]
    """
    parts = []
    current = []

    i = 0
    while i < len(path):
        ch = path[i]
        if ch == '.':
            if current:
                parts.append(''.join(current))
                current = []
        elif ch == '[':
            if current:
                parts.append(''.join(current))
                current = []
            # Find closing ]
            j = i + 1
            while j < len(path) and path[j] != ']':
                j += 1
            if j < len(path):
                index_str = path[i+1:j]
                parts.append(int(index_str))
                i = j
            else:
                raise ValueError(f"Unclosed bracket in path: {path}")
        else:
            current.append(ch)
        i += 1

    if current:
        parts.append(''.join(current))

    return parts


def detect_list_indentation(data: Any, original_bytes: bytes) -> int | None:
    """
    Detect the list indentation offset used in the document.
    Returns the offset (0 for aligned, 2 for indented) or None if no lists found.
    """
    offsets = []

    def scan_for_lists(obj, parent_obj=None, parent_key=None):
        if isinstance(obj, CommentedSeq):
            # This is a list - check its indentation
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
    from collections import Counter
    counts = Counter(offsets)
    most_common_offset, count = counts.most_common(1)[0]

    # If there's disagreement, check if it's significant
    if len(counts) > 1:
        total = sum(counts.values())
        if count / total < 0.7:  # Less than 70% consensus
            # Mixed indentation - return None to signal ambiguity
            return None

    return most_common_offset


def serialize_to_yaml(value: Any, indent: int = 0, style: str = 'block', list_offset: int | None = None) -> str:
    """
    Serialize a Python value to YAML string with specific indentation.

    Args:
        value: The value to serialize
        indent: Additional indentation to add to all lines
        style: 'block' or 'flow'
        list_offset: Offset for list items from parent key (0=aligned, 2=indented).
                    If None, uses default based on environment or raises.
    """
    if list_offset is None:
        # Check environment variable for default
        env_default = os.environ.get('LOSSLESS_YAML_LIST_OFFSET', '').strip()
        if env_default:
            try:
                list_offset = int(env_default)
            except ValueError:
                warnings.warn(f"Invalid LOSSLESS_YAML_LIST_OFFSET value: {env_default!r}, using offset=2")
                list_offset = 2
        else:
            # Default to 2 (GitHub Actions style)
            list_offset = 2

    yaml = YAML()
    yaml.default_flow_style = (style == 'flow')
    yaml.width = 4096
    # mapping=2: indent nested mappings by 2 spaces
    # sequence=2: indent list items by 2 spaces
    # offset: indent the dash of list items from parent key (0=aligned, 2=indented)
    yaml.indent(mapping=2, sequence=2, offset=list_offset)

    from io import StringIO
    stream = StringIO()
    yaml.dump(value, stream)
    result = stream.getvalue()

    # Add indentation to all lines if needed
    if indent > 0:
        lines = result.rstrip('\n').split('\n')
        indented_lines = [(' ' * indent) + line for line in lines]
        return '\n'.join(indented_lines)

    return result.rstrip('\n')


class LosslessYAML:
    """Lossless YAML editor that preserves exact bytes."""

    def __init__(self, original_bytes: bytes, data: Any, file_path: Path | None = None):
        self.original_bytes = original_bytes
        self.data = data
        self.file_path = file_path
        self.modifications: dict[tuple[int, int], bytes] = {}
        # Detect list indentation style from document
        self._detected_list_offset = detect_list_indentation(data, original_bytes)
        self._list_offset_override: int | None = None

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

    def set_list_indent_style(self, offset: int | Literal['aligned', 'indented']):
        """
        Override the list indentation style for this document.

        Args:
            offset: 0 or 'aligned' for bullets aligned with parent key,
                   2 or 'indented' for bullets indented 2 spaces from parent
        """
        if offset == 'aligned':
            self._list_offset_override = 0
        elif offset == 'indented':
            self._list_offset_override = 2
        elif isinstance(offset, int):
            self._list_offset_override = offset
        else:
            raise ValueError(f"Invalid offset: {offset}. Use 0, 2, 'aligned', or 'indented'")

    def _get_list_offset(self) -> int | None:
        """
        Get the list offset to use, considering overrides and detection.
        Returns None if ambiguous and no override set.
        """
        if self._list_offset_override is not None:
            return self._list_offset_override

        if self._detected_list_offset is not None:
            return self._detected_list_offset

        # Check for mixed/ambiguous indentation behavior
        env_behavior = os.environ.get('LOSSLESS_YAML_MIXED_INDENT', 'warn').lower()
        if env_behavior == 'error':
            raise ValueError(
                "Mixed or ambiguous list indentation detected in document. "
                "Use doc.set_list_indent_style() to specify explicitly, or set "
                "LOSSLESS_YAML_LIST_OFFSET environment variable."
            )
        elif env_behavior == 'warn':
            warnings.warn(
                "No consistent list indentation detected in document. "
                "Defaulting to offset=2 (indented). Use doc.set_list_indent_style() "
                "to override or set LOSSLESS_YAML_LIST_OFFSET environment variable.",
                UserWarning
            )

        # Fall through to serialize_to_yaml's default handling
        return None

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
                for line in new_lines:
                    if not line.strip():
                        # Empty lines - preserve as-is
                        indented_lines.append(line)
                    else:
                        # Add indent to all non-empty lines
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

    def replace_in_values_regex(self, pattern: str, replacement: str):
        """Replace all occurrences matching regex `pattern` with `replacement` in all string values."""
        compiled_pattern = re.compile(pattern)

        def replace_recursive(obj):
            if isinstance(obj, CommentedMap):
                for key, value in obj.items():
                    if isinstance(value, str) and compiled_pattern.search(value):
                        new_value = compiled_pattern.sub(replacement, value)
                        self._record_modification(obj, key, new_value)
                        obj[key] = new_value
                    else:
                        replace_recursive(value)
            elif isinstance(obj, CommentedSeq):
                for i, item in enumerate(obj):
                    if isinstance(item, str) and compiled_pattern.search(item):
                        new_value = compiled_pattern.sub(replacement, item)
                        self._record_modification(obj, i, new_value)
                        obj[i] = new_value
                    else:
                        replace_recursive(item)

        replace_recursive(self.data)

    def _navigate_to_path(self, path: str | list[str | int]) -> tuple[Any, Any, str | int]:
        """
        Navigate to a path and return (parent, current_value, final_key).
        Raises KeyError if path doesn't exist.
        """
        if isinstance(path, str):
            parts = parse_path(path)
        else:
            parts = path

        if not parts:
            raise ValueError("Empty path")

        current = self.data
        parent = None
        final_key = None

        for i, part in enumerate(parts):
            parent = current
            final_key = part

            if isinstance(current, CommentedMap):
                if part not in current:
                    raise KeyError(f"Path not found: {'.'.join(str(p) for p in parts[:i+1])}")
                current = current[part]
            elif isinstance(current, CommentedSeq):
                if not isinstance(part, int):
                    raise TypeError(f"Expected integer index for sequence, got {type(part).__name__}")
                if part < 0 or part >= len(current):
                    raise IndexError(f"Index {part} out of range for sequence of length {len(current)}")
                current = current[part]
            else:
                raise TypeError(f"Cannot navigate through {type(current).__name__}")

        return parent, current, final_key

    def get_path(self, path: str) -> Any:
        """Get value at path. Example: doc.get_path("jobs.test.runs-on")"""
        _, value, _ = self._navigate_to_path(path)
        return value

    def __getitem__(self, key: str) -> Any:
        """Dict-like access: doc["jobs"]["test"]["runs-on"]"""
        return self.data[key]

    def assert_value(self, path: str, expected: Any):
        """Assert that value at path equals expected. Raises AssertionError if not."""
        actual = self.get_path(path)
        if actual != expected:
            raise AssertionError(f"Expected {expected!r} at path {path!r}, got {actual!r}")

    def assert_absent(self, path: str):
        """Assert that path does not exist. Raises AssertionError if it exists."""
        try:
            self.get_path(path)
            raise AssertionError(f"Path {path!r} should be absent but exists")
        except KeyError:
            pass

    def assert_present(self, path: str):
        """Assert that path exists. Raises AssertionError if absent."""
        try:
            self.get_path(path)
        except KeyError:
            raise AssertionError(f"Path {path!r} should be present but is absent")

    def _find_key_byte_range(self, parent: CommentedMap, key: str) -> tuple[int, int]:
        """
        Find the byte range for a key-value pair in a CommentedMap.
        Returns (start, end) where start is the beginning of the key line
        and end is the end of the value (or end of last line of value).
        """
        if not hasattr(parent, 'lc') or key not in parent.lc.data:
            raise ValueError(f"Key {key!r} not found in line/col data")

        lc_info = parent.lc.data[key]
        if len(lc_info) < 4:
            raise ValueError(f"Incomplete line/col info for key {key!r}")

        key_line, key_col, val_line, val_col = lc_info[:4]

        # Find start of key line
        key_start_idx = line_col_to_index(self.original_bytes, key_line, 0)

        # Find end of value
        val_start, val_end = find_scalar_value_range(self.original_bytes, val_line, val_col)

        # For non-scalar values (maps, sequences), we need to find the actual end
        value = parent[key]
        if isinstance(value, (CommentedMap, CommentedSeq)):
            # Find the end by looking for the next sibling key or dedent
            # For now, use a simple heuristic: find the next line with same or less indentation
            val_end_line = val_line
            if hasattr(value, 'lc') and hasattr(value.lc, 'data'):
                # Get the last item's position
                if isinstance(value, CommentedMap) and value:
                    last_key = list(value.keys())[-1]
                    if last_key in value.lc.data:
                        last_info = value.lc.data[last_key]
                        if len(last_info) >= 4:
                            val_end_line = last_info[2]
                elif isinstance(value, CommentedSeq) and value:
                    last_idx = len(value) - 1
                    if last_idx in value.lc.data:
                        last_info = value.lc.data[last_idx]
                        if len(last_info) >= 2:
                            val_end_line = last_info[0]

            # Find end of that line
            val_end = line_col_to_index(self.original_bytes, val_end_line, 0)
            while val_end < len(self.original_bytes) and self.original_bytes[val_end] != ord('\n'):
                val_end += 1

        return key_start_idx, val_end

    def add_key(self, path: str, value: Any, force: bool = False):
        """
        Add a new key at path. If force=True, replaces existing key.
        For adding keys at specific positions, use add_key_after.
        """
        parts = parse_path(path) if isinstance(path, str) else path
        if len(parts) == 1:
            # Top-level key
            parent = self.data
            final_key = parts[0]
        else:
            # Navigate to parent
            parent_path = parts[:-1]
            final_key = parts[-1]
            current = self.data
            for part in parent_path:
                if isinstance(current, CommentedMap):
                    if part not in current:
                        raise KeyError(f"Parent path not found: {'.'.join(str(p) for p in parent_path)}")
                    current = current[part]
                elif isinstance(current, CommentedSeq):
                    if not isinstance(part, int):
                        raise TypeError(f"Expected integer index for sequence")
                    current = current[part]
                else:
                    raise TypeError(f"Cannot navigate through {type(current).__name__}")
            parent = current

        if not isinstance(parent, CommentedMap):
            raise TypeError(f"Can only add keys to mappings, not {type(parent).__name__}")

        if final_key in parent and not force:
            raise KeyError(f"Key {final_key!r} already exists. Use force=True to overwrite.")

        # For new keys at root or arbitrary position, append at end
        # Serialize the value
        if isinstance(value, (dict, list)):
            yaml_value = serialize_to_yaml(value, indent=0, list_offset=self._get_list_offset())

            # Determine indentation
            if hasattr(parent, 'lc') and len(parent) > 0:
                # Get indentation from first existing key
                first_key = list(parent.keys())[0]
                if first_key in parent.lc.data:
                    key_col = parent.lc.data[first_key][1]
                else:
                    key_col = 0
            else:
                key_col = 0

            # Find insertion point (end of parent)
            if len(parent) > 0:
                # Find end of last key in parent
                last_key = list(parent.keys())[-1]
                if hasattr(parent, 'lc') and last_key in parent.lc.data:
                    _, existing_end = self._find_key_byte_range(parent, last_key)
                else:
                    # No position info, append to end of file
                    existing_end = len(self.original_bytes)
            else:
                # Empty parent, insert at beginning
                existing_end = 0

            # Build the new key-value pair
            indent_spaces = ' ' * key_col
            key_str = str(final_key)

            if '\n' in yaml_value:
                # Block style
                new_lines = [f"\n{indent_spaces}{key_str}:"]
                value_lines = yaml_value.split('\n')
                for line in value_lines:
                    if line.strip():
                        new_lines.append(f"{indent_spaces}  {line}")
                    else:
                        new_lines.append('')
                new_content = '\n'.join(new_lines)
            else:
                # Single line
                new_content = f"\n{indent_spaces}{key_str}: {yaml_value}"

            self.modifications[(existing_end, existing_end)] = new_content.encode('utf-8')
        else:
            # Scalar - simpler approach
            parent[final_key] = value

        # Update data structure
        parent[final_key] = value

    def replace_key(self, path: str, value: Any):
        """
        Replace the value at path with a new value.
        The new value can be a dict, list, or scalar.
        If the key doesn't exist, adds it (same as add_key with force=True).
        """
        try:
            parent, old_value, final_key = self._navigate_to_path(path)
        except KeyError:
            # Key doesn't exist, add it
            self.add_key(path, value, force=True)
            return

        if not isinstance(parent, CommentedMap):
            raise TypeError(f"Can only replace keys in mappings, not {type(parent).__name__}")

        # Determine indentation from the key's position
        if hasattr(parent, 'lc') and final_key in parent.lc.data:
            lc_info = parent.lc.data[final_key]
            key_line, key_col = lc_info[0], lc_info[1]

            # Serialize the new value
            if isinstance(value, (dict, list)):
                # Convert plain dict/list to YAML
                yaml_value = serialize_to_yaml(value, indent=0, list_offset=self._get_list_offset())

                # Find the byte range to replace
                start, end = self._find_key_byte_range(parent, final_key)

                # Build the replacement: key: value
                indent_spaces = ' ' * key_col
                key_str = str(final_key)

                # Handle multiline values
                if '\n' in yaml_value:
                    # Block style - value starts on next line
                    replacement_lines = [f"{indent_spaces}{key_str}:"]
                    value_lines = yaml_value.split('\n')
                    for line in value_lines:
                        if line.strip():
                            replacement_lines.append(f"{indent_spaces}  {line}")
                        else:
                            replacement_lines.append('')
                    replacement = '\n'.join(replacement_lines)
                else:
                    # Single line value
                    replacement = f"{indent_spaces}{key_str}: {yaml_value}"

                self.modifications[(start, end)] = replacement.encode('utf-8')
            else:
                # Scalar value - use existing _record_modification
                self._record_modification(parent, final_key, str(value))

            # Update the data structure
            parent[final_key] = value

    def add_key_after(self, existing_path: str, new_key: str, value: Any):
        """
        Add a new key after an existing key in a mapping.
        Example: doc.add_key_after("jobs.test.runs-on", "defaults", {...})
        """
        # Navigate to the parent containing the existing key
        parent, _, existing_key = self._navigate_to_path(existing_path)

        if not isinstance(parent, CommentedMap):
            raise TypeError(f"Can only add keys to mappings, not {type(parent).__name__}")

        if new_key in parent:
            raise KeyError(f"Key {new_key!r} already exists")

        # Find the position to insert
        if not hasattr(parent, 'lc') or existing_key not in parent.lc.data:
            raise ValueError(f"Cannot find position info for key {existing_key!r}")

        lc_info = parent.lc.data[existing_key]
        key_col = lc_info[1]

        # Find the end of the existing key's value
        _, existing_end = self._find_key_byte_range(parent, existing_key)

        # Serialize the new value
        yaml_value = serialize_to_yaml(value, indent=0, list_offset=self._get_list_offset())

        # Build the new key-value pair
        indent_spaces = ' ' * key_col
        if '\n' in yaml_value:
            # Block style
            new_lines = [f"\n{indent_spaces}{new_key}:"]
            value_lines = yaml_value.split('\n')
            for line in value_lines:
                if line.strip():
                    new_lines.append(f"{indent_spaces}  {line}")
                else:
                    new_lines.append('')
            new_content = '\n'.join(new_lines)
        else:
            # Single line
            new_content = f"\n{indent_spaces}{new_key}: {yaml_value}"

        # Insert after the existing key
        # We insert by replacing the range (existing_end, existing_end) with the new content
        self.modifications[(existing_end, existing_end)] = new_content.encode('utf-8')

        # Update the data structure - need to maintain order
        # Create a new CommentedMap with the key inserted in the right position
        keys = list(parent.keys())
        existing_index = keys.index(existing_key)

        # Insert the new value into the data structure
        # We'll do this by rebuilding the map with the new key in the right place
        items = list(parent.items())
        items.insert(existing_index + 1, (new_key, value))

        parent.clear()
        for k, v in items:
            parent[k] = v

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
