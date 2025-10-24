# Lossless YAML Test Plan for Workflow Transformations

This document describes the YAML transformations needed for the workspace migration, serving as test cases and requirements for extending lossless-yaml.

## Desired API

The ideal interface would allow:

1. **Dict-like traversal**: Navigate parsed YAML as if it were a nested dict
2. **Assertion methods**: Assert a key is absent, or matches a specific value/structure
3. **Replacement with dicts**: Replace values with dict-like objects that become YAML
4. **Format hints**: Optionally specify formatting (indent, style) or use sensible defaults inferred from context
5. **Atomic operations**: Each change should be traceable and reversible

### Example API Sketch

```python
doc = YAYA.load("workflow.yaml")

# Assert current value before replacing (raises if mismatch)
doc.assert_value("on", ["push"])

# Replace with dict (formatting inferred from surrounding YAML)
doc.replace_key("on", {
    "push": {
        "branches": ["main"],
        "paths": ["lib/levanter/**", "uv.lock"]
    },
    "pull_request": {
        "paths": ["lib/levanter/**", "uv.lock"]
    }
})

# Or more granular: add a key if absent
doc.assert_absent("jobs.test.defaults")
doc.add_key("jobs.test.defaults", {
    "run": {
        "working-directory": "lib/levanter"
    }
})

# Or conditional: only add if not present
doc.ensure_key("jobs.test.defaults.run.working-directory", "lib/levanter")

doc.save()
```

## Test Case 1: Expand Flow-Style `on:` Trigger

**Input YAML:**
```yaml
name: Run tests that use ray

on: [push]

jobs:
  ray_tests:
    runs-on: ubuntu-latest
```

**Transformation:**
- Assert `on` equals `["push"]` (or `["push", "pull_request"]`)
- Replace with expanded dict structure including path filters

**Expected Output:**
```yaml
name: Run tests that use ray

on:
  push:
    branches:
      - main
    paths:
      - 'lib/levanter/**'
      - 'uv.lock'
      - '.github/workflows/levanter-run_ray_tests.yaml'
  pull_request:
    paths:
      - 'lib/levanter/**'
      - 'uv.lock'
      - '.github/workflows/levanter-run_ray_tests.yaml'

jobs:
  ray_tests:
    runs-on: ubuntu-latest
```

**Key Requirements:**
- Preserve blank line between `on:` section and `jobs:`
- Use block style (not flow style) for replacement
- Infer proper indentation (2 spaces per level)
- Use quoted strings for paths (match common GHA convention)

## Test Case 2: Add `defaults` Section to Job

**Input YAML:**
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11"]
    steps:
      - uses: actions/checkout@v4
```

**Transformation:**
- Assert `jobs.test.defaults` is absent
- Add `defaults` section after `runs-on`, before `strategy`

**Expected Output:**
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: lib/levanter
    strategy:
      matrix:
        python-version: ["3.11"]
    steps:
      - uses: actions/checkout@v4
```

**Key Requirements:**
- Insert at specific position (after `runs-on`, before next sibling)
- Maintain indentation consistent with siblings (4 spaces for job-level keys)
- Nested values use additional indentation (6 spaces for `run:`, 8 spaces for `working-directory:`)

**Alternative positions to handle:**
```yaml
# Pattern 1: runs-on → strategy (shown above)
# Pattern 2: runs-on → env
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      VAR: value

# Pattern 3: runs-on → if
jobs:
  test:
    runs-on: ubuntu-latest
    if: github.event_name == 'push'

# Pattern 4: runs-on → steps
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
```

## Test Case 3: Add Key to Existing Dict (setup-uv `with:`)

**Input YAML:**
```yaml
steps:
  - name: Install uv and Python
    uses: astral-sh/setup-uv@v6
    with:
      version: "0.7.20"
      python-version: ${{ matrix.python-version }}
      enable-cache: true
  - name: Next step
```

**Transformation:**
- Navigate to the `setup-uv` step's `with:` dict
- Assert `working-directory` is absent (or add idempotently)
- Add `working-directory: lib/levanter` as last item in `with:`

**Expected Output:**
```yaml
steps:
  - name: Install uv and Python
    uses: astral-sh/setup-uv@v6
    with:
      version: "0.7.20"
      python-version: ${{ matrix.python-version }}
      enable-cache: true
      working-directory: lib/levanter
  - name: Next step
```

**Key Requirements:**
- Find specific step by matching action name pattern (`uses` contains `astral-sh/setup-uv`)
- Add key to existing dict at end (preserve order of existing keys)
- Match indentation of sibling keys (10 spaces)

## Test Case 4: Conditional Replacement Based on File Name

