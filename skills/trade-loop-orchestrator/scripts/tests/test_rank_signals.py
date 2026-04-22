"""Tests for rank_signals.py — pure functions, no I/O."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "trade-loop-orchestrator" / "scripts"))

import rank_signals as rs  # noqa: E402


@pytest.fixture
def weights():
    return {
        "screeners": {
            "vcp-screener": {"weight": 1.0},
            "canslim-screener": {"weight": 0.85},
            "pead-screener": {"weight": 0.75},
            "earnings-trade-analyzer": {"weight": 0.7},
        },
        "regime_gates": {
            "vcp-screener": {"allowed_regimes": ["GOLDILOCKS", "REFLATION", "RECOVERY"],
                             "min_risk_on": 40},
            "canslim-screener": {"min_risk_on": 50},
        },
    }


def _cand(ticker, screener, score=70, conf=0.7, supporting=None):
    return {
        "ticker": ticker,
        "primary_screener": screener,
        "strategy_score": score,
        "confidence": conf,
        "supporting_screeners": supporting or [],
        "side": "buy", "entry_price": 100.0, "stop_loss": 95.0, "target": 110.0,
    }


def test_compute_composite_basic(weights):
    c = _cand("AAPL", "vcp-screener", score=80, conf=0.8)
    # 0.80 * 1.0 * 1.0 * 0.8 = 0.64
    assert rs.compute_composite(c, weights) == pytest.approx(0.64)


def test_compute_composite_with_supporting(weights):
    c = _cand("AAPL", "vcp-screener", score=80, conf=0.8,
              supporting=["canslim-screener", "pead-screener"])
    # bonus = 0.15 * 2 = 0.30 -> 0.64 * 1.30 = 0.832
    assert rs.compute_composite(c, weights) == pytest.approx(0.832)


def test_compute_composite_supporting_capped_at_3(weights):
    c = _cand("AAPL", "vcp-screener", score=80, conf=0.8,
              supporting=["a", "b", "c", "d", "e"])
    # bonus capped at 0.45 -> 0.64 * 1.45 = 0.928
    assert rs.compute_composite(c, weights) == pytest.approx(0.928)


def test_compute_composite_missing_weight_defaults_to_1(weights):
    c = _cand("AAPL", "unknown-screener", score=50, conf=0.5)
    # 0.50 * 1.0 (default weight) * 1.0 * 0.5 = 0.25
    assert rs.compute_composite(c, weights) == pytest.approx(0.25)


def test_dedupe_keeps_highest_composite(weights):
    cands = [
        _cand("AAPL", "vcp-screener", score=80, conf=0.8),       # 0.64
        _cand("AAPL", "canslim-screener", score=90, conf=0.9),   # 0.6885 wins
        _cand("MSFT", "pead-screener", score=70, conf=0.7),
    ]
    out = rs.dedupe_by_ticker(cands, weights)
    aapl = next(c for c in out if c["ticker"] == "AAPL")
    # canslim has higher composite, so it becomes primary
    assert aapl["primary_screener"] == "canslim-screener"
    assert "vcp-screener" in aapl["supporting_screeners"]


def test_dedupe_orders_by_composite_descending(weights):
    cands = [
        _cand("AAA", "pead-screener", score=60, conf=0.6),
        _cand("BBB", "vcp-screener", score=90, conf=0.9),
        _cand("CCC", "canslim-screener", score=70, conf=0.7),
    ]
    out = rs.dedupe_by_ticker(cands, weights)
    tickers = [c["ticker"] for c in out]
    # BBB has highest composite (0.81)
    assert tickers[0] == "BBB"


def test_apply_regime_gates_blocks_disallowed_regime(weights):
    cands = [_cand("AAPL", "vcp-screener", 80, 0.8)]
    out = rs.apply_regime_gates(cands, regime="STAGFLATION",
                                risk_on_score=50, weights_cfg=weights)
    assert out == []  # blocked by allowed_regimes


def test_apply_regime_gates_blocks_low_risk_on(weights):
    cands = [_cand("AAPL", "canslim-screener", 80, 0.8)]
    # canslim requires risk_on >= 50
    out = rs.apply_regime_gates(cands, regime="GOLDILOCKS",
                                risk_on_score=40, weights_cfg=weights)
    assert out == []


def test_apply_regime_gates_passes_when_no_rules(weights):
    cands = [_cand("XYZ", "earnings-trade-analyzer", 80, 0.8)]
    out = rs.apply_regime_gates(cands, regime="STAGFLATION",
                                risk_on_score=20, weights_cfg=weights)
    assert len(out) == 1


def test_rank_and_dedupe_end_to_end(weights):
    cands = [
        _cand("AAPL", "vcp-screener", 80, 0.8),
        _cand("AAPL", "canslim-screener", 90, 0.9),
        _cand("MSFT", "vcp-screener", 70, 0.7),
        _cand("XYZ", "vcp-screener", 95, 0.95),  # blocked under STAGFLATION
    ]
    out = rs.rank_and_dedupe(cands, weights, regime="STAGFLATION", risk_on_score=60)
    # vcp-screener blocked, canslim requires risk_on>=50 (60 ok)
    # so AAPL keeps canslim only; MSFT blocked entirely; XYZ blocked
    tickers = [c["ticker"] for c in out]
    assert tickers == ["AAPL"]
    assert out[0]["primary_screener"] == "canslim-screener"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
