"""
Test for list indentation issue.
Based on ISSUE-list-indentation.md
"""
import pytest
from pathlib import Path
from lossless_yaml import LosslessYAML


def test_list_indentation_inference(tmp_path):
    """Test that list indentation is inferred from existing lists."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    steps:
      - uses: actions/checkout@v4
      - name: Test
        run: echo "test"
""")

    doc = LosslessYAML.load(yaml_file)

    # Add a new on: trigger with lists
    doc.replace_key("on", {
        "push": {
            "branches": ["main"],
            "paths": ["lib/**"]
        }
    })
    doc.save()

    result = yaml_file.read_text()

    # List items should be indented by 2 spaces (matching the steps list)
    # The pattern should be: "    branches:" followed by "      - main"
    # (4 spaces for branches, 6 spaces for the list item)
    assert "branches:" in result
    assert "      - main" in result, f"Expected '      - main' but got:\n{result}"
    assert "paths:" in result
    assert "      - lib/**" in result, f"Expected '      - lib/**' but got:\n{result}"


def test_replace_key_at_root_with_list(tmp_path):
    """Test adding a structure with lists at root level."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""name: Test workflow

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
""")

    doc = LosslessYAML.load(yaml_file)

    # Insert on: trigger before jobs
    doc.replace_key("on", {
        "push": {
            "branches": ["main", "develop"],
            "paths": ["lib/levanter/**", "uv.lock"]
        },
        "pull_request": {
            "paths": ["lib/levanter/**"]
        }
    })
    doc.save()

    result = yaml_file.read_text()
    print("Result:")
    print(result)

    # Check for proper indentation
    # Top-level keys like "push:" should have 2 spaces
    assert "  push:" in result
    # Nested keys like "branches:" should have 4 spaces
    assert "    branches:" in result
    # List items should have 6 spaces (2 more than parent)
    assert "      - main" in result
    assert "      - develop" in result
    assert "      - lib/levanter/**" in result


def test_add_key_after_with_lists(tmp_path):
    """Test that add_key_after also uses proper list indentation."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Test
        run: echo "test"
""")

    doc = LosslessYAML.load(yaml_file)

    # Add env section with a list-like structure
    doc.add_key_after("jobs.test.runs-on", "strategy", {
        "matrix": {
            "python-version": ["3.10", "3.11", "3.12"]
        }
    })
    doc.save()

    result = yaml_file.read_text()
    print("Result:")
    print(result)

    # Check indentation matches existing pattern
    assert "    strategy:" in result
    assert "      matrix:" in result
    assert "        python-version:" in result
    # List items should be indented 2 spaces from parent
    assert '          - "3.10"' in result or "          - '3.10'" in result


def test_aligned_list_style_detection(tmp_path):
    """Test that aligned list style (offset=0) is detected and used."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""config:
  items:
  - foo
  - bar
  nested:
    subitems:
    - one
    - two
""")

    doc = LosslessYAML.load(yaml_file)

    # Should detect offset=0 (aligned)
    assert doc._detected_list_offset == 0

    # Add a new key with a list
    doc.add_key("config.newlist", {
        "things": ["a", "b", "c"]
    })
    doc.save()

    result = yaml_file.read_text()
    print("Result:")
    print(result)

    # New list should also be aligned (not indented)
    # things: is at 4 spaces (nested under newlist), dash should also be at 4 spaces
    assert "    things:\n    - a" in result or "    things:\n    - 'a'" in result


def test_indented_list_style_detection(tmp_path):
    """Test that indented list style (offset=2) is detected and used."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""config:
  items:
    - foo
    - bar
  nested:
    subitems:
      - one
      - two
""")

    doc = LosslessYAML.load(yaml_file)

    # Should detect offset=2 (indented)
    assert doc._detected_list_offset == 2

    # Add a new key with a list
    doc.add_key("config.newlist", {
        "things": ["a", "b", "c"]
    })
    doc.save()

    result = yaml_file.read_text()
    print("Result:")
    print(result)

    # New list should also be indented
    # things: is at 4 spaces, dash should be at 6 spaces (indented 2 from parent)
    assert "    things:\n      - a" in result or "    things:\n      - 'a'" in result


def test_set_list_indent_style_override(tmp_path):
    """Test manually overriding list indentation style."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""config:
  items:
    - foo
""")

    doc = LosslessYAML.load(yaml_file)

    # Override to use aligned style
    doc.set_list_indent_style('aligned')

    doc.add_key("config.newlist", {
        "things": ["a", "b"]
    })
    doc.save()

    result = yaml_file.read_text()
    print("Result:")
    print(result)

    # Should use aligned style despite original being indented
    # things: is at 4 spaces, dash should also be at 4 spaces (aligned)
    assert "    things:\n    - a" in result or "    things:\n    - 'a'" in result


def test_mixed_indentation_warning(tmp_path):
    """Test that mixed indentation triggers a warning."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""config:
  aligned:
  - foo
  indented:
    - bar
""")

    doc = LosslessYAML.load(yaml_file)

    # Should detect ambiguity
    assert doc._detected_list_offset is None

    # Should warn when using it
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        doc.add_key("config.newlist", {"things": ["a"]})
        # Should have issued a warning
        assert len(w) == 1
        assert "No consistent list indentation" in str(w[0].message)
