"""Tests for FixtureBarsAdapter.

Fixture filtering behaviour matters because Phase 3 advances the
simulated clock between runs by varying ``until_et`` against the
*same* fixture file, so the adapter must hide bars that close after
``until_et``.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

# Add adapters/ to sys.path so the bare-name import inside
# fixture_market_data_adapter resolves.
ADAPTERS_DIR = Path(__file__).resolve().parents[1] / "adapters"
if str(ADAPTERS_DIR) not in sys.path:
    sys.path.insert(0, str(ADAPTERS_DIR))

from fixture_market_data_adapter import FixtureBarsAdapter

ET = ZoneInfo("America/New_York")


def _bar(ts: str, c: float = 100.0, v: int = 1_000_000) -> dict:
    return {"ts_et": ts, "o": c, "h": c + 0.5, "l": c - 0.5, "c": c, "v": v}


@pytest.fixture
def mixed_fixture(tmp_path):
    """A two-symbol fixture covering 09:30 → 10:00 ET."""
    payload = {
        "AAPL": [
            _bar("2026-05-05T09:30:00-04:00", 150.00),
            _bar("2026-05-05T09:35:00-04:00", 150.20),
            _bar("2026-05-05T09:40:00-04:00", 150.10),
            _bar("2026-05-05T09:45:00-04:00", 149.95),
            _bar("2026-05-05T09:50:00-04:00", 149.80),
            _bar("2026-05-05T09:55:00-04:00", 149.70),
        ],
        "NVDA": [
            _bar("2026-05-05T09:30:00-04:00", 900.0),
            _bar("2026-05-05T09:35:00-04:00", 902.5),
        ],
    }
    p = tmp_path / "bars.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class TestFiltering:
    def test_until_et_truncates_future_bars(self, mixed_fixture):
        # bar_open=09:30 closes 09:35 ≤ 09:40 ✓; 09:35 closes 09:40 ≤ 09:40 ✓;
        # 09:40 bar closes 09:45 > 09:40 ✗ (still open at 09:40).
        adapter = FixtureBarsAdapter(mixed_fixture)
        until = datetime(2026, 5, 5, 9, 40, tzinfo=ET)
        bars = adapter.get_bars_5min("AAPL", session_date="2026-05-05", until_et=until)
        assert [b["ts_et"] for b in bars] == [
            "2026-05-05T09:30:00-04:00",
            "2026-05-05T09:35:00-04:00",
        ]

    def test_unconfirmed_current_minute_bar_excluded(self, mixed_fixture):
        # The 09:35 bar covers [09:35, 09:40). At until_et=09:35 it is
        # NOT yet confirmed (it confirms at 09:40). Only the 09:30 bar
        # (which closes at 09:35) is confirmed at this clock.
        adapter = FixtureBarsAdapter(mixed_fixture)
        until = datetime(2026, 5, 5, 9, 35, tzinfo=ET)
        bars = adapter.get_bars_5min("AAPL", session_date="2026-05-05", until_et=until)
        assert [b["ts_et"] for b in bars] == ["2026-05-05T09:30:00-04:00"]

    def test_pre_open_returns_empty(self, mixed_fixture):
        adapter = FixtureBarsAdapter(mixed_fixture)
        until = datetime(2026, 5, 5, 9, 0, tzinfo=ET)
        bars = adapter.get_bars_5min("AAPL", session_date="2026-05-05", until_et=until)
        assert bars == []

    def test_unknown_symbol_returns_empty(self, mixed_fixture):
        adapter = FixtureBarsAdapter(mixed_fixture)
        until = datetime(2026, 5, 5, 16, 0, tzinfo=ET)
        bars = adapter.get_bars_5min("FAKE", session_date="2026-05-05", until_et=until)
        assert bars == []

    def test_different_session_date_excluded(self, mixed_fixture):
        adapter = FixtureBarsAdapter(mixed_fixture)
        until = datetime(2026, 5, 5, 16, 0, tzinfo=ET)
        bars = adapter.get_bars_5min("AAPL", session_date="2026-05-06", until_et=until)
        assert bars == []

    def test_naive_until_raises(self, mixed_fixture):
        adapter = FixtureBarsAdapter(mixed_fixture)
        with pytest.raises(ValueError):
            adapter.get_bars_5min(
                "AAPL", session_date="2026-05-05", until_et=datetime(2026, 5, 5, 10, 0)
            )

    def test_multi_symbol_fixture_independent(self, mixed_fixture):
        # At until_et=09:40: AAPL has 09:30/09:35 confirmed (2 bars);
        # NVDA has 09:30/09:35 confirmed (2 bars). The 09:40 bar of
        # AAPL is still open, so it's excluded.
        adapter = FixtureBarsAdapter(mixed_fixture)
        until = datetime(2026, 5, 5, 9, 40, tzinfo=ET)
        aapl = adapter.get_bars_5min("AAPL", session_date="2026-05-05", until_et=until)
        nvda = adapter.get_bars_5min("NVDA", session_date="2026-05-05", until_et=until)
        assert len(aapl) == 2
        assert len(nvda) == 2

    def test_fixture_with_naive_ts_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(
            json.dumps(
                {"AAPL": [{"ts_et": "2026-05-05T09:30:00", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]}
            ),
            encoding="utf-8",
        )
        adapter = FixtureBarsAdapter(bad)
        with pytest.raises(ValueError):
            adapter.get_bars_5min(
                "AAPL",
                session_date="2026-05-05",
                until_et=datetime(2026, 5, 5, 10, 0, tzinfo=ET),
            )

    def test_non_dict_fixture_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps([]), encoding="utf-8")
        adapter = FixtureBarsAdapter(bad)
        with pytest.raises(ValueError):
            adapter.get_bars_5min(
                "AAPL",
                session_date="2026-05-05",
                until_et=datetime(2026, 5, 5, 10, 0, tzinfo=ET),
            )
