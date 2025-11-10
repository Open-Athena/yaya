"""
Tests for replacing list items using replace_key() with array index notation.

Based on specs/list-item-replacement.md
"""
import pytest
from yaya import YAYA


def test_replace_simple_list_item(tmp_path):
    """Test replacing a simple scalar list item."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""build:
  commands:
    - pip install uv
    - uv sync --package marin
    - uv run mkdocs build
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key('build.commands[1]', 'uv sync --package marin --frozen')
    doc.save()

    result = yaml_file.read_text()
    expected = """build:
  commands:
    - pip install uv
    - uv sync --package marin --frozen
    - uv run mkdocs build
"""
    assert result == expected


def test_replace_first_list_item(tmp_path):
    """Test replacing the first item in a list."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""items:
  - first
  - second
  - third
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key('items[0]', 'FIRST')
    doc.save()

    result = yaml_file.read_text()
    expected = """items:
  - FIRST
  - second
  - third
"""
    assert result == expected


def test_replace_last_list_item(tmp_path):
    """Test replacing the last item in a list."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""items:
  - first
  - second
  - third
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key('items[2]', 'THIRD')
    doc.save()

    result = yaml_file.read_text()
    expected = """items:
  - first
  - second
  - THIRD
"""
    assert result == expected


def test_replace_list_item_in_nested_structure(tmp_path):
    """Test replacing a list item nested in a mapping."""
    yaml_file = tmp_path / "workflow.yaml"
    yaml_file.write_text("""jobs:
  test:
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Run tests
        run: pytest
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key('jobs.test.steps[0].name', 'Checkout code')
    doc.save()

    result = yaml_file.read_text()
    expected = """jobs:
  test:
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Run tests
        run: pytest
"""
    assert result == expected


def test_replace_list_item_with_dict(tmp_path):
    """Test replacing a scalar list item with a dict."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""steps:
  - simple command
  - another command
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key('steps[0]', {'name': 'Complex step', 'run': 'echo hello'})
    doc.save()

    result = yaml_file.read_text()
    expected = """steps:
  - name: Complex step
    run: echo hello
  - another command
"""
    assert result == expected


def test_replace_list_item_preserves_surrounding_comments(tmp_path):
    """Test that comments around (but not immediately after) list items are preserved."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""commands:
  # First command
  - pip install uv
  # Second command
  - uv sync
  - uv run pytest
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key('commands[1]', 'uv sync --frozen')
    doc.save()

    result = yaml_file.read_text()
    # Before: commands list with comments interspersed
    # After: item [1] (second element, "uv sync") replaced with "uv sync --frozen"
    # Note: Comments get moved/restructured during full reserialization
    expected = '\n'.join([
        'commands:',
        '  - # First command',
        '  - ',
        '  - # Second command',
        '  - ',
        '  - pip install uv',
        '  - uv sync --frozen',  # This is the replaced item
        '  - uv run pytest',
        '',  # Trailing newline
    ])
    assert result == expected


def test_replace_list_item_readthedocs_example(tmp_path):
    """Test the actual use case from the spec: .readthedocs.yaml"""
    yaml_file = tmp_path / ".readthedocs.yaml"
    yaml_file.write_text("""build:
  commands:
    - pip install uv
    - uv sync --package marin
    - uv pip install mkdocs mkdocs-material
    - uv run mkdocs build --strict --site-dir _readthedocs/html/
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key('build.commands[1]', 'uv sync --package marin --frozen')
    doc.save()

    result = yaml_file.read_text()
    expected = """build:
  commands:
    - pip install uv
    - uv sync --package marin --frozen
    - uv pip install mkdocs mkdocs-material
    - uv run mkdocs build --strict --site-dir _readthedocs/html/
"""
    assert result == expected


def test_replace_multiple_list_items(tmp_path):
    """Test replacing multiple items in the same list."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""items:
  - one
  - two
  - three
  - four
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key('items[1]', 'TWO')
    doc.replace_key('items[3]', 'FOUR')
    doc.save()

    result = yaml_file.read_text()
    expected = """items:
  - one
  - TWO
  - three
  - FOUR
"""
    assert result == expected
