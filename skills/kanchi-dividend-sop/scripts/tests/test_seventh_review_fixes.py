"""7th-review fixes: trailing-median special, MD/CSV surfacing, safety=None."""

import csv
from datetime import date, timedelta

from build_entry_signals import build_entry_row, render_markdown, write_csv
from dividend_basis import analyze_dividends
from event_scanner import CLEAN_CONFIRMED, ScanResult
from verdict import synthesize_verdict


def _q(start, n, amt, step=91):
    return [
        {
            "date": (start + timedelta(days=step * i)).isoformat(),
            "dividend": (amt[i] if isinstance(amt, list) else amt),
            "label": "cash",
        }
        for i in range(n)
    ]


# --- Blocker1: long-term regular growth must NOT be flagged special ---
def test_long_term_regular_growth_not_marked_special():
    hist = _q(
        date(2018, 1, 1),
        16,
        [
            0.10,
            0.10,
            0.11,
            0.12,
            0.13,
            0.14,
            0.15,
            0.16,
            0.18,
            0.20,
            0.22,
            0.24,
            0.26,
            0.28,
            0.30,
            0.33,
        ],
    )
    b = analyze_dividends(hist, price=25.0, floor_pct=3.0)
    assert b.special_dividend_flag is False
    assert b.latest_declared_dividend == 0.33  # not collapsed to a stale amount


def test_true_special_still_detected_against_local_median():
    # Steady ~0.30 regular with a single 1.50 spike -> still special.
    amts = [0.30] * 11 + [1.50] + [0.30]
    b = analyze_dividends(_q(date(2022, 1, 1), 13, amts), price=40.0, floor_pct=3.0)
    assert b.special_dividend_flag is True
    assert b.variable_policy_flag is False


# --- Blocker2: Markdown + CSV surface verdict / t1_blocked / blockers ---
def _row_triggered_skipped():
    return build_entry_row(
        ticker="TRG",
        alpha_pp=0.5,
        quote={"price": 10.0},
        profile={"sector": "Industrials"},
        key_metrics=[{"dividendYield": 0.03}],
        dividend_history=_q(date(2023, 1, 1), 13, [0.10 + 0.01 * i for i in range(13)]),
        floor_pct=3.0,  # no event_scan -> SKIPPED -> HOLD-REVIEW + T1 block
    )


def test_markdown_surfaces_verdict_and_blockers():
    md = render_markdown([_row_triggered_skipped()], as_of="2026-05-17", alpha_pp=0.5)
    assert "Verdict" in md and "T1 Blocked" in md and "Pre-order Blockers" in md
    assert "HOLD-REVIEW" in md
    assert "event_scan_failed_or_skipped" in md


def test_csv_surfaces_verdict_and_blockers(tmp_path):
    p = tmp_path / "out.csv"
    write_csv([_row_triggered_skipped()], p)
    rows = list(csv.DictReader(p.open()))
    r = rows[0]
    assert r["verdict"] == "HOLD-REVIEW"
    assert r["t1_blocked"] in ("True", "true", "1")
    assert "event_scan_failed_or_skipped" in r["pre_order_blockers"]
    assert "event_scan_result" in r and "step1_verdict" in r


# --- Medium: safety_verdict None must not be CLEAN-PASS by default ---
def test_safety_none_defaults_hold_review():
    v = synthesize_verdict(
        step1_verdict="STEP1-PASS",
        safety_verdict=None,
        event_verdict_cap=None,
        pre_order_blockers=[],
    )
    assert v.verdict == "HOLD-REVIEW"
    assert "payout_safety_not_evaluated" in v.reasons


def test_safety_none_allowed_when_require_safety_false():
    v = synthesize_verdict(
        step1_verdict="STEP1-PASS",
        safety_verdict=None,
        event_verdict_cap=None,
        pre_order_blockers=[],
        require_safety=False,
    )
    assert v.verdict == "CLEAN-PASS"


def test_library_path_no_financials_not_clean_pass():
    # build_entry_row with financials omitted: Step-2 not evaluated.
    row = build_entry_row(
        ticker="LIB",
        alpha_pp=0.5,
        quote={"price": 20.0},
        profile={"sector": "Industrials"},
        key_metrics=[{"dividendYield": 0.05}],
        dividend_history=_q(date(2022, 1, 1), 13, 0.20),
        floor_pct=3.0,
        event_scan=ScanResult("LIB", CLEAN_CONFIRMED),
    )
    assert row["verdict"] != "CLEAN-PASS"
