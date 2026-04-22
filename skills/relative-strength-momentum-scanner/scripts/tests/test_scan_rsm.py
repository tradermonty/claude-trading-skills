"""Tests for relative-strength-momentum-scanner/scripts/scan_rsm.py."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "relative-strength-momentum-scanner" / "scripts"))

import scan_rsm  # noqa: E402


# ---------- load_universe ----------

def test_load_universe_parses_lines(tmp_path):
    p = tmp_path / "u.txt"
    p.write_text("# comment\nAAPL\nmsft\n\n# AMZN skipped?\nAMZN\nAAPL\n")
    out = scan_rsm.load_universe(p)
    # Dedup, uppercase, skip blanks and comments
    assert out == ["AAPL", "MSFT", "AMZN"]


def test_load_universe_missing(tmp_path):
    assert scan_rsm.load_universe(tmp_path / "missing.txt") == []


# ---------- load_bars ----------

def test_load_bars_sorts_ascending(tmp_path):
    (tmp_path / "AAPL.csv").write_text(
        "date,open,high,low,close,volume\n"
        "2026-03-03,101,103,100,102,100\n"
        "2026-03-02,100,102,99,101,100\n"
    )
    rows = scan_rsm.load_bars(tmp_path, "AAPL")
    assert [r["date"] for r in rows] == [dt.date(2026, 3, 2), dt.date(2026, 3, 3)]


def test_load_bars_missing_returns_empty(tmp_path):
    assert scan_rsm.load_bars(tmp_path, "NOPE") == []


# ---------- trim_to_as_of ----------

def test_trim_to_as_of():
    rows = [
        {"date": dt.date(2026, 3, 1), "close": 100},
        {"date": dt.date(2026, 3, 15), "close": 110},
        {"date": dt.date(2026, 4, 1), "close": 120},
    ]
    out = scan_rsm.trim_to_as_of(rows, dt.date(2026, 3, 20))
    assert len(out) == 2
    assert out[-1]["date"] == dt.date(2026, 3, 15)


def test_trim_to_as_of_none_passthrough():
    rows = [{"date": dt.date(2026, 3, 1), "close": 100}]
    assert scan_rsm.trim_to_as_of(rows, None) is rows


# ---------- return_over_n ----------

def _bars(prices):
    """Build rows from a list of closes."""
    base = dt.date(2025, 1, 1)
    return [
        {"date": base + dt.timedelta(days=i), "open": p, "high": p,
         "low": p, "close": p, "volume": 1000}
        for i, p in enumerate(prices)
    ]


def test_return_over_n_basic():
    # 100 -> 110 is +10%
    rows = _bars([100, 105, 110])
    assert scan_rsm.return_over_n(rows, 2) == pytest.approx(10.0)


def test_return_over_n_insufficient_history():
    rows = _bars([100, 101])
    assert scan_rsm.return_over_n(rows, 5) is None


def test_return_over_n_zero_start_price():
    rows = _bars([0, 100, 110])
    assert scan_rsm.return_over_n(rows, 2) is None


# ---------- moving_average ----------

def test_moving_average():
    rows = _bars([100, 102, 104, 106, 108])
    # MA5 = 104
    assert scan_rsm.moving_average(rows, 5) == pytest.approx(104)


def test_moving_average_insufficient():
    rows = _bars([100, 102])
    assert scan_rsm.moving_average(rows, 5) is None


# ---------- high_over_n / swing_low_over_n ----------

def test_high_over_n_uses_highs():
    rows = _bars([100, 110, 105])
    # high == close in the helper; 110 is max
    assert scan_rsm.high_over_n(rows, 3) == 110


def test_swing_low_over_n_uses_lows():
    rows = _bars([100, 95, 98])
    assert scan_rsm.swing_low_over_n(rows, 3) == 95


# ---------- composite_rs ----------

def test_composite_rs_weights():
    # 0.4*10 + 0.2*5 + 0.2*5 + 0.2*5 = 4 + 1 + 1 + 1 = 7
    assert scan_rsm.composite_rs(10, 5, 5, 5) == pytest.approx(7.0)


# ---------- percentile_rank ----------

def test_percentile_rank_basic():
    vals = [10.0, 50.0, 20.0, 30.0, 40.0]
    r = scan_rsm.percentile_rank(vals)
    # 10 is lowest -> rank 1; 50 is highest -> rank 99
    assert r[0] == 1  # 10.0
    assert r[1] == 99  # 50.0
    # 30 is median
    assert 40 <= r[3] <= 60


def test_percentile_rank_empty():
    assert scan_rsm.percentile_rank([]) == {}


def test_percentile_rank_single_element():
    r = scan_rsm.percentile_rank([42.0])
    # Single element -> rank 1 (only defined floor)
    assert r[0] == 1


# ---------- Gates ----------

def test_passes_trend_filter_all_good():
    assert scan_rsm.passes_trend_filter(
        close=100, ma50=90, ma200=80, high_52w=105) is True


def test_trend_filter_fails_below_ma50():
    assert scan_rsm.passes_trend_filter(
        close=85, ma50=90, ma200=80, high_52w=105) is False


def test_trend_filter_fails_ma50_below_ma200():
    assert scan_rsm.passes_trend_filter(
        close=100, ma50=80, ma200=90, high_52w=105) is False


def test_trend_filter_fails_far_from_52w_high():
    # Close = 100 but 52w high = 120 → 100/120 = 83% → fails 90% gate
    assert scan_rsm.passes_trend_filter(
        close=100, ma50=90, ma200=80, high_52w=120) is False


def test_trend_filter_none_inputs():
    assert scan_rsm.passes_trend_filter(100, None, 80, 105) is False


def test_pullback_ready_at_ma20():
    # close within 2% of MA20, MA20 > MA50
    assert scan_rsm.is_pullback_ready(close=100.5, ma20=100.0, ma50=95.0) is True


def test_pullback_ready_too_far_from_ma20():
    assert scan_rsm.is_pullback_ready(close=110, ma20=100, ma50=95) is False


def test_pullback_ready_ma20_below_ma50():
    assert scan_rsm.is_pullback_ready(close=100, ma20=95, ma50=96) is False


# ---------- compute_ticker ----------

def test_compute_ticker_insufficient_history():
    bench = _bars([100] * 252)
    assert scan_rsm.compute_ticker(_bars([100] * 100), bench) is None


def test_compute_ticker_full_history():
    # 300 days: ticker flat around 100, benchmark flat at 100.
    # -> all relative returns = 0, composite raw = 0.
    bench = _bars([100] * 300)
    rows = _bars([100] * 300)
    m = scan_rsm.compute_ticker(rows, bench)
    assert m is not None
    assert m["rel_63"] == pytest.approx(0)
    assert m["rel_252"] == pytest.approx(0)
    assert m["ma50"] == pytest.approx(100)
    assert m["high_52w"] == 100


def test_compute_ticker_uptrend_positive_relative():
    # Benchmark flat at 100, ticker rises linearly from 100 to 200 over 300 days.
    bench = _bars([100] * 300)
    prices = [100 + (i * 100 / 299) for i in range(300)]
    rows = _bars(prices)
    m = scan_rsm.compute_ticker(rows, bench)
    assert m is not None
    # Ticker outperformed benchmark -> positive rel_returns
    assert m["rel_252"] > 0
    assert m["rel_63"] > 0
    assert m["composite_raw"] > 0
    assert m["close"] > m["ma50"] > m["ma200"]


# ---------- build_candidate ----------

def test_build_candidate_entry_ready():
    # Construct metrics that pass trend + pullback filters
    metrics = {
        "close": 100.5,
        "ma20": 100.0, "ma50": 90.0, "ma200": 80.0,
        "high_52w": 105.0, "swing_low_20d": 95.0,
        "rel_63": 12.0, "rel_126": 8.0, "rel_189": 6.0, "rel_252": 20.0,
        "composite_raw": 11.2,
    }
    cand = scan_rsm.build_candidate("AAPL", metrics, rs_score=92, sector="Technology")
    assert cand["status"] == "entry_ready"
    assert cand["primary_screener"] == "rsm-scanner"
    # stop_loss = max(MA50=90, swing=95) * 0.99 = 95 * 0.99 = 94.05
    assert cand["stop_loss"] == pytest.approx(94.05)
    assert cand["entry_price"] == 100.5
    # 2R target: entry + 2 * (100.5 - 94.05) = 100.5 + 12.9 = 113.4
    assert cand["target"] == pytest.approx(113.4)
    assert cand["rs_score"] == 92
    assert cand["confidence"] > 0.7


def test_build_candidate_watchlist_when_far_from_ma20():
    metrics = {
        "close": 103.0,  # >2% from MA20
        "ma20": 100.0, "ma50": 90.0, "ma200": 80.0,
        "high_52w": 105.0, "swing_low_20d": 95.0,
        "rel_63": 10.0, "rel_126": 5.0, "rel_189": 3.0, "rel_252": 15.0,
        "composite_raw": 8.0,
    }
    cand = scan_rsm.build_candidate("AAPL", metrics, rs_score=75, sector=None)
    assert cand["status"] == "watchlist"


def test_build_candidate_filtered_when_below_ma50():
    metrics = {
        "close": 88.0,  # below MA50
        "ma20": 90.0, "ma50": 90.0, "ma200": 80.0,
        "high_52w": 95.0, "swing_low_20d": 85.0,
        "rel_63": 2.0, "rel_126": 1.0, "rel_189": 0.0, "rel_252": 5.0,
        "composite_raw": 1.6,
    }
    cand = scan_rsm.build_candidate("X", metrics, rs_score=50, sector=None)
    assert cand["status"] == "filtered"


# ---------- run_scan (integration) ----------

def _write_ramp(path, n=300, start=100.0, end=150.0):
    prices = [start + i * (end - start) / (n - 1) for i in range(n)]
    base = dt.date(2025, 1, 1)
    lines = ["date,open,high,low,close,volume"]
    for i, p in enumerate(prices):
        d = base + dt.timedelta(days=i)
        lines.append(f"{d.isoformat()},{p:.4f},{p:.4f},{p:.4f},{p:.4f},1000000")
    path.write_text("\n".join(lines) + "\n")


def test_run_scan_integration(tmp_path):
    bars_dir = tmp_path / "bars"
    bars_dir.mkdir()
    # Benchmark: flat around 100
    base = dt.date(2025, 1, 1)
    (bars_dir / "SPY.csv").write_text(
        "date,open,high,low,close,volume\n"
        + "\n".join(
            f"{(base + dt.timedelta(days=i)).isoformat()},100,101,99,100,1000000"
            for i in range(300)
        ) + "\n"
    )
    # AAPL: strong uptrend
    _write_ramp(bars_dir / "AAPL.csv", n=300, start=100, end=180)
    # MSFT: weaker uptrend
    _write_ramp(bars_dir / "MSFT.csv", n=300, start=100, end=115)
    # LOSER: downtrend — should be filtered
    _write_ramp(bars_dir / "LOSER.csv", n=300, start=100, end=70)

    payload = scan_rsm.run_scan(
        tickers=["AAPL", "MSFT", "LOSER"],
        bars_dir=bars_dir,
        benchmark="SPY",
        as_of=None,
        sector_map={"AAPL": "Technology", "MSFT": "Technology"},
    )

    tickers = [c["ticker"] for c in payload["candidates"]]
    # LOSER is filtered out (downtrend)
    assert "LOSER" not in tickers
    # AAPL should rank above MSFT
    assert tickers.index("AAPL") < tickers.index("MSFT")
    # AAPL's RS score should be 99 (top of 3 evaluated)
    aapl = next(c for c in payload["candidates"] if c["ticker"] == "AAPL")
    assert aapl["rs_score"] == 99
    assert aapl["primary_screener"] == "rsm-scanner"
    assert aapl["sector"] == "Technology"


def test_run_scan_raises_on_short_benchmark(tmp_path):
    bars_dir = tmp_path / "bars"
    bars_dir.mkdir()
    # Too few bars for benchmark
    (bars_dir / "SPY.csv").write_text(
        "date,open,high,low,close,volume\n2026-01-01,100,100,100,100,100\n"
    )
    with pytest.raises(SystemExit):
        scan_rsm.run_scan(
            tickers=["AAPL"], bars_dir=bars_dir,
            benchmark="SPY", as_of=None, sector_map={},
        )


# ---------- render_markdown ----------

def test_render_markdown_contains_sections():
    payload = {
        "as_of": "2026-04-21", "benchmark": "SPY",
        "universe_size": 50, "evaluated": 48,
        "entry_ready_count": 12, "watchlist_count": 9,
        "candidates": [{
            "ticker": "AAPL", "rs_score": 99, "status": "entry_ready",
            "close": 185.4, "entry_price": 185.4,
            "stop_loss": 175.3, "target": 205.6,
            "sector": "Technology",
        }],
    }
    md = scan_rsm.render_markdown(payload)
    assert "# Relative Strength Momentum Scan — 2026-04-21" in md
    assert "SPY" in md
    assert "AAPL" in md
    assert "99" in md
    assert "entry_ready" in md


# ---------- CSV output roundtrip ----------

def test_run_scan_output_json_is_serializable(tmp_path):
    bars_dir = tmp_path / "bars"
    bars_dir.mkdir()
    (bars_dir / "SPY.csv").write_text(
        "date,open,high,low,close,volume\n"
        + "\n".join(
            f"{(dt.date(2025, 1, 1) + dt.timedelta(days=i)).isoformat()},100,101,99,100,1000000"
            for i in range(300)
        ) + "\n"
    )
    _write_ramp(bars_dir / "AAPL.csv", n=300, start=100, end=160)
    payload = scan_rsm.run_scan(["AAPL"], bars_dir, "SPY", None, {})
    text = json.dumps(payload, default=str)
    parsed = json.loads(text)
    assert parsed["benchmark"] == "SPY"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
