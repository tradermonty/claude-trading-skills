"""Tests for execute_trade.py validation and safety logic.

No network. Mocks env vars + monkeypatches the Alpaca call.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "alpaca-executor" / "scripts"))

import execute_trade as et  # noqa: E402


@pytest.fixture
def good_cfg():
    return {
        "active_profile": "test_profile",
        "global": {
            "mode": "paper",
            "dry_run": True,
            "min_rr_ratio": 1.5,
            "trading_hours": {"start": "09:45", "end": "15:45", "timezone": "America/New_York"},
        },
        "profiles": {
            "test_profile": {
                "account_size_usd": 100000,
                "risk_per_trade_pct": 2.0,   # $2,000 max risk
                "max_daily_loss_pct": 5.0,
                "max_positions": 6,
                "max_sector_exposure_pct": 25,
                "max_position_size_pct": 20,  # $20,000 max notional
                "min_position_size_usd": 1000,
            }
        },
    }


def test_compute_client_order_id_stable():
    a = et.compute_client_order_id("AAPL", "vcp-1", "2026-04-21")
    b = et.compute_client_order_id("AAPL", "vcp-1", "2026-04-21")
    assert a == b
    assert a.startswith("ace_")


def test_compute_client_order_id_unique_per_input():
    a = et.compute_client_order_id("AAPL", "vcp-1", "2026-04-21")
    b = et.compute_client_order_id("AAPL", "vcp-1", "2026-04-22")
    c = et.compute_client_order_id("AAPL", "vcp-2", "2026-04-21")
    d = et.compute_client_order_id("MSFT", "vcp-1", "2026-04-21")
    assert len({a, b, c, d}) == 4


def test_validate_buy_good(good_cfg):
    ok, reason = et.validate_order(
        "AAPL", "buy", quantity=50, entry_price=150,
        stop_loss=145, target=165, cfg=good_cfg
    )
    # risk = 5 * 50 = 250 (below $2000), notional = 7500 (below $20000), R/R = 15/5 = 3.0
    assert ok, reason


def test_validate_rejects_stop_too_close(good_cfg):
    ok, reason = et.validate_order(
        "AAPL", "buy", quantity=50, entry_price=150,
        stop_loss=149.5, target=165, cfg=good_cfg  # 0.33% stop
    )
    assert not ok
    assert "too close" in reason


def test_validate_rejects_excess_risk(good_cfg):
    # risk per share = 10, qty = 300 = $3000 risk > $2000 max
    ok, reason = et.validate_order(
        "AAPL", "buy", quantity=300, entry_price=150,
        stop_loss=140, target=170, cfg=good_cfg
    )
    assert not ok
    assert "risk" in reason


def test_validate_rejects_oversize_position(good_cfg):
    # notional = 200 * 150 = $30000 > $20000 max position
    ok, reason = et.validate_order(
        "AAPL", "buy", quantity=200, entry_price=150,
        stop_loss=149, target=152, cfg=good_cfg
    )
    assert not ok


def test_validate_rejects_low_rr(good_cfg):
    # R/R = 1/5 = 0.2 below 1.5 min
    ok, reason = et.validate_order(
        "AAPL", "buy", quantity=50, entry_price=150,
        stop_loss=145, target=151, cfg=good_cfg
    )
    assert not ok
    assert "R/R" in reason


def test_validate_rejects_buy_with_inverted_stop(good_cfg):
    ok, reason = et.validate_order(
        "AAPL", "buy", quantity=50, entry_price=150,
        stop_loss=155, target=170, cfg=good_cfg
    )
    assert not ok
    assert "stop" in reason.lower()


def test_validate_sell_short_works(good_cfg):
    # Short: stop above entry, target below
    ok, reason = et.validate_order(
        "AAPL", "sell", quantity=50, entry_price=150,
        stop_loss=153, target=140, cfg=good_cfg
    )
    assert ok, reason


def test_validate_below_min_position_size(good_cfg):
    # 5 * 150 = $750 < $1000 min
    ok, reason = et.validate_order(
        "AAPL", "buy", quantity=5, entry_price=150,
        stop_loss=145, target=170, cfg=good_cfg
    )
    assert not ok
    assert "min" in reason.lower()


def test_safety_gate_paper_match(good_cfg, monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "true")
    ok, reason = et.safety_gate(good_cfg)
    assert ok, reason


def test_safety_gate_paper_mismatch(good_cfg, monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "false")
    ok, reason = et.safety_gate(good_cfg)
    assert not ok
    assert "paper" in reason.lower()


def test_safety_gate_live_no_checklist(good_cfg, monkeypatch, tmp_path):
    good_cfg["global"]["mode"] = "live"
    monkeypatch.setenv("ALPACA_PAPER", "false")
    monkeypatch.setenv("LIVE_TRADING_CHECKLIST_PATH", str(tmp_path / "no_such_file.md"))
    ok, reason = et.safety_gate(good_cfg)
    assert not ok
    assert "checklist" in reason.lower()


def test_safety_gate_live_with_signed_checklist(good_cfg, monkeypatch, tmp_path):
    good_cfg["global"]["mode"] = "live"
    monkeypatch.setenv("ALPACA_PAPER", "false")
    cl = tmp_path / "checklist.md"
    cl.write_text("# Live Trading Checklist\n\nsigned: true\n")
    monkeypatch.setenv("LIVE_TRADING_CHECKLIST_PATH", str(cl))
    ok, reason = et.safety_gate(good_cfg)
    assert ok, reason


def test_safety_gate_live_unsigned_checklist(good_cfg, monkeypatch, tmp_path):
    good_cfg["global"]["mode"] = "live"
    monkeypatch.setenv("ALPACA_PAPER", "false")
    cl = tmp_path / "checklist.md"
    cl.write_text("# Live Trading Checklist\n\nsigned: false\n")
    monkeypatch.setenv("LIVE_TRADING_CHECKLIST_PATH", str(cl))
    ok, reason = et.safety_gate(good_cfg)
    assert not ok


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
