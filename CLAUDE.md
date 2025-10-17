# lossless-yaml Development Context

## Project Overview

**lossless-yaml** is a Python library for byte-for-byte preserving YAML editing. Unlike ruamel.yaml's round-trip mode (which preserves most formatting but makes small changes), this library guarantees that only the values you explicitly modify will change.

## Key Innovation

Instead of parse → modify → serialize, we:
1. Parse YAML with ruamel.yaml to get AST + position info (`lc.data` contains line/col for every value)
2. Convert line/col to byte offsets in the original file
3. Track modifications as you change values
4. Apply byte-level replacements when saving, leaving everything else untouched

## Architecture

```
src/lossless_yaml/
├── __init__.py          # Package exports
└── core.py              # Main implementation
    ├── line_col_to_index()           # Convert (line, col) → byte offset
    ├── find_scalar_value_range()     # Find byte range of a scalar value
    └── LosslessYAML                   # Main class
        ├── .load(file_path)          # Load YAML file
        ├── .replace_in_values(old, new)  # Bulk string replacement
        └── .save(file_path=None)     # Save with modifications
```

## Current Status

### Working (4/6 tests passing)
- ✅ Simple string replacements in plain scalars
- ✅ Comment preservation
- ✅ Whitespace preservation
- ✅ No-op when pattern doesn't match
- ✅ Basic example works perfectly

### Failing (2/6 tests)
1. **Block scalars** (`test_block_scalar`)
   - Modifications to block scalar content aren't being applied
   - Issue: Block scalar indentation preservation in `_format_replacement()` may be incorrect
   - The function exists but may not be working as expected

2. **Nested structures** (`test_nested_structures`)
   - Values in nested mappings within sequences aren't being replaced
   - Example: `list: [{item1: old_value}]` - the `old_value` doesn't get replaced
   - Issue: Sequence items that are mappings aren't being tracked properly

## Known Issues & TODOs

### High Priority
- [ ] Fix block scalar replacement (test_block_scalar)
- [ ] Fix nested structure tracking (test_nested_structures)
  - Specifically: mappings that are items in sequences
  - Need to ensure `_record_modification` handles this case

### Medium Priority
- [ ] Add yq-style path selectors (`.jobs.test.steps[*].run`)
- [ ] Add direct dict-like access with `__setitem__` tracking
- [ ] Better error messages when modifications fail
- [ ] Handle edge cases: flow-style collections, anchors/aliases, multi-document streams

### Future Enhancements
- [ ] Regex-based replacement
- [ ] Callback-based value transformation
- [ ] Preserving anchors and aliases through modifications
- [ ] Support for adding/removing keys (currently only value replacement)

## Key Files to Review

1. **`src/lossless_yaml/core.py`**: Main implementation
   - `_record_modification()`: Records byte positions for changed values
   - `_format_replacement()`: Formats replacement values (handles block scalar indent)
   - `replace_in_values()`: Recursively replaces strings in the AST

2. **`tests/test_basic.py`**: Test suite
   - Look at `test_block_scalar` and `test_nested_structures` for failing cases
   - These tests show exactly what needs to be fixed

3. **`examples/github_actions.py`**: Real-world use case
   - Shows the intended usage for updating paths in workflows

## Debugging Tips

### To debug modifications not being applied:
```python
doc = LosslessYAML.load('test.yaml')
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

## Questions to Explore

1. Why aren't block scalar modifications being recorded?
   - Check if `find_scalar_value_range()` is returning correct offsets for block scalars
   - Debug print the byte ranges being stored in `modifications`

2. Why aren't sequence items (that are mappings) being tracked?
   - Check `replace_in_values()` recursion logic
   - Verify `_record_modification()` handles this case
   - Look at `lc.data` structure for sequence items

3. Should we preserve block scalar chomping indicators?
   - Currently we replace content but might change `|` to `|-`
   - Need to preserve the original indicator

## Git History

- **Initial commit (3befb06)**: Working implementation with 4/6 tests passing
  - All core infrastructure in place
  - Known issues documented
  - Ready for iteration
