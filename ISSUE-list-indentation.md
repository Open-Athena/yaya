# List Indentation Issue

When adding new list values to a YAML document, lossless-yaml should infer the indentation style from existing lists in the document.

## Current Behavior

When adding new list items, they are aligned with the parent key instead of being indented by 2 spaces (the common GitHub Actions convention).

## Example

Given this existing structure in a GitHub Actions workflow:

```yaml
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
      - name: Install uv and Python
        uses: astral-sh/setup-uv@v6
```

When adding a new `on:` trigger structure, the current code produces:

```yaml
on:
  push:
    branches:
    - main
    paths:
    - lib/levanter/**
```

## Expected Behavior

It should infer the 2-space indentation pattern from the existing `steps:` list and produce:

```yaml
on:
  push:
    branches:
      - main
    paths:
      - lib/levanter/**
```

## Code Location

The issue is in the serialization logic when creating new list structures. The code should:

1. Scan the document for existing list items
2. Detect the most common indentation pattern (e.g., 2 spaces before `-`)
3. Apply that pattern when serializing new list items

## Test Case

```python
import lossless_yaml as ly

# Document with existing 2-space list indentation
yaml_content = """
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
      - name: Test
        run: echo "test"
"""

doc = ly.load(yaml_content)

# Add a new on: trigger with lists
doc['on'] = {
    'push': {
        'branches': ['main'],
        'paths': ['lib/**']
    }
}

result = ly.dump(doc)

# Expected: branches and paths should be indented with 2 spaces before `-`
# Current: branches and paths align with parent key (0 spaces before `-`)
```

## Priority

High - This affects readability and consistency of generated GitHub Actions workflows.

## Workaround

Manually edit the generated YAML files to adjust indentation, or use string replacement after serialization.
