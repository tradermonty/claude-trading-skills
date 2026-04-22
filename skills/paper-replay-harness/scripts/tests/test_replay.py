"""Tests for paper-replay-harness/scripts/replay.py — pure helpers + SimBroker.

Covers the deterministic parts of the replay engine. The `run_replay()` driver
is exercised indirectly via an end-to-end integration test that builds a tiny
bars/candidates fixture.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "paper-replay-harness" / "scripts"))

import replay  # noqa: E402

# ---------- trading_days ----------


def test_trading_days_skips_weekends():
    # Mon 2026-04-20 → Mon 2026-04-27
    days = replay.trading_days(dt.date(2026, 4, 20), dt.date(2026, 4, 27))
    # Mon, Tue, Wed, Thu, Fri, Mon = 6 weekdays (skip Sat/Sun)
    assert len(days) == 6
    assert dt.date(2026, 4, 25) not in days  # Saturday
    assert dt.date(2026, 4, 26) not in days  # Sunday
    assert dt.date(2026, 4, 20) in days
    assert dt.date(2026, 4, 27) in days


def test_trading_days_single_day_weekend_returns_empty():
    # Saturday
    assert replay.trading_days(dt.date(2026, 4, 25), dt.date(2026, 4, 25)) == []


def test_trading_days_reverse_range_empty():
    assert replay.trading_days(dt.date(2026, 4, 30), dt.date(2026, 4, 20)) == []


# ---------- load_bars ----------


def test_load_bars_parses_csv(tmp_path):
    csv_text = (
        "date,open,high,low,close,volume\n"
        "2026-03-02,100.00,102.50,99.50,101.00,1500000\n"
        "2026-03-03,101.00,103.00,100.50,102.80,1800000\n"
    )
    (tmp_path / "AAPL.csv").write_text(csv_text)
    bars = replay.load_bars(tmp_path, "aapl")  # case-insensitive
    assert len(bars) == 2
    assert bars[dt.date(2026, 3, 2)]["open"] == 100.00
    assert bars[dt.date(2026, 3, 3)]["close"] == 102.80


def test_load_bars_missing_file_returns_empty(tmp_path):
    assert replay.load_bars(tmp_path, "NOPE") == {}


def test_load_bars_skips_malformed_rows(tmp_path):
    csv_text = (
        "date,open,high,low,close,volume\n"
        "2026-03-02,100,102,99,101,100\n"
        "bad-date,1,1,1,1,1\n"
        "2026-03-03,101,103,100,102,200\n"
    )
    (tmp_path / "MSFT.csv").write_text(csv_text)
    bars = replay.load_bars(tmp_path, "MSFT")
    assert len(bars) == 2


# ---------- load_candidates_for_day ----------


def test_load_candidates_list_format(tmp_path):
    day = dt.date(2026, 4, 21)
    data = [{"ticker": "AAPL", "primary_screener": "vcp-screener"}]
    (tmp_path / f"candidates_{day.isoformat()}.json").write_text(json.dumps(data))
    assert replay.load_candidates_for_day(tmp_path, day) == data


def test_load_candidates_dict_format(tmp_path):
    day = dt.date(2026, 4, 21)
    data = {"candidates": [{"ticker": "AAPL"}]}
    (tmp_path / f"candidates_{day.isoformat()}.json").write_text(json.dumps(data))
    out = replay.load_candidates_for_day(tmp_path, day)
    assert out == [{"ticker": "AAPL"}]


def test_load_candidates_missing_file_returns_empty(tmp_path):
    day = dt.date(2026, 4, 21)
    assert replay.load_candidates_for_day(tmp_path, day) == []


def test_load_candidates_corrupt_file_returns_empty(tmp_path):
    day = dt.date(2026, 4, 21)
    (tmp_path / f"candidates_{day.isoformat()}.json").write_text("{not json")
    assert replay.load_candidates_for_day(tmp_path, day) == []


def test_load_candidates_wrong_shape_returns_empty(tmp_path):
    day = dt.date(2026, 4, 21)
    (tmp_path / f"candidates_{day.isoformat()}.json").write_text('"string-root"')
    assert replay.load_candidates_for_day(tmp_path, day) == []


# ---------- SimBroker: submit + open fill ----------


def test_submit_and_fill_at_next_open():
    b = replay.SimBroker(100_000)
    b.submit_bracket("AAPL", 10, 100.00, 97.00, 106.00, "vcp-screener")
    assert len(b.pending_buys) == 1
    assert len(b.positions) == 0

    # Next day's open is 100.50
    b._open_fill_pending(dt.date(2026, 4, 22), {"AAPL": 100.50})
    assert "AAPL" in b.positions
    assert b.positions["AAPL"]["entry"] == 100.50
    assert b.positions["AAPL"]["qty"] == 10
    assert b.cash == pytest.approx(100_000 - 10 * 100.50)
    assert b.pending_buys == []


def test_open_fill_carries_forward_when_no_bar():
    b = replay.SimBroker(100_000)
    b.submit_bracket("GOOG", 5, 50.0, 48.0, 56.0, "vcp-screener")
    # No bar for GOOG today
    b._open_fill_pending(dt.date(2026, 4, 22), {})
    # Order remains pending
    assert len(b.pending_buys) == 1
    assert len(b.positions) == 0


def test_open_fill_skips_when_cash_constrained():
    b = replay.SimBroker(1_000)  # only $1k available
    b.submit_bracket("AAPL", 100, 100.0, 95.0, 110.0, "vcp-screener")
    # Notional = $10,000 > cash → skip
    b._open_fill_pending(dt.date(2026, 4, 22), {"AAPL": 100.0})
    assert "AAPL" not in b.positions
    assert b.pending_buys == []  # dropped, not carried forward
    assert b.cash == 1_000  # unchanged


# ---------- SimBroker: exits ----------


def test_check_exits_target_hit():
    b = replay.SimBroker(100_000)
    b.positions["AAPL"] = {
        "qty": 10,
        "entry": 100.0,
        "stop": 97.0,
        "target": 106.0,
        "screener": "vcp-screener",
        "entry_date": "2026-04-21",
        "intended_entry": 100.0,
    }
    b.cash = 100_000 - 1000  # $99k after buying
    bars = {"AAPL": {"open": 101, "high": 107, "low": 101, "close": 106.5}}
    closed = b._check_exits(dt.date(2026, 4, 22), bars)
    assert len(closed) == 1
    t = closed[0]
    assert t["exit_reason"] == "target_hit"
    assert t["exit_price"] == 106.0
    # R multiple: +6 / 3 = 2.0
    assert t["r_multiple"] == 2.0
    assert t["pnl_dollars"] == 60.0
    assert "AAPL" not in b.positions
    assert b.cash == pytest.approx(99_000 + 106.0 * 10)


def test_check_exits_stop_hit():
    b = replay.SimBroker(100_000)
    b.positions["MSFT"] = {
        "qty": 10,
        "entry": 100.0,
        "stop": 97.0,
        "target": 106.0,
        "screener": "pead-screener",
        "entry_date": "2026-04-21",
        "intended_entry": 100.0,
    }
    bars = {"MSFT": {"open": 99, "high": 99.5, "low": 96.0, "close": 97.5}}
    closed = b._check_exits(dt.date(2026, 4, 22), bars)
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "stop_hit"
    assert closed[0]["r_multiple"] == -1.0


def test_check_exits_stop_wins_when_both_printed():
    """Conservative: stop wins over target if both hit same bar."""
    b = replay.SimBroker(100_000)
    b.positions["AAPL"] = {
        "qty": 10,
        "entry": 100.0,
        "stop": 97.0,
        "target": 106.0,
        "screener": "vcp-screener",
        "entry_date": "2026-04-21",
        "intended_entry": 100.0,
    }
    # Bar touched both 96 (below stop) AND 108 (above target)
    bars = {"AAPL": {"open": 101, "high": 108, "low": 96, "close": 100}}
    closed = b._check_exits(dt.date(2026, 4, 22), bars)
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "stop_hit"
    assert closed[0]["exit_price"] == 97.0


def test_check_exits_no_trigger():
    b = replay.SimBroker(100_000)
    b.positions["AAPL"] = {
        "qty": 10,
        "entry": 100.0,
        "stop": 97.0,
        "target": 106.0,
        "screener": "vcp-screener",
        "entry_date": "2026-04-21",
        "intended_entry": 100.0,
    }
    bars = {"AAPL": {"open": 100, "high": 102, "low": 99, "close": 101}}
    closed = b._check_exits(dt.date(2026, 4, 22), bars)
    assert closed == []
    assert "AAPL" in b.positions


def test_check_exits_skips_positions_without_bar():
    b = replay.SimBroker(100_000)
    b.positions["AAPL"] = {
        "qty": 10,
        "entry": 100.0,
        "stop": 97.0,
        "target": 106.0,
        "screener": "vcp-screener",
        "entry_date": "2026-04-21",
        "intended_entry": 100.0,
    }
    closed = b._check_exits(dt.date(2026, 4, 22), {})
    assert closed == []
    assert "AAPL" in b.positions


# ---------- SimBroker: mark_to_market ----------


def test_mark_to_market_uses_close_prices():
    b = replay.SimBroker(50_000)
    b.positions["AAPL"] = {
        "qty": 10,
        "entry": 100.0,
        "stop": 97.0,
        "target": 106.0,
        "screener": "vcp-screener",
        "entry_date": "2026-04-21",
        "intended_entry": 100.0,
    }
    b.positions["MSFT"] = {
        "qty": 5,
        "entry": 200.0,
        "stop": 194.0,
        "target": 218.0,
        "screener": "vcp-screener",
        "entry_date": "2026-04-21",
        "intended_entry": 200.0,
    }
    equity = b.mark_to_market({"AAPL": 105.0, "MSFT": 210.0})
    # cash 50k + (10*105) + (5*210) = 50000 + 1050 + 1050 = 52100
    assert equity == pytest.approx(52_100)


def test_mark_to_market_falls_back_to_entry_when_no_close():
    b = replay.SimBroker(10_000)
    b.positions["AAPL"] = {
        "qty": 10,
        "entry": 100.0,
        "stop": 97.0,
        "target": 106.0,
        "screener": "vcp-screener",
        "entry_date": "2026-04-21",
        "intended_entry": 100.0,
    }
    equity = b.mark_to_market({})  # no close data
    # Uses entry: 10_000 + 10 * 100 = 11_000
    assert equity == pytest.approx(11_000)


def test_snapshot_records_equity_curve():
    b = replay.SimBroker(100_000)
    b.snapshot(dt.date(2026, 4, 21), 100_000)
    b.snapshot(dt.date(2026, 4, 22), 100_250.5)
    assert len(b.equity_curve) == 2
    assert b.equity_curve[0]["equity"] == 100_000
    assert b.equity_curve[1]["equity"] == 100_250.5
    assert b.equity_curve[0]["positions"] == 0


# ---------- plan_entries ----------


def _cand(
    ticker,
    screener="vcp-screener",
    score=80,
    entry=100.0,
    stop=97.0,
    target=106.0,
    sector="Technology",
    confidence=0.7,
):
    return {
        "ticker": ticker,
        "primary_screener": screener,
        "strategy_score": score,
        "confidence": confidence,
        "entry_price": entry,
        "stop_loss": stop,
        "target": target,
        "sector": sector,
        "thesis": "test",
        "supporting_screeners": [],
    }


def _profile():
    return {
        "account_size_usd": 100_000,
        "risk_per_trade_pct": 2.0,
        "max_positions": 6,
        "max_sector_exposure_pct": 25.0,
        "max_position_size_pct": 20.0,
        "min_position_size_usd": 500,
    }


def test_plan_entries_filters_held_tickers():
    b = replay.SimBroker(100_000)
    b.positions["AAPL"] = {
        "qty": 10,
        "entry": 100.0,
        "stop": 97.0,
        "target": 106.0,
        "screener": "vcp-screener",
        "entry_date": "2026-04-21",
        "intended_entry": 100.0,
    }
    cands = [_cand("AAPL"), _cand("MSFT", entry=200.0, stop=194.0, target=218.0)]
    submits = replay.plan_entries(
        cands,
        b,
        _profile(),
        {"screeners": {}},
        {},
        regime="GOLDILOCKS",
        risk_on=70.0,
        exposure_scale=1.0,
        current_equity=100_000,
    )
    tickers = [s["ticker"] for s in submits]
    assert "AAPL" not in tickers
    assert "MSFT" in tickers


def test_plan_entries_respects_max_positions_budget():
    b = replay.SimBroker(100_000)
    # 5 already held out of max 6 => budget = 1
    for i in range(5):
        b.positions[f"T{i}"] = {
            "qty": 10,
            "entry": 50.0,
            "stop": 48.0,
            "target": 54.0,
            "screener": "vcp-screener",
            "entry_date": "2026-04-21",
            "intended_entry": 50.0,
        }
    cands = [
        _cand("A", entry=100.0, stop=97.0, target=106.0, sector="Technology"),
        _cand("B", entry=100.0, stop=97.0, target=106.0, sector="Healthcare"),
        _cand("C", entry=100.0, stop=97.0, target=106.0, sector="Financial"),
    ]
    submits = replay.plan_entries(
        cands,
        b,
        _profile(),
        {"screeners": {}},
        {},
        regime="GOLDILOCKS",
        risk_on=70.0,
        exposure_scale=1.0,
        current_equity=100_000,
    )
    assert len(submits) == 1


def test_plan_entries_enforces_sector_cap():
    b = replay.SimBroker(100_000)
    # Pre-load tech exposure close to cap: 24% of 100k = $24k
    b.positions["NVDA"] = {
        "qty": 240,
        "entry": 100.0,
        "stop": 95.0,
        "target": 115.0,
        "screener": "vcp-screener",
        "entry_date": "2026-04-21",
        "intended_entry": 100.0,
    }
    # Another Technology entry that would push past 25%
    cands = [_cand("AAPL", entry=100.0, stop=97.0, target=106.0, sector="Technology")]
    sector_map = {"NVDA": "Technology", "AAPL": "Technology"}
    submits = replay.plan_entries(
        cands,
        b,
        _profile(),
        {"screeners": {}},
        sector_map,
        regime="GOLDILOCKS",
        risk_on=70.0,
        exposure_scale=1.0,
        current_equity=100_000,
    )
    assert submits == []


# ---------- aggregate_stats ----------


def _trade(ticker, pnl, r, screener="vcp-screener"):
    return {
        "ticker": ticker,
        "pnl_dollars": pnl,
        "r_multiple": r,
        "screener": screener,
        "entry_date": "2026-04-21",
        "exit_date": "2026-04-22",
        "entry_price": 100,
        "exit_price": 100 + pnl / 10,
        "qty": 10,
        "exit_reason": "target_hit",
    }


def test_aggregate_stats_basic():
    b = replay.SimBroker(100_000)
    b.closed_trades = [
        _trade("A", 600, 2.0),
        _trade("B", -300, -1.0),
        _trade("C", 900, 1.5, screener="pead-screener"),
    ]
    b.equity_curve = [
        {"date": "2026-04-21", "equity": 100_000, "cash": 100_000, "positions": 0},
        {"date": "2026-04-22", "equity": 100_300, "cash": 100_000, "positions": 0},
        {"date": "2026-04-23", "equity": 99_700, "cash": 100_000, "positions": 0},
        {"date": "2026-04-24", "equity": 101_200, "cash": 101_200, "positions": 0},
    ]
    stats = replay.aggregate_stats(b, 100_000, 101_200)
    assert stats["trades_count"] == 3
    assert stats["win_rate"] == pytest.approx(2 / 3, rel=1e-3)
    # avg R: (2.0 + -1.0 + 1.5) / 3 = 0.833
    assert stats["avg_r_multiple"] == pytest.approx(0.833, abs=0.01)
    assert stats["total_return_pct"] == pytest.approx(1.2)
    # Max drawdown: peak 100_300 -> 99_700 = 0.598%
    assert stats["max_drawdown_pct"] == pytest.approx(0.598, abs=0.01)

    by_s = stats["by_strategy"]
    assert by_s["vcp-screener"]["trades"] == 2
    assert by_s["vcp-screener"]["wins"] == 1
    assert by_s["vcp-screener"]["win_rate"] == pytest.approx(0.5)
    assert by_s["vcp-screener"]["pnl_dollars"] == 300.0
    assert by_s["pead-screener"]["trades"] == 1
    assert by_s["pead-screener"]["win_rate"] == 1.0


def test_aggregate_stats_no_trades():
    b = replay.SimBroker(100_000)
    b.equity_curve = [
        {"date": "2026-04-21", "equity": 100_000, "cash": 100_000, "positions": 0},
    ]
    stats = replay.aggregate_stats(b, 100_000, 100_000)
    assert stats["trades_count"] == 0
    assert stats["win_rate"] is None
    assert stats["avg_r_multiple"] is None
    assert stats["max_drawdown_pct"] == 0
    assert stats["by_strategy"] == {}


def test_aggregate_stats_max_drawdown_on_declining_curve():
    b = replay.SimBroker(100_000)
    b.equity_curve = [
        {"date": "2026-04-21", "equity": 100_000, "cash": 100_000, "positions": 0},
        {"date": "2026-04-22", "equity": 95_000, "cash": 100_000, "positions": 0},
        {"date": "2026-04-23", "equity": 90_000, "cash": 100_000, "positions": 0},
    ]
    stats = replay.aggregate_stats(b, 100_000, 90_000)
    # Peak 100k → 90k = 10%
    assert stats["max_drawdown_pct"] == pytest.approx(10.0)
    assert stats["total_return_pct"] == pytest.approx(-10.0)


# ---------- render_markdown ----------


def test_render_markdown_contains_key_sections():
    payload = {
        "from": "2026-03-01",
        "to": "2026-03-31",
        "starting_equity": 100_000.0,
        "ending_equity": 103_250.0,
        "total_return_pct": 3.25,
        "max_drawdown_pct": 1.8,
        "trades_count": 42,
        "win_rate": 0.55,
        "avg_r_multiple": 0.7,
        "by_strategy": {
            "vcp-screener": {
                "trades": 18,
                "wins": 11,
                "win_rate": 0.61,
                "avg_r_multiple": 0.9,
                "pnl_dollars": 1650.0,
            },
        },
    }
    md = replay.render_markdown(payload)
    assert "# Replay — 2026-03-01 → 2026-03-31" in md
    assert "$100,000.00" in md
    assert "$103,250.00" in md
    assert "+3.25%" in md
    assert "1.80%" in md
    assert "42" in md  # trades count
    assert "vcp-screener" in md
    assert "$1,650.00" in md


def test_render_markdown_handles_none_stats():
    payload = {
        "from": "2026-03-01",
        "to": "2026-03-02",
        "starting_equity": 100_000.0,
        "ending_equity": 100_000.0,
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "trades_count": 0,
        "win_rate": None,
        "avg_r_multiple": None,
        "by_strategy": {},
    }
    md = replay.render_markdown(payload)
    assert "—" in md  # em dash fallback for None


# ---------- integration: run_replay end-to-end ----------


def test_run_replay_integration_small(tmp_path):
    """Tiny fixture: 3 trading days, one AAPL candidate, confirm target hit."""
    bars_dir = tmp_path / "bars"
    bars_dir.mkdir()
    cand_dir = tmp_path / "candidates"
    cand_dir.mkdir()

    # AAPL bars: entry day (open 100 after signal), runs up, target hit day 3
    (bars_dir / "AAPL.csv").write_text(
        "date,open,high,low,close,volume\n"
        "2026-03-02,99.50,100.00,99.00,99.80,1000000\n"  # signal day
        "2026-03-03,100.00,102.00,99.80,101.50,1200000\n"  # fill @ open 100
        "2026-03-04,102.00,107.00,101.50,106.80,1500000\n"  # target 106 hit
    )
    # Candidate posted on day 1 (Mon) → fills Tue open @ 100 → exits Wed @ 106
    cand = [
        {
            "ticker": "AAPL",
            "primary_screener": "vcp-screener",
            "strategy_score": 85,
            "confidence": 0.8,
            "entry_price": 100.0,
            "stop_loss": 97.0,
            "target": 106.0,
            "sector": "Technology",
            "supporting_screeners": [],
        }
    ]
    (cand_dir / "candidates_2026-03-02.json").write_text(json.dumps(cand))

    # Minimal config files
    cfg = {
        "active_profile": "test",
        "profiles": {
            "test": {
                "account_size_usd": 100_000,
                "risk_per_trade_pct": 2.0,
                "max_positions": 6,
                "max_sector_exposure_pct": 25.0,
                "max_position_size_pct": 20.0,
                "min_position_size_usd": 500,
            }
        },
    }
    cfg_path = tmp_path / "cfg.yaml"
    import yaml

    cfg_path.write_text(yaml.safe_dump(cfg))
    weights_path = tmp_path / "weights.yaml"
    weights_path.write_text("screeners:\n  vcp-screener:\n    weight: 1.0\n")
    sector_path = tmp_path / "sectors.yaml"
    sector_path.write_text("AAPL: Technology\n")

    args = argparse.Namespace(
        bars_dir=bars_dir,
        candidates_dir=cand_dir,
        from_date=dt.date(2026, 3, 2),
        to_date=dt.date(2026, 3, 4),
        config=cfg_path,
        weights=weights_path,
        sector_map=sector_path,
        regime="GOLDILOCKS",
        risk_on=70.0,
        exposure_scale=1.0,
    )
    payload = replay.run_replay(args)

    assert payload["trades_count"] == 1
    t = payload["closed_trades"][0]
    assert t["ticker"] == "AAPL"
    assert t["exit_reason"] == "target_hit"
    assert t["entry_price"] == 100.0
    assert t["exit_price"] == 106.0
    assert t["r_multiple"] == 2.0
    assert payload["ending_equity"] > payload["starting_equity"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
