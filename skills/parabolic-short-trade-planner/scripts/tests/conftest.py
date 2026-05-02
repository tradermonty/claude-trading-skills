"""Shared test fixtures for parabolic-short-trade-planner.

Conventions:
- All daily OHLCV fixtures are returned in chronological order (oldest first).
- The bar_normalizer is responsible for converting FMP's most-recent-first
  output to chronological. Calculators receive chronological input.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable as the test package root
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
CALCULATORS_DIR = SCRIPTS_DIR / "calculators"
for _p in (str(CALCULATORS_DIR), str(SCRIPTS_DIR)):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

# When the full repo test suite runs, other skills (pead-screener, vcp-screener,
# market-top-detector, ...) may have already imported their own ``calculators``
# package and ``fmp_client`` module under those exact names. Drop those entries
# from sys.modules so this skill's imports below resolve to its own files.
_NAMESPACES_TO_RESET = ("calculators", "fmp_client", "scorer", "report_generator")
for _key in [
    k
    for k in list(sys.modules)
    if k in _NAMESPACES_TO_RESET or any(k.startswith(p + ".") for p in _NAMESPACES_TO_RESET)
]:
    del sys.modules[_key]


def _make_bar(date: str, o: float, h: float, low: float, c: float, v: int) -> dict:
    return {"date": date, "open": o, "high": h, "low": low, "close": c, "volume": v}


@pytest.fixture
def parabolic_bars_chrono() -> list[dict]:
    """A 60-bar parabolic series (chronological, oldest first).

    Designed to trigger:
      - return_5d > 100%
      - 4 consecutive green days at end
      - close ~70% above 20DMA
      - volume_ratio_20d > 4
    """
    bars = []
    base_price = 30.0
    base_volume = 1_000_000
    # 50 sideways bars
    for i in range(50):
        date = f"2026-02-{(i % 28) + 1:02d}"
        bars.append(
            _make_bar(
                date,
                base_price,
                base_price + 0.5,
                base_price - 0.5,
                base_price + (0.1 if i % 2 else -0.1),
                base_volume,
            )
        )
    # 10 parabolic bars — the final 3 must accelerate further so that
    # acceleration_ratio (3-bar avg return / 10-bar avg return) > 1.5.
    prices = [32.0, 35.0, 39.0, 44.0, 50.0, 56.0, 63.0, 71.0, 80.0, 90.0]
    for i, p in enumerate(prices):
        date = f"2026-04-{i + 1:02d}"
        prev = bars[-1]["close"]
        o = prev
        c = p
        h = c + 1.0
        low = min(o, c) - 0.3
        v = base_volume * (3 + i // 2)
        bars.append(_make_bar(date, o, h, low, c, v))
    return bars


@pytest.fixture
def normal_bars_chrono() -> list[dict]:
    """A 60-bar non-parabolic series (steady uptrend, chronological)."""
    bars = []
    base_volume = 1_000_000
    for i in range(60):
        date = f"2026-02-{(i % 28) + 1:02d}" if i < 28 else f"2026-03-{(i - 27):02d}"
        price = 50.0 + i * 0.3
        bars.append(_make_bar(date, price - 0.2, price + 0.4, price - 0.4, price, base_volume))
    return bars


@pytest.fixture
def short_bars_chrono() -> list[dict]:
    """Only 20 bars — used to test handling of insufficient history.

    Range-expansion needs ``short_window + long_window + 1 = 26`` bars,
    so 20 keeps it short enough to verify the None-return path.
    """
    bars = []
    for i in range(20):
        date = f"2026-04-{i + 1:02d}"
        bars.append(_make_bar(date, 50.0, 51.0, 49.0, 50.0, 1_000_000))
    return bars


@pytest.fixture
def parabolic_bars_recent_first(parabolic_bars_chrono) -> list[dict]:
    """Same data as parabolic_bars_chrono but in most-recent-first order
    (matches raw FMP historical-price-eod/full output)."""
    return list(reversed(parabolic_bars_chrono))


@pytest.fixture
def bars_with_duplicate_dates() -> list[dict]:
    """Bars with one duplicate date — bar_normalizer should de-dup keeping
    the last occurrence (latest fetch wins)."""
    return [
        _make_bar("2026-04-01", 100, 101, 99, 100, 1_000_000),
        _make_bar("2026-04-02", 100, 101, 99, 100, 1_000_000),
        _make_bar("2026-04-02", 100, 102, 99, 101, 2_000_000),  # duplicate, newer
        _make_bar("2026-04-03", 101, 102, 100, 101, 1_000_000),
    ]


@pytest.fixture
def bars_with_gaps() -> list[dict]:
    """Bars with a date gap — bar_normalizer should warn but not drop."""
    return [
        _make_bar("2026-04-01", 100, 101, 99, 100, 1_000_000),
        _make_bar("2026-04-02", 100, 101, 99, 100, 1_000_000),
        # 04-03 missing
        _make_bar("2026-04-04", 100, 101, 99, 100, 1_000_000),
        _make_bar("2026-04-05", 100, 101, 99, 100, 1_000_000),
    ]
