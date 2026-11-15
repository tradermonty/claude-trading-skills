from datetime import date, timedelta

import pytest
from dividend_basis import analyze_dividends, step1_decision
from payout_safety import assess_payout_safety
from verdict import synthesize_verdict


def consumer(**changes):
    args = dict(
        sector="Consumer Defensive",
        annual_dividend=2.0,
        gaap_eps=4.0,
        adjusted_eps=4.0,
        adjusted_eps_source="MANUAL",
        fcf_per_share=5.0,
    )
    args.update(changes)
    return assess_payout_safety(**args)


def final(a):
    return synthesize_verdict(
        step1_verdict="STEP1-PASS",
        safety_verdict=a.safety_verdict,
        event_verdict_cap=None,
        pre_order_blockers=a.blockers,
    ).verdict


@pytest.mark.parametrize("field", ["gaap_eps", "adjusted_eps", "fcf_per_share"])
@pytest.mark.parametrize("value", [-4.0, 0.0, float("nan"), float("inf"), True])
def test_invalid_cover_never_clean(field, value):
    a = consumer(**{field: value})
    assert a.safety_verdict in ("FAIL", "HOLD-REVIEW")
    assert a.reasons and a.blockers
    assert final(a) != "CLEAN-PASS"


def test_original_negative_case():
    a = consumer(gaap_eps=-4.0, adjusted_eps=-4.0, fcf_per_share=-4.0)
    assert a.adjusted_eps_payout is None
    assert final(a) != "CLEAN-PASS"


@pytest.mark.parametrize(
    "cet1,cre",
    [
        (0, "high"),
        (0.069, "low"),
        (0.12, "high"),
        (float("nan"), "low"),
        (0.12, "unknown"),
        (12, "low"),
    ],
)
def test_unhealthy_bank_never_clean(cet1, cre):
    a = assess_payout_safety(
        sector="Financial Services",
        annual_dividend=1.0,
        gaap_eps=4.0,
        bank_metrics={"cet1": cet1, "cre_concentration": cre},
    )
    assert a.safety_verdict != "PASS"
    assert a.reasons and a.blockers
    assert final(a) != "CLEAN-PASS"


def test_healthy_controls():
    assert final(consumer()) == "CLEAN-PASS"
    a = assess_payout_safety(
        sector="Financial Services",
        annual_dividend=1.0,
        gaap_eps=4.0,
        bank_metrics={"cet1": 0.12, "cre_concentration": "low"},
    )
    assert final(a) == "CLEAN-PASS"


def test_recent_cut_above_prior_year_blocks_step1():
    amounts = [0.25] * 4 + [0.40] * 3 + [0.35]
    history = [
        {
            "date": (date(2023, 1, 1) + timedelta(days=91 * i)).isoformat(),
            "dividend": v,
            "original_dividend": v,
            "original_currency": "USD",
            "original_dividend_source": "synthetic issuer declaration",
        }
        for i, v in enumerate(amounts)
    ]
    b = analyze_dividends(history, price=20, floor_pct=1.0)
    assert b.cut_flag
    assert "sequential_regular_rate_cut" in b.reasons
    assert step1_decision(b, 1.0)[0] == "FAIL"


def test_bank_reports_both_capital_and_cre_reasons():
    a = assess_payout_safety(
        sector="banks",
        annual_dividend=1.0,
        gaap_eps=4.0,
        bank_metrics={"cet1": 0, "cre_concentration": "high"},
    )
    assert "bank_capital_weak" in a.blockers
    assert "bank_cre_concentration_high" in a.blockers


@pytest.mark.parametrize("sector", ["banks", "utilities", "insurers"])
def test_sector_negative_income_anchor_holds(sector):
    a = assess_payout_safety(sector=sector, annual_dividend=1.0, gaap_eps=-4.0)
    assert a.safety_verdict == "HOLD-REVIEW"
    assert a.gaap_eps_payout is None


def test_cet1_floor_boundary():
    for cet1, expected in [(0.069999, "CAUTION"), (0.07, "PASS")]:
        a = assess_payout_safety(
            sector="banks",
            annual_dividend=1.0,
            gaap_eps=4.0,
            bank_metrics={"cet1": cet1, "cre_concentration": "low"},
        )
        assert a.safety_verdict == expected


def dividend_fixture(amounts, days=91):
    return [
        {
            "date": (date(2023, 1, 1) + timedelta(days=days * i)).isoformat(),
            "dividend": value,
            "original_dividend": value,
            "original_currency": "USD",
            "original_dividend_source": "synthetic issuer declaration",
        }
        for i, value in enumerate(amounts)
    ]


@pytest.mark.parametrize("n", [1, 2, 3])
def test_recent_cut_persists_through_flat_payments(n):
    b = analyze_dividends(
        dividend_fixture([0.25] * 4 + [0.4] + [0.35] * n), price=20.0, floor_pct=1.0
    )
    assert b.cut_flag
    assert step1_decision(b, 1.0)[0] == "FAIL"


def test_small_fx_like_decline_does_not_hard_fail_as_cut():
    b = analyze_dividends(dividend_fixture([0.53] * 4 + [0.55, 0.53]), price=20.0, floor_pct=1.0)
    assert not b.cut_flag
    assert step1_decision(b, 1.0)[0] != "FAIL"


def test_repeated_semiannual_interim_final_pattern_is_not_a_cut():
    b = analyze_dividends(
        dividend_fixture([0.4, 0.6] * 4 + [0.4], days=182), price=20.0, floor_pct=1.0
    )
    assert b.cadence == "semiannual"
    assert not b.cut_flag
    assert not b.variable_policy_flag
    assert step1_decision(b, 1.0)[0] != "FAIL"


@pytest.mark.parametrize("latest,cut", [(0.381, False), (0.38, False), (0.379, True)])
def test_material_cut_relative_boundary(latest, cut):
    b = analyze_dividends(dividend_fixture([0.25] * 4 + [0.4, latest]), price=20.0)
    assert b.cut_flag is cut


def test_cut_expires_outside_trailing_year_and_clears_on_recovery():
    for amounts in ([0.25] * 4 + [0.4] + [0.35] * 6, [0.25] * 4 + [0.4, 0.35, 0.4]):
        b = analyze_dividends(dividend_fixture(amounts), price=20.0)
        assert not b.cut_flag


def test_semiannual_material_annual_reduction_is_still_detected():
    b = analyze_dividends(dividend_fixture([0.4, 0.6] * 4 + [0.3], days=182), price=20.0)
    assert b.cut_flag
