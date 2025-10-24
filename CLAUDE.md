# yaya Development Context

## Project Overview

**yaya** (Yet Another YAML AST transformer) is a Python library for byte-for-byte preserving YAML editing. Unlike ruamel.yaml's round-trip mode (which preserves most formatting but makes small changes), this library guarantees that only the values you explicitly modify will change.

## Key Innovation

Instead of parse → modify → serialize, we:
1. Parse YAML with ruamel.yaml to get AST + position info (`lc.data` contains line/col for every value)
2. Convert line/col to byte offsets in the original file
3. Track modifications as you change values
4. Apply byte-level replacements when saving, leaving everything else untouched

## Architecture

```
src/yaya/
├── __init__.py          # Package exports
├── document.py          # YAYA class (main interface)
├── byte_ops.py          # Byte/position utilities
├── modifications.py     # ModificationTracker class
├── serialization.py     # YAML serialization with indentation
└── path.py              # Path parsing and navigation
```

Key functions and classes:
- `byte_ops.line_col_to_index()`: Convert (line, col) → byte offset
- `byte_ops.find_scalar_value_range()`: Find byte range of a scalar value
- `YAYA`: Main class
    - `.load(file_path)`: Load YAML file
    - `.replace_in_values(old, new)`: Bulk string replacement
    - `.save(file_path=None)`: Save with modifications

## Current Status

### ✅ All Tests Passing (21/21)
- ✅ Simple string replacements in plain scalars
- ✅ Comment preservation
- ✅ Whitespace preservation
- ✅ Block scalar handling
- ✅ Nested structures (mappings in sequences)
- ✅ No-op when pattern doesn't match
- ✅ Regex-based replacement
- ✅ List indentation detection and configuration
- ✅ Path navigation and assertions
- ✅ Key addition and replacement
- ✅ Idempotency
- ✅ Examples work perfectly

## Known Issues & TODOs

### Medium Priority
- [ ] Add yq-style path selectors with wildcards (`.jobs.test.steps[*].run`)
- [ ] Add direct dict-like access with `__setitem__` tracking
- [ ] Better error messages when modifications fail
- [ ] Handle edge cases: flow-style collections, anchors/aliases, multi-document streams

### Future Enhancements
- [ ] Callback-based value transformation
- [ ] Preserving anchors and aliases through modifications
- [ ] Support for removing keys (currently only adding/replacing)

## Key Files to Review

1. **`src/yaya/document.py`**: Main YAYA class
   - `replace_in_values()`: Recursively replaces strings in the AST
   - `add_key()`, `replace_key()`, `add_key_after()`: Key manipulation
   - `get_path()`, `assert_value()`, etc.: Path navigation and assertions

2. **`src/yaya/modifications.py`**: ModificationTracker class
   - `record_scalar_modification()`: Records byte positions for changed values
   - `_format_replacement()`: Formats replacement values (handles block scalar indent)
   - `apply_modifications()`: Applies all modifications to original bytes

3. **`src/yaya/byte_ops.py`**: Low-level byte operations
   - `line_col_to_index()`: Position to byte offset conversion
   - `find_scalar_value_range()`: Finds byte ranges of values

4. **`src/yaya/path.py`**: Path parsing and navigation
   - `parse_path()`: Parses dotted paths with array indices
   - `navigate_to_path()`: Navigates to paths in the AST

5. **`src/yaya/serialization.py`**: YAML serialization utilities
   - `detect_list_indentation()`: Detects list indentation style
   - `serialize_to_yaml()`: Serializes values with specific indentation

6. **`tests/`**: Comprehensive test suite
   - `test_basic.py`: Core functionality tests
   - `test_list_indentation.py`: List indentation tests
   - `test_workflow_transforms.py`: Real-world workflow transformation tests

7. **`examples/`**: Usage examples
   - `basic.py`: Simple example
   - `github_actions.py`: Real-world use case for updating paths in workflows

## Debugging Tips

### To debug modifications not being applied:
```python
doc = YAYA.load('test.yaml')
print(f"Before: {doc.modifications}")  # Should be {}
doc.replace_in_values('old', 'new')
print(f"After: {doc.modifications}")   # Should show byte ranges
```

### To inspect ruamel.yaml's position tracking:
```python
from ruamel.yaml import YAML
yaml = YAML()
data = yaml.load(open('test.yaml'))

# For mappings
if hasattr(data, 'lc'):
    print(data.lc.data)  # {key: [key_line, key_col, val_line, val_col]}

# For sequences
if hasattr(data['list'], 'lc'):
    print(data['list'].lc.data)  # {index: [line, col]}
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_basic.py::test_block_scalar -v

# Run with debugging
pytest tests/ -vv -s
```

## Original Use Case

This library was created to solve a specific problem: updating file paths in GitHub Actions workflows when restructuring a monorepo. For example:

```yaml
# Before
run: pytest src/marin/tests

# After (preserving everything else)
run: pytest lib/marin/src/marin/tests
```

Using ruamel.yaml's round-trip mode would change:
- Block scalar indicators (`|` → `|-`)
- Trailing whitespace in blank lines
- Sometimes indentation

This library guarantees those stay untouched.

## Design Decisions

### Why not fork ruamel.yaml?
- The lossless approach works **with** stock ruamel.yaml
- Easier to maintain as a separate library
- Can iterate independently
- ruamel.yaml maintainer might not want this complexity

### Why byte-level editing instead of AST serialization?
- Guarantees perfect preservation
- Simpler mental model: "only change what I explicitly modified"
- Avoids the complexity of tracking every formatting detail in the AST

### Why not use yq?
- `yq` is written in Go, doesn't integrate well with Python workflows
- `yq` doesn't support arbitrary string replacement within values
- We want programmatic Python access to the AST

## Related Resources

- ruamel.yaml docs: https://yaml.dev/doc/ruamel.yaml/
- ruamel.yaml source: https://sourceforge.net/p/ruamel-yaml/code/ (Mercurial)
- Original discussion in: `/Users/ryan/c/ruamel-yaml/` (cloned from SourceForge)

## Recent Improvements

1. **Refactored codebase** (latest): Split single 772-line file into focused modules
   - Created `byte_ops.py` for low-level operations
   - Created `path.py` for path parsing/navigation
   - Created `serialization.py` for YAML serialization
   - Created `modifications.py` for modification tracking
   - Simplified `document.py` (main YAYA class)
   - All tests still pass (21/21)

2. **Block scalar handling**: Fixed indentation preservation
3. **Nested structures**: Fixed tracking of mappings within sequences
4. **List indentation**: Smart detection and configuration
5. **Path operations**: Full support for dotted paths with array indices
6. **Key manipulation**: Can add, replace, and insert keys
