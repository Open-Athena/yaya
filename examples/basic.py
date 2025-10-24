#!/usr/bin/env python3
"""
Basic example of using yaya.
"""
from pathlib import Path
from yaya import YAYA

# Create a sample YAML file
sample_yaml = """# Configuration file
database:
  host: prod-db-1.example.com
  port: 5432
  # Connection pool settings
  pool:
    min: 5
    max: 20
"""

# Write it
config_file = Path('config.yaml')
config_file.write_text(sample_yaml)

# Load and modify
doc = YAYA.load(config_file)

# Replace host
doc.replace_in_values('prod-db-1', 'prod-db-2')

# Save
doc.save()

# Show result
print("Modified config.yaml:")
print(config_file.read_text())

# Clean up
config_file.unlink()
