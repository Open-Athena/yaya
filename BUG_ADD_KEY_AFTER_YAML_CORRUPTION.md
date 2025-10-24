# Bug: add_key_after corrupts YAML with jinja2 expressions

## Summary

When using `add_key_after` to insert a key after a field containing a GitHub Actions jinja2 expression (`${{ ... }}`), the YAML gets corrupted - the jinja2 expression gets split and part of it concatenated onto the newly added key's value.

## Reproduction

**Input YAML** (`levanter-publish_dev.yaml`):
```yaml
jobs:
  build-package:
    runs-on: ubuntu-latest
    if: ${{  github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success'}}
    steps:
      - name: Checkout code
```

**Code**:
```python
from yaya import YAYA

doc = YAYA.load("levanter-publish_dev.yaml")

# Try to add defaults after the 'if' key
doc.add_key_after(
    "jobs.build-package.if",
    "defaults",
    {"run": {"working-directory": "lib/levanter"}}
)

doc.save()
```

**Expected output**:
```yaml
jobs:
  build-package:
    runs-on: ubuntu-latest
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success'}}
    defaults:
      run:
        working-directory: lib/levanter
    steps:
      - name: Checkout code
```

**Actual output** (BUG):
```yaml
jobs:
  build-package:
    runs-on: ubuntu-latest
    if: $
    defaults:
      run:
        working-directory: lib/levanter{{  github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success'}}
    steps:
      - name: Checkout code
```

## Analysis

The jinja2 expression `${{  github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success'}}` got split:
- The `if:` key kept only `$`
- The rest (`{{  github.event_name == ... }}`) got concatenated onto the `working-directory` value

This suggests that:
1. The jinja2 expression is being parsed/tokenized incorrectly
2. String concatenation is happening when it shouldn't
3. YAML anchors/aliases or some other mechanism is incorrectly merging values

## Workaround

Manually correct the YAML after `add_key_after`:
```python
doc.add_key_after(...)
# Manually fix the corrupted YAML
doc.replace_key("jobs.build-package.if", "${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success'}}")
doc.replace_key("jobs.build-package.defaults.run.working-directory", "lib/levanter")
doc.save()
```

## Investigation needed

1. Check if ruamel.yaml has special handling for `${{` sequences
2. Verify if this is specific to GitHub Actions syntax or affects all jinja2-like expressions
3. Test with simpler cases:
   - `if: ${{ true }}`
   - `if: ${{ a || b }}`
   - `if: some-plain-value`

## Related

This bug was discovered during workspace migration step 2, in the `update_workflows.py` script when trying to add `defaults.run.working-directory` to Levanter workflow jobs.

See: `/Users/ryan/c/oa/marin/workspace-migration/step2/STEP2_ISSUES.md`
