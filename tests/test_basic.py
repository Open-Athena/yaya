"""
Basic tests for yaya.
"""
import pytest
from pathlib import Path
from yaya import YAYA


def test_simple_replacement(tmp_path):
    """Test basic string replacement."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""key: old_value
another: keep_this
""")

    doc = YAYA.load(yaml_file)
    doc.replace_in_values('old_value', 'new_value')
    doc.save()

    result = yaml_file.read_text()
    expected = """key: new_value
another: keep_this
"""
    assert result == expected


def test_preserves_comments(tmp_path):
    """Test that comments are preserved."""
    yaml_file = tmp_path / "test.yaml"
    original = """# Top comment
key: value  # inline comment
# Bottom comment
"""
    yaml_file.write_text(original)

    doc = YAYA.load(yaml_file)
    doc.replace_in_values('value', 'newvalue')
    result = doc.save()

    expected = b"""# Top comment
key: newvalue  # inline comment
# Bottom comment
"""
    assert result == expected


def test_preserves_whitespace(tmp_path):
    """Test that exact whitespace is preserved."""
    yaml_file = tmp_path / "test.yaml"
    original = """jobs:
  test:
    runs-on: ubuntu-latest
"""
    yaml_file.write_text(original)

    doc = YAYA.load(yaml_file)
    doc.replace_in_values('ubuntu', 'debian')
    result = doc.save()

    expected = b"""jobs:
  test:
    runs-on: debian-latest
"""
    assert result == expected


def test_block_scalar(tmp_path):
    """Test block scalar handling."""
    yaml_file = tmp_path / "test.yaml"
    original = """script: |
  echo "hello"
  echo "world"
"""
    yaml_file.write_text(original)

    doc = YAYA.load(yaml_file)
    doc.replace_in_values('hello', 'goodbye')
    doc.save()
    result = yaml_file.read_text()

    expected = (
        'script: |\n'
        '  echo "goodbye"\n'
        '  echo "world"\n'
        '\n'
        '\n'
    )
    assert result == expected


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

    doc = YAYA.load(yaml_file)
    doc.replace_in_values('old_value', 'new_value')
    doc.save()
    result = yaml_file.read_text()

    expected = (
        'outer:\n'
        '  inner:\n'
        '    deep: new_value\n'
        '  list:\n'
        '    - item1: new_value\n'
        '    - item2: keep\n'
    )
    assert result == expected


def test_no_changes_when_no_match(tmp_path):
    """Test that file is unchanged when pattern doesn't match."""
    yaml_file = tmp_path / "test.yaml"
    original = """key: value
another: thing
"""
    yaml_file.write_bytes(original.encode())

    doc = YAYA.load(yaml_file)
    doc.replace_in_values('nonexistent', 'replacement')
    result = doc.save()

    assert result == original.encode()
