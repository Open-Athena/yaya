# yaya

Yet Another YAML AST - programmatically transform YAML, preserving whitespace and comments

[![lossless-yaml](https://img.shields.io/pypi/v/lossless-yaml?label=lossless-yaml)](https://pypi.org/project/lossless-yaml/)

## Why?

Programmatically edit YAML at the AST level, so re-serializing doesn't introduce extraneous changes. Preserves:

- Comments
- Whitespace (including trailing spaces)
- Quote styles (`'`, `"`, or none)
  - By default, will switch between `'` and `"` if the other is added to a string (as a literal character) 
- Block scalar indicators (`|`, `|-`, `|+`)
- Other formatting choices (e.g. indentation)

Other libraries (e.g. [ruamel.yaml]) make formatting changes when serializing. `yaya` avoids this by:

1. Parsing YAML to get the AST (with position information)
2. Applying modifications only to specific values or subtrees
3. Leaving everything else untouched

It also tries to mimic neighboring formatting, when adding values/trees, while also supporting `dict`-like ergonomics and path-based navigation.

## Installation

```bash
pip install lossless-yaml
```

## Usage

### Basic String Replacement

```python
from yaya import YAYA

# Load a YAML file
doc = YAYA.load('.github/workflows/test.yaml')

# Simple string replacement in all values
doc.replace_in_values('src/marin', 'lib/marin/src/marin')

# Regex-based replacement
doc.replace_in_values_regex(r'\buv sync(?! --package)', 'uv sync --package myapp')

doc.save()
```

### Path-Based Navigation and Assertions

```python
# Navigate using paths
runs_on = doc.get_path("jobs.test.runs-on")
step_name = doc.get_path("jobs.test.steps[0].name")

# Or dict-like access
runs_on = doc["jobs"]["test"]["runs-on"]

# Assert values before making changes
doc.assert_value("on", ["push"])
doc.assert_absent("jobs.test.defaults")
doc.assert_present("jobs.test.steps")
```

### Replacing Values or Subtrees

```python
# Replace a simple value
doc.replace_key("jobs.test.runs-on", "ubuntu-22.04")

# Replace a list item
doc.replace_key("build.commands[1]", "uv sync --package marin --frozen")

# Replace with a complex structure
doc.replace_key("on", {
    "push": {
        "branches": ["main"],
        "paths": ["lib/**", "uv.lock"]
    },
    "pull_request": {
        "paths": ["lib/**", "uv.lock"]
    }
})

doc.save()
```

### Adding Keys

```python
# Add key after another (maintains order)
doc.add_key_after("jobs.test.runs-on", "defaults", {
    "run": {
        "working-directory": "lib/myapp"
    }
})

# Add or replace (convenience method)
doc.ensure_key("jobs.test.timeout-minutes", 30)

doc.save()
```

### Deleting Keys

```python
# Delete a key
doc.delete_key("build.mkdocs")  # Returns True if deleted, False if not found

# Delete nested key
doc.delete_key("jobs.test.defaults.run.shell")

# Delete multiple keys
doc.delete_key("build.python")
doc.delete_key("build.obsolete")

doc.save()
```

## Example

Given this YAML file:

```yaml
# Production config
database:
  host: prod-db-1.example.com
  port: 5432
```

This code:

```python
doc = YAYA.load('config.yaml')
doc.replace_in_values('prod-db-1', 'prod-db-2')
doc.save()
```

Produces **exactly**:

```yaml
# Production config
database:
  host: prod-db-2.example.com
  port: 5432
```

No reformatting. No comment loss. Just the change you made.

## How It Works

yaya uses a clean AST architecture for truly lossless editing:

1. Parse YAML with [ruamel.yaml] to get AST + position information
2. Extract formatting details (indentation, quotes, styles, blank lines) from original bytes
3. Convert to a clean, immutable AST with all formatting metadata preserved
4. When you make changes, track modifications in the AST
5. Re-serialize the entire document, preserving all formatting for unchanged sections

This approach guarantees byte-for-byte preservation while supporting arbitrary modifications.

## Features

- **Byte-for-byte preservation** of unchanged content (including blank lines within dicts)
- **String replacement** (literal and regex)
- **Path-based navigation** (`jobs.test.steps[0].name`)
- **Replace values or subtrees** (scalars, dicts, lists, list items)
- **Add keys** with order control (`add_key_after`, `insert_key_between`)
- **Delete keys** while preserving surrounding content
- **Assertions** for validation (`assert_value`, `assert_present`, `assert_absent`)
- **Quote style preservation** (single, double, unquoted)
- **Comment preservation** (inline and standalone)
- **Block scalar support** (preserves `|`, `|-`, `|+` indicators)
- **Flow vs block style control** (auto-detect or explicit)
- **List indentation detection** (aligned vs indented styles)
- **Jinja2 expression preservation** (treats as opaque strings)

## Limitations

- Binary data not supported
- Multi-document YAML streams not tested
- Anchors and aliases work but aren't specifically tested

## Comparison with ruamel.yaml

[ruamel.yaml] is excellent for round-trip YAML editing and preserves most formatting. However:

| Feature | [ruamel.yaml] | yaya |
|---------|-------------|---------------|
| Preserves comments | ✅ | ✅ |
| Preserves most whitespace | ✅ | ✅ |
| **Byte-for-byte identical** | ❌ | ✅ |
| Trailing whitespace | ❌ | ✅ |
| Blank lines within dicts | ❌ | ✅ |
| Block scalar indicators | ❌ (computes new ones) | ✅ |
| Quote styles | ❌ (sometimes changes) | ✅ |

`yaya` uses [ruamel.yaml] under the hood but takes a different approach: instead of just serializing the modified AST, it extracts all formatting details from the original bytes and preserves them during re-serialization.

## License

MIT

## Contributing

Issues and pull requests welcome!

[ruamel.yaml]: https://pypi.org/project/ruamel.yaml/
