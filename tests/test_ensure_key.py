"""
Tests for ensure_key() API and related features for workspace migration.

These tests cover the APIs requested in WORKSPACE_MIGRATION_API_NEEDS.md:
1. ensure_key() - Idempotent key addition
2. replace_key() on scalars - Targeted replacement (not global like replace_in_values)
"""
import pytest
from yaya import YAYA


def test_ensure_key_adds_missing_key(tmp_path):
    """Test that ensure_key adds a key that doesn't exist."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)
    added = doc.ensure_key("jobs.test.timeout-minutes", 30)

    assert added is True

    doc.save()
    result = yaml_file.read_text()
    expected = """jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 30
"""
    assert result == expected


def test_ensure_key_skips_existing_key(tmp_path):
    """Test that ensure_key is idempotent - doesn't modify existing keys."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)

    # First call - adds the key
    doc.ensure_key("jobs.test.timeout-minutes", 30)

    # Second call - should be no-op
    added = doc.ensure_key("jobs.test.timeout-minutes", 30)
    assert added is False


def test_ensure_key_with_nested_structure(tmp_path):
    """Test ensure_key with nested dict values."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)

    added = doc.ensure_key("jobs.test.defaults", {
        "run": {
            "working-directory": "lib/levanter"
        }
    })

    assert added is True

    doc.save()
    result = yaml_file.read_text()
    expected = """jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: lib/levanter
"""
    assert result == expected


def test_ensure_key_verify_if_exists_matching(tmp_path):
    """Test that verify_if_exists=True passes when value matches."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)

    # Should not raise
    added = doc.ensure_key("jobs.test.runs-on", "ubuntu-latest", verify_if_exists=True)
    assert added is False


def test_ensure_key_verify_if_exists_mismatch(tmp_path):
    """Test that verify_if_exists=True raises when value doesn't match."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)

    with pytest.raises(ValueError, match="exists with value.*expected"):
        doc.ensure_key("jobs.test.runs-on", "macos-latest", verify_if_exists=True)


def test_ensure_key_in_list_item(tmp_path):
    """Test ensure_key works with list indices (e.g., steps[0].with.working-directory)."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""steps:
  - uses: astral-sh/setup-uv@v6
    with:
      version: "0.7.20"
      enable-cache: true
""")

    doc = YAYA.load(yaml_file)
    added = doc.ensure_key("steps[0].with.working-directory", "lib/levanter")

    assert added is True

    doc.save()
    result = yaml_file.read_text()
    expected = """steps:
  - uses: astral-sh/setup-uv@v6
    with:
      version: "0.7.20"
      enable-cache: true
      working-directory: lib/levanter
"""
    assert result == expected


def test_replace_key_scalar_targeted(tmp_path):
    """
    Test that replace_key only changes the specific key, not all occurrences.

    This is the key difference from replace_in_values which would change both.
    """
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""name: GPT-2 Small Integration Test
jobs:
  test:
    steps:
      - name: Run GPT-2 Small Integration Test
""")

    doc = YAYA.load(yaml_file)

    # Replace only the workflow name, not the step name
    doc.replace_key("name", "Levanter - GPT-2 Small Integration Test")

    doc.save()
    result = yaml_file.read_text()
    expected = """name: Levanter - GPT-2 Small Integration Test
jobs:
  test:
    steps:
      - name: Run GPT-2 Small Integration Test
"""
    assert result == expected


def test_replace_key_vs_replace_in_values(tmp_path):
    """
    Demonstrate the difference between replace_key and replace_in_values.

    replace_key: Changes only the specific field
    replace_in_values: Changes all occurrences of the string
    """
    yaml_file = tmp_path / "test.yaml"
    yaml_content = """name: Test Workflow
env:
  WORKFLOW_NAME: Test Workflow
"""
    yaml_file.write_text(yaml_content)

    # Test replace_key - targeted
    doc1 = YAYA.load(yaml_file)
    doc1.replace_key("name", "New Test Workflow")
    result1 = doc1.save(tmp_path / "result1.yaml")
    result1_text = result1.decode()

    expected1 = """name: New Test Workflow
env:
  WORKFLOW_NAME: Test Workflow
"""
    assert result1_text == expected1

    # Test replace_in_values - global
    yaml_file.write_text(yaml_content)  # Reset
    doc2 = YAYA.load(yaml_file)
    doc2.replace_in_values("Test Workflow", "New Test Workflow")
    result2 = doc2.save(tmp_path / "result2.yaml")
    result2_text = result2.decode()

    expected2 = """name: New Test Workflow
env:
  WORKFLOW_NAME: New Test Workflow
"""
    assert result2_text == expected2


def test_ensure_key_deep_nested_path(tmp_path):
    """Test ensure_key with nested dict value (creates full structure at once)."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)

    # Create the nested structure all at once by passing a dict
    added = doc.ensure_key("jobs.test.defaults", {
        "run": {
            "working-directory": "lib/levanter"
        }
    })

    assert added is True

    doc.save()
    result = yaml_file.read_text()
    expected = """jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: lib/levanter
"""
    assert result == expected


def test_ensure_key_multiple_calls_idempotent(tmp_path):
    """Test that calling ensure_key multiple times is safe and idempotent."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""steps:
  - uses: astral-sh/setup-uv@v6
    with:
      version: 0.7.20
""")

    doc = YAYA.load(yaml_file)

    # Call ensure_key three times with the same value
    result1 = doc.ensure_key("steps[0].with.working-directory", "lib/levanter")
    result2 = doc.ensure_key("steps[0].with.working-directory", "lib/levanter")
    result3 = doc.ensure_key("steps[0].with.working-directory", "lib/levanter")

    assert result1 is True   # First call adds it
    assert result2 is False  # Second call sees it exists
    assert result3 is False  # Third call sees it exists

    doc.save()
    result = yaml_file.read_text()
    expected = """steps:
  - uses: astral-sh/setup-uv@v6
    with:
      version: 0.7.20
      working-directory: lib/levanter
"""
    assert result == expected
