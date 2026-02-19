"""Pytest configuration for theme-detector tests."""

import os
import sys

# Add scripts directory to path so calculators, scorer, etc. are importable
scripts_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
)
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)
