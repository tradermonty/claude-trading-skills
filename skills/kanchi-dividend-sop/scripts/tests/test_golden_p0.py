"""WS-7a: P0 GOLDEN REGRESSION GATE (end-to-end, offline, deterministic).

This module is the merge gate for P0 (CR-1 fix): it pins the end-to-end
build_entry_row verdict for every known-hard case that previously produced
a wrong call. A future SOP/threshold edit that regresses any of these MUST
fail here. No live FMP / WebSearch — all inputs are frozen fixtures.

# DATA-DATE: 2026-05-17
# VALID-UNTIL: 2026-08-31
# REVIEW-TRIGGER: CMCSA dividend restart, CFR dividend change,
#                 MKC-Unilever close (~mid-2027), FITB post-Comerica normalize
"""

from datetime import date, timedelta

from build_entry_signals import build_entry_row
from event_scanner import MAJOR_EVENT, ScanResult


def _q(start: date, n: int, amounts, step=91):
    return [
        {
            "date": (start + timedelta(days=step * i)).isoformat(),
            "dividend": (amounts[i] if isinstance(amounts, list) else amounts),
            "label": "cash",
        }
        for i in range(n)
    ]


def _verdict(**kw):
    return build_entry_row(alpha_pp=0.5, key_metrics=[{"dividendYield": 0.04}], **kw)


# --- CALM: variable dividend policy -> FAIL ---
def test_golden_calm_fail():
    hist = _q(
        date(2023, 2, 1),
        12,
        [0.006, 0.116, 0.755, 0.77, 0.997, 1.019, 1.378, 1.489, 3.495, 2.354, 0.723, 0.357],
    )
    row = _verdict(
        ticker="CALM",
        quote={"price": 76.88},
        profile={"sector": "Consumer Defensive"},
        dividend_history=hist,
        floor_pct=4.0,
    )
    assert row["verdict"] == "FAIL"


# --- ORI: specials removed before variable test; not a CALM-style payer ---
def test_golden_ori_special_not_variable():
    reg = _q(date(2023, 12, 1), 9, [0.245, 0.265, 0.265, 0.265, 0.265, 0.29, 0.29, 0.29, 0.315])
    reg += [
        {"date": "2025-01-03", "dividend": 2.00, "label": "cash"},
        {"date": "2026-01-02", "dividend": 2.50, "label": "cash"},
    ]
    row = _verdict(
        ticker="ORI",
        quote={"price": 39.32},
        profile={"sector": "Insurance"},
        dividend_history=reg,
        floor_pct=3.0,
    )
    db = row["dividend_basis"]
    assert db["special_dividend_flag"] is True
    assert db["variable_policy_flag"] is False
    assert row["verdict"] != "FAIL"  # not wrongly killed as variable


# --- CMCSA: 2026 freeze + strong safety -> CONDITIONAL-PASS (income cash-cow) ---
def test_golden_cmcsa_freeze_conditional_pass():
    hist = _q(date(2022, 3, 1), 13, 0.33)  # multi-year flat
    row = _verdict(
        ticker="CMCSA",
        quote={"price": 24.76},
        profile={"sector": "Communication Services"},
        dividend_history=hist,
        floor_pct=4.0,
        financials={
            "sector": "Communication Services",
            "gaap_eps": 4.2,
            "adjusted_eps": 4.2,
            "adjusted_eps_source": "FMP",
            "fcf_per_share": 4.5,
        },
    )
    assert row["dividend_basis"]["freeze_flag"] is True
    assert row["verdict"] == "CONDITIONAL-PASS"


# --- MKC: pending mega-merger -> HOLD-REVIEW + T1 blocked ---
def test_golden_mkc_event_hold_review():
    hist = _q(date(2023, 1, 1), 13, 0.45)
    row = _verdict(
        ticker="MKC",
        quote={"price": 46.35},
        profile={"sector": "Consumer Defensive"},
        dividend_history=hist,
        floor_pct=3.0,
        event_scan=ScanResult(
            ticker="MKC", result=MAJOR_EVENT, pending_mna=True, reasons=["tx_value_280pct_mcap"]
        ),
    )
    assert row["verdict"] == "HOLD-REVIEW"
    assert row["t1_blocked"] is True
    assert "major_structural_event" in row["pre_order_blockers"]


# --- CFR D5: stale 2.97% would FAIL; latest declared $1.03 -> STEP1-RECHECK ---
def test_golden_cfr_d5_recheck_not_fail():
    hist = _q(date(2023, 5, 30), 13, [1.00] * 12 + [1.03])
    row = _verdict(
        ticker="CFR",
        quote={"price": 134.70},
        profile={"sector": "Financial Services"},
        dividend_history=hist,
        floor_pct=3.0,
    )
    assert row["verdict"] == "STEP1-RECHECK"  # NOT FAIL (the D5 bug)
    assert row["t1_blocked"] is True


# --- recent cut -> FAIL (distinct from freeze) ---
def test_golden_recent_cut_fail():
    hist = _q(date(2023, 1, 1), 12, [0.50] * 8 + [0.40] * 4)
    row = _verdict(
        ticker="CUTX",
        quote={"price": 30.0},
        profile={"sector": "Industrials"},
        dividend_history=hist,
        floor_pct=3.0,
    )
    assert row["dividend_basis"]["cut_flag"] is True
    assert row["verdict"] == "FAIL"
