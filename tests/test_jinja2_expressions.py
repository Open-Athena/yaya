"""
Tests for handling GitHub Actions jinja2 expressions in YAML.

GitHub Actions uses jinja2-like syntax (${{ ... }}) which contains curly braces
that would normally be YAML flow indicators. We need special handling to not
treat these as flow syntax.
"""
import pytest
from yaya import YAYA


def test_add_key_after_with_jinja2_expression(tmp_path):
    """Test that add_key_after preserves jinja2 expressions like ${{ ... }}."""
    yaml_file = tmp_path / "workflow.yaml"
    yaml_file.write_text("""jobs:
  build-package:
    runs-on: ubuntu-latest
    if: ${{  github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success'}}
    steps:
      - name: Checkout code
""")

    doc = YAYA.load(yaml_file)

    # Add defaults after the 'if' key
    doc.add_key_after(
        "jobs.build-package.if",
        "defaults",
        {"run": {"working-directory": "lib/levanter"}}
    )

    doc.save()
    result = yaml_file.read_text()

    # Verify the jinja2 expression wasn't corrupted
    doc2 = YAYA.load(yaml_file)
    if_value = doc2.get_path('jobs.build-package.if')
    defaults_value = doc2.get_path('jobs.build-package.defaults.run.working-directory')

    assert if_value == "${{  github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success'}}"
    assert defaults_value == "lib/levanter"
    assert "{{" not in defaults_value  # Ensure no corruption leaked


def test_replace_in_values_with_jinja2(tmp_path):
    """Test that replace_in_values replaces everywhere (including jinja2)."""
    yaml_file = tmp_path / "workflow.yaml"
    yaml_file.write_text("""jobs:
  test:
    runs-on: ubuntu-latest
    if: ${{ github.ref == 'refs/heads/main' }}
    steps:
      - run: echo "main branch"
""")

    doc = YAYA.load(yaml_file)

    # replace_in_values replaces EVERYWHERE, including inside jinja2
    doc.replace_in_values("main", "production")

    doc.save()

    doc2 = YAYA.load(yaml_file)
    if_value = doc2.get_path('jobs.test.if')
    run_value = doc2.get_path('jobs.test.steps[0].run')

    # Both should be updated (replace_in_values is global)
    assert if_value == "${{ github.ref == 'refs/heads/production' }}"
    assert run_value == 'echo "production branch"'


# NOTE: Additional edge cases like nested jinja2 or complex expressions
# may have other issues and are not tested here. The main bug (corruption
# when adding keys after jinja2 expressions) is fixed and tested above.


def test_jinja2_with_logical_operators(tmp_path):
    """Test jinja2 expressions with logical operators (||, &&)."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""jobs:
  test:
    if: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}
    runs-on: ubuntu-latest
""")

    doc = YAYA.load(yaml_file)

    # Replace key value
    doc.replace_key("jobs.test.runs-on", "ubuntu-22.04")

    doc.save()

    doc2 = YAYA.load(yaml_file)
    if_value = doc2.get_path("jobs.test.if")

    # Should preserve the && operator and entire expression
    assert if_value == "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
    assert doc2.get_path("jobs.test.runs-on") == "ubuntu-22.04"
