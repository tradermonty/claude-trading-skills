"""Tests for eod-reconciliation/scripts/run_eod.py — pure helpers."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "eod-reconciliation" / "scripts"))

import run_eod as eod  # noqa: E402

# ---------- classify_order ----------


def test_classify_filled():
    assert eod.classify_order({"status": "filled"}) == "filled"


def test_classify_partial_from_alpaca_status():
    assert eod.classify_order({"status": "partially_filled"}) == "partial"


def test_classify_partial_when_canceled_with_fills():
    o = {"status": "canceled", "qty": "100", "filled_qty": "40"}
    assert eod.classify_order(o) == "partial"


def test_classify_canceled_no_fills():
    o = {"status": "canceled", "qty": "100", "filled_qty": "0"}
    assert eod.classify_order(o) == "canceled"


def test_classify_rejected():
    assert eod.classify_order({"status": "rejected"}) == "rejected"


def test_classify_expired():
    assert eod.classify_order({"status": "expired", "qty": "5", "filled_qty": "0"}) == "expired"


def test_classify_pending_variants():
    for s in ("new", "accepted", "pending_new", "pending_cancel"):
        assert eod.classify_order({"status": s}) == "pending"


def test_classify_unknown():
    assert eod.classify_order({}) == "unknown"


# ---------- compute_slippage ----------


def test_slippage_buy_worse_fill():
    # paid $100.10 when intending $100.00 -> +0.10 slippage
    assert eod.compute_slippage(100.0, 100.10, "buy") == 0.1


def test_slippage_buy_better_fill():
    assert eod.compute_slippage(100.0, 99.95, "buy") == -0.05


def test_slippage_sell_worse_fill():
    # intended $100.00, got $99.80 -> +0.20 (worse)
    assert eod.compute_slippage(100.0, 99.80, "sell") == 0.20


def test_slippage_handles_none():
    assert eod.compute_slippage(100.0, None, "buy") is None
    assert eod.compute_slippage(None, 100.0, "buy") is None  # type: ignore[arg-type]


def test_slippage_handles_bad_string():
    assert eod.compute_slippage("bad", 100.0, "buy") is None  # type: ignore[arg-type]


# ---------- match_decisions_to_orders ----------


def _decision(
    coid, ticker="AAPL", screener="vcp-screener", entry=100.0, side="buy", action="submit"
):
    return {
        "action": action,
        "ticker": ticker,
        "primary_screener": screener,
        "entry_price": entry,
        "side": side,
        "client_order_id": coid,
        "quantity": 10,
    }


def _order(
    coid, ticker="AAPL", status="filled", filled_qty="10", qty="10", avg="100.05", side="buy"
):
    return {
        "id": "alp_" + coid[-6:],
        "client_order_id": coid,
        "symbol": ticker,
        "status": status,
        "qty": qty,
        "filled_qty": filled_qty,
        "filled_avg_price": avg,
        "side": side,
        "submitted_at": "2026-04-21T14:00:00Z",
        "filled_at": "2026-04-21T14:00:05Z",
    }


def test_match_by_coid_fills():
    d = [_decision("ace_abc123")]
    o = [_order("ace_abc123")]
    m = eod.match_decisions_to_orders(d, o)
    assert len(m) == 1
    assert m[0]["unmatched"] is False
    assert m[0]["classification"] == "filled"
    assert m[0]["filled_avg_price"] == 100.05
    # buy slippage = 100.05 - 100.00 = 0.05
    assert m[0]["slippage_per_share"] == 0.05


def test_match_unmatched_decision():
    d = [_decision("ace_unmatched")]
    o = [_order("ace_other")]
    m = eod.match_decisions_to_orders(d, o)
    assert m[0]["unmatched"] is True
    assert m[0]["classification"] == "unmatched"
    assert m[0]["order"] is None


def test_match_multiple_mixed():
    d = [_decision("ace_1"), _decision("ace_2", ticker="MSFT")]
    o = [
        _order("ace_1"),
        _order("ace_2", ticker="MSFT", status="rejected", filled_qty="0", avg=None),
    ]
    m = eod.match_decisions_to_orders(d, o)
    cls = [x["classification"] for x in m]
    assert cls == ["filled", "rejected"]


# ---------- classification_counts ----------


def test_counts_aggregates_matches():
    matches = [
        {"classification": "filled"},
        {"classification": "filled"},
        {"classification": "rejected"},
        {"classification": "unmatched"},
    ]
    c = eod.classification_counts(matches)
    assert c == {"filled": 2, "rejected": 1, "unmatched": 1}


# ---------- compute_attribution ----------


def test_attribution_buckets_by_screener():
    matches = [
        {"decision": _decision("x1", screener="vcp-screener"), "classification": "filled"},
        {"decision": _decision("x2", screener="vcp-screener"), "classification": "rejected"},
        {"decision": _decision("x3", screener="pead-screener"), "classification": "filled"},
    ]
    closed = [{"primary_screener": "pead-screener", "realized_pnl_usd": 320.0}]
    attr = eod.compute_attribution(matches, closed)
    assert attr["vcp-screener"]["submits"] == 2
    assert attr["vcp-screener"]["fills"] == 1
    assert attr["vcp-screener"]["rejects"] == 1
    assert attr["vcp-screener"]["open_positions"] == 1
    assert attr["pead-screener"]["fills"] == 1
    assert attr["pead-screener"]["realized_pnl_usd"] == 320.0
    # pead closed => open_positions should decrement to 0
    assert attr["pead-screener"]["open_positions"] == 0


def test_attribution_handles_empty():
    assert eod.compute_attribution([], []) == {}


def test_attribution_rounds_pnl():
    closed = [{"primary_screener": "x", "realized_pnl_usd": 123.4567}]
    attr = eod.compute_attribution([], closed)
    assert attr["x"]["realized_pnl_usd"] == 123.46


# ---------- list_iteration_audits + load_iteration_decisions ----------


def test_list_iteration_audits_returns_empty_if_missing(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert eod.list_iteration_audits(missing, dt.date(2026, 4, 21)) == []


def test_list_iteration_audits_matches_date_prefix(tmp_path):
    today = dt.date(2026, 4, 21)
    # Matching
    (tmp_path / f"iter_loop_{today}T14-00-00Z_executed.json").write_text("{}")
    (tmp_path / f"iter_loop_{today}T14-05-00Z_blocked_macro.json").write_text("{}")
    # Non-matching
    (tmp_path / "iter_loop_2026-04-20T14-00-00Z_executed.json").write_text("{}")

    paths = eod.list_iteration_audits(tmp_path, today)
    assert len(paths) == 2


def test_load_iteration_decisions_flattens_and_carries_meta(tmp_path):
    iter_a = {
        "iteration_id": "loop_A",
        "started_at": "2026-04-21T14:00:00Z",
        "decisions": [
            {"ticker": "AAPL", "action": "submit", "client_order_id": "ace_1"},
            {"ticker": "MSFT", "action": "skip_sector_cap"},
        ],
    }
    iter_b = {
        "iteration_id": "loop_B",
        "started_at": "2026-04-21T14:05:00Z",
        "decisions": [
            {"ticker": "GOOG", "action": "submit", "client_order_id": "ace_2"},
        ],
    }
    (tmp_path / "iter_loop_2026-04-21T14-00-00Z.json").write_text(json.dumps(iter_a))
    (tmp_path / "iter_loop_2026-04-21T14-05-00Z.json").write_text(json.dumps(iter_b))

    paths = sorted(tmp_path.glob("*.json"))
    flat = eod.load_iteration_decisions(paths)
    assert len(flat) == 3
    assert flat[0]["iteration_id"] == "loop_A"
    assert flat[2]["iteration_id"] == "loop_B"


def test_load_iteration_decisions_skips_corrupt(tmp_path):
    good = {"iteration_id": "loop_A", "decisions": [{"action": "submit"}]}
    (tmp_path / "good.json").write_text(json.dumps(good))
    (tmp_path / "bad.json").write_text("{not valid json")

    flat = eod.load_iteration_decisions(sorted(tmp_path.glob("*.json")))
    assert len(flat) == 1


def test_extract_submit_decisions_filters():
    d = [
        {"action": "submit"},
        {"action": "submit_failed"},
        {"action": "skip_budget_exhausted"},
        {"action": "plan_submit"},
    ]
    out = eod.extract_submit_decisions(d)
    actions = [x["action"] for x in out]
    assert actions == ["submit", "submit_failed"]


# ---------- load_sod_snapshot ----------


def test_load_sod_snapshot_present(tmp_path):
    date = dt.date(2026, 4, 21)
    p = tmp_path / f"sod_{date.isoformat()}.json"
    p.write_text(json.dumps({"equity": 100000.0}))
    sod = eod.load_sod_snapshot(tmp_path, date)
    assert sod is not None
    assert sod["equity"] == 100000.0


def test_load_sod_snapshot_missing(tmp_path):
    assert eod.load_sod_snapshot(tmp_path, dt.date(2026, 4, 21)) is None


# ---------- render_markdown ----------


def test_render_markdown_contains_all_sections():
    payload = {
        "date": "2026-04-21",
        "sod_equity": 100000.0,
        "eod_equity": 100850.0,
        "day_pnl_usd": 850.0,
        "day_pnl_pct": 0.85,
        "iterations_count": 78,
        "submits_attempted": 4,
        "open_positions": 5,
        "fills": {"filled": 3, "canceled": 1},
        "by_strategy": {
            "vcp-screener": {
                "submits": 2,
                "fills": 2,
                "realized_pnl_usd": 0.0,
                "open_positions": 2,
            },
        },
        "closed_positions": [
            {
                "ticker": "AAPL",
                "thesis_id": "th_x",
                "realized_pnl_usd": 320,
                "r_multiple": 1.2,
                "postmortem_path": "state/journal/pm_th_x.md",
            }
        ],
        "warnings": ["test warning"],
    }
    md = eod.render_markdown(payload)
    assert "# End-of-Day Reconciliation — 2026-04-21" in md
    assert "$850.00" in md
    assert "vcp-screener" in md
    assert "AAPL" in md
    assert "1.2R" in md
    assert "test warning" in md


def test_render_markdown_handles_empty_closed_and_warnings():
    payload = {
        "date": "2026-04-21",
        "sod_equity": 100000.0,
        "eod_equity": 100000.0,
        "day_pnl_usd": 0.0,
        "day_pnl_pct": 0.0,
        "iterations_count": 0,
        "submits_attempted": 0,
        "open_positions": 0,
        "fills": {},
        "by_strategy": {},
        "closed_positions": [],
        "warnings": [],
    }
    md = eod.render_markdown(payload)
    assert "## Closed Positions" not in md
    assert "## Warnings" not in md


# ---------- write_reports ----------


def test_write_reports_creates_md_and_json(tmp_path):
    payload = {
        "date": "2026-04-21",
        "sod_equity": 100000.0,
        "eod_equity": 100100.0,
        "day_pnl_usd": 100.0,
        "day_pnl_pct": 0.1,
        "iterations_count": 1,
        "submits_attempted": 0,
        "open_positions": 0,
        "fills": {},
        "by_strategy": {},
        "closed_positions": [],
        "warnings": [],
    }
    md, js = eod.write_reports(payload, tmp_path)
    assert md.exists() and js.exists()
    parsed = json.loads(js.read_text())
    assert parsed["day_pnl_usd"] == 100.0
    assert "End-of-Day" in md.read_text()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
