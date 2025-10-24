"""
YAYA main document class for byte-preserving YAML editing.

Provides the primary API for loading, modifying, and saving YAML files
while preserving exact byte-for-byte formatting.
"""
import os
import warnings
import re
from pathlib import Path
from typing import Any, Literal
from io import BytesIO
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .byte_ops import line_col_to_index, find_scalar_value_range
from .modifications import ModificationTracker
from .path import parse_path, navigate_to_path
from .serialization import detect_list_indentation, serialize_to_yaml


class YAYA:
    """
    YAYA - Yet Another YAML AST transformer.

    Preserves exact bytes of YAML files while allowing programmatic modifications
    to values. Only the values you explicitly modify will change; all other
    formatting, comments, and whitespace are preserved byte-for-byte.

    Examples:
        >>> doc = YAYA.load('config.yaml')
        >>> doc.replace_in_values('old_path', 'new_path')
        >>> doc.save()
    """

    def __init__(self, original_bytes: bytes, data: Any, file_path: Path | None = None):
        """
        Initialize YAYA document.

        Args:
            original_bytes: Original document bytes
            data: Parsed YAML data from ruamel.yaml
            file_path: Optional path to source file
        """
        self.original_bytes = original_bytes
        self.data = data
        self.file_path = file_path
        self._tracker = ModificationTracker(original_bytes)

        # Detect list indentation style from document
        self._detected_list_offset = detect_list_indentation(data, original_bytes)
        self._list_offset_override: int | None = None

    @property
    def modifications(self) -> dict[tuple[int, int], bytes]:
        """
        Get the current modifications dictionary.

        Returns:
            Dictionary mapping byte ranges to replacement bytes
        """
        return self._tracker.modifications

    @classmethod
    def load(cls, file_path: str | Path) -> 'YAYA':
        """
        Load a YAML file for editing.

        Args:
            file_path: Path to YAML file

        Returns:
            YAYA document instance

        Examples:
            >>> doc = YAYA.load('config.yaml')
        """
        path = Path(file_path)
        original_bytes = path.read_bytes()

        yaml = YAML()
        data = yaml.load(BytesIO(original_bytes))

        return cls(original_bytes, data, path)

    def set_list_indent_style(self, offset: int | Literal['aligned', 'indented']):
        """
        Override the list indentation style for this document.

        Args:
            offset: 0 or 'aligned' for bullets aligned with parent key,
                   2 or 'indented' for bullets indented 2 spaces from parent

        Examples:
            >>> doc.set_list_indent_style('indented')  # GitHub Actions style
            >>> doc.set_list_indent_style(0)  # Aligned style

        Raises:
            ValueError: If offset is not a valid value
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

        Returns:
            List offset value, or None if ambiguous and no override set

        Note:
            Falls back to environment variables and warnings if detection fails.
        """
        if self._list_offset_override is not None:
            return self._list_offset_override

        if self._detected_list_offset is not None:
            return self._detected_list_offset

        # Check for mixed/ambiguous indentation behavior
        env_behavior = os.environ.get('YAYA_MIXED_INDENT', 'warn').lower()
        if env_behavior == 'error':
            raise ValueError(
                "Mixed or ambiguous list indentation detected in document. "
                "Use doc.set_list_indent_style() to specify explicitly, or set "
                "YAYA_LIST_OFFSET environment variable."
            )
        elif env_behavior == 'warn':
            warnings.warn(
                "No consistent list indentation detected in document. "
                "Defaulting to offset=2 (indented). Use doc.set_list_indent_style() "
                "to override or set YAYA_LIST_OFFSET environment variable.",
                UserWarning
            )

        # Fall through to serialize_to_yaml's default handling
        return None

    def replace_in_values(self, old: str, new: str):
        """
        Replace all occurrences of `old` with `new` in all string values.

        Args:
            old: String to find
            new: String to replace with

        Examples:
            >>> doc.replace_in_values('src/', 'lib/src/')
        """
        self._replace_recursive(self.data, lambda v: v.replace(old, new) if old in v else None)

    def replace_in_values_regex(self, pattern: str, replacement: str):
        r"""
        Replace all occurrences matching regex `pattern` with `replacement` in all string values.

        Args:
            pattern: Regular expression pattern
            replacement: Replacement string (can include backreferences like \1)

        Examples:
            >>> doc.replace_in_values_regex(r'v(\d+)', r'version-\1')
        """
        compiled_pattern = re.compile(pattern)
        self._replace_recursive(
            self.data,
            lambda v: compiled_pattern.sub(replacement, v) if compiled_pattern.search(v) else None
        )

    def _replace_recursive(self, obj: Any, transform_func: callable):
        """
        Recursively apply a transformation function to all string values.

        Args:
            obj: Object to traverse (CommentedMap, CommentedSeq, or scalar)
            transform_func: Function that takes a string and returns transformed string or None
        """
        if isinstance(obj, CommentedMap):
            for key, value in obj.items():
                if isinstance(value, str):
                    new_value = transform_func(value)
                    if new_value is not None:
                        self._tracker.record_scalar_modification(obj, key, new_value)
                        obj[key] = new_value
                else:
                    self._replace_recursive(value, transform_func)
        elif isinstance(obj, CommentedSeq):
            for i, item in enumerate(obj):
                if isinstance(item, str):
                    new_value = transform_func(item)
                    if new_value is not None:
                        self._tracker.record_scalar_modification(obj, i, new_value)
                        obj[i] = new_value
                else:
                    self._replace_recursive(item, transform_func)

    def get_path(self, path: str) -> Any:
        """
        Get value at path.

        Args:
            path: Dotted path with optional array indices

        Returns:
            Value at the specified path

        Examples:
            >>> doc.get_path("jobs.test.runs-on")
            'ubuntu-latest'
            >>> doc.get_path("jobs.test.steps[0].uses")
            'actions/checkout@v3'

        Raises:
            KeyError: If path doesn't exist
        """
        _, value, _ = navigate_to_path(self.data, path)
        return value

    def __getitem__(self, key: str) -> Any:
        """
        Dict-like access to top-level keys.

        Args:
            key: Top-level key name

        Returns:
            Value at the key

        Examples:
            >>> doc["jobs"]["test"]["runs-on"]
            'ubuntu-latest'
        """
        return self.data[key]

    def assert_value(self, path: str, expected: Any):
        """
        Assert that value at path equals expected.

        Args:
            path: Dotted path to check
            expected: Expected value

        Raises:
            AssertionError: If actual value doesn't match expected
        """
        actual = self.get_path(path)
        if actual != expected:
            raise AssertionError(f"Expected {expected!r} at path {path!r}, got {actual!r}")

    def assert_absent(self, path: str):
        """
        Assert that path does not exist.

        Args:
            path: Dotted path that should not exist

        Raises:
            AssertionError: If path exists
        """
        try:
            self.get_path(path)
            raise AssertionError(f"Path {path!r} should be absent but exists")
        except KeyError:
            pass

    def assert_present(self, path: str):
        """
        Assert that path exists.

        Args:
            path: Dotted path that should exist

        Raises:
            AssertionError: If path doesn't exist
        """
        try:
            self.get_path(path)
        except KeyError:
            raise AssertionError(f"Path {path!r} should be present but is absent")

    def ensure_key(self, path: str, value: Any, verify_if_exists: bool = False) -> bool:
        """
        Ensure a key exists with a specific value (idempotent).

        If the key doesn't exist, adds it (creating intermediate paths as needed).
        If it exists and verify_if_exists=True, checks that it matches the expected value.

        Args:
            path: Full dotted path including the key (e.g., "jobs.test.defaults.run.working-directory")
            value: Expected value
            verify_if_exists: If True, raises if key exists with different value

        Returns:
            True if key was added, False if it already existed

        Raises:
            ValueError: If verify_if_exists=True and existing value doesn't match

        Examples:
            >>> # Add if missing, ignore if exists
            >>> doc.ensure_key("jobs.test.defaults.run.working-directory", "lib/levanter")
            True

            >>> # Add if missing, verify if exists
            >>> doc.ensure_key("jobs.test.runs-on", "ubuntu-latest", verify_if_exists=True)
            False
        """
        try:
            existing_value = self.get_path(path)
            # Key exists
            if verify_if_exists and existing_value != value:
                raise ValueError(
                    f"Key {path!r} exists with value {existing_value!r}, "
                    f"expected {value!r}"
                )
            return False
        except KeyError:
            # Key doesn't exist - need to add it
            # First ensure all parent paths exist
            parts = parse_path(path) if isinstance(path, str) else list(path)

            # Create intermediate paths if needed
            for i in range(1, len(parts)):
                parent_path_str = '.'.join(str(p) if not isinstance(p, int) else f'[{p}]' for p in parts[:i])
                # Clean up the path string (remove .[ patterns)
                parent_path_str = parent_path_str.replace('.[', '[')

                try:
                    self.get_path(parent_path_str)
                except KeyError:
                    # Parent doesn't exist, create it as empty dict
                    # Use add_key with force=True to create it
                    self.add_key(parent_path_str, CommentedMap(), force=True)

            # Now add the final key using add_key which properly tracks modifications
            self.add_key(path, value, force=True)
            return True

    def _find_key_byte_range(self, parent: CommentedMap, key: str) -> tuple[int, int]:
        """
        Find the byte range for a key-value pair in a CommentedMap.

        Args:
            parent: Parent mapping
            key: Key to find

        Returns:
            Tuple of (start, end) where start is the beginning of the key line
            and end is the end of the value

        Raises:
            ValueError: If key not found or lacks position info
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
            # Find the end by looking for the last item's position
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

        Args:
            path: Dotted path where key should be added
            value: Value to set
            force: If True, overwrites existing key

        Raises:
            KeyError: If key exists and force=False, or if parent path doesn't exist
            TypeError: If trying to add key to non-mapping

        Examples:
            >>> doc.add_key("jobs.new-job", {"runs-on": "ubuntu-latest"})
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

            self._tracker.record_insertion(existing_end, new_content.encode('utf-8'))
            # Update data structure
            parent[final_key] = value
        else:
            # Scalar value - also needs to be serialized and inserted
            # Determine indentation
            if hasattr(parent, 'lc') and len(parent) > 0:
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
                # Empty parent
                existing_end = 0

            # Build the new key-value pair
            indent_spaces = ' ' * key_col
            key_str = str(final_key)
            new_content = f"\n{indent_spaces}{key_str}: {value}"

            self._tracker.record_insertion(existing_end, new_content.encode('utf-8'))
            # Update data structure
            parent[final_key] = value

    def replace_key(self, path: str, value: Any):
        """
        Replace the value at path with a new value.

        Args:
            path: Dotted path to key
            value: New value (can be dict, list, or scalar)

        Note:
            If the key doesn't exist, adds it (same as add_key with force=True).

        Examples:
            >>> doc.replace_key("jobs.test.runs-on", "ubuntu-22.04")
        """
        try:
            parent, old_value, final_key = navigate_to_path(self.data, path)
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

                self._tracker.modifications[(start, end)] = replacement.encode('utf-8')
            else:
                # Scalar value - use existing record_scalar_modification
                self._tracker.record_scalar_modification(parent, final_key, str(value))

            # Update the data structure
            parent[final_key] = value

    def add_key_after(self, existing_path: str, new_key: str, value: Any):
        """
        Add a new key after an existing key in a mapping.

        Args:
            existing_path: Path to existing key to insert after
            new_key: Name of new key to add
            value: Value for new key

        Raises:
            KeyError: If new_key already exists
            TypeError: If parent is not a mapping
            ValueError: If position info not available

        Examples:
            >>> doc.add_key_after("jobs.test.runs-on", "defaults", {"run": {"shell": "bash"}})
        """
        # Navigate to the parent containing the existing key
        parent, _, existing_key = navigate_to_path(self.data, existing_path)

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
        self._tracker.record_insertion(existing_end, new_content.encode('utf-8'))

        # Update the data structure - need to maintain order
        # Create a new CommentedMap with the key inserted in the right position
        keys = list(parent.keys())
        existing_index = keys.index(existing_key)

        # Insert the new value into the data structure
        items = list(parent.items())
        items.insert(existing_index + 1, (new_key, value))

        parent.clear()
        for k, v in items:
            parent[k] = v

    def save(self, file_path: Path | str | None = None) -> bytes:
        """
        Save the modified YAML, preserving all formatting.

        Args:
            file_path: Optional path to save to (defaults to original file path)

        Returns:
            Final document bytes with modifications applied

        Examples:
            >>> doc.save()  # Save to original file
            >>> doc.save('output.yaml')  # Save to different file
        """
        target_path = Path(file_path) if file_path else self.file_path

        final_bytes = self._tracker.apply_modifications()

        if target_path:
            target_path.write_bytes(final_bytes)

        return final_bytes
