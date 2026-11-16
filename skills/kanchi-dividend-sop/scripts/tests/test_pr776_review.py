"""Offline regressions for the four PR #776 review findings."""

import importlib.util
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import pytest
from build_entry_signals import build_entry_row
from dividend_basis import analyze_dividends, step1_decision
from verdict import synthesize_verdict


def history(amounts, days=91, native=None):
    rows = [
        {"date": (date(2023, 1, 1) + timedelta(days=i * days)).isoformat(), "dividend": a}
        for i, a in enumerate(amounts)
    ]
    if native:
        for row, amount in zip(rows, native):
            row.update(
                original_dividend=amount,
                original_currency="JPY",
                original_dividend_source="synthetic",
            )
    return rows


@pytest.mark.parametrize(
    "days,amounts",
    [
        (91, [0.5] * 7 + [0.4]),
        (91, [0.5] * 7 + [0.4] * 2),
        (30, [0.5] * 15 + [0.4]),
        (182, [0.4, 0.6] * 4 + [0.3]),
    ],
)
def test_plain_usd_cut_without_synthetic_native_metadata(days, amounts):
    basis = analyze_dividends(history(amounts, days), 20)
    assert basis.cut_flag and not basis.cut_confirmation_required
    assert basis.cut_amount_basis == "usd_history"
    assert step1_decision(basis, 0.1)[0] == "FAIL"


@pytest.mark.parametrize(
    "currency,is_adr,review",
    [
        ("JPY", False, True),
        (" usd ", False, False),
        (None, True, True),
        (None, "false", False),
        ("", False, False),
        (17, False, False),
        ("BAD!", False, False),
    ],
)
def test_currency_hint_types(currency, is_adr, review):
    basis = analyze_dividends(
        history([0.5] * 7 + [0.4]), 20, issuer_currency=currency, is_adr=is_adr
    )
    assert basis.cut_flag
    assert basis.cut_confirmation_required is review
    assert step1_decision(basis, 0.1)[0] == ("CURRENCY-REVIEW" if review else "FAIL")


@pytest.mark.parametrize("profile", [{}, {"isAdr": True}, {"currency": "JPY"}, {"isAdr": "false"}])
def test_exported_cut_still_triggers_t6(profile):
    row = build_entry_row(
        "SYNTH",
        0.5,
        {"price": 20},
        {"lastDiv": 1.6, **profile},
        [],
        dividend_history=history([0.5] * 7 + [0.4]),
        floor_pct=0.1,
    )
    path = (
        Path(__file__).resolve().parents[3]
        / "kanchi-dividend-review-monitor/scripts/build_review_queue.py"
    )
    # Import under a unique name to avoid other skill test-module collisions.
    spec = importlib.util.spec_from_file_location("pr776_monitor", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        finding = module.t6_dividend_policy_change({"dividend": row["dividend_basis"]})
        assert row["dividend_basis"]["cut_flag"]
        assert (finding.trigger, finding.status) == ("T6", "REVIEW")
    finally:
        sys.modules.pop(spec.name, None)


@pytest.mark.parametrize("usd", [[0.55] * 7 + [0.4, 0.4], [0.4] * 7 + [0.55, 0.55]])
def test_native_freeze_never_becomes_clean_pass(usd):
    basis = analyze_dividends(history(usd, native=[100] * 9), 20)
    assert not basis.cut_flag and not basis.variable_policy_flag
    assert basis.freeze_flag and basis.last_increase_date is None
    assert "sequential_regular_rate_cut" not in basis.reasons
    step1, _ = step1_decision(basis, 0.1)
    assert step1 == "HOLD-REVIEW"
    final = synthesize_verdict(step1_verdict=step1, safety_verdict="PASS", event_verdict_cap=None)
    assert final.verdict == "CONDITIONAL-PASS"
    assert basis.latest_declared_annualized == round(usd[-1] * 4, 4)


def test_native_raise_hidden_by_flat_usd_sets_increase_date():
    rows = history([0.5] * 9, native=[100] * 8 + [105])
    basis = analyze_dividends(rows, 20)
    assert not basis.freeze_flag
    assert basis.last_increase_date == rows[-1]["date"]


@pytest.mark.parametrize(
    "step1,blockers",
    [("CURRENCY-REVIEW", []), ("HOLD-REVIEW", ["dividend_cut_currency_basis_unconfirmed"])],
)
def test_currency_review_library_call_cannot_be_actionable(step1, blockers):
    result = synthesize_verdict(
        step1_verdict=step1,
        safety_verdict="PASS",
        event_verdict_cap=None,
        pre_order_blockers=blockers,
    )
    assert asdict(result) == {
        "verdict": "HOLD-REVIEW",
        "t1_blocked": True,
        "reasons": ["dividend_cut_currency_basis_unconfirmed"],
    }
