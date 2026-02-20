"""Test fixtures for backtest evaluator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def evaluator_module():
    """Load evaluate_backtest.py as a module for unit tests."""
    script_path = Path(__file__).resolve().parents[1] / "evaluate_backtest.py"
    spec = importlib.util.spec_from_file_location("evaluate_backtest", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load evaluate_backtest.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
