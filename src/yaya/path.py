"""
Path parsing and navigation utilities for YAML documents.

Supports dotted path notation with array indices: "jobs.test.steps[0].uses"
"""
from typing import Any
from ruamel.yaml.comments import CommentedMap, CommentedSeq


def parse_path(path: str) -> list[str | int]:
    """
    Parse a dotted path string into components.

    Supports:
    - Dot notation: "jobs.test.runs-on"
    - Array indices: "steps[0]" or "steps[0].uses"
    - Combined: "jobs.test.steps[0].uses"

    Args:
        path: A dotted path string with optional array indices

    Returns:
        List of path components (strings for keys, ints for indices)

    Examples:
        >>> parse_path("jobs.test.runs-on")
        ["jobs", "test", "runs-on"]
        >>> parse_path("jobs.test.steps[0].uses")
        ["jobs", "test", "steps", 0, "uses"]

    Raises:
        ValueError: If brackets are unclosed or invalid
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


def navigate_to_path(data: Any, path: str | list[str | int]) -> tuple[Any, Any, str | int]:
    """
    Navigate to a path and return (parent, current_value, final_key).

    Args:
        data: Root data structure (typically CommentedMap)
        path: Path string or parsed path list

    Returns:
        Tuple of (parent_object, current_value, final_key)
        - parent_object: The container holding the final key
        - current_value: The value at the path
        - final_key: The last key/index in the path

    Raises:
        ValueError: If path is empty
        KeyError: If a key in the path doesn't exist
        IndexError: If a sequence index is out of range
        TypeError: If path tries to navigate through a scalar value
    """
    if isinstance(path, str):
        parts = parse_path(path)
    else:
        parts = path

    if not parts:
        raise ValueError("Empty path")

    current = data
    parent = None
    final_key = None

    for i, part in enumerate(parts):
        parent = current
        final_key = part

        if isinstance(current, (CommentedMap, dict)):
            if part not in current:
                raise KeyError(f"Path not found: {'.'.join(str(p) for p in parts[:i+1])}")
            current = current[part]
        elif isinstance(current, (CommentedSeq, list)):
            if not isinstance(part, int):
                raise TypeError(f"Expected integer index for sequence, got {type(part).__name__}")
            if part < 0 or part >= len(current):
                raise IndexError(f"Index {part} out of range for sequence of length {len(current)}")
            current = current[part]
        else:
            raise TypeError(f"Cannot navigate through {type(current).__name__}")

    return parent, current, final_key
