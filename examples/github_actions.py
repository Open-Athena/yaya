#!/usr/bin/env python3
"""
Example: Update paths in GitHub Actions workflows.

This is useful when restructuring a monorepo.
"""
from pathlib import Path
from yaya import YAYA

# Create a sample workflow
workflow_yaml = """name: Test
on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: pytest src/mypackage/tests
      - name: Build
        run: |
          cd src/mypackage
          python setup.py build
"""

# Write it
workflow_file = Path('test.yaml')
workflow_file.write_text(workflow_yaml)

# Load and modify
doc = YAYA.load(workflow_file)

# Update paths from src/mypackage to lib/mypackage/src/mypackage
doc.replace_in_values('src/mypackage', 'lib/mypackage/src/mypackage')

# Save
doc.save()

# Show changes
print("Modified workflow:")
print(workflow_file.read_text())
print("\nNotice how:")
print("- Comments are preserved")
print("- Indentation is preserved")
print("- Block scalar (|) formatting is preserved")

# Clean up
workflow_file.unlink()
