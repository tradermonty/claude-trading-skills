"""5th-review integration-gap fixes F1-F4 (offline, deterministic)."""

from datetime import date, timedelta

import pytest
from build_entry_signals import build_entry_row
from dividend_basis import analyze_dividends, step1_decision
from payout_safety import assess_payout_safety


def _q(start, n, amt, step=91, decl=False):
    out = []
    for i in range(n):
        rec = {
            "date": (start + timedelta(days=step * i)).isoformat(),
            "dividend": (amt[i] if isinstance(amt, list) else amt),
            "label": "cash",
        }
        if decl:
            rec["declarationDate"] = (start + timedelta(days=step * i - 30)).isoformat()
        out.append(rec)
    return out


# --- F4: confirmed-source path via declarationDate ---
def test_f4_confirmed_declaration_resolves_near_floor():
    hist = _q(date(2023, 5, 30), 13, [1.00] * 12 + [1.03], decl=True)
    b = analyze_dividends(hist, price=134.70, floor_pct=3.0)
    assert b.latest_declared_confirmed is True
    # 3.06% > 3.0 floor, borderline, but board-declared -> resolves (not stuck)
    v, _ = step1_decision(b, 3.0, source_confirmed=b.latest_declared_confirmed)
    assert v == "STEP1-PASS"


def test_f4_unconfirmed_stays_recheck():
    hist = _q(date(2023, 5, 30), 13, [1.00] * 12 + [1.03], decl=False)
    b = analyze_dividends(hist, price=134.70, floor_pct=3.0)
    assert b.latest_declared_confirmed is False
    v, _ = step1_decision(b, 3.0, source_confirmed=b.latest_declared_confirmed)
    assert v == "STEP1-RECHECK"


@pytest.mark.parametrize("declaration", ["", " ", "\t\r\n", "\u3000", "\u00a0"])
@pytest.mark.parametrize("reverse", [False, True])
def test_blank_latest_declaration_does_not_confirm_borderline_yield(declaration, reverse):
    hist = _q(date(2023, 5, 30), 13, [1.00] * 12 + [1.03], decl=True)
    hist[-1]["declarationDate"] = declaration
    if reverse:
        hist.reverse()
    basis = analyze_dividends(hist, price=134.70, floor_pct=3.0)
    assert basis.latest_declared_confirmed is False
    verdict, reason = step1_decision(basis, 3.0, source_confirmed=basis.latest_declared_confirmed)
    assert verdict == "STEP1-RECHECK"
    assert reason == "floor_borderline_confirm_latest_declared"


@pytest.mark.parametrize("reverse", [False, True])
def test_valid_latest_declaration_is_independent_of_other_rows(reverse):
    hist = _q(date(2023, 5, 30), 13, [1.00] * 12 + [1.03], decl=True)
    hist[0]["declarationDate"] = " \t"
    hist[-1]["declarationDate"] = " \t" + hist[-1]["declarationDate"] + "\n"
    if reverse:
        hist.reverse()
    basis = analyze_dividends(hist, price=134.70, floor_pct=3.0)
    assert basis.latest_declared_confirmed is True
    verdict, _ = step1_decision(basis, 3.0, source_confirmed=basis.latest_declared_confirmed)
    assert verdict == "STEP1-PASS"


def test_f4_cli_path_cfr_confirmed_not_recheck():
    hist = _q(date(2023, 5, 30), 13, [1.00] * 12 + [1.03], decl=True)
    row = build_entry_row(
        ticker="CFR",
        alpha_pp=0.5,
        quote={"price": 134.70},
        profile={"sector": "Financial Services", "industry": "Banks - Regional"},
        key_metrics=[{"dividendYield": 0.031}],
        dividend_history=hist,
        floor_pct=3.0,
    )
    assert row["step1_verdict"] == "STEP1-PASS"  # confirmed declaration


