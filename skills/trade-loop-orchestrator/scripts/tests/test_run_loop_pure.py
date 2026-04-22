"""Tests for pure helpers in run_loop.py — sizing, sector cap, signal_id."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "trade-loop-orchestrator" / "scripts"))

import run_loop as rl  # noqa: E402


@pytest.fixture
def profile():
    return {
        "account_size_usd": 100000,
        "risk_per_trade_pct": 2.0,  # max risk $2,000
        "max_positions": 6,
        "max_position_size_pct": 20,  # max notional $20,000
        "max_sector_exposure_pct": 25,
        "min_position_size_usd": 1000,
    }


# ---------- size_position ----------


def test_size_position_normal(profile):
    qty, detail = rl.size_position(entry=100, stop=95, profile=profile, exposure_scale=1.0)
    # risk per share = 5; max risk = 2000; raw = 400 shares
    # but 400 * 100 = $40k > $20k max -> qty floored to 200
    assert qty == 200
    assert detail["notional"] == 20000.0


def test_size_position_constrained_by_risk(profile):
    qty, detail = rl.size_position(entry=100, stop=98, profile=profile, exposure_scale=1.0)
    # risk per share = 2; max risk = 2000; raw = 1000
    # 1000 * 100 = $100k > $20k -> qty = 200
    assert qty == 200


def test_size_position_scales_down_with_exposure(profile):
    qty_full, _ = rl.size_position(entry=100, stop=90, profile=profile, exposure_scale=1.0)
    qty_half, _ = rl.size_position(entry=100, stop=90, profile=profile, exposure_scale=0.5)
    assert qty_half < qty_full


def test_size_position_floors_at_quarter(profile):
    """exposure_scale below 0.25 should still allow some size."""
    qty, detail = rl.size_position(entry=100, stop=90, profile=profile, exposure_scale=0.0)
    assert detail["scaled_max_risk"] == pytest.approx(
        profile["account_size_usd"] * profile["risk_per_trade_pct"] / 100 * 0.25
    )


def test_size_position_zero_when_below_min(profile):
    # entry=100 stop=99 -> risk/share = 1, qty would be 200 (capped notional 20000)
    # but if account is tiny the min check kicks in
    small = {**profile, "account_size_usd": 100, "min_position_size_usd": 1000}
    qty, detail = rl.size_position(entry=100, stop=95, profile=small, exposure_scale=1.0)
    assert qty == 0
    assert "min" in detail["reason"]


def test_size_position_invalid_prices(profile):
    qty, detail = rl.size_position(entry=0, stop=0, profile=profile, exposure_scale=1.0)
    assert qty == 0


def test_size_position_entry_equals_stop(profile):
    qty, _ = rl.size_position(entry=100, stop=100, profile=profile, exposure_scale=1.0)
    assert qty == 0


# ---------- sector_of ----------


def test_sector_of_uses_candidate_sector_first():
    assert rl.sector_of("AAPL", "Technology", {"AAPL": "Energy"}) == "Technology"


def test_sector_of_falls_back_to_map():
    assert rl.sector_of("aapl", None, {"AAPL": "Technology"}) == "Technology"


def test_sector_of_unclassified_when_unknown():
    assert rl.sector_of("ZZZZ", None, {}) == "Unclassified"


# ---------- would_breach_sector_cap ----------


def test_sector_cap_clear():
    assert not rl.would_breach_sector_cap(
        "AAPL",
        "Technology",
        new_notional=5000,
        current_exposures={"Technology": 10000},
        account_equity=100000,
        cap_pct=25.0,
    )  # projected 15% < 25%


def test_sector_cap_breached():
    assert rl.would_breach_sector_cap(
        "AAPL",
        "Technology",
        new_notional=20000,
        current_exposures={"Technology": 10000},
        account_equity=100000,
        cap_pct=25.0,
    )  # projected 30% > 25%


def test_sector_cap_blocks_when_no_equity():
    assert rl.would_breach_sector_cap(
        "AAPL", "Technology", 5000, {}, account_equity=0, cap_pct=25.0
    )


def test_sector_cap_first_entry_in_sector():
    assert not rl.would_breach_sector_cap(
        "JPM",
        "Financials",
        new_notional=20000,
        current_exposures={},
        account_equity=100000,
        cap_pct=25.0,
    )


# ---------- signal_id ----------


def test_signal_id_stable():
    a = rl._signal_id("AAPL", "2026-04-21", "vcp-screener")
    b = rl._signal_id("AAPL", "2026-04-21", "vcp-screener")
    assert a == b
    assert len(a) == 16


def test_signal_id_unique_per_inputs():
    a = rl._signal_id("AAPL", "2026-04-21", "vcp-screener")
    b = rl._signal_id("AAPL", "2026-04-22", "vcp-screener")
    c = rl._signal_id("MSFT", "2026-04-21", "vcp-screener")
    d = rl._signal_id("AAPL", "2026-04-21", "canslim-screener")
    assert len({a, b, c, d}) == 4


# ---------- in_trading_window ----------


def test_in_trading_window_blackout():
    """Blackout check must trigger before the weekday-hours check."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    et_now = dt.datetime.now(ZoneInfo("America/New_York"))
    cfg = {
        "global": {
            "trading_hours": {"start": "09:45", "end": "15:45", "timezone": "America/New_York"},
            "blackout_dates": [et_now.date().isoformat()],
        }
    }
    inside, reason = rl.in_trading_window(cfg)
    assert not inside
    # On weekends the weekend check wins; otherwise blackout should fire
    if et_now.weekday() < 5:
        assert "blackout" in reason
    else:
        assert "weekend" in reason


def test_in_trading_window_weekend_excluded():
    """Sat/Sun should always return False with a weekend reason."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    et_now = dt.datetime.now(ZoneInfo("America/New_York"))
    if et_now.weekday() < 5:
        pytest.skip("only meaningful on weekends")
    cfg = {
        "global": {
            "trading_hours": {"start": "09:45", "end": "15:45", "timezone": "America/New_York"}
        }
    }
    inside, reason = rl.in_trading_window(cfg)
    assert not inside
    assert "weekend" in reason


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
