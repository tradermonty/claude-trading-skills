"""6th-review safety-gap fixes (offline, deterministic)."""

from datetime import date, timedelta

from build_entry_signals import build_entry_row
from event_scanner import (
    CLEAN_CONFIRMED,
    FAILED_DEGRADED,
    ScanResult,
    apply_event_cap,
)
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


# --- High1: Step-1 not run cannot reach a PASS tier ---
def test_high1_step1_none_is_recheck():
    v = synthesize_verdict(
        step1_verdict=None,
        safety_verdict="PASS",
        event_verdict_cap=None,
        pre_order_blockers=[],
    )
    assert v.verdict == "STEP1-RECHECK" and v.t1_blocked is True


def test_high1_unknown_step1_is_recheck():
    v = synthesize_verdict(step1_verdict="WHATEVER", safety_verdict="PASS", event_verdict_cap=None)
    assert v.verdict == "STEP1-RECHECK"


def test_high1_cli_without_yield_floor_not_pass_tier():
    row = build_entry_row(
        ticker="X",
        alpha_pp=0.5,
        quote={"price": 50.0},
        profile={"sector": "Industrials"},
        key_metrics=[{"dividendYield": 0.04}],
        dividend_history=_q(date(2023, 1, 1), 13, 0.50),
        floor_pct=None,  # Step-1 gate skipped
        event_scan=ScanResult("X", CLEAN_CONFIRMED),
    )
    assert row["verdict"] == "STEP1-RECHECK"


# --- High2: missing event scan caps a TRIGGERED name ---
def test_high2_missing_scan_on_triggered_caps_hold_review():
    # Deeply in the buy zone -> TRIGGERED; no event_scan passed at all.
    row = build_entry_row(
        ticker="TRG",
        alpha_pp=0.5,
        quote={"price": 10.0},
        profile={"sector": "Industrials"},
        key_metrics=[{"dividendYield": 0.03}],
        dividend_history=_q(date(2023, 1, 1), 13, [0.10 + 0.01 * i for i in range(13)]),
        floor_pct=3.0,
        # event_scan omitted -> treated as SKIPPED
    )
    assert row["event_scan"]["result"] == "SKIPPED"
    assert row["verdict"] == "HOLD-REVIEW"
    assert row["t1_blocked"] is True
    assert "event_scan_failed_or_skipped" in row["pre_order_blockers"]


# --- High3: completed M&A from the event scan feeds WS-2 ---
def test_high3_event_completed_mna_feeds_payout_safety():
    row = build_entry_row(
        ticker="FITB",
        alpha_pp=0.5,
        quote={"price": 40.0},
        profile={"sector": "Financial Services"},
        key_metrics=[{"dividendYield": 0.035}],
        dividend_history=_q(date(2023, 1, 1), 13, 0.35),
        floor_pct=3.0,
        financials={
            "sector": "Financial Services",
            "gaap_eps": 0.60,
            "adjusted_eps": None,
            "adjusted_eps_source": "UNAVAILABLE",
        },
        event_scan=ScanResult("FITB", CLEAN_CONFIRMED, completed_mna_within_4q=True),
    )
    # GAAP distorted by the completed merger + no adjusted EPS -> HOLD-REVIEW
    assert row["payout_safety"]["safety_verdict"] == "HOLD-REVIEW"
    assert row["payout_safety"]["one_off_flag"] is True


# --- Med1: invalid result string is pessimistic, not clean ---
def test_med1_typo_result_is_pessimistic():
    # "FAILED_DEGRADED" (underscore) is NOT the valid "FAILED-DEGRADED".
    cap = apply_event_cap(ScanResult("Z", "FAILED_DEGRADED"), step5_triggered=True)
    assert cap["verdict_cap"] == "HOLD-REVIEW"
    assert "event_scan_failed_or_skipped" in cap["blockers"]


def test_med1_unknown_result_not_clean():
    cap = apply_event_cap(ScanResult("Z", "totally-bogus"), step5_triggered=False)
    assert cap["t1_blocked"] is True  # not silently clean


def test_clean_confirmed_still_clean():
    cap = apply_event_cap(ScanResult("Z", FAILED_DEGRADED), step5_triggered=False)
    assert cap["t1_blocked"] is True
    ok = apply_event_cap(ScanResult("Z", CLEAN_CONFIRMED), step5_triggered=True)
    assert ok["verdict_cap"] is None and ok["t1_blocked"] is False


# --- 7th-review: provenance.unresolved_blockers must match the full set ---
def test_provenance_unresolved_blockers_includes_event_blockers():
    row = build_entry_row(
        ticker="TRG2",
        alpha_pp=0.5,
        quote={"price": 10.0},
        profile={"sector": "Industrials"},
        key_metrics=[{"dividendYield": 0.03}],
        dividend_history=_q(date(2023, 1, 1), 13, [0.10 + 0.01 * i for i in range(13)]),
        floor_pct=3.0,
        # no event_scan -> SKIPPED -> event_scan_failed_or_skipped blocker
    )
    assert "event_scan_failed_or_skipped" in row["pre_order_blockers"]
    # Audit provenance must report the COMPLETE set, not the verdict subset.
    assert row["provenance"]["unresolved_blockers"] == row["pre_order_blockers"]
    assert "event_scan_failed_or_skipped" in row["provenance"]["unresolved_blockers"]
