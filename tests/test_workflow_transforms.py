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
    assert 'uv sync --package levanter --dev' in result
    assert 'uv run --package levanter pytest tests/' in result
    assert 'uv sync --package other --dev' in result


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

    assert "on:" in result
    assert "push:" in result
    assert "branches:" in result
    assert "- main" in result
    assert "lib/levanter/**" in result
    assert "pull_request:" in result

    assert "\n\njobs:" in result or "\n\njobs" in result


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

    assert "defaults:" in result
    assert "run:" in result
    assert "working-directory: lib/levanter" in result

    lines = result.split('\n')
    runs_on_idx = next(i for i, line in enumerate(lines) if 'runs-on:' in line)
    defaults_idx = next(i for i, line in enumerate(lines) if 'defaults:' in line)
    strategy_idx = next(i for i, line in enumerate(lines) if 'strategy:' in line)

    assert runs_on_idx < defaults_idx < strategy_idx


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
    assert "ubuntu-22.04" in result
    assert "ubuntu-latest" not in result


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
