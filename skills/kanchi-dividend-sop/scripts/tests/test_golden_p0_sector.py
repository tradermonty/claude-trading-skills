"""WS-7b: expanded sector-dispatch golden gate (end-to-end, offline).

Locks WS-2/WS-4 sector behaviour through build_entry_row so a future
threshold/dispatch edit cannot silently regress the bank / utility /
insurer paths that the 2026-05 runs got wrong.

# DATA-DATE: 2026-05-17
# VALID-UNTIL: 2026-08-31
# REVIEW-TRIGGER: OZK credit-trend reversal, WTRG/AWK close, ORI special cadence
"""

from datetime import date, timedelta

from build_entry_signals import build_entry_row
from event_scanner import CLEAN_CONFIRMED, ScanResult

# Step 4b ran clean — required for a PASS tier on a TRIGGERED name.
_CLEAN = ScanResult(ticker="_", result=CLEAN_CONFIRMED)


def _q(start, n, amt, step=91):
    amounts = amt if isinstance(amt, list) else [amt] * n
    return [
        {
            "date": (start + timedelta(days=step * i)).isoformat(),
            "dividend": amounts[i],
            "label": "cash",
        }
        for i in range(n)
    ]


_RAISER = [0.40, 0.41, 0.42, 0.43, 0.43, 0.44, 0.45, 0.46, 0.46, 0.47, 0.48, 0.49, 0.50]


# OZK-style: strong serial raiser but deteriorating credit -> PASS-CAUTION.
def test_ws7b_bank_credit_deterioration_pass_caution():
    hist = _q(date(2023, 1, 1), 13, _RAISER)
    row = build_entry_row(
        ticker="OZK",
        alpha_pp=0.5,
        quote={"price": 46.73},
        profile={"sector": "Financial Services"},
        key_metrics=[{"dividendYield": 0.04}],
        dividend_history=hist,
        floor_pct=3.0,
        financials={
            "sector": "Financial Services",
            "gaap_eps": 6.17,
            "adjusted_eps": 6.17,
            "adjusted_eps_source": "FMP",
            "fcf_per_share": -50.0,  # must be ignored for a bank
            "bank_metrics": {
                "cet1": 0.11,
                "cre_concentration": "high",
                "npl_trend": "deteriorating",
                "nco_trend": "deteriorating",
            },
        },
        event_scan=_CLEAN,
    )
    assert row["payout_safety"]["sector_kind"] == "bank"
    assert row["verdict"] == "PASS-CAUTION"
    assert "bank_npl_nco_deteriorating" in row["pre_order_blockers"]


# EXC-style regulated utility: structurally negative FCF must NOT auto-FAIL.
def test_ws7b_utility_negative_fcf_not_fail():
    hist = _q(date(2023, 1, 1), 13, _RAISER)
    row = build_entry_row(
        ticker="EXC",
        alpha_pp=0.5,
        quote={"price": 43.38},
        profile={"sector": "Utilities"},
        key_metrics=[{"dividendYield": 0.037}],
        dividend_history=hist,
        floor_pct=3.0,
        financials={
            "sector": "Utilities",
            "gaap_eps": 2.74,
            "adjusted_eps": 2.74,
            "adjusted_eps_source": "FMP",
            "fcf_per_share": -3.0,
            "utility_metrics": {"ffo_to_debt": 0.16, "rate_case_status": "constructive"},
        },
        event_scan=_CLEAN,
    )
    assert row["payout_safety"]["sector_kind"] == "utility"
    assert row["verdict"] in ("CLEAN-PASS", "PASS-CAUTION")  # NOT FAIL


# ORI-style insurer: regular yield clears the 3% floor; specials excluded.
def test_ws7b_insurer_regular_yield_passes_floor():
    reg = _q(date(2023, 12, 1), 10, 0.30)
    reg.append({"date": "2026-01-02", "dividend": 2.50, "label": "cash"})  # special
    row = build_entry_row(
        ticker="ORI",
        alpha_pp=0.5,
        quote={"price": 37.0},
        profile={"sector": "Insurance"},
        key_metrics=[{"dividendYield": 0.032}],
        dividend_history=reg,
        floor_pct=3.0,
        financials={
            "sector": "Insurance",
            "gaap_eps": 3.7,
            "adjusted_eps": 3.7,
            "adjusted_eps_source": "FMP",
            "insurer_metrics": {
                "combined_ratio": 0.95,
                "reserve_development": "favorable",
                "statutory_capital": "strong",
            },
        },
        event_scan=_CLEAN,
    )
    db = row["dividend_basis"]
    assert db["special_dividend_flag"] is True
    assert db["variable_policy_flag"] is False
    assert row["verdict"] != "FAIL"  # not a trap; insurer-module review path
