"""Shared fixtures for crypto-regime-analyzer tests."""

import os
import sys

import pytest

# Ensure scripts/ is on sys.path so calculators and scorer can be imported.
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


@pytest.fixture
def trending_series():
    """Factory for a synthetic daily close series.

    Usage::

        closes = trending_series(n=400, start=100.0, daily_pct=0.3)

    Positive daily_pct produces a steady uptrend (price ends above both
    MAs with rising 200DMA); negative produces a downtrend.
    """

    def _factory(n=400, start=100.0, daily_pct=0.3):
        closes, price = [], start
        for _ in range(n):
            price *= 1 + daily_pct / 100
            closes.append(price)
        return closes

    return _factory


@pytest.fixture
def universe(trending_series):
    """Factory for a {symbol: closes} universe.

    Usage::

        series = universe(n_up=8, n_down=2)  # 80% breadth
    """

    def _factory(n_up=8, n_down=2, length=400):
        out = {}
        for i in range(n_up):
            out[f"UP{i}"] = trending_series(n=length, daily_pct=0.3)
        for i in range(n_down):
            out[f"DN{i}"] = trending_series(n=length, daily_pct=-0.3)
        return out

    return _factory
