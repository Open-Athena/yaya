# yaya

Yet Another YAML AST - programmatically transform YAML, preserving whitespace and comments

## Why?

Ever need to programmatically edit YAML files but want to preserve:
- All comments
- Exact whitespace (including trailing spaces)
- Quote styles
- Block scalar indicators (`|`, `|-`, `|+`)
- Formatting choices

Most YAML libraries (including ruamel.yaml's round-trip mode) make small formatting changes when serializing. `yaya` solves this by:

1. Parsing YAML to get the AST with position information
2. Keeping the original bytes
3. Applying modifications only to the specific values you change
4. Leaving everything else untouched

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

### Replacing Entire Values

```python
# Replace a simple value
doc.replace_key("jobs.test.runs-on", "ubuntu-22.04")

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

### Adding New Keys

```python
# Add a key after another key (maintains order)
doc.add_key_after("jobs.test.runs-on", "defaults", {
    "run": {
        "working-directory": "lib/myapp"
    }
})

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

1. Uses `ruamel.yaml` to parse YAML and extract position information
2. Converts line/column positions to byte offsets
3. Tracks modifications as you change values
4. Applies byte-level replacements when saving

## Features

- ✅ Byte-for-byte preservation of unchanged content
- ✅ String replacement (literal and regex)
- ✅ Path-based navigation (`jobs.test.steps[0].name`)
- ✅ Replace entire values (scalars, dicts, lists)
- ✅ Add new keys with proper positioning
- ✅ Assertions for validation
- ✅ Comment preservation
- ✅ Block scalar support
- ✅ Flow and block style handling

## Limitations

- Removing keys not yet implemented
- Binary data in YAML is not supported
- Adding keys at arbitrary positions (only `add_key_after` currently)

## Comparison with ruamel.yaml

`ruamel.yaml` is excellent for round-trip YAML editing and preserves most formatting. However:

| Feature | ruamel.yaml | yaya |
|---------|-------------|---------------|
| Preserves comments | ✅ | ✅ |
| Preserves most whitespace | ✅ | ✅ |
| **Byte-for-byte identical** | ❌ | ✅ |
| Trailing whitespace | ❌ | ✅ |
| Block scalar indicators | ❌ (computes new ones) | ✅ |

`yaya` uses `ruamel.yaml` under the hood but takes a different approach: instead of serializing the AST back to YAML, it modifies the original bytes directly.

## License

MIT

## Contributing

Issues and pull requests welcome!
