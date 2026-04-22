"""Tests for screener_adapters: fixture JSON -> normalized candidate list."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "trade-loop-orchestrator" / "scripts"))

import screener_adapters as sa  # noqa: E402


def test_vcp_adapter_parses_valid_row(tmp_path):
    import datetime as dt
    today = dt.date.today().isoformat()
    p = tmp_path / f"vcp_screener_{today}.json"
    p.write_text(json.dumps({
        "as_of": today,
        "candidates": [
            {"ticker": "AAPL", "pivot_price": 185.00, "stop_price": 179.50,
             "target_price": 198.00, "score": 82, "confidence": 0.85,
             "sector": "Technology", "atr": 3.1, "base_count": 3}
        ]
    }))
    out = sa.adapt_vcp_screener(tmp_path)
    assert len(out) == 1
    c = out[0]
    assert c["ticker"] == "AAPL"
    assert c["primary_screener"] == "vcp-screener"
    assert c["side"] == "buy"
    assert c["entry_type"] == "limit"
    assert c["entry_price"] == 185.0
    assert c["sector"] == "Technology"
    assert c["strategy_score"] == 82


def test_vcp_adapter_missing_dir_ok(tmp_path):
    out = sa.adapt_vcp_screener(tmp_path / "does_not_exist")
    assert out == []


def test_vcp_adapter_skips_malformed_rows(tmp_path):
    p = tmp_path / "vcp_screener_2020-01-01.json"
    p.write_text(json.dumps({"candidates": [
        {"ticker": "AAPL"},  # missing required pivot_price
        {"ticker": "MSFT", "pivot_price": 300, "stop_price": 290,
         "target_price": 320, "score": 75}
    ]}))
    out = sa.adapt_vcp_screener(tmp_path)
    assert len(out) == 1
    assert out[0]["ticker"] == "MSFT"


def test_pead_adapter_filters_by_state(tmp_path):
    import datetime as dt
    today = dt.date.today().isoformat()
    p = tmp_path / f"pead_{today}.json"
    p.write_text(json.dumps({"candidates": [
        {"ticker": "AAA", "state": "BREAKOUT",
         "breakout_price": 50, "red_candle_low": 47, "target_price": 56, "score": 70},
        {"ticker": "BBB", "state": "SIGNAL_READY",
         "breakout_price": 30, "red_candle_low": 28, "target_price": 34, "score": 65},
        {"ticker": "CCC", "state": "EXPIRED",
         "breakout_price": 10, "red_candle_low": 9, "target_price": 12, "score": 60},
    ]}))
    out = sa.adapt_pead_screener(tmp_path)
    tickers = [c["ticker"] for c in out]
    assert "AAA" in tickers
    assert "BBB" in tickers
    assert "CCC" not in tickers


def test_earnings_adapter_filters_grade(tmp_path):
    p = tmp_path / "earnings_trade_2020-01-01.json"
    p.write_text(json.dumps({"candidates": [
        {"ticker": "A", "grade": "A", "entry_price": 100,
         "stop_price": 94, "target_price": 110},
        {"ticker": "B", "grade": "B", "entry_price": 100,
         "stop_price": 94, "target_price": 110},
        {"ticker": "C", "grade": "C", "entry_price": 100,
         "stop_price": 94, "target_price": 110},
    ]}))
    out = sa.adapt_earnings_trade_analyzer(tmp_path)
    tickers = [c["ticker"] for c in out]
    assert tickers == ["A", "B"]


def test_kanchi_adapter(tmp_path):
    import datetime as dt
    today = dt.date.today().isoformat()
    p = tmp_path / f"kanchi_entry_signals_{today}.json"
    p.write_text(json.dumps({"entries": [
        {"ticker": "JNJ", "entry_price": 160, "stop_price": 154,
         "target_price": 172, "score": 75, "sector": "Healthcare"},
    ]}))
    out = sa.adapt_kanchi_dividend(tmp_path)
    assert len(out) == 1
    assert out[0]["primary_screener"] == "kanchi-dividend-sop"
    assert out[0]["sector"] == "Healthcare"


def test_rsm_adapter_parses_entry_ready(tmp_path):
    import datetime as dt
    today = dt.date.today().isoformat()
    p = tmp_path / f"rsm_scanner_{today}.json"
    p.write_text(json.dumps({
        "as_of": today,
        "benchmark": "SPY",
        "candidates": [
            {"ticker": "AAPL", "rs_score": 92, "status": "entry_ready",
             "entry_price": 185.4, "stop_loss": 175.3, "target": 205.6,
             "sector": "Technology", "strategy_score": 92,
             "confidence": 0.78, "side": "buy", "entry_type": "market",
             "notes": "RS 92 leader at MA20 pullback"},
            {"ticker": "MSFT", "rs_score": 88, "status": "watchlist",
             "entry_price": 400.0, "stop_loss": 380.0, "target": 440.0,
             "sector": "Technology", "strategy_score": 88,
             "confidence": 0.75, "side": "buy", "entry_type": "market"},
        ]
    }))
    out = sa.adapt_rsm_scanner(tmp_path)
    # Only entry_ready is forwarded
    assert len(out) == 1
    c = out[0]
    assert c["ticker"] == "AAPL"
    assert c["primary_screener"] == "rsm-scanner"
    assert c["entry_type"] == "market"
    assert c["strategy_score"] == 92
    assert c["sector"] == "Technology"


def test_rsm_adapter_missing_dir_ok(tmp_path):
    out = sa.adapt_rsm_scanner(tmp_path / "does_not_exist")
    assert out == []


def test_rsm_adapter_skips_bad_rows(tmp_path):
    import datetime as dt
    today = dt.date.today().isoformat()
    p = tmp_path / f"rsm_scanner_{today}.json"
    p.write_text(json.dumps({
        "candidates": [
            {"ticker": "OK", "status": "entry_ready",
             "entry_price": 100.0, "stop_loss": 95.0, "target": 110.0},
            {"ticker": "BAD", "status": "entry_ready"},  # missing prices
        ]
    }))
    out = sa.adapt_rsm_scanner(tmp_path)
    assert len(out) == 1
    assert out[0]["ticker"] == "OK"


def test_load_all_respects_enabled_list(tmp_path):
    import datetime as dt
    today = dt.date.today().isoformat()
    (tmp_path / f"vcp_screener_{today}.json").write_text(json.dumps({
        "candidates": [{"ticker": "AAPL", "pivot_price": 100,
                        "stop_price": 95, "target_price": 110, "score": 80}]
    }))
    (tmp_path / f"canslim_{today}.json").write_text(json.dumps({
        "candidates": [{"ticker": "MSFT", "entry_price": 100,
                        "stop_price": 95, "target_price": 115, "score": 80}]
    }))
    out = sa.load_all_candidates(tmp_path, enabled_screeners=["vcp-screener"])
    tickers = [c["ticker"] for c in out]
    assert tickers == ["AAPL"]


def test_load_all_handles_empty_dir(tmp_path):
    out = sa.load_all_candidates(tmp_path, enabled_screeners=None)
    assert out == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
