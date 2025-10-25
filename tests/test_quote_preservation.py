"""
Tests for quote style preservation and proper escaping.

YAML supports single quotes, double quotes, and unquoted strings.
When values are NOT modified, their quote style should be preserved.
When values ARE modified, we need to handle escaping properly.
"""
import pytest
from yaya import YAYA


def test_preserve_unquoted_when_not_modified(tmp_path):
    """Test that unquoted values stay unquoted when not modified."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""name: simple value
other: unchanged
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("other", "modified")
    doc.save()

    result = yaml_file.read_text()
    expected = """name: simple value
other: modified
"""
    assert result == expected


def test_preserve_single_quotes_when_not_modified(tmp_path):
    """Test that single-quoted values stay single-quoted when not modified."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""name: 'single quoted'
other: unchanged
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("other", "modified")
    doc.save()

    result = yaml_file.read_text()
    expected = """name: 'single quoted'
other: modified
"""
    assert result == expected


def test_preserve_double_quotes_when_not_modified(tmp_path):
    """Test that double-quoted values stay double-quoted when not modified."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""name: "double quoted"
other: unchanged
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("other", "modified")
    doc.save()

    result = yaml_file.read_text()
    expected = """name: "double quoted"
other: modified
"""
    assert result == expected


def test_preserve_quotes_when_modified_simple(tmp_path):
    """Test that quote style is preserved when modifying simple values."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""unquoted: old value
single: 'old value'
double: "old value"
""")

    doc = YAYA.load(yaml_file)
    doc.replace_in_values("old value", "new value")
    doc.save()

    result = yaml_file.read_text()
    expected = """unquoted: new value
single: 'new value'
double: "new value"
"""
    assert result == expected


def test_single_quote_with_apostrophe(tmp_path):
    """Test that single quotes are escaped when inserting apostrophes."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""message: 'old value'
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("message", "it's new")
    doc.save()

    result = yaml_file.read_text()
    # Should escape the apostrophe: 'it''s new' OR switch to double quotes
    # Let's be flexible - either is acceptable
    assert result in [
        """message: 'it''s new'\n""",  # Escaped single quote
        """message: "it's new"\n""",   # Switched to double quotes
    ]

    # Verify it's valid YAML by reloading
    doc2 = YAYA.load(yaml_file)
    assert doc2.get_path("message") == "it's new"


def test_double_quote_with_embedded_quotes(tmp_path):
    """Test that double quotes are escaped when inserting double quotes."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""message: "old value"
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("message", 'say "hello"')
    doc.save()

    result = yaml_file.read_text()
    # Should escape: "say \"hello\"" OR switch to single quotes
    assert result in [
        """message: "say \\"hello\\""\n""",  # Escaped double quote
        """message: 'say "hello"'\n""",      # Switched to single quotes
    ]

    # Verify it's valid YAML by reloading
    doc2 = YAYA.load(yaml_file)
    assert doc2.get_path("message") == 'say "hello"'


def test_replace_in_values_with_quotes(tmp_path):
    """Test replace_in_values handles quotes properly."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""message: 'old text'
other: "old text"
""")

    doc = YAYA.load(yaml_file)
    doc.replace_in_values("old text", "it's new")
    doc.save()

    # Verify it's valid YAML by reloading
    doc2 = YAYA.load(yaml_file)
    assert doc2.get_path("message") == "it's new"
    assert doc2.get_path("other") == "it's new"


def test_unquoted_values_dont_need_quotes(tmp_path):
    """Test that values without special chars stay unquoted."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""name: old
""")

    doc = YAYA.load(yaml_file)
    doc.replace_key("name", "new")
    doc.save()

    result = yaml_file.read_text()
    expected = """name: new
"""
    assert result == expected
