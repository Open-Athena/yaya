"""
Tests for ordered key insertion APIs.

Tests insert_key_between() which verifies key adjacency before inserting.
"""
import pytest
from yaya import YAYA


def test_insert_key_between_adjacent_keys(tmp_path):
    """Test inserting a key between two adjacent keys."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  build:
    runs-on: ubuntu-latest
    if: ${{ github.event_name == 'push' }}
    steps:
      - run: echo test
""")

    doc = YAYA.load(yaml_file)

    # Insert defaults between 'if' and 'steps'
    doc.insert_key_between(
        "jobs.build",
        prev_key="if",
        next_key="steps",
        new_key="defaults",
        value={"run": {"working-directory": "lib/levanter"}}
    )

    doc.save()

    doc2 = YAYA.load(yaml_file)
    # Verify order
    keys = list(doc2.get_path("jobs.build").keys())
    assert keys.index("if") < keys.index("defaults") < keys.index("steps")
    assert doc2.get_path("jobs.build.defaults.run.working-directory") == "lib/levanter"


def test_insert_key_between_not_adjacent(tmp_path):
    """Test that insert_key_between raises ValueError when keys aren't adjacent."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""config:
  first: 1
  second: 2
  third: 3
""")

    doc = YAYA.load(yaml_file)

    # Try to insert between non-adjacent keys
    with pytest.raises(ValueError, match="not adjacent.*Found 1 key"):
        doc.insert_key_between(
            "config",
            prev_key="first",
            next_key="third",  # 'second' is between them
            new_key="new",
            value=42
        )


def test_insert_key_between_missing_key(tmp_path):
    """Test that insert_key_between raises KeyError when a key doesn't exist."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""config:
  first: 1
  second: 2
""")

    doc = YAYA.load(yaml_file)

    # Missing prev_key
    with pytest.raises(KeyError, match="Previous key 'missing'"):
        doc.insert_key_between(
            "config",
            prev_key="missing",
            next_key="second",
            new_key="new",
            value=42
        )

    # Missing next_key
    with pytest.raises(KeyError, match="Next key 'missing'"):
        doc.insert_key_between(
            "config",
            prev_key="first",
            next_key="missing",
            new_key="new",
            value=42
        )
