"""
Tests for workflow transformation features.
Based on workflow_transform_requirements.md
"""
import pytest
from pathlib import Path
from yaya import YAYA


def test_path_navigation(tmp_path):
    """Test path-based navigation."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
""")

    doc = YAYA.load(yaml_file)

    assert doc.get_path("jobs.test.runs-on") == "ubuntu-latest"
    assert doc["jobs"]["test"]["runs-on"] == "ubuntu-latest"


def test_assert_value(tmp_path):
    """Test assertion methods."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)

    doc.assert_value("on", ["push"])
    doc.assert_present("jobs.test")
    doc.assert_absent("jobs.test.defaults")

    with pytest.raises(AssertionError):
        doc.assert_value("on", ["pull_request"])

    with pytest.raises(AssertionError):
        doc.assert_absent("jobs.test")

    with pytest.raises(AssertionError):
        doc.assert_present("jobs.test.defaults")


def test_regex_replacement(tmp_path):
    """Test Case 5: Regex replacement in values."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""steps:
  - name: Install dependencies
    run: uv sync --dev
  - name: Run tests
    run: uv run pytest tests/
  - name: Already has package
    run: uv sync --package other --dev
""")

    doc = YAYA.load(yaml_file)
    doc.replace_in_values_regex(r'\buv sync(?! --package)', r'uv sync --package levanter')
    doc.replace_in_values_regex(r'\buv run(?! --package)', r'uv run --package levanter')
    doc.save()

    result = yaml_file.read_text()
    # Before: Generic `uv sync` and `uv run` commands
    # After: Commands without --package get it added via regex replacement
    expected = '\n'.join([
        'steps:',
        '  - name: Install dependencies',
        '    run: uv sync --package levanter --dev',  # Added --package levanter
        '  - name: Run tests',
        '    run: uv run --package levanter pytest tests/',  # Added --package levanter
        '  - name: Already has package',
        '    run: uv sync --package other --dev',  # Unchanged (already had --package)
        '',
    ])
    assert result == expected


def test_expand_flow_style_on(tmp_path):
    """Test Case 1: Expand flow-style on: trigger."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""name: Run tests that use ray

on: [push]

jobs:
  ray_tests:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)
    doc.assert_value("on", ["push"])

    doc.replace_key("on", {
        "push": {
            "branches": ["main"],
            "paths": [
                "lib/levanter/**",
                "uv.lock",
                ".github/workflows/levanter-run_ray_tests.yaml"
            ]
        },
        "pull_request": {
            "paths": [
                "lib/levanter/**",
                "uv.lock",
                ".github/workflows/levanter-run_ray_tests.yaml"
            ]
        }
    })
    doc.save()

    result = yaml_file.read_text()
    # Before: on: [push, pull_request] (flow style)
    # After: Expanded to nested structure with branches and paths
    expected = '\n'.join([
        'name: Run tests that use ray',
        '',
        'on:',
        '  push:',
        '    branches:',
        '      - main',
        '    paths:',
        '      - lib/levanter/**',
        '      - uv.lock',
        '      - .github/workflows/levanter-run_ray_tests.yaml',
        '  pull_request:',
        '    paths:',
        '      - lib/levanter/**',
        '      - uv.lock',
        '      - .github/workflows/levanter-run_ray_tests.yaml',
        '',
        'jobs:',  # Blank line preserved
        '  ray_tests:',
        '    runs-on: ubuntu-latest',
        '',
    ])
    assert result == expected


def test_add_defaults_section(tmp_path):
    """Test Case 2: Add defaults section to job."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11"]
    steps:
      - uses: actions/checkout@v4
""")

    doc = YAYA.load(yaml_file)
    doc.assert_absent("jobs.test.defaults")

    doc.add_key_after("jobs.test.runs-on", "defaults", {
        "run": {
            "working-directory": "lib/levanter"
        }
    })
    doc.save()

    result = yaml_file.read_text()
    # Before: job with runs-on, strategy, and steps
    # After: defaults section inserted between runs-on and strategy
    expected = '\n'.join([
        'jobs:',
        '  test:',
        '    runs-on: ubuntu-latest',
        '    defaults:',  # Inserted after runs-on
        '      run:',
        '        working-directory: lib/levanter',
        '    strategy:',  # Existing strategy comes after
        '      matrix:',
        "        python-version: ['3.11']",
        '    steps:',
        '      - uses: actions/checkout@v4',
        '',
    ])
    assert result == expected


def test_parse_path_with_array_index(tmp_path):
    """Test path parsing with array indices."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    steps:
      - name: First step
        uses: actions/checkout@v4
      - name: Second step
        uses: actions/setup-python@v5
""")

    doc = YAYA.load(yaml_file)

    assert doc.get_path("jobs.test.steps[0].name") == "First step"
    assert doc.get_path("jobs.test.steps[1].name") == "Second step"
    assert "checkout" in doc.get_path("jobs.test.steps[0].uses")


def test_replace_key_simple_value(tmp_path):
    """Test replace_key with simple scalar value."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("jobs.test.runs-on", "ubuntu-22.04")
    doc.save()

    result = yaml_file.read_text()
    # Before: runs-on: ubuntu-latest
    # After: runs-on: ubuntu-22.04 (simple value replacement)
    expected = '\n'.join([
        'jobs:',
        '  test:',
        '    runs-on: ubuntu-22.04',  # Changed from ubuntu-latest
        '',
    ])
    assert result == expected


def test_idempotency(tmp_path):
    """Test that running transformations twice produces same result."""
    yaml_file = tmp_path / "test.yaml"
    original = """steps:
  - run: uv sync --dev
"""
    yaml_file.write_text(original)

    doc = YAYA.load(yaml_file)
    doc.replace_in_values_regex(r'\buv sync(?! --package)', r'uv sync --package levanter')
    doc.save()
    first_result = yaml_file.read_text()

    doc2 = YAYA.load(yaml_file)
    doc2.replace_in_values_regex(r'\buv sync(?! --package)', r'uv sync --package levanter')
    doc2.save()
    second_result = yaml_file.read_text()

    assert first_result == second_result
    assert 'uv sync --package levanter --dev' in first_result
