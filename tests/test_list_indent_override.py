"""Tests for list indentation override with set_list_indent_style()."""
from pathlib import Path
from yaya import YAYA


def test_set_list_indent_style_respected_in_replace_key(tmp_path):
    """Test that set_list_indent_style() is respected when creating new structures."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)
    doc.set_list_indent_style(offset=2)

    doc.replace_key("on", {
        "push": {
            "branches": ["main"],
            "paths": [
                "lib/haliax/**",
                "uv.lock",
            ],
        },
        "pull_request": {
            "paths": [
                "lib/haliax/**",
                "uv.lock",
            ],
        },
    })

    doc.save()

    result = yaml_file.read_text()
    expected = """on:
  push:
    branches:
      - main
    paths:
      - lib/haliax/**
      - uv.lock
  pull_request:
    paths:
      - lib/haliax/**
      - uv.lock

jobs:
  build:
    runs-on: ubuntu-latest
"""
    assert result == expected


def test_set_list_indent_style_aligned(tmp_path):
    """Test that offset=0 (aligned) style works."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""config:
  old: value
""")

    doc = YAYA.load(yaml_file)
    doc.set_list_indent_style(offset=0)

    doc.replace_key("config.items", ["item1", "item2"])

    doc.save()

    result = yaml_file.read_text()
    expected = """config:
  old: value
  items:
  - item1
  - item2
"""
    assert result == expected


def test_set_list_indent_style_with_add_key(tmp_path):
    """Test that set_list_indent_style() works with add_key()."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)
    doc.set_list_indent_style(offset=2)

    doc.add_key("jobs.test.steps", [
        {"uses": "actions/checkout@v3"},
        {"run": "echo test"},
    ], force=True)

    doc.save()

    result = yaml_file.read_text()
    # Before: no steps
    # After: steps added with 2-space offset (6 total spaces for list items at depth 2)
    expected = (
        'jobs:\n'
        '  test:\n'
        '    runs-on: ubuntu-latest\n'
        '    steps:\n'
        '      - uses: actions/checkout@v3\n'  # 4 (key indent) + 2 (offset) = 6 spaces
        '      - run: echo test\n'
    )
    assert result == expected


def test_default_offset_without_override(tmp_path):
    """Test that without explicit override, uses safe default (2)."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""on: [push]
""")

    doc = YAYA.load(yaml_file)
    # Don't call set_list_indent_style()

    doc.replace_key("on", {
        "push": {
            "branches": ["main"],
        },
    })

    doc.save()

    result = yaml_file.read_text()
    # Before: on: [push] (flow style)
    # After: on expanded to nested structure with offset=2 (default)
    expected = (
        'on:\n'
        '  push:\n'
        '    branches:\n'
        '      - main\n'  # 4 (key indent) + 2 (default offset) = 6 spaces
    )
    assert result == expected