# --- F3: as_of threaded so suspension is reachable from build_entry_row ---
def test_f3_as_of_makes_suspension_reachable():
    hist = _q(date(2023, 1, 1), 12, 0.50)  # last pay ~2025-09
    row = build_entry_row(
        ticker="SUSP",
        alpha_pp=0.5,
        quote={"price": 40.0},
        profile={"sector": "Industrials"},
        key_metrics=[{"dividendYield": 0.05}],
        dividend_history=hist,
        floor_pct=3.0,
        as_of="2026-05-17",
    )
    assert row["dividend_basis"]["suspension_flag"] is True
    assert row["verdict"] == "FAIL"


# --- F2: adjusted-EPS unavailable must NOT HOLD a bank (sector is anchor) ---
def test_f2_bank_adjusted_unavailable_not_hold_review():
    a = assess_payout_safety(
        sector="financial services",
        industry="Banks - Regional",
        annual_dividend=1.88,
        gaap_eps=6.17,
        adjusted_eps=None,
        adjusted_eps_source="UNAVAILABLE",
        bank_metrics={
            "cet1": 0.11,
            "cre_concentration": "low",
            "npl_trend": "stable",
            "nco_trend": "stable",
        },
    )
    assert "adjusted_eps_unavailable" not in a.blockers
    assert a.safety_verdict == "PASS"  # sector anchor governs, not adj EPS


def test_f2_consumer_adjusted_unavailable_still_holds():
    a = assess_payout_safety(
        sector="consumer staples",
        annual_dividend=1.0,
        gaap_eps=3.0,
        adjusted_eps=None,
        adjusted_eps_source="UNAVAILABLE",
        fcf_per_share=2.5,
    )
    assert "adjusted_eps_unavailable" in a.blockers
    assert a.safety_verdict == "HOLD-REVIEW"


def test_f2_bank_deposit_beta_elevated_caution():
    a = assess_payout_safety(
        sector="banks",
        annual_dividend=1.0,
        gaap_eps=5.0,
        adjusted_eps=5.0,
        adjusted_eps_source="FMP",
        bank_metrics={
            "cet1": 0.12,
            "cre_concentration": "low",
            "npl_trend": "stable",
            "nco_trend": "stable",
            "deposit_beta": 0.7,
        },
    )
    assert a.safety_verdict == "CAUTION"
    assert "bank_deposit_beta_elevated" in a.reasons


def test_f2_utility_ffo_debt_below_min_caution():
    a = assess_payout_safety(
        sector="utilities",
        annual_dividend=1.5,
        gaap_eps=2.5,
        adjusted_eps=2.5,
        adjusted_eps_source="FMP",
        utility_metrics={"ffo_to_debt": 0.10, "rate_case_status": "constructive"},
    )
    assert "utility_ffo_debt_weak" in a.blockers
    assert a.safety_verdict == "CAUTION"


def test_f2_utility_allowed_roe_falling_caution():
    a = assess_payout_safety(
        sector="utilities",
        annual_dividend=1.5,
        gaap_eps=2.5,
        adjusted_eps=2.5,
        adjusted_eps_source="FMP",
        utility_metrics={
            "ffo_to_debt": 0.18,
            "rate_case_status": "constructive",
            "allowed_roe_trend": "falling",
        },
    )
    assert "utility_allowed_roe_falling" in a.reasons
    assert a.safety_verdict == "CAUTION"


def test_f2_insurer_operating_eps_payout_high_fails():
    a = assess_payout_safety(
        sector="insurance",
        annual_dividend=4.0,
        gaap_eps=4.0,
        adjusted_eps=4.0,
        adjusted_eps_source="FMP",
        insurer_metrics={
            "combined_ratio": 0.95,
            "reserve_development": "favorable",
            "statutory_capital": "strong",
        },
    )
    # op-EPS payout = 4.0/4.0 = 100% > 85% ceiling -> FAIL, not downgraded
    assert a.safety_verdict == "FAIL"
