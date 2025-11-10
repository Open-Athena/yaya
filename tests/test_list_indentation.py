"""
Test for list indentation issue.
Based on ISSUE-list-indentation.md
"""
import pytest
from pathlib import Path
from yaya import YAYA


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

    doc = YAYA.load(yaml_file)

    # Add a new on: trigger with lists
    doc.replace_key("on", {
        "push": {
            "branches": ["main"],
            "paths": ["lib/**"]
        }
    })
    doc.save()

    result = yaml_file.read_text()
    # Before: existing workflow with steps (indented list style, offset=2)
    # After: new "on" trigger added, inheriting offset=2 from steps
    expected = (
        'jobs:\n'
        '  test:\n'
        '    steps:\n'
        '      - uses: actions/checkout@v4\n'
        '      - name: Test\n'
        '        run: echo "test"\n'
        'on:\n'
        '  push:\n'
        '    branches:\n'
        '      - main\n'  # Inherits offset=2 (6 spaces total at depth 2)
        '    paths:\n'
        '      - lib/**\n'
    )
    assert result == expected


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

    doc = YAYA.load(yaml_file)

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
    # Before: workflow with name and jobs
    # After: "on" trigger added with nested lists, using offset=2 from existing steps
    expected = (
        'name: Test workflow\n'
        '\n'
        'jobs:\n'
        '  test:\n'
        '    runs-on: ubuntu-latest\n'
        '    steps:\n'
        '      - uses: actions/checkout@v4\n'
        'on:\n'
        '  push:\n'  # 2 spaces (depth 1)
        '    branches:\n'  # 4 spaces (depth 2)
        '      - main\n'  # 6 spaces (depth 2 key + offset 2)
        '      - develop\n'
        '    paths:\n'
        '      - lib/levanter/**\n'
        '      - uv.lock\n'
        '  pull_request:\n'
        '    paths:\n'
        '      - lib/levanter/**\n'
    )
    assert result == expected


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

    doc = YAYA.load(yaml_file)

    # Add env section with a list-like structure
    doc.add_key_after("jobs.test.runs-on", "strategy", {
        "matrix": {
            "python-version": ["3.10", "3.11", "3.12"]
        }
    })
    doc.save()

    result = yaml_file.read_text()
    # Before: job with runs-on and steps
    # After: strategy matrix inserted between runs-on and steps, with proper indentation
    expected = (
        'jobs:\n'
        '  test:\n'
        '    runs-on: ubuntu-latest\n'
        '    strategy:\n'  # 4 spaces (depth 2)
        '      matrix:\n'  # 6 spaces (depth 3)
        '        python-version:\n'  # 8 spaces (depth 4)
        "          - '3.10'\n"  # 10 spaces (depth 4 key + offset 2)
        "          - '3.11'\n"
        "          - '3.12'\n"
        '    steps:\n'
        '      - uses: actions/checkout@v4\n'
        '      - name: Test\n'
        '        run: echo "test"\n'
    )
    assert result == expected


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

    doc = YAYA.load(yaml_file)

    # Should detect offset=0 (aligned)
    assert doc._detected_list_offset == 0

    # Add a new key with a list
    doc.add_key("config.newlist", {
        "things": ["a", "b", "c"]
    })
    doc.save()

    result = yaml_file.read_text()
    # Before: config with aligned lists (offset=0: dashes at same indent as parent key)
    # After: newlist added, inheriting offset=0 style
    expected = (
        'config:\n'
        '  items:\n'
        '  - foo\n'  # Aligned: dash at same level as "items:"
        '  - bar\n'
        '  nested:\n'
        '    subitems:\n'
        '    - one\n'  # Also aligned
        '    - two\n'
        '  newlist:\n'
        '    things:\n'
        '    - a\n'  # New list also aligned (offset=0 detected and inherited)
        '    - b\n'
        '    - c\n'
    )
    assert result == expected


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

    doc = YAYA.load(yaml_file)

    # Should detect offset=2 (indented)
    assert doc._detected_list_offset == 2

    # Add a new key with a list
    doc.add_key("config.newlist", {
        "things": ["a", "b", "c"]
    })
    doc.save()

    result = yaml_file.read_text()
    # Before: config with indented lists (offset=2: dashes 2 spaces beyond parent key)
    # After: newlist added, inheriting offset=2 style
    expected = (
        'config:\n'
        '  items:\n'
        '    - foo\n'  # Indented: dash 2 spaces beyond "items:" (4 total)
        '    - bar\n'
        '  nested:\n'
        '    subitems:\n'
        '      - one\n'  # Also indented (6 total spaces)
        '      - two\n'
        '  newlist:\n'
        '    things:\n'
        '      - a\n'  # New list also indented (offset=2 detected and inherited)
        '      - b\n'
        '      - c\n'
    )
    assert result == expected


def test_set_list_indent_style_override(tmp_path):
    """Test manually overriding list indentation style."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""config:
  items:
    - foo
""")

    doc = YAYA.load(yaml_file)

    # Override to use aligned style
    doc.set_list_indent_style('aligned')

    doc.add_key("config.newlist", {
        "things": ["a", "b"]
    })
    doc.save()

    result = yaml_file.read_text()
    # Before: config with indented list (offset=2)
    # After: newlist added, but using OVERRIDDEN aligned style (offset=0)
    expected = (
        'config:\n'
        '  items:\n'
        '    - foo\n'  # Original list still indented
        '  newlist:\n'
        '    things:\n'
        '    - a\n'  # New list is aligned (offset=0) due to override
        '    - b\n'
    )
    assert result == expected


def test_mixed_indentation_warning(tmp_path):
    """Test that mixed indentation triggers a warning."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""config:
  aligned:
  - foo
  indented:
    - bar
""")

    doc = YAYA.load(yaml_file)

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
