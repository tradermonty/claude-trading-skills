"""Regular-only payment years must not manufacture screening eligibility."""

from copy import deepcopy
from datetime import date, timedelta

import pytest
from screen_dividend_stocks import StockAnalyzer as A

AS_OF = date(2026, 11, 20)


def quarterly(growth=1.0, drift=False):
    return [
        {
            "date": f"{year}-{month:02d}-{15 - (year - 2020) if drift else 15:02d}",
            "dividend": 0.5 * growth ** (year - 2020),
        }
        for year in range(2020, 2027)
        for month in (3, 6, 9, 12)
    ]


@pytest.mark.parametrize(
    "field,label",
    [
        ("frequency", "Special"),
        ("label", "supplemental"),
        ("label", "One-Time Dividend"),
        ("label", "EXTRA cash"),
    ],
)
def test_special_cannot_inflate_growth_and_yield(field, label):
    rows = quarterly()
    rows.append({"date": "2026-07-15", "dividend": 3.0, field: label})
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (0.0, True, 2.0)


def test_day_drift_flat_payer_is_not_a_cut():
    rows = quarterly(drift=True)
    for row in rows:
        row["dividend"] = 1.0
    assert A.analyze_dividend_growth({"historical": rows}, as_of=date(2025, 3, 12)) == (
        0.0,
        True,
        4.0,
    )


def test_recent_ordinary_raise_remains_in_latest_regular_payment_year():
    rows = quarterly(1.1)
    original = deepcopy(rows)
    cagr, consistent, annual = A.analyze_dividend_growth(
        {"historical": rows}, as_of=date(2026, 5, 20)
    )
    assert cagr == pytest.approx(10.0)
    assert consistent
    assert annual == pytest.approx(3 * (0.5 * 1.1**5) + 0.5 * 1.1**6)
    assert annual > 4 * (0.5 * 1.1**5)  # current regular raise is already reflected
    assert rows == original


@pytest.mark.parametrize("ppy,days", [(12, 30), (4, 91), (2, 182), (1, 365)])
def test_supported_payment_cadences_have_annual_not_partial_numerator(ppy, days):
    rows = [
        {"date": (AS_OF - timedelta(days=days * i)).isoformat(), "dividend": 1.0, "frequency": ppy}
        for i in range(ppy * 4)
    ]
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (0.0, True, float(ppy))


@pytest.mark.parametrize("frequency", [None, "Monthly", "Irregular", "weekly", 24])
def test_twice_monthly_or_unsupported_cadence_is_unavailable(frequency):
    rows = [
        {"date": (AS_OF - timedelta(days=15 * i)).isoformat(), "dividend": 1.0} for i in range(60)
    ]
    if frequency is not None:
        for row in rows:
            row["frequency"] = frequency
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None)


@pytest.mark.parametrize(
    "days,valid", [(24, False), (25, False), (30, True), (31, True), (36, False), (37, False)]
)
@pytest.mark.parametrize("explicit", [False, True])
def test_median_band_also_requires_annual_payment_spacing(days, valid, explicit):
    rows = [
        {"date": (AS_OF - timedelta(days=days * i)).isoformat(), "dividend": 1.0} for i in range(48)
    ]
    if explicit:
        for row in rows:
            row["frequency"] = "Monthly"
    result = A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF)
    assert result == ((0.0, True, 12.0) if valid else (None, False, None))


@pytest.mark.parametrize("value", [None, True, "bad", float("nan"), float("inf"), 0, -1, 10**400])
def test_bad_regular_amount_is_unavailable_not_a_zero_or_partial_year(value):
    rows = quarterly()
    rows[-3]["dividend"] = value
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None)


def test_missing_regular_payment_and_duplicate_date_are_unavailable():
    rows = quarterly()
    rows = [r for r in rows if r["date"] != "2025-06-15"]
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None)
    rows = quarterly()
    rows.append(dict(rows[-3]))
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None)


def test_special_does_not_contaminate_separate_stability_gate():
    rows = quarterly(1.1)
    expected = A.analyze_dividend_stability({"historical": rows}, as_of=AS_OF)
    rows.append({"date": "2025-04-01", "dividend": 100, "frequency": "Special"})
    assert A.analyze_dividend_stability({"historical": rows}, as_of=AS_OF) == expected


def test_future_bad_regular_value_is_not_consumed():
    rows = quarterly(1.1)
    expected = A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF)
    rows.append({"date": "2030-01-01", "dividend": "bad"})
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == expected


@pytest.mark.parametrize("growth", [1.0, 1.1])
def test_real_screening_special_does_not_manufacture_candidate(monkeypatch, capsys, growth):
    from functools import partial

    import screen_dividend_stocks as mod
    from test_clients_and_pipeline import FakeFMP, _falling_prices, _good_candidate, _income

    rows = quarterly(growth)
    rows.append({"date": "2026-07-15", "dividend": 30.0, "frequency": "Special"})
    FakeFMP.cfg = {
        "candidates": [_good_candidate(sector="Utilities")],
        "income": {"GOOD": _income()},
        "dividends": {"GOOD": {"historical": rows}},
        "prices": {"GOOD": _falling_prices()},
    }
    monkeypatch.setattr(mod, "FMPClient", FakeFMP)
    monkeypatch.setattr(
        A, "analyze_dividend_growth", staticmethod(partial(A.analyze_dividend_growth, as_of=AS_OF))
    )
    monkeypatch.setattr(
        A,
        "analyze_dividend_stability",
        staticmethod(partial(A.analyze_dividend_stability, as_of=AS_OF)),
    )
    results = mod.screen_value_dividend_stocks("offline-test-value")
    if growth == 1.0:
        assert results == []
        assert "Dividend CAGR < 4%" in capsys.readouterr().err
    else:
        assert len(results) == 1
        assert results[0]["dividend_cagr_3y"] == 10.0
        assert results[0]["annual_dividend"] == 3.46
        assert results[0]["dividend_yield"] == 17.31
        assert results[0]["annual_dividend_basis"] == "regular_payment_year"


def test_value_cli_reports_basis_metadata(monkeypatch, tmp_path, capsys):
    import json
    import sys

    import screen_dividend_stocks as mod

    def fake_screen(*args, **kwargs):
        return [{"symbol": "SYN"}]

    monkeypatch.setattr(mod, "screen_value_dividend_stocks", fake_screen)
    monkeypatch.setenv("FMP_API_KEY", "offline-test-value")
    path = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", ["screen_dividend_stocks.py", "--output", str(path)])
    mod.main()
    assert (
        json.loads(path.read_text())["metadata"]["annual_dividend_basis"] == "regular_payment_year"
    )
    assert "latest N regular payments" in capsys.readouterr().err
