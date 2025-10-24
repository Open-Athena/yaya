# API Proposal: Ordered Key Insertions

## Motivation

When transforming YAML files, we often need to insert keys at specific positions while maintaining a particular order. The current `add_key_after` API is useful but doesn't verify the structure, which can lead to bugs or incorrect insertions.

## Use Cases

1. **Insert between two adjacent keys** - Add a key between two existing keys, verifying they're adjacent
2. **Add as first key** - Prepend a key, optionally verifying what was previously first
3. **Add as last key** - Append a key, optionally verifying what was previously last

## Proposed APIs

### 1. `insert_key_between(path, prev_key, next_key, new_key, value)`

Insert a new key between two adjacent keys, verifying they're actually adjacent.

**Parameters**:
- `path` (str): Path to the parent dict (e.g., `"jobs.build-package"`)
- `prev_key` (str): Key that should come immediately before the new key
- `next_key` (str): Key that should come immediately after the new key
- `new_key` (str): Name of the key to insert
- `value`: Value for the new key

**Behavior**:
- Verify that `prev_key` and `next_key` exist in the dict at `path`
- Verify that `prev_key` immediately precedes `next_key` (no keys between them)
- Insert `new_key` between them
- Raise `KeyError` if keys don't exist
- Raise `ValueError` if keys aren't adjacent

**Example**:
```python
# YAML:
# jobs:
#   build:
#     runs-on: ubuntu-latest
#     if: ${{ condition }}
#     steps: [...]

doc.insert_key_between(
    "jobs.build",
    prev_key="if",
    next_key="steps",
    new_key="defaults",
    value={"run": {"working-directory": "lib/levanter"}}
)

# Result:
# jobs:
#   build:
#     runs-on: ubuntu-latest
#     if: ${{ condition }}
#     defaults:
#       run:
#         working-directory: lib/levanter
#     steps: [...]
```

---

### 2. `add_before_first(path, new_key, value, verify_first=None)`

Add a key as the first key in a dict, optionally verifying what was previously first.

**Parameters**:
- `path` (str): Path to the parent dict
- `new_key` (str): Name of the key to add
- `value`: Value for the new key
- `verify_first` (str, optional): If provided, verify this was the first key before adding

**Behavior**:
- If `verify_first` is provided:
  - Verify it's currently the first key in the dict
  - Raise `ValueError` if it's not first
- Insert `new_key` as the new first key

**Example**:
```python
# YAML:
# jobs:
#   build:
#     runs-on: ubuntu-latest
#     steps: [...]

doc.add_before_first(
    "jobs.build",
    new_key="name",
    value="Build Package",
    verify_first="runs-on"  # Optional verification
)

# Result:
# jobs:
#   build:
#     name: Build Package
#     runs-on: ubuntu-latest
#     steps: [...]
```

**Without verification**:
```python
# Just prepend without checking current structure
doc.add_before_first(
    "jobs.build",
    new_key="name",
    value="Build Package"
)
```

---

### 3. `add_after_last(path, new_key, value, verify_last=None)`

Add a key as the last key in a dict, optionally verifying what was previously last.

**Parameters**:
- `path` (str): Path to the parent dict
- `new_key` (str): Name of the key to add
- `value`: Value for the new key
- `verify_last` (str, optional): If provided, verify this was the last key before adding

**Behavior**:
- If `verify_last` is provided:
  - Verify it's currently the last key in the dict
  - Raise `ValueError` if it's not last
- Insert `new_key` as the new last key

**Example**:
```python
# YAML:
# jobs:
#   build:
#     runs-on: ubuntu-latest
#     steps: [...]

doc.add_after_last(
    "jobs.build",
    new_key="timeout-minutes",
    value=30,
    verify_last="steps"  # Optional verification
)

# Result:
# jobs:
#   build:
#     runs-on: ubuntu-latest
#     steps: [...]
#     timeout-minutes: 30
```

---

## Implementation Notes

### Key Ordering in YAML

These APIs require tracking key order in YAML dicts. With `ruamel.yaml`, this is available through:
- `CommentedMap` preserves insertion order (like Python dicts since 3.7+)
- Keys can be iterated in order using `.keys()`, `.items()`, etc.

### Verification Logic

For `insert_key_between`:
```python
def insert_key_between(self, path, prev_key, next_key, new_key, value):
    parent = self.get_path(path)
    if not isinstance(parent, dict):
        raise ValueError(f"Path {path} is not a dict")

    keys = list(parent.keys())

    if prev_key not in keys:
        raise KeyError(f"Previous key '{prev_key}' not found in {path}")
    if next_key not in keys:
        raise KeyError(f"Next key '{next_key}' not found in {path}")

    prev_idx = keys.index(prev_key)
    next_idx = keys.index(next_key)

    if next_idx != prev_idx + 1:
        raise ValueError(
            f"Keys '{prev_key}' and '{next_key}' are not adjacent. "
            f"Found {next_idx - prev_idx - 1} keys between them."
        )

    # Insert the new key between them
    # This requires reconstructing the dict with the new key in the right position
    # while preserving ruamel.yaml's CommentedMap structure
    ...
```

### Alternative: `insert_between` (without `_key_`)

Could simplify the name to `insert_between` since the context (inserting a key) is implicit:

```python
doc.insert_between("jobs.build", "if", "steps", "defaults", {...})
```

Similarly: `add_first`, `add_last` instead of `add_before_first`, `add_after_last`.

---

## Benefits

1. **Type safety**: Verify structure before modifying
2. **Better error messages**: Know exactly why an insertion failed
3. **Idempotency**: Can check current state before deciding to insert
4. **Clearer intent**: Code explicitly states where keys should be inserted relative to others

## Use in workspace-migration

These APIs would simplify the workflow transformation code:

**Current code** (with workaround):
```python
# Try to add after 'if' if it exists, otherwise after 'runs-on'
after_key = None
try:
    doc.get_path(f"jobs.{job_name}.if")
    after_key = "if"
except KeyError:
    after_key = "runs-on"

try:
    doc.add_key_after(
        f"jobs.{job_name}.{after_key}",
        "defaults",
        {"run": {"working-directory": "lib/levanter"}}
    )
except KeyError:
    raise WorkflowConflict(f"Job {job_name} has no runs-on key")
```

**With new APIs**:
```python
# Try to insert between 'if' and 'steps', or just add after 'runs-on'
try:
    doc.insert_between(
        f"jobs.{job_name}",
        "if", "steps",
        "defaults",
        {"run": {"working-directory": "lib/levanter"}}
    )
except (KeyError, ValueError):
    # No 'if', or not adjacent - fall back to adding after 'runs-on'
    doc.add_key_after(
        f"jobs.{job_name}.runs-on",
        "defaults",
        {"run": {"working-directory": "lib/levanter"}}
    )
```

Or even simpler with optional verification:
```python
# Add as last key, but verify 'steps' is currently last (semantic check)
doc.add_before_first(
    f"jobs.{job_name}",
    "defaults",
    {"run": {"working-directory": "lib/levanter"}},
    verify_first="runs-on"  # Ensure we're working with expected structure
)
```
