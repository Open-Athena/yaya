"""Tests for style hints in collection formatting."""
from pathlib import Path
from yaya import YAYA


def test_replace_key_flow_style_list(tmp_path):
    """Test replacing a list with flow style."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""strategy:
  matrix:
    python-version:
      - "3.11"
      - "3.12"
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("strategy.matrix.python-version", ["3.11", "3.12"], style='flow')
    doc.save()

    result = yaml_file.read_text()
    expected = """strategy:
  matrix:
    python-version: ['3.11', '3.12']
"""
    assert result == expected


def test_replace_key_block_style_list(tmp_path):
    """Test replacing a list with explicit block style."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""strategy:
  matrix:
    python-version: ["3.11"]
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("strategy.matrix.python-version", ["3.11", "3.12"], style='block')
    doc.save()

    result = yaml_file.read_text()
    expected = """strategy:
  matrix:
    python-version:
      - '3.11'
      - '3.12'
"""
    assert result == expected


def test_replace_key_auto_style(tmp_path):
    """Test that auto style works (current default behavior)."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""strategy:
  matrix:
    python-version: ["3.11"]
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("strategy.matrix.python-version", ["3.11", "3.12"], style='auto')
    doc.save()

    result = yaml_file.read_text()
    # Auto style defaults to block for lists in this context
    expected = """strategy:
  matrix:
    python-version:
      - '3.11'
      - '3.12'
"""
    assert result == expected


def test_replace_key_preserve_flow_style(tmp_path):
    """Test that preserve style maintains flow style."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""strategy:
  matrix:
    python-version: ["3.11"]
    jax-version: [0.6.2]
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("strategy.matrix.python-version", ["3.11", "3.12"], style='preserve')
    doc.save()

    result = yaml_file.read_text()
    expected = """strategy:
  matrix:
    python-version: ['3.11', '3.12']
    jax-version: [0.6.2]
"""
    assert result == expected


def test_replace_key_preserve_block_style(tmp_path):
    """Test that preserve style maintains block style."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""strategy:
  matrix:
    python-version:
      - "3.11"
    jax-version: [0.6.2]
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("strategy.matrix.python-version", ["3.11", "3.12"], style='preserve')
    doc.save()

    result = yaml_file.read_text()
    expected = """strategy:
  matrix:
    python-version:
      - '3.11'
      - '3.12'
    jax-version: [0.6.2]
"""
    assert result == expected


def test_replace_key_preserve_falls_back_to_auto(tmp_path):
    """Test that preserve style falls back to auto when key doesn't exist."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""strategy:
  matrix:
    jax-version: [0.6.2]
""")

    doc = YAYA.load(yaml_file)
    # Key doesn't exist yet - preserve should fall back to auto
    doc.replace_key("strategy.matrix.python-version", ["3.11", "3.12"], style='preserve')
    doc.save()

    result = yaml_file.read_text()
    # Before: strategy with jax-version in flow style
    # After: python-version added with style='preserve', but since key doesn't exist,
    #        falls back to auto (block style)
    expected = '\n'.join([
        'strategy:',
        '  matrix:',
        '    jax-version: [0.6.2]',
        '    python-version:',
        "      - '3.11'",  # Auto style = block (not flow like jax-version)
        "      - '3.12'",
        '',
    ])
    assert result == expected


def test_add_key_flow_style(tmp_path):
    """Test adding a new key with flow style."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)
    doc.add_key(
        "jobs.test.strategy",
        {"matrix": {"python-version": ["3.11", "3.12"]}},
        force=True,
        style='flow'
    )
    doc.save()

    result = yaml_file.read_text()
    expected = """jobs:
  test:
    runs-on: ubuntu-latest
    strategy: {matrix: {python-version: ['3.11', '3.12']}}
"""
    assert result == expected


def test_add_key_after_flow_style(tmp_path):
    """Test adding a key after another with flow style."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo test
""")

    doc = YAYA.load(yaml_file)
    doc.add_key_after(
        "jobs.test.runs-on",
        "strategy",
        {"matrix": {"python-version": ["3.11", "3.12"]}},
        style='flow'
    )
    doc.save()

    result = yaml_file.read_text()
    expected = """jobs:
  test:
    runs-on: ubuntu-latest
    strategy: {matrix: {python-version: ['3.11', '3.12']}}
    steps:
      - run: echo test
"""
    assert result == expected


def test_flow_style_with_nested_dict(tmp_path):
    """Test flow style with nested dictionaries."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""config:
  old: value
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key(
        "config.settings",
        {
            "database": {"host": "localhost", "port": 5432},
            "cache": {"enabled": True}
        },
        style='flow'
    )
    doc.save()

    result = yaml_file.read_text()
    expected = """config:
  old: value
  settings: {database: {host: localhost, port: 5432}, cache: {enabled: true}}
"""
    assert result == expected


def test_mixed_styles_in_document(tmp_path):
    """Test that different keys can have different styles."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)
    # Add one with flow style
    doc.add_key("jobs.test.env", {"NODE_ENV": "production"}, force=True, style='flow')
    # Add one with block style
    doc.add_key("jobs.test.steps", [{"run": "echo test"}], force=True, style='block')
    doc.save()

    result = yaml_file.read_text()
    # Before: job with only runs-on
    # After: env added in flow style, steps added in block style
    expected = '\n'.join([
        'jobs:',
        '  test:',
        '    runs-on: ubuntu-latest',
        '    env: {NODE_ENV: production}',  # Flow style
        '    steps:',  # Block style
        '      - run: echo test',
        '',
    ])
    assert result == expected


def test_flow_style_with_numbers(tmp_path):
    """Test that flow style preserves number types (not quoted)."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""matrix:
  old: value
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("matrix.versions", [0.6, 0.7, 0.8], style='flow')
    doc.save()

    result = yaml_file.read_text()
    expected = """matrix:
  old: value
  versions: [0.6, 0.7, 0.8]
"""
    assert result == expected


def test_replace_list_item_with_flow_style(tmp_path):
    """Test replacing a list item with flow style."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""build:
  commands:
    - pip install uv
    - uv sync
    - uv run mkdocs build
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("build.commands[1]", {"cmd": "uv sync", "args": ["--frozen"]}, style='flow')
    doc.save()

    result = yaml_file.read_text()
    expected = """build:
  commands:
    - pip install uv
    - {cmd: uv sync, args: [--frozen]}
    - uv run mkdocs build
"""
    assert result == expected
