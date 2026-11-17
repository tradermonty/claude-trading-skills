"""Shared fixtures for Theme Detector tests"""

import os
import sys

# Add scripts directory to path so modules can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Add tests directory to path so helpers can be imported
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _allow_small_elite_group_fixtures(monkeypatch):
    """Most tests use one- or two-row group CSVs; the row floor has its own tests."""
    import finviz_performance_client

    monkeypatch.setattr(finviz_performance_client, "ELITE_MIN_ROWS", {"sector": 1, "industry": 1})
