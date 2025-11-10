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

    def _detect_style(self, value: Any) -> Literal['block', 'flow']:
        """
        Detect the style of an existing value by checking original bytes.

        Args:
            value: The value to detect style for (must be a list or dict)

        Returns:
            'flow' if the value uses flow style ([...] or {...}), 'block' otherwise

        Note:
            This is a best-effort detection. If uncertain, returns 'block'.
        """
        if not isinstance(value, (list, dict, CommentedSeq, CommentedMap)):
            # Scalar values don't have a style
            return 'block'

        # For CommentedSeq/CommentedMap, check if they have position info
        if isinstance(value, (CommentedSeq, CommentedMap)) and hasattr(value, 'lc'):
            if isinstance(value, CommentedSeq) and len(value) > 0:
                # Check if first item has position info
                if 0 in value.lc.data:
                    first_line, first_col = value.lc.data[0][0], value.lc.data[0][1]
                    # Find the start of this line to look for opening bracket
                    line_start = line_col_to_index(self.original_bytes, first_line, 0)
                    # Look backward from first_col to see if there's a '[' on the same line
                    search_start = line_start
                    search_end = line_col_to_index(self.original_bytes, first_line, first_col)
                    line_bytes = self.original_bytes[search_start:search_end]
                    if b'[' in line_bytes:
                        return 'flow'
            elif isinstance(value, CommentedMap) and len(value) > 0:
                # Similar check for mappings with '{'
                first_key = list(value.keys())[0]
                if first_key in value.lc.data:
                    key_line, key_col = value.lc.data[first_key][0], value.lc.data[first_key][1]
                    line_start = line_col_to_index(self.original_bytes, key_line, 0)
                    search_end = line_col_to_index(self.original_bytes, key_line, key_col)
                    line_bytes = self.original_bytes[line_start:search_end]
                    if b'{' in line_bytes:
                        return 'flow'

        # Default to block style
        return 'block'

    def _get_list_offset_for_serialization(self) -> int:
        """
        Get the list offset to use for serialize_to_yaml().

        Returns:
            List offset value, preferring user override, defaulting to 2

        Note:
            Unlike _get_list_offset(), this never returns None and always
            returns a safe default (2) if no override is set, to avoid using
            potentially incorrect auto-detected offsets from flow-style originals.
        """
        if self._list_offset_override is not None:
            return self._list_offset_override

        # Default to 2 (standard indented style)
        # Don't use auto-detected offset which may be wrong for flow-style documents
        return 2

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
        # by recursively finding the last item in nested structures
        value = parent[key]
        if isinstance(value, (CommentedMap, CommentedSeq)):
            val_end_line = val_line

            # Recursively find the deepest last item
            def find_last_line(obj):
                """Recursively find the line number of the last item in nested structures."""
                if isinstance(obj, CommentedMap) and obj and hasattr(obj, 'lc'):
                    last_key = list(obj.keys())[-1]
                    if last_key in obj.lc.data:
                        last_info = obj.lc.data[last_key]
                        if len(last_info) >= 4:
                            # Check if the value is also nested
                            last_value = obj[last_key]
                            if isinstance(last_value, (CommentedMap, CommentedSeq)):
                                # Recurse into nested structure
                                return find_last_line(last_value)
                            else:
                                # Scalar value - return its line
                                return last_info[2]
                elif isinstance(obj, CommentedSeq) and obj and hasattr(obj, 'lc'):
                    last_idx = len(obj) - 1
                    if last_idx in obj.lc.data:
                        last_info = obj.lc.data[last_idx]
                        if len(last_info) >= 2:
                            # Check if the item is also nested
                            last_item = obj[last_idx]
                            if isinstance(last_item, (CommentedMap, CommentedSeq)):
                                # Recurse into nested structure
                                return find_last_line(last_item)
                            else:
                                # Scalar item - return its line
                                return last_info[0]
                return None

            last_line = find_last_line(value)
            if last_line is not None:
                val_end_line = last_line

            # Find end of that line
            val_end = line_col_to_index(self.original_bytes, val_end_line, 0)
            while val_end < len(self.original_bytes) and self.original_bytes[val_end] != ord('\n'):
                val_end += 1

        return key_start_idx, val_end

    def add_key(
        self,
        path: str,
        value: Any,
        force: bool = False,
        style: Literal['auto', 'block', 'flow'] = 'auto',
        quote_style: Literal['auto', 'double', 'single', 'plain'] = 'auto',
        blank_lines_before: int = 0,
        formatting: dict | None = None,
    ):
        """
        Add a new key at path. If force=True, replaces existing key.

        Args:
            path: Dotted path where key should be added
            value: Value to set
            force: If True, overwrites existing key
            style: How to format collections:
                - 'auto': Use ruamel.yaml's default
                - 'block': Force block style for collections
                - 'flow': Force inline/flow style for collections
            quote_style: How to quote string scalars (default: 'auto')
            blank_lines_before: Number of blank lines to add before this key (default: 0)
            formatting: Nested formatting hints for sub-nodes

        Raises:
            KeyError: If key exists and force=False, or if parent path doesn't exist
            TypeError: If trying to add key to non-mapping

        Examples:
            >>> doc.add_key("jobs.new-job", {"runs-on": "ubuntu-latest"})
            >>> doc.add_key("matrix.python-version", ["3.11"], style='flow')
            >>> doc.add_key("jobs.build.strategy", {...}, blank_lines_before=1)
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
            # Build formatted YAML node with proper metadata
            from .formatting import build_yaml_node

            # Determine flow style for node
            flow_style = None
            if style == 'flow':
                flow_style = True
            elif style == 'block':
                flow_style = False

            # Build node with formatting metadata
            yaml_node = build_yaml_node(
                value,
                flow_style=flow_style,
                quote_style=quote_style,
                formatting=formatting,
            )

            # For block-style dicts, we need indent=2 to properly nest top-level keys
            # For flow-style or lists, use indent=0
            base_indent = 2 if (isinstance(value, dict) and style != 'flow') else 0
            yaml_value = serialize_to_yaml(
                yaml_node,
                indent=base_indent,
                style='auto',  # Let node's formatting metadata control this
                list_offset=self._get_list_offset()
            )

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
                # serialize_to_yaml() already applied proper indentation (indent=2 for dicts)
                # We just need to add the base key indentation to match nesting level
                for line in value_lines:
                    if line.strip():
                        new_lines.append(f"{indent_spaces}{line}")
                    else:
                        new_lines.append('')
                new_content = '\n'.join(new_lines)
            else:
                # Single line
                new_content = f"\n{indent_spaces}{key_str}: {yaml_value}"

            self._tracker.record_insertion(existing_end, new_content.encode('utf-8'))
            # Update data structure (use formatted node to preserve .fa metadata)
            parent[final_key] = yaml_node

            # Add blank lines if requested
            if blank_lines_before > 0:
                parent.yaml_set_comment_before_after_key(
                    final_key,
                    before='\n' * blank_lines_before
                )
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

            # Add blank lines if requested
            if blank_lines_before > 0:
                parent.yaml_set_comment_before_after_key(
                    final_key,
                    before='\n' * blank_lines_before
                )

    def _replace_list_item(
        self,
        parent: CommentedSeq,
        index: int,
        value: Any,
        style: Literal['auto', 'block', 'flow'] = 'auto'
    ):
        """
        Replace a list item at the given index.

        Args:
            parent: The CommentedSeq (list) containing the item
            index: The index of the item to replace
            value: The new value for the item
            style: How to format collections in the value

        Note:
            Preserves the list item marker (`-`) and indentation.
        """
        if not hasattr(parent, 'lc') or index not in parent.lc.data:
            # No position info - just update the data structure
            return

        lc_info = parent.lc.data[index]
        item_line, item_col = lc_info[0], lc_info[1]

        # Find the byte range of the list item value
        # item_col points to the start of the value (after "- ")
        start_idx = line_col_to_index(self.original_bytes, item_line, item_col)

        # Find the end of this item (either next item or end of list)
        if index + 1 < len(parent) and (index + 1) in parent.lc.data:
            # There's a next item - end before it
            next_line, _ = parent.lc.data[index + 1][0], parent.lc.data[index + 1][1]
            # Go to end of line before next item
            end_idx = line_col_to_index(self.original_bytes, next_line, 0)
            # Trim back to end of previous line
            while end_idx > start_idx and self.original_bytes[end_idx - 1] in b'\n\r':
                end_idx -= 1
        else:
            # Last item in list - find end of line
            end_idx = start_idx
            while end_idx < len(self.original_bytes) and self.original_bytes[end_idx] not in b'\n\r':
                end_idx += 1

        # Serialize the new value
        if isinstance(value, (dict, list)):
            yaml_value = serialize_to_yaml(
                value,
                indent=0,
                style=style,
                list_offset=self._get_list_offset()
            )
            # For multi-line values, need proper indentation
            if '\n' in yaml_value:
                # Block style - indent all lines
                indent_spaces = ' ' * item_col
                value_lines = yaml_value.split('\n')
                indented_lines = []
                for i, line in enumerate(value_lines):
                    if i == 0:
                        # First line goes on the same line as the dash
                        indented_lines.append(line)
                    elif line.strip():
                        # Subsequent lines need full indentation
                        indented_lines.append(f"\n{indent_spaces}{line}")
                    else:
                        indented_lines.append('')
                replacement = ''.join(indented_lines)
            else:
                replacement = yaml_value
        else:
            replacement = str(value)

        self._tracker.modifications[(start_idx, end_idx)] = replacement.encode('utf-8')

    def _detect_quote_style_from_original(
        self,
        node: Any,
    ) -> Literal['double', 'single', 'plain'] | None:
        """
        Detect the quote style used in the original YAML for a node.

        Args:
            node: A ruamel node (CommentedSeq, scalar, etc.)

        Returns:
            Quote style if detectable, None otherwise
        """
        from ruamel.yaml.comments import CommentedSeq
        from .extract import extract_quote_style

        # For sequences, check the first item
        if isinstance(node, CommentedSeq) and len(node) > 0:
            if hasattr(node, 'lc') and node.lc.data and 0 in node.lc.data:
                line, col = node.lc.data[0][:2]
                return extract_quote_style(self.original_bytes, line, col)

        # For scalars with position info, extract directly
        # (This would require storing position info with the parent, which we don't have here)

        return None

    def replace_key(
        self,
        path: str,
        value: Any,
        style: Literal['auto', 'block', 'flow', 'preserve'] = 'auto',
        quote_style: Literal['auto', 'double', 'single', 'plain'] = 'auto',
        blank_lines_before: int = 0,
        formatting: dict | None = None,
    ):
        """
        Replace the value at path with a new value.

        Args:
            path: Dotted path to key
            value: New value (can be dict, list, or scalar)
            style: How to format collections:
                - 'auto': Use ruamel.yaml's default (current behavior)
                - 'block': Force block style for collections
                - 'flow': Force inline/flow style for collections (e.g., [1, 2, 3])
                - 'preserve': Try to match existing style (falls back to 'auto' if no existing value)
            quote_style: How to quote string scalars (default: 'auto')
            blank_lines_before: Number of blank lines to add before this key (default: 0)
            formatting: Nested formatting hints for sub-nodes
                Example: {'branches': {'flow_style': True}, 'paths[0]': {'quote_style': 'double'}}

        Note:
            If the key doesn't exist, adds it (same as add_key with force=True).

        Examples:
            >>> doc.replace_key("jobs.test.runs-on", "ubuntu-22.04")
            >>> doc.replace_key("matrix.python-version", ["3.11", "3.12"], style='flow')
            >>> # Produces: python-version: ["3.11", "3.12"]

            >>> # With blank line before
            >>> doc.replace_key("jobs.build.strategy", {...}, blank_lines_before=1)

            >>> # With nested formatting
            >>> doc.replace_key("matrix", {
            ...     "python-version": ["3.11", "3.12"],
            ...     "os": ["ubuntu", "macos"],
            ... }, formatting={
            ...     'python-version': {'flow_style': True},
            ...     'os': {'flow_style': False},
            ... })
        """
        # Handle preserve style
        if style == 'preserve':
            try:
                old_value = self.get_path(path)
                style = self._detect_style(old_value)
            except KeyError:
                style = 'auto'

        try:
            parent, old_value, final_key = navigate_to_path(self.data, path)
        except KeyError:
            # Key doesn't exist, add it
            self.add_key(
                path, value, force=True, style=style,
                quote_style=quote_style, blank_lines_before=blank_lines_before,
                formatting=formatting
            )
            return

        # Handle list items
        if isinstance(parent, CommentedSeq):
            if not isinstance(final_key, int):
                raise TypeError(f"List items must be accessed with integer index, not {type(final_key).__name__}")

            # Build formatted YAML node if value is a collection
            if isinstance(value, (dict, list)):
                from .formatting import build_yaml_node

                # Determine flow style for node
                flow_style = None
                if style == 'flow':
                    flow_style = True
                elif style == 'block':
                    flow_style = False

                # Build node with formatting metadata
                yaml_node = build_yaml_node(
                    value,
                    flow_style=flow_style,
                    quote_style=quote_style,
                    formatting=formatting,
                )
            else:
                yaml_node = value

            # Replace list item
            self._replace_list_item(parent, final_key, yaml_node, style=style)
            parent[final_key] = yaml_node
            return

        if not isinstance(parent, CommentedMap):
            raise TypeError(f"Can only replace keys in mappings or list items, not {type(parent).__name__}")

        # Determine indentation from the key's position
        if hasattr(parent, 'lc') and final_key in parent.lc.data:
            lc_info = parent.lc.data[final_key]
            key_line, key_col = lc_info[0], lc_info[1]

            # Serialize the new value
            if isinstance(value, (dict, list)):
                # Build formatted YAML node with proper metadata
                from .formatting import build_yaml_node

                # Determine flow style for node
                flow_style = None
                if style == 'flow':
                    flow_style = True
                elif style == 'block':
                    flow_style = False
                # else 'auto' - let ruamel decide

                # Build node with formatting metadata
                yaml_node = build_yaml_node(
                    value,
                    flow_style=flow_style,
                    quote_style=quote_style,
                    formatting=formatting,
                )

                # Get the proper list offset (respects user override or defaults)
                use_list_offset = self._get_list_offset_for_serialization()

                # Base indentation: values start 2 spaces after their key
                # serialize_to_yaml() will add this to all content
                value_indent = key_col + 2

                # Serialize the formatted node
                yaml_value = serialize_to_yaml(
                    yaml_node,
                    indent=value_indent,
                    style='auto',  # Let node's formatting metadata control this
                    list_offset=use_list_offset
                )

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
                    # serialize_to_yaml() already applied proper indentation
                    # Don't add more indent - just use the lines as-is
                    for line in value_lines:
                        replacement_lines.append(line)
                    replacement = '\n'.join(replacement_lines)
                else:
                    # Single line value (flow style)
                    replacement = f"{indent_spaces}{key_str}: {yaml_value}"

                self._tracker.modifications[(start, end)] = replacement.encode('utf-8')
                # Update the data structure with formatted node (preserves .fa metadata)
                parent[final_key] = yaml_node
            else:
                # Scalar value - use existing record_scalar_modification
                self._tracker.record_scalar_modification(parent, final_key, str(value))
                # Update the data structure
                parent[final_key] = value

            # Add blank lines if requested
            # Note: ruamel consumes one newline, so add 1 extra
            if blank_lines_before > 0 and isinstance(parent, CommentedMap):
                parent.yaml_set_comment_before_after_key(
                    final_key,
                    before='\n' * (blank_lines_before + 1)
                )

    def add_key_after(
        self,
        existing_path: str,
        new_key: str,
        value: Any,
        style: Literal['auto', 'block', 'flow'] = 'auto',
        quote_style: Literal['auto', 'double', 'single', 'plain'] = 'auto',
        blank_lines_before: int = 0,
        formatting: dict | None = None,
    ):
        """
        Add a new key after an existing key in a mapping.

        Args:
            existing_path: Path to existing key to insert after
            new_key: Name of new key to add
            value: Value for new key
            style: How to format collections:
                - 'auto': Use ruamel.yaml's default
                - 'block': Force block style for collections
                - 'flow': Force inline/flow style for collections
            quote_style: How to quote string scalars (default: 'auto')
            blank_lines_before: Number of blank lines to add before this key (default: 0)
            formatting: Nested formatting hints for sub-nodes

        Raises:
            KeyError: If new_key already exists
            TypeError: If parent is not a mapping
            ValueError: If position info not available

        Examples:
            >>> doc.add_key_after("jobs.test.runs-on", "defaults", {"run": {"shell": "bash"}})
            >>> doc.add_key_after("strategy", "matrix", {"python-version": ["3.11"]}, style='flow')
            >>> doc.add_key_after("runs-on", "strategy", {...}, blank_lines_before=1)
        """
        # Navigate to the parent containing the existing key
        parent, _, existing_key = navigate_to_path(self.data, existing_path)

        if not isinstance(parent, CommentedMap):
            raise TypeError(f"Can only add keys to mappings, not {type(parent).__name__}")

        if new_key in parent:
            raise KeyError(f"Key {new_key!r} already exists")

        # Find the position to insert
        if not hasattr(parent, 'lc') or existing_key not in parent.lc.data:
            # Position info not available (programmatically-added key)
            # Fall back to regular add_key() - ordering not guaranteed
            import warnings
            warnings.warn(
                f"Key {existing_key!r} has no position info (programmatically added). "
                f"Using add_key() instead - insertion order not guaranteed.",
                UserWarning
            )
            return self.add_key(
                existing_path.rsplit('.', 1)[0] + f'.{new_key}',
                value,
                style=style,
                quote_style=quote_style,
                blank_lines_before=blank_lines_before,
                formatting=formatting,
                force=False
            )

        lc_info = parent.lc.data[existing_key]
        key_col = lc_info[1]

        # Find the end of the existing key's value
        _, existing_end = self._find_key_byte_range(parent, existing_key)

        # Serialize the new value
        if isinstance(value, (dict, list)):
            # Build formatted YAML node with proper metadata
            from .formatting import build_yaml_node

            # Determine flow style for node
            flow_style = None
            if style == 'flow':
                flow_style = True
            elif style == 'block':
                flow_style = False

            # Build node with formatting metadata
            yaml_node = build_yaml_node(
                value,
                flow_style=flow_style,
                quote_style=quote_style,
                formatting=formatting,
            )

            # For block-style dicts, we need indent=2 to properly nest top-level keys
            # For flow-style or lists, use indent=0
            base_indent = 2 if (isinstance(value, dict) and style != 'flow') else 0
            yaml_value = serialize_to_yaml(
                yaml_node,
                indent=base_indent,
                style='auto',
                list_offset=self._get_list_offset()
            )
            # Store the formatted node to preserve .fa metadata
            value_to_store = yaml_node
        else:
            # Scalar value
            yaml_value = str(value)
            value_to_store = value

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

        # Insert the new value into the data structure (use formatted node to preserve .fa)
        items = list(parent.items())
        items.insert(existing_index + 1, (new_key, value_to_store))

        parent.clear()
        for k, v in items:
            parent[k] = v

        # Add blank lines before the new key if requested
        if blank_lines_before > 0:
            parent.yaml_set_comment_before_after_key(
                new_key,
                before='\n' * (blank_lines_before + 1)
            )

    def insert_key_between(
        self,
        path: str,
        prev_key: str,
        next_key: str,
        new_key: str,
        value: Any
    ):
        """
        Insert a new key between two adjacent keys in a mapping.

        Verifies that prev_key and next_key are adjacent before inserting,
        providing better error messages and preventing mistakes.

        Args:
            path: Path to the parent dict (e.g., "jobs.build")
            prev_key: Key that should immediately precede the new key
            next_key: Key that should immediately follow the new key
            new_key: Name of the key to insert
            value: Value for the new key

        Raises:
            KeyError: If prev_key or next_key don't exist
            ValueError: If prev_key and next_key aren't adjacent
            TypeError: If path doesn't point to a mapping

        Examples:
            >>> # Insert defaults between 'if' and 'steps'
            >>> doc.insert_key_between(
            ...     "jobs.build",
            ...     prev_key="if",
            ...     next_key="steps",
            ...     new_key="defaults",
            ...     value={"run": {"working-directory": "lib/levanter"}}
            ... )
        """
        parent = self.get_path(path)

        if not isinstance(parent, (CommentedMap, dict)):
            raise TypeError(f"Path {path!r} is not a mapping")

        keys = list(parent.keys())

        if prev_key not in keys:
            raise KeyError(f"Previous key {prev_key!r} not found in {path}")
        if next_key not in keys:
            raise KeyError(f"Next key {next_key!r} not found in {path}")

        prev_idx = keys.index(prev_key)
        next_idx = keys.index(next_key)

        if next_idx != prev_idx + 1:
            keys_between = keys[prev_idx+1:next_idx]
            raise ValueError(
                f"Keys {prev_key!r} and {next_key!r} are not adjacent. "
                f"Found {len(keys_between)} key(s) between them: {keys_between}"
            )

        # Keys are adjacent - use add_key_after
        self.add_key_after(f"{path}.{prev_key}", new_key, value)

    def delete_key(self, path: str) -> bool:
        """
        Delete a key from the YAML document while preserving formatting.

        Deletes the entire key-value pair including:
        - The key name
        - The colon separator
        - The value (whether scalar, list, or mapping)
        - Any inline comments on the same line
        - The trailing newline
        - Comment lines immediately preceding the key (no blank lines between)

        Preserves:
        - Comments separated from the key by blank lines
        - Comments on following lines (below the deleted key)
        - Indentation of surrounding keys
        - Blank lines between sections

        Args:
            path: Dot-separated path to the key to delete (e.g., "build.mkdocs")

        Returns:
            True if key was deleted, False if key didn't exist

        Raises:
            ValueError: If path is invalid or points to root

        Examples:
            >>> doc = YAYA.load("config.yaml")
            >>> doc.delete_key("build.mkdocs")  # Delete build.mkdocs key
            True
            >>> doc.delete_key("build.python")  # Delete build.python key
            True
            >>> doc.delete_key("nonexistent")    # Returns False if key doesn't exist
            False
        """
        # Parse the path
        parts = parse_path(path) if isinstance(path, str) else path

        # Prevent deleting root
        if len(parts) == 0:
            raise ValueError("Cannot delete root")

        # Navigate to parent and key
        try:
            parent, _, final_key = navigate_to_path(self.data, path)
        except KeyError:
            # Key doesn't exist
            return False

        # Only support deleting from CommentedMap for now
        if not isinstance(parent, CommentedMap):
            raise TypeError(f"Can only delete keys from mappings, not {type(parent).__name__}")

        # Check if key exists in parent
        if final_key not in parent:
            return False

        # Delete from the ruamel data structure
        # The save() method will resave the entire document via clean AST,
        # which will naturally omit the deleted key
        del parent[final_key]
        return True

        # OLD BYTE-PATCHING APPROACH (DISABLED)
        # The code below is incompatible with full reserialization via clean AST.
        # Keeping for reference but unreachable.

        # Find the byte range to delete
        if not hasattr(parent, 'lc') or final_key not in parent.lc.data:
            # No position info - just delete from data structure
            del parent[final_key]
            return True

        # Get the line info for this key
        lc_info = parent.lc.data[final_key]
        key_line = lc_info[0]

        # Get the byte range for this key-value pair
        start_idx, end_idx = self._find_key_byte_range(parent, final_key)

        # Extend end_idx to include inline comments (rest of the line)
        while end_idx < len(self.original_bytes) and self.original_bytes[end_idx] != ord('\n'):
            end_idx += 1

        # Include the trailing newline
        if end_idx < len(self.original_bytes) and self.original_bytes[end_idx] == ord('\n'):
            end_idx += 1

        # Check if the next line is blank - if so, delete it too (prevents double blank lines)
        next_line_start = end_idx
        next_line_end = next_line_start
        while next_line_end < len(self.original_bytes) and self.original_bytes[next_line_end] != ord('\n'):
            next_line_end += 1

        # Check if this line is blank
        if next_line_start < len(self.original_bytes):
            next_line_content = self.original_bytes[next_line_start:next_line_end].decode('utf-8')
            if not next_line_content.strip():
                # Next line is blank - include it in deletion
                end_idx = next_line_end
                if end_idx < len(self.original_bytes) and self.original_bytes[end_idx] == ord('\n'):
                    end_idx += 1

        # Check for preceding comment lines that should be deleted with this key
        # Walk backwards from the key line to find comment lines with same indentation
        current_line = key_line - 1
        while current_line >= 0:
            # Find the start of this line
            line_start = line_col_to_index(self.original_bytes, current_line, 0)
            line_end = line_start
            while line_end < len(self.original_bytes) and self.original_bytes[line_end] != ord('\n'):
                line_end += 1

            # Get the line content
            line_content = self.original_bytes[line_start:line_end].decode('utf-8')

            # Check if it's a blank line - if so, stop (don't delete comments beyond blank lines)
            if not line_content.strip():
                break

            # Check if it's a comment line with same or greater indentation
            stripped = line_content.lstrip()
            if stripped.startswith('#'):
                # This is a comment line - check indentation matches
                indent = len(line_content) - len(stripped)
                key_indent = lc_info[1]

                # If comment has same indentation as key, it belongs to this key
                if indent == key_indent:
                    # Include this line in deletion
                    start_idx = line_start
                    current_line -= 1
                else:
                    # Different indentation - stop here
                    break
            else:
                # Not a comment line - stop here
                break

        # Record the deletion (replace with empty bytes)
        self._tracker.modifications[(start_idx, end_idx)] = b''

        # Delete from data structure
        del parent[final_key]

        return True

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

        # Use clean AST architecture for truly lossless serialization
        from .converter import convert_to_clean_ast
        from .emitter import serialize

        # Pass detected list offset to converter for programmatic sequences
        # If no offset detected, use default of 2 (indented style)
        detected = self._get_list_offset()
        default_offset = detected if detected is not None else 2
        clean_ast = convert_to_clean_ast(self.data, self.original_bytes, default_list_offset=default_offset)
        final_bytes = serialize(clean_ast)

        if target_path:
            target_path.write_bytes(final_bytes)

        return final_bytes
