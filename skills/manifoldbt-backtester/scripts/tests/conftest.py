"""Shared fixtures for manifoldbt-backtester tests."""

import os
import sys

import pytest

# Ensure scripts/ is on sys.path so round_trips and bridge import cleanly.
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


@pytest.fixture
def fill():
    """Factory for one fill row, matching the engine's trade log columns.

    Usage::

        fill(side=1, price=100.0, qty=10)
    """

    def _factory(side, price, qty=1.0, symbol_id=1, fees=0.0, ts=None):
        return {
            "side": side,
            "quantity": qty,
            "fill_price": price,
            "symbol_id": symbol_id,
            "fees": fees,
            "execution_timestamp": ts,
        }

    return _factory
