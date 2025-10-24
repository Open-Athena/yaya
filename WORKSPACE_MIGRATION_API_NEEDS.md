# yaya API Needs for Workspace Migration

This document describes API additions needed for the Marin/Levanter workspace migration scripts, based on bugs discovered during implementation.

## Context

The workspace migration uses yaya to transform GitHub Actions workflow files from standalone repos to monorepo structure. During testing, we discovered limitations in the current API that cause bugs.

## Current Issues

### Issue 1: `replace_in_values` is Too Broad

**Problem**: `replace_in_values(old, new)` replaces ALL occurrences of a string throughout the entire YAML file, not just in a specific field.

**Example Bug**:
```python
# We want to add "Levanter - " prefix to workflow name only
doc.replace_in_values("GPT-2 Small Integration Test", "Levanter - GPT-2 Small Integration Test")
```

**Input**:
```yaml
name: GPT-2 Small Integration Test
jobs:
  test:
    steps:
      - name: Run GPT-2 Small Integration Test
```

**Actual output** (BUG - step name also changed):
```yaml
name: Levanter - GPT-2 Small Integration Test
jobs:
  test:
    steps:
      - name: Run Levanter - GPT-2 Small Integration Test  # ← Unintended!
```

**Expected output**:
```yaml
name: Levanter - GPT-2 Small Integration Test
jobs:
  test:
    steps:
      - name: Run GPT-2 Small Integration Test  # ← Should be unchanged
```

**Current workaround**: None that's reliable. We could check if the string appears multiple times and handle specially, but that's fragile.

### Issue 2: Direct Dict Mutation Doesn't Work

**Problem**: Adding keys to nested dicts via direct assignment doesn't integrate with yaya's modification tracking, so changes aren't persisted.

**Example Bug**:
```python
# Try to add working-directory to setup-uv step
for i, step in enumerate(job.get("steps", [])):
    if "astral-sh/setup-uv" in step.get("uses", ""):
        step["with"]["working-directory"] = "lib/levanter"  # Direct mutation
        modified = True

if modified:
    doc.save()  # ← Change is NOT saved!
```

**Input**:
```yaml
steps:
  - uses: astral-sh/setup-uv@v6
    with:
      version: "0.7.20"
      enable-cache: true
```

**Actual output** (BUG - no change):
```yaml
steps:
  - uses: astral-sh/setup-uv@v6
    with:
      version: "0.7.20"
      enable-cache: true
```

**Expected output**:
```yaml
steps:
  - uses: astral-sh/setup-uv@v6
    with:
      version: "0.7.20"
      enable-cache: true
      working-directory: lib/levanter
```

**Current workaround**: None. The script has a TODO comment acknowledging this limitation.

## Needed API Additions

### 1. `set_scalar_value(path, value)` - Set Specific Field Only

Replace a single scalar value at a specific path, without affecting other occurrences of the same string elsewhere in the file.

**Signature**:
```python
def set_scalar_value(self, path: str, value: str | int | bool | float) -> None:
    """
    Set a scalar value at a specific path.

    Unlike replace_in_values, this only affects the value at the given path,
    not all occurrences of that string in the file.

    Args:
        path: Dotted path to the scalar (e.g., "name", "jobs.test.runs-on")
        value: New scalar value

    Examples:
        >>> doc.set_scalar_value("name", "Levanter - GPT-2 Test")
        >>> doc.set_scalar_value("jobs.test.runs-on", "ubuntu-22.04")
    """
```

**Use case**:
```python
# Add "Levanter - " prefix to workflow name ONLY
old_name = doc.data["name"]
new_name = f"Levanter - {old_name}"
doc.set_scalar_value("name", new_name)  # Only changes top-level name field
```

**Alternative API designs**:

Option A - Extend `replace_key` to handle scalars better:
```python
doc.replace_key("name", new_name)  # Already works, but could be more explicit
```

Option B - Add `update_scalar` method:
```python
doc.update_scalar("name", lambda old: f"Levanter - {old}")
```

**Recommendation**: Option A (ensure `replace_key` handles scalars properly) is simplest since that API already exists.