**Context:**
Only TPU workflows need SSH path updates. The transformation should be conditional on workflow filename.

**Input YAML (levanter-tpu_unit_tests.yaml):**
```yaml
jobs:
  test:
    steps:
      - name: Run most tests
        run: |
          export TPU_NAME=ci-run-${{ github.run_id }}
          gcloud compute tpus tpu-vm ssh $TPU_NAME --zone ${TPU_ZONE} --command "JAX_TRACEBACK_FILTERING=off PYTHONPATH=$PYTHONPATH:levanter/tests CI=1 bash levanter/infra/run.sh pytest levanter/tests -m 'not entry and not ray' --durations=20"
```

**Transformation:**
- Only apply if `"tpu" in workflow_path.name.lower()`
- Replace `levanter/tests` → `marin/lib/levanter/tests` in string values
- Replace `levanter/infra` → `marin/lib/levanter/infra` in string values

**Expected Output:**
```yaml
jobs:
  test:
    steps:
      - name: Run most tests
        run: |
          export TPU_NAME=ci-run-${{ github.run_id }}
          gcloud compute tpus tpu-vm ssh $TPU_NAME --zone ${TPU_ZONE} --command "JAX_TRACEBACK_FILTERING=off PYTHONPATH=$PYTHONPATH:marin/lib/levanter/tests CI=1 bash marin/lib/levanter/infra/run.sh pytest marin/lib/levanter/tests -m 'not entry and not ray' --durations=20"
```

**Key Requirements:**
- String value replacement (already supported by `replace_in_values`)
- Preserve block scalar style (`|`)
- This case is mainly for completeness; current API handles it

## Test Case 5: Update Command Strings (Regex Replacement in Values)

**Input YAML:**
```yaml
steps:
  - name: Install dependencies
    run: uv sync --dev
  - name: Run tests
    run: uv run pytest tests/
```

**Transformation:**
- Replace `uv sync` → `uv sync --package levanter` (but not if already has `--package`)
- Replace `uv run` → `uv run --package levanter` (but not if already has `--package`)

**Expected Output:**
```yaml
steps:
  - name: Install dependencies
    run: uv sync --package levanter --dev
  - name: Run tests
    run: uv run --package levanter pytest tests/
```

**Key Requirements:**
- Regex-based replacement within string values: `\buv sync(?! --package)` → `uv sync --package levanter`
- Skip if pattern already exists (idempotent)
- Preserve surrounding content in string

**Possible API:**
```python
doc.replace_in_values_regex(
    pattern=r'\buv sync(?! --package)',
    replacement=r'uv sync --package levanter'
)
```

## API Requirements Summary

### Navigation and Assertion

```python
# Dict-like access
value = doc["jobs"]["test"]["runs-on"]

# Path-based access
value = doc.get_path("jobs.test.runs-on")

# Assertions
doc.assert_value("on", ["push"])  # Raises if not equal
doc.assert_absent("jobs.test.defaults")  # Raises if present
doc.assert_present("jobs.test.steps")  # Raises if absent
doc.assert_matches("jobs.test.runs-on", lambda v: "ubuntu" in v)
```

### Replacement and Addition

```python
# Replace entire value (preserves formatting context)
doc.replace_key("on", {"push": {"branches": ["main"]}})

# Add key (raises if present, unless force=True)
doc.add_key("jobs.test.defaults", {"run": {"working-directory": "lib/levanter"}})

# Add key at specific position relative to sibling
doc.add_key_after("jobs.test.runs-on", "defaults", {"run": {"working-directory": "lib/levanter"}})
doc.add_key_before("jobs.test.strategy", "defaults", {...})

# Ensure key exists (idempotent, only adds if absent)
doc.ensure_key("jobs.test.defaults.run.working-directory", "lib/levanter")

# Find and modify (for list items like steps)
step = doc.find_first("jobs.test.steps", lambda s: "setup-uv" in s.get("uses", ""))
step.add_key("with.working-directory", "lib/levanter")
```

### String Replacement (Current API, Keep)

```python
# Simple string replacement in all values
doc.replace_in_values("levanter/tests", "marin/lib/levanter/tests")

# Regex replacement in all values (new)
doc.replace_in_values_regex(r'\buv sync(?! --package)', r'uv sync --package levanter')
```

### Formatting Control (Optional)

```python
# Explicit style hints
doc.add_key("on", {
    "push": {"branches": ["main"]},
    "pull_request": {"paths": ["lib/**"]}
}, style="block", indent=2, quote_strings=True)

# Or rely on context inference (preferred default)
doc.add_key("on", {...})  # Infers: block style, 2-space indent from siblings
```

## Implementation Notes

### Positioning New Keys

When adding a key to a dict, we need to specify where it goes:

