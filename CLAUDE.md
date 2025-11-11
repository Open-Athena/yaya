# yaya Development Context

## Project Overview

**yaya** (Yet Another YAML AST transformer) is a Python library for byte-for-byte preserving YAML editing. Unlike ruamel.yaml's round-trip mode (which preserves most formatting but makes small changes), this library guarantees that only the values you explicitly modify will change.

## Key Innovation

We use a clean AST architecture for truly lossless editing:
1. Parse YAML with ruamel.yaml to get AST + position info
2. Extract all formatting metadata (quotes, indentation, styles, blank lines) from original bytes
3. Convert ruamel's CommentedMap/CommentedSeq to a clean, immutable AST
4. Track modifications in the clean AST as you make changes
5. Re-serialize the entire document, preserving all formatting for unchanged sections

This guarantees byte-for-byte preservation while supporting arbitrary modifications.

## Architecture

```
src/yaya/
├── __init__.py          # Package exports
├── document.py          # YAYA class (main interface)
├── converter.py         # Convert ruamel AST → clean AST
├── emitter.py           # Serialize clean AST → bytes
├── nodes.py             # Clean AST node types (Scalar, Mapping, Sequence, etc.)
├── extract.py           # Extract formatting from original bytes
├── serialization.py     # ruamel.yaml wrapper for programmatic nodes
├── path.py              # Path parsing and navigation
├── formatting.py        # Style hints for programmatic nodes
└── jinja2_helpers.py    # Detect/preserve Jinja2 expressions
```

Key components:
- **nodes.py**: Immutable AST nodes (Document, Mapping, Sequence, Scalar, Comment, BlankLines, etc.)
- **converter.py**: `convert_to_clean_ast()` - Extract formatting and build clean AST
- **emitter.py**: `serialize()` - Render clean AST to bytes with full formatting preservation
- **extract.py**: Extract quotes, indentation, styles, offsets from original bytes
- **YAYA class**: Main interface with dict-like access, path navigation, modifications

## Current Status

### ✅ All Tests Passing (95/95)
- ✅ String replacements (literal and regex)
- ✅ Comment preservation (inline and standalone)
- ✅ Whitespace preservation (including trailing spaces)
- ✅ Blank line preservation (including within dicts)
- ✅ Quote style preservation (single, double, unquoted)
- ✅ Block scalar handling with indicator preservation
- ✅ Flow vs block style control
- ✅ List indentation detection (aligned vs indented)
- ✅ Path navigation and assertions
- ✅ Key addition, replacement, deletion with order control
- ✅ Jinja2 expression preservation
- ✅ Idempotency
- ✅ Real-world workflow transformations

## Known Issues & TODOs

### Medium Priority
- [ ] Add yq-style path selectors with wildcards (`.jobs.test.steps[*].run`)
- [ ] Better error messages when modifications fail
- [ ] Explicit testing for anchors/aliases, multi-document streams

### Future Enhancements
- [ ] Callback-based value transformation
- [ ] More flexible key insertion (not just `add_key_after`, `insert_key_between`)
- [ ] Preserve and manipulate standalone comments (not attached to keys)

## Key Files to Review

1. **`src/yaya/document.py`**: Main YAYA class (user-facing API)
   - `replace_in_values()`, `replace_in_values_regex()`: String replacements
   - `add_key()`, `replace_key()`, `add_key_after()`, `insert_key_between()`, `delete_key()`: Key manipulation
   - `get_path()`, `assert_value()`, `assert_present()`, `assert_absent()`: Navigation and assertions
   - `ensure_key()`: Idempotent key addition
   - `set_list_indent_style()`: Control list indentation

2. **`src/yaya/converter.py`**: Convert ruamel AST to clean AST
   - `convert_to_clean_ast()`: Main entry point
   - `_convert_mapping()`: Extract formatting from mappings (includes blank line preservation)
   - `_convert_sequence()`: Extract formatting from sequences
   - `_convert_scalar()`: Extract quotes and values from scalars

3. **`src/yaya/emitter.py`**: Serialize clean AST to bytes
   - `serialize()`: Main entry point
   - `_emit_mapping()`, `_emit_sequence()`, `_emit_scalar()`: Per-node renderers
   - Preserves all formatting metadata during rendering

4. **`src/yaya/nodes.py`**: Clean AST node definitions
   - `Document`, `Mapping`, `Sequence`, `Scalar`: Core structure
   - `Comment`, `BlankLines`, `InlineCommented`: Formatting metadata
   - `KeyValue`: Mapping key-value pairs
   - All nodes are immutable (NamedTuple)

5. **`src/yaya/extract.py`**: Extract formatting from original bytes
   - `extract_quote_style()`: Detect single/double/plain quotes
   - `extract_indentation()`: Find indentation at line
   - `extract_mapping_style()`, `extract_sequence_style()`: Flow vs block
   - `extract_sequence_offset()`: List dash offset

6. **`src/yaya/path.py`**: Path parsing and navigation
   - `parse_path()`: Parse dotted paths with array indices
   - `navigate_to_path()`: Navigate in ruamel AST

7. **`tests/`**: Comprehensive test suite (95 tests)
   - `test_basic.py`: Core functionality
   - `test_blank_lines.py`: Blank line preservation (NEW in 0.3.0)
   - `test_quote_preservation.py`: Quote style handling
   - `test_list_indentation.py`: List indent detection
   - `test_style_hints.py`: Flow vs block style control
   - `test_workflow_transforms.py`: Real-world transformations
   - `test_jinja2_expressions.py`: Jinja2 preservation
   - Plus many more specialized tests

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
