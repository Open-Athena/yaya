# lossless-yaml

Byte-for-byte preserving YAML editor for programmatic modifications.

## Why?

Ever need to programmatically edit YAML files but want to preserve:
- All comments
- Exact whitespace (including trailing spaces)
- Quote styles
- Block scalar indicators (`|`, `|-`, `|+`)
- Formatting choices

Most YAML libraries (including ruamel.yaml's round-trip mode) make small formatting changes when serializing. `lossless-yaml` solves this by:

1. Parsing YAML to get the AST with position information
2. Keeping the original bytes
3. Applying modifications only to the specific values you change
4. Leaving everything else untouched

## Installation

```bash
pip install lossless-yaml
```

## Usage

```python
from lossless_yaml import LosslessYAML

# Load a YAML file
doc = LosslessYAML.load('.github/workflows/test.yaml')

# Option 1: Bulk string replacement
doc.replace_in_values('src/marin', 'lib/marin/src/marin')

# Option 2: Dict-like access
doc.data['jobs']['test']['runs-on'] = 'ubuntu-22.04'

# Save (overwrites original file by default)
doc.save()

# Or save to a new file
doc.save('new-workflow.yaml')
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
doc = LosslessYAML.load('config.yaml')
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

## Limitations

- Currently handles scalar string values
- Block scalars with complex indentation may need additional handling
- Binary data in YAML is not supported

## Comparison with ruamel.yaml

`ruamel.yaml` is excellent for round-trip YAML editing and preserves most formatting. However:

| Feature | ruamel.yaml | lossless-yaml |
|---------|-------------|---------------|
| Preserves comments | ✅ | ✅ |
| Preserves most whitespace | ✅ | ✅ |
| **Byte-for-byte identical** | ❌ | ✅ |
| Trailing whitespace | ❌ | ✅ |
| Block scalar indicators | ❌ (computes new ones) | ✅ |

`lossless-yaml` uses `ruamel.yaml` under the hood but takes a different approach: instead of serializing the AST back to YAML, it modifies the original bytes directly.

## License

MIT

## Contributing

Issues and pull requests welcome!