1. **Default**: Add at end (append to existing keys)
2. **After specific key**: `add_key_after("existing_key", "new_key", value)`
3. **Before specific key**: `add_key_before("existing_key", "new_key", value)`
4. **At start**: `add_key_at_start("new_key", value)`

For our use case, we need `add_key_after("runs-on", "defaults", {...})` to insert `defaults` between `runs-on` and the next sibling (`strategy`, `env`, `if`, or `steps`).

### Format Inference

When adding new YAML structures, infer formatting from context:

1. **Indentation**: Use same indent level as sibling keys
2. **Quoting**: Look at nearby string values (e.g., if paths are quoted, quote new paths)
3. **Flow vs Block**: Generally prefer block style unless all siblings are flow style
4. **Blank lines**: Preserve blank line patterns (e.g., between top-level sections)

### Preserving Comments

Comments should be preserved when:
- Modifying nearby keys
- Inserting new keys
- Replacing values

ruamel.yaml's `CommentedMap` tracks comments, and lossless-yaml should maintain them through transformations.

## Testing Strategy

1. **Unit tests**: Each test case above should be a unit test
2. **Round-trip**: Load → modify → save → load should produce semantically identical YAML
3. **Byte comparison**: For simple changes, output should match manually-edited reference files
4. **Error cases**: Assert appropriate errors for conflicting assertions
5. **Idempotency**: Running transformations twice should produce same result as once

## Example Usage in Our Migration Script

```python
def update_levanter_workflow(workflow_path: Path) -> bool:
    doc = LosslessYAML.load(workflow_path)
    modified = False

    # 1. Update name
    if "name" in doc.data:
        old_name = doc.data["name"]
        if not old_name.startswith("Levanter - "):
            doc.replace_in_values(old_name, f"Levanter - {old_name}")
            modified = True

    # 2. Expand trigger with path filters
    if doc["on"] in (["push"], ["push", "pull_request"]):
        doc.replace_key("on", {
            "push": {
                "branches": ["main"],
                "paths": ["lib/levanter/**", "uv.lock", f".github/workflows/{workflow_path.name}"]
            },
            "pull_request": {
                "paths": ["lib/levanter/**", "uv.lock", f".github/workflows/{workflow_path.name}"]
            }
        })
        modified = True

    # 3. Add defaults.run.working-directory
    for job_name, job in doc["jobs"].items():
        if "defaults" not in job:
            # Insert after runs-on, before next key
            doc.add_key_after(
                f"jobs.{job_name}.runs-on",
                "defaults",
                {"run": {"working-directory": "lib/levanter"}}
            )
            modified = True

    # 4. Update setup-uv step
    for job_name, job in doc["jobs"].items():
        for i, step in enumerate(job.get("steps", [])):
            if "astral-sh/setup-uv" in step.get("uses", ""):
                if "with" in step and "working-directory" not in step["with"]:
                    doc.add_key(f"jobs.{job_name}.steps[{i}].with.working-directory", "lib/levanter")
                    modified = True

    # 5. Update uv commands
    doc.replace_in_values_regex(r'\buv sync(?! --package)', 'uv sync --package levanter')
    doc.replace_in_values_regex(r'\buv run(?! --package)', 'uv run --package levanter')

    # 6. Update TPU SSH paths
    if "tpu" in workflow_path.name.lower():
        doc.replace_in_values("levanter/tests", "marin/lib/levanter/tests")
        doc.replace_in_values("levanter/infra", "marin/lib/levanter/infra")

    if modified:
        doc.save()

    return modified
```

## Priority Order for Implementation

1. **High Priority** (needed for our immediate use case):
   - `replace_key(path, value)` - Replace entire value at path with dict/list
   - `add_key_after(existing_path, new_key, value)` - Insert key after another
   - `assert_value(path, expected)` - Assert current value matches
   - `replace_in_values_regex(pattern, replacement)` - Regex replacement in strings

2. **Medium Priority** (nice to have, improves API):
   - `add_key(path, value, force=False)` - Add key (optionally overwrite)
   - `ensure_key(path, value)` - Idempotent add
   - `find_first(path, predicate)` - Find list item matching condition

3. **Low Priority** (can be added later):
   - Explicit formatting hints
   - `add_key_before()`, `add_key_at_start()`
   - Fine-grained comment manipulation

## Questions for LosslessYAML Design

1. Should `replace_key` preserve comments attached to the old value?
2. When adding keys, should blank lines be inferred or explicit?
3. Should path syntax support `jobs.test.steps[0].uses` or require a different API for list indices?
4. Error handling: raise on conflicts, or provide `force=True` flags?
5. Should there be a "dry run" mode that reports what would change without modifying?
