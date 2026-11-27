"""Shared fixtures for Technical Analyst tests."""

import os
import sys

# The skill's scripts/ directory holds weekly_price_action.py, the vendored
# _price_bars helper and the CLI; tests import them as top-level modules.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