### 2. `add_key_to_dict(path, key, value)` - Add Key to Existing Dict

Add a key to an existing dict at a specific path, properly integrated with modification tracking.

**Signature**:
```python
def add_key_to_dict(self, dict_path: str, key: str, value: Any, position: Literal['end', 'start'] = 'end') -> None:
    """
    Add a key to an existing dictionary.

    Args:
        dict_path: Path to the dictionary (e.g., "jobs.test.steps[0].with")
        key: New key name
        value: Value for the key (scalar, dict, or list)
        position: Where to add ('end' or 'start', default 'end')

    Raises:
        KeyError: If dict_path doesn't exist or key already exists
        TypeError: If path doesn't point to a dict

    Examples:
        >>> # Add to existing dict
        >>> doc.add_key_to_dict("jobs.test.steps[0].with", "working-directory", "lib/levanter")

        >>> # Add nested structure
        >>> doc.add_key_to_dict("jobs.test", "env", {"PYTHONPATH": "src"})
    """
```

**Use case**:
```python
# Add working-directory to setup-uv step's with: dict
for job_name, job in doc["jobs"].items():
    for i, step in enumerate(job.get("steps", [])):
        if "astral-sh/setup-uv" in step.get("uses", ""):
            path = f"jobs.{job_name}.steps[{i}].with"
            doc.add_key_to_dict(path, "working-directory", "lib/levanter")
```

**Alternative API designs**:

Option A - Use full path to new key:
```python
doc.add_key("jobs.test.steps[0].with.working-directory", "lib/levanter")
# ^ This currently fails or doesn't work properly for nested dicts
```

Option B - Add method to modify specific paths:
```python
doc.ensure_key("jobs.test.steps[0].with.working-directory", "lib/levanter")
# Idempotent - only adds if absent
```

**Recommendation**: Option B (`ensure_key`) is most useful since it's idempotent and handles the common case where we don't know if the key already exists.

### 3. `ensure_key(path, value)` - Idempotent Key Addition

Add a key if it doesn't exist, or optionally verify it matches expected value if it does exist.

**Signature**:
```python
def ensure_key(self, path: str, value: Any, verify_if_exists: bool = False) -> bool:
    """
    Ensure a key exists with a specific value.

    Idempotent - safe to call multiple times. If the key exists and verify_if_exists=True,
    checks that it matches the expected value.

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

        >>> # Add if missing, verify if exists
        >>> doc.ensure_key("jobs.test.runs-on", "ubuntu-latest", verify_if_exists=True)
    """
```

**Use case**:
```python
# Ensure working-directory exists in setup-uv, safe to run multiple times
for job_name, job in doc["jobs"].items():
    for i, step in enumerate(job.get("steps", [])):
        if "astral-sh/setup-uv" in step.get("uses", ""):
            doc.ensure_key(
                f"jobs.{job_name}.steps[{i}].with.working-directory",
                "lib/levanter"
            )
```

## Implementation Notes

### For `set_scalar_value` / Better `replace_key`

The key insight is that we want to modify only the value at a specific path, not search-and-replace everywhere. This is conceptually what `replace_key` should do (and may already do?), but we were using `replace_in_values` incorrectly.

**Proposed fix in migration script**:
```python
# WRONG (current code):
doc.replace_in_values(old_name, new_name)

# RIGHT:
doc.replace_key("name", new_name)
# OR:
doc.data["name"] = new_name
doc.save()
```

**Question**: Does `replace_key` already handle this correctly? If yes, we just need to fix our usage. If no, we need to fix yaya.

### For `ensure_key` / `add_key_to_dict`

The current `add_key` and `add_key_after` APIs work for adding new top-level or job-level keys, but struggle with:
1. Adding keys to existing nested dicts (like `with:` in a step)
2. Idempotent operations (add if missing, skip if present)

The path parsing and navigation already works (per `get_path`), so this is mainly about:
1. Supporting full paths that include the new key name (not just the parent)
2. Making the modification tracking work with nested additions
3. Providing an idempotent interface

