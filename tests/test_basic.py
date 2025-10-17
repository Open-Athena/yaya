"""
Basic tests for lossless-yaml.
"""
import pytest
from pathlib import Path
from lossless_yaml import LosslessYAML


def test_simple_replacement(tmp_path):
    """Test basic string replacement."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""key: old_value
another: keep_this
""")

    doc = LosslessYAML.load(yaml_file)
    doc.replace_in_values('old_value', 'new_value')
    doc.save()

    result = yaml_file.read_text()
    assert 'new_value' in result
    assert 'keep_this' in result


def test_preserves_comments(tmp_path):
    """Test that comments are preserved."""
    yaml_file = tmp_path / "test.yaml"
    original = """# Top comment
key: value  # inline comment
# Bottom comment
"""
    yaml_file.write_text(original)

    doc = LosslessYAML.load(yaml_file)
    doc.replace_in_values('value', 'newvalue')
    result = doc.save()

    # Comments should be preserved
    assert b'# Top comment' in result
    assert b'# inline comment' in result
    assert b'# Bottom comment' in result


def test_preserves_whitespace(tmp_path):
    """Test that exact whitespace is preserved."""
    yaml_file = tmp_path / "test.yaml"
    original = """jobs:
  test:
    runs-on: ubuntu-latest
"""
    yaml_file.write_text(original)

    doc = LosslessYAML.load(yaml_file)
    doc.replace_in_values('ubuntu', 'debian')
    result = doc.save()

    # Should preserve exact spacing
    assert b'  test:' in result
    assert b'    runs-on:' in result


def test_block_scalar(tmp_path):
    """Test block scalar handling."""
    yaml_file = tmp_path / "test.yaml"
    original = """script: |
  echo "hello"
  echo "world"
"""
    yaml_file.write_text(original)

    doc = LosslessYAML.load(yaml_file)
    doc.replace_in_values('hello', 'goodbye')
    result = yaml_file.read_text()

    assert 'goodbye' in result
    assert 'world' in result
    # Indentation should be preserved
    assert '  echo "goodbye"' in result
    assert '  echo "world"' in result


def test_nested_structures(tmp_path):
    """Test replacement in nested structures."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
outer:
  inner:
    deep: old_value
  list:
    - item1: old_value
    - item2: keep
""")

    doc = LosslessYAML.load(yaml_file)
    doc.replace_in_values('old_value', 'new_value')
    result = yaml_file.read_text()

    assert result.count('new_value') == 2
    assert 'keep' in result


def test_no_changes_when_no_match(tmp_path):
    """Test that file is unchanged when pattern doesn't match."""
    yaml_file = tmp_path / "test.yaml"
    original = """key: value
another: thing
"""
    yaml_file.write_bytes(original.encode())

    doc = LosslessYAML.load(yaml_file)
    doc.replace_in_values('nonexistent', 'replacement')
    result = doc.save()

    assert result == original.encode()
