"""Tests for kill-switch check_limits.py.

Pure unit tests on the check helpers. No network, no subprocess.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "kill-switch" / "scripts"))

import check_limits as cl  # noqa: E402


# ---------- daily_loss ----------

def test_daily_loss_within_limit():
    r = cl.check_daily_loss(current_equity=99000, sod_equity=100000,
                            max_daily_loss_pct=5.0)
    assert r["status"] == "ok"
    assert r["value_pct"] == -1.0


def test_daily_loss_at_limit_breaches():
    r = cl.check_daily_loss(current_equity=95000, sod_equity=100000,
                            max_daily_loss_pct=5.0)
    assert r["status"] == "BREACH"
    assert r["severity"] == "hard"
    assert "5.00%" in r["message"]


def test_daily_loss_exceeds_limit():
    r = cl.check_daily_loss(current_equity=94500, sod_equity=100000,
                            max_daily_loss_pct=5.0)
    assert r["status"] == "BREACH"
    assert r["value_pct"] == -5.5


def test_daily_loss_skipped_when_sod_missing():
    r = cl.check_daily_loss(current_equity=100000, sod_equity=0,
                            max_daily_loss_pct=5.0)
    assert r["status"] == "skipped"


def test_daily_loss_positive_pnl_ok():
    r = cl.check_daily_loss(current_equity=103000, sod_equity=100000,
                            max_daily_loss_pct=5.0)
    assert r["status"] == "ok"
    assert r["value_pct"] == 3.0


# ---------- position_count ----------

def test_position_count_under_cap():
    positions = [{"symbol": s} for s in ["AAPL", "MSFT", "NVDA"]]
    r = cl.check_position_count(positions, max_positions=6)
    assert r["status"] == "ok"
    assert r["value"] == 3


def test_position_count_at_cap_breaches():
    positions = [{"symbol": s} for s in ["A", "B", "C", "D", "E", "F"]]
    r = cl.check_position_count(positions, max_positions=6)
    assert r["status"] == "BREACH"
    assert r["severity"] == "soft"


def test_position_count_empty():
    r = cl.check_position_count([], max_positions=6)
    assert r["status"] == "ok"
    assert r["value"] == 0


# ---------- single_position_size ----------

def test_single_position_within_cap():
    positions = [
        {"symbol": "AAPL", "market_value": "15000"},
        {"symbol": "MSFT", "market_value": "10000"},
    ]
    r = cl.check_single_position_size(positions, account_equity=100000,
                                      max_position_size_pct=20.0)
    assert r["status"] == "ok"
    assert r["offenders"] == []


def test_single_position_exceeds_cap():
    positions = [
        {"symbol": "AAPL", "market_value": "25000"},  # 25% > 20%
        {"symbol": "MSFT", "market_value": "10000"},
    ]
    r = cl.check_single_position_size(positions, account_equity=100000,
                                      max_position_size_pct=20.0)
    assert r["status"] == "BREACH"
    assert r["severity"] == "soft"
    assert r["offenders"][0]["symbol"] == "AAPL"
    assert r["offenders"][0]["pct_of_account"] == 25.0


def test_single_position_short_uses_abs_value():
    positions = [{"symbol": "TSLA", "market_value": "-30000"}]
    r = cl.check_single_position_size(positions, account_equity=100000,
                                      max_position_size_pct=20.0)
    assert r["status"] == "BREACH"


# ---------- sector_exposure ----------

@pytest.fixture
def sector_map():
    return {
        "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
        "JPM": "Financials", "BAC": "Financials",
        "XOM": "Energy",
    }


def test_sector_exposure_within_cap(sector_map):
    positions = [
        {"symbol": "AAPL", "market_value": "10000"},
        {"symbol": "JPM", "market_value": "8000"},
    ]
    r = cl.check_sector_exposure(positions, account_equity=100000,
                                 max_sector_exposure_pct=25.0,
                                 sector_map=sector_map)
    assert r["status"] == "ok"
    assert r["exposures_pct"]["Technology"] == 10.0
    assert r["exposures_pct"]["Financials"] == 8.0


def test_sector_exposure_breaches_when_aggregate_over_cap(sector_map):
    positions = [
        {"symbol": "AAPL", "market_value": "12000"},
        {"symbol": "MSFT", "market_value": "10000"},
        {"symbol": "NVDA", "market_value": "8000"},  # tech total = 30%
    ]
    r = cl.check_sector_exposure(positions, account_equity=100000,
                                 max_sector_exposure_pct=25.0,
                                 sector_map=sector_map)
    assert r["status"] == "BREACH"
    assert r["severity"] == "soft"
    assert any(b["sector"] == "Technology" for b in r["breaches"])


def test_sector_exposure_unknown_ticker_falls_into_unclassified(sector_map):
    positions = [
        {"symbol": "ZZZZ", "market_value": "5000"},
        {"symbol": "AAPL", "market_value": "5000"},
    ]
    r = cl.check_sector_exposure(positions, account_equity=100000,
                                 max_sector_exposure_pct=25.0,
                                 sector_map=sector_map)
    assert "Unclassified" in r["exposures_pct"]
    assert r["exposures_pct"]["Unclassified"] == 5.0


def test_sector_exposure_skipped_when_no_equity(sector_map):
    r = cl.check_sector_exposure([], account_equity=0,
                                 max_sector_exposure_pct=25.0,
                                 sector_map=sector_map)
    assert r["status"] == "skipped"


# ---------- distribution_days ----------

def test_distribution_days_no_state_file_skipped(tmp_path):
    r = cl.check_distribution_days(tmp_path / "missing.json", limit=6)
    assert r["status"] == "skipped"


def test_distribution_days_below_limit(tmp_path):
    p = tmp_path / "dd.json"
    p.write_text(json.dumps({"distribution_day_count": 4}))
    r = cl.check_distribution_days(p, limit=6)
    assert r["status"] == "ok"


def test_distribution_days_at_limit_breaches(tmp_path):
    p = tmp_path / "dd.json"
    p.write_text(json.dumps({"distribution_day_count": 6}))
    r = cl.check_distribution_days(p, limit=6)
    assert r["status"] == "BREACH"
    assert r["severity"] == "soft"


# ---------- sector_map loader ----------

def test_load_sector_map_nested_format(tmp_path):
    p = tmp_path / "map.yaml"
    p.write_text(
        "sectors:\n"
        "  Technology:\n"
        "    - aapl\n"
        "    - MSFT\n"
        "  Financials:\n"
        "    - JPM\n"
    )
    m = cl.load_sector_map(p)
    assert m["AAPL"] == "Technology"
    assert m["MSFT"] == "Technology"
    assert m["JPM"] == "Financials"


def test_load_sector_map_flat_format(tmp_path):
    p = tmp_path / "map.yaml"
    p.write_text("AAPL: Technology\nJPM: Financials\n")
    m = cl.load_sector_map(p)
    assert m["AAPL"] == "Technology"


def test_load_sector_map_missing(tmp_path):
    m = cl.load_sector_map(tmp_path / "no.yaml")
    assert m == {}


# ---------- build_status (integration of pure functions) ----------

@pytest.fixture
def profile():
    return {
        "max_daily_loss_pct": 5.0,
        "max_positions": 6,
        "max_sector_exposure_pct": 25.0,
        "max_position_size_pct": 20.0,
    }


def test_build_status_ok_state(profile, tmp_path, sector_map):
    account = {"equity": "99500", "cash": "50000", "buying_power": "100000"}
    positions = [{"symbol": "AAPL", "market_value": "10000"}]
    sod = {"equity": 100000}
    s = cl.build_status(account, positions, sod, profile, sector_map,
                        tmp_path / "no.json")
    assert s["status"] == "OK"
    assert s["account"]["pnl_pct"] == -0.5
    assert s["positions"]["count"] == 1


def test_build_status_tripped_on_daily_loss(profile, tmp_path, sector_map):
    account = {"equity": "94000", "cash": "0", "buying_power": "0"}
    positions = []
    sod = {"equity": 100000}
    s = cl.build_status(account, positions, sod, profile, sector_map,
                        tmp_path / "no.json")
    assert s["status"] == "TRIPPED"
    assert s["reason"] is not None
    assert "Daily loss" in s["reason"]


def test_build_status_warn_on_soft_breach(profile, tmp_path, sector_map):
    account = {"equity": "100000", "cash": "0", "buying_power": "0"}
    # 6 positions hits the soft cap
    positions = [{"symbol": s, "market_value": "5000"}
                 for s in ["AAPL", "MSFT", "NVDA", "JPM", "BAC", "XOM"]]
    sod = {"equity": 100000}
    s = cl.build_status(account, positions, sod, profile, sector_map,
                        tmp_path / "no.json")
    assert s["status"] == "WARN"
    assert len(s["soft_breaches"]) >= 1


def test_build_status_hard_takes_precedence_over_soft(profile, tmp_path, sector_map):
    """When daily loss is tripped AND positions are at cap, status is TRIPPED."""
    account = {"equity": "94000", "cash": "0", "buying_power": "0"}
    positions = [{"symbol": s, "market_value": "5000"}
                 for s in ["AAPL", "MSFT", "NVDA", "JPM", "BAC", "XOM"]]
    sod = {"equity": 100000}
    s = cl.build_status(account, positions, sod, profile, sector_map,
                        tmp_path / "no.json")
    assert s["status"] == "TRIPPED"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