### Direct Mutation Issue

Looking at the document.py code, direct mutations like `step["with"]["working-directory"] = "lib/levanter"` modify the `CommentedMap` in memory but don't call any yaya tracking methods. The `_tracker` only knows about modifications made through yaya APIs.

Possible solutions:
1. Add the new `ensure_key` API that properly tracks modifications
2. Override `__setitem__` on the data structure to auto-track (complex, may have side effects)
3. Document that direct mutations don't work and require using yaya APIs (current state)

**Recommendation**: Solution 1 (add proper APIs) is cleanest.

## API Audit: `replace_in_values` Usage

Current usage in `workspace-migration/step2/update_workflows.py`:

### Line 65, 88: Workflow name prefix (PROBLEMATIC)
```python
doc.replace_in_values(old_name, new_name)
```
**Issue**: Too broad, affects step names and other strings.
**Fix**: Use `doc.replace_key("name", new_name)` instead.

### Line 268-269: uv command updates (OK)
```python
doc.replace_in_values_regex(r'\buv sync(?! --package)', 'uv sync --package levanter')
doc.replace_in_values_regex(r'\buv run(?! --package)', 'uv run --package levanter')
```
**Issue**: None - this legitimately wants to update all `run:` command strings.
**Fix**: None needed.

### Line 283-284: TPU SSH paths (OK)
```python
doc.replace_in_values("levanter/tests", "marin/lib/levanter/tests")
doc.replace_in_values("levanter/infra", "marin/lib/levanter/infra")
```
**Issue**: None - these path strings should be updated everywhere they appear.
**Fix**: None needed.

## Recommended Changes

### High Priority (Blocks Migration)

1. **Fix workflow name updates**: Change lines 65, 88 in update_workflows.py to use `replace_key` instead of `replace_in_values`
2. **Add `ensure_key` API** to yaya: Enables idempotent nested key additions with proper tracking

### Medium Priority (Nice to Have)

3. **Document `replace_in_values` semantics**: Clearly state in docs that it affects ALL occurrences, and when to use `replace_key` instead
4. **Add `set_scalar_value` alias**: If it makes the API clearer (though `replace_key` may be sufficient)

### Low Priority

5. **Add `update_scalar` with transform function**: For programmatic transformations like `lambda old: f"Prefix - {old}"`

## Test Cases

### Test 1: Targeted Scalar Replacement
```python
doc = YAYA.load_string("""
name: GPT-2 Small Integration Test
jobs:
  test:
    steps:
      - name: Run GPT-2 Small Integration Test
""")

doc.replace_key("name", "Levanter - GPT-2 Small Integration Test")
doc.save()

# Expected: Only workflow name changes, step name unchanged
```

### Test 2: Nested Dict Key Addition
```python
doc = YAYA.load_string("""
steps:
  - uses: astral-sh/setup-uv@v6
    with:
      version: "0.7.20"
      enable-cache: true
""")

doc.ensure_key("steps[0].with.working-directory", "lib/levanter")
doc.save()

# Expected: working-directory added to with:
```

### Test 3: Idempotent Addition
```python
doc = YAYA.load_string("""
jobs:
  test:
    runs-on: ubuntu-latest
""")

# First call - adds the key
added = doc.ensure_key("jobs.test.runs-on", "ubuntu-latest")
assert added == False  # Already exists

# Second call - no-op
added = doc.ensure_key("jobs.test.runs-on", "ubuntu-latest")
assert added == False

doc.save()
# Expected: No changes (idempotent)
```

## Summary

**Critical APIs needed**:
1. `ensure_key(path, value)` - Idempotent nested key addition
2. Better documentation/examples for when to use `replace_key` vs `replace_in_values`

**Migration script fixes**:
1. Replace `doc.replace_in_values(old_name, new_name)` with `doc.replace_key("name", new_name)` (lines 65, 88)
2. Replace direct mutations like `step["with"]["key"] = value` with `doc.ensure_key(path, value)`

**Impact**: Fixes both discovered bugs (unintended step name changes, lost working-directory additions).
