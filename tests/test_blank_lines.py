"""
Tests for blank line preservation within dict structures.

Based on specs/blank-lines-within-dicts.md
"""
import pytest
from pathlib import Path
from yaya import YAYA


def test_preserve_blank_lines_within_dict(tmp_path):
    """Test basic preservation of blank lines within dict."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  build:

    runs-on: ubuntu-latest

    steps:
      - name: test
""")

    doc = YAYA.load(yaml_file)
    doc.save()

    result = yaml_file.read_text()
    # Before: jobs.build with blank line after 'build:' and after 'runs-on:'
    # After: All blank lines preserved byte-for-byte
    expected = '\n'.join([
        'jobs:',
        '  build:',
        '',  # Blank line after 'build:', before 'runs-on:'
        '    runs-on: ubuntu-latest',
        '',  # Blank line after 'runs-on:', before 'steps:'
        '    steps:',
        '      - name: test',
        '',
    ])
    assert result == expected


def test_preserve_blank_lines_with_other_modifications(tmp_path):
    """Test that blank lines are preserved when other parts of document are modified."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""name: Test

jobs:
  build:

    runs-on: ubuntu-latest

    steps:
      - name: test
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("name", "Updated")
    doc.save()

    result = yaml_file.read_text()
    # Before: name: Test, with blank lines in jobs.build section
    # After: name changed to "Updated", but blank lines in jobs.build preserved
    expected = '\n'.join([
        'name: Updated',
        '',
        'jobs:',
        '  build:',
        '',  # Preserved
        '    runs-on: ubuntu-latest',
        '',  # Preserved
        '    steps:',
        '      - name: test',
        '',
    ])
    assert result == expected


def test_preserve_multiple_blank_lines(tmp_path):
    """Test preservation of multiple consecutive blank lines."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  build:


    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)
    doc.save()

    result = yaml_file.read_text()
    # Before: Two blank lines after 'build:'
    # After: Both blank lines preserved
    expected = '\n'.join([
        'jobs:',
        '  build:',
        '',  # First blank line
        '',  # Second blank line
        '    runs-on: ubuntu-latest',
        '',
    ])
    assert result == expected


def test_blank_lines_at_all_levels(tmp_path):
    """Test that blank lines are preserved at different nesting levels."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""top:

  level1:

    level2:

      level3: value
""")

    doc = YAYA.load(yaml_file)
    doc.save()

    result = yaml_file.read_text()
    # Before: Blank lines at each nesting level
    # After: All blank lines preserved
    expected = '\n'.join([
        'top:',
        '',  # After 'top:'
        '  level1:',
        '',  # After 'level1:'
        '    level2:',
        '',  # After 'level2:'
        '      level3: value',
        '',
    ])
    assert result == expected


def test_github_actions_workflow_blank_lines(tmp_path):
    """Test real-world GitHub Actions workflow with blank lines."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""name: Test

on: [push]

jobs:
  build:

    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3
""")

    doc = YAYA.load(yaml_file)
    doc.save()

    result = yaml_file.read_text()
    # Before: GitHub Actions workflow with typical blank line spacing
    # After: All blank lines preserved (byte-for-byte identical)
    expected = '\n'.join([
        'name: Test',
        '',
        'on: [push]',
        '',
        'jobs:',
        '  build:',
        '',
        '    runs-on: ubuntu-latest',
        '',
        '    steps:',
        '      - uses: actions/checkout@v3',
        '',
    ])
    assert result == expected
