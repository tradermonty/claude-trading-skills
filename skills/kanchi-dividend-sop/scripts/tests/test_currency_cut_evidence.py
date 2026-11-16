from datetime import date, timedelta

from build_entry_signals import build_entry_row
from dividend_basis import analyze_dividends, step1_decision


def history(native=None, currency="JPY", source="synthetic issuer declaration"):
    amounts = [0.55] * 7 + [0.40, 0.40]
    rows = [
        {"date": (date(2023, 1, 1) + timedelta(days=91 * i)).isoformat(), "dividend": amount}
        for i, amount in enumerate(amounts)
    ]
    if native is not None:
        for i, row in enumerate(rows):
            row.update(
                original_dividend=native[i],
                original_currency=currency,
                original_dividend_source=source,
            )
    return rows


def test_large_fx_decline_with_unchanged_issuer_dividend_is_not_cut():
    b = analyze_dividends(history([100] * 9), 20.0)
    assert not b.cut_flag
    assert "fx_like_decline_original_dividend_not_cut" in b.reasons
    assert step1_decision(b, 1.0)[0] != "FAIL"


def test_unknown_currency_decline_is_review_not_hard_fail_or_clean_pass():
    b = analyze_dividends(history(), 20.0, is_adr=True)
    assert b.cut_flag
    assert step1_decision(b, 1.0) == ("CURRENCY-REVIEW", "dividend_cut_currency_basis_unconfirmed")


def test_confirmed_original_currency_cut_remains_fail_after_flat_payment():
    b = analyze_dividends(history([100] * 7 + [85, 85]), 20.0)
    assert b.cut_flag
    assert step1_decision(b, 1.0)[0] == "FAIL"


def test_original_cut_hidden_by_fx_is_detected():
    h = history([100] * 7 + [85, 85])
    for row in h:
        row["dividend"] = 0.55
    assert analyze_dividends(h, 20.0).cut_flag


def test_missing_source_or_mixed_currency_cannot_confirm_cut():
    for h in (history([100] * 9, source=""), history([100] * 9)):
        h[-1]["original_currency"] = "EUR"
        b = analyze_dividends(h, 20.0)
        assert b.cut_flag
        assert step1_decision(b, 1.0)[0] == "CURRENCY-REVIEW"


def test_row_records_currency_blocker():
    row = build_entry_row(
        "FX",
        0.5,
        {"price": 20.0},
        {"lastDiv": 1.6, "isAdr": True},
        [{"dividendYield": 0.04}] * 5,
        dividend_history=history(),
        floor_pct=1.0,
    )
    assert row["step1_reason"] == "dividend_cut_currency_basis_unconfirmed"
    assert row["verdict"] == "HOLD-REVIEW"
    assert row["t1_blocked"]
    assert "dividend_cut_currency_basis_unconfirmed" in row["pre_order_blockers"]


def test_large_fx_variation_does_not_become_variable_policy_fail():
    for native in (None, [100] * 9):
        h = history(native)
        h[-2]["dividend"] = h[-1]["dividend"] = 0.10
        b = analyze_dividends(h, 20.0, is_adr=True)
        assert step1_decision(b, 0.1)[0] != "FAIL"
        if native:
            assert not b.variable_policy_flag


def test_invalid_original_amounts_fail_closed_to_review():
    for value in (float("nan"), float("inf"), True, -1, None, 10**400):
        h = history([100] * 9)
        h[-1]["original_dividend"] = value
        b = analyze_dividends(h, 20.0)
        assert b.cut_flag
        assert step1_decision(b, 1.0)[0] == "CURRENCY-REVIEW"


def test_explicit_variable_policy_is_not_downgraded_by_currency_uncertainty():
    b = analyze_dividends(history(), 20.0, issuer_language="variable dividend policy")
    assert step1_decision(b, 1.0) == ("FAIL", "variable_dividend_policy")


def test_csv_exports_cut_evidence_basis(tmp_path):
    import csv

    from build_entry_signals import write_csv

    row = build_entry_row(
        "FX",
        0.5,
        {"price": 20.0},
        {"lastDiv": 1.6, "isAdr": True},
        [{"dividendYield": 0.04}] * 5,
        dividend_history=history([100] * 9),
        floor_pct=1.0,
    )
    path = tmp_path / "signals.csv"
    write_csv([row], path)
    with path.open() as f:
        output = next(csv.DictReader(f))
    assert output["cut_amount_basis"] == "original_currency"
    assert output["original_dividend_currency"] == "JPY"
