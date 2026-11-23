"""Complete calendar payout years exclude future declarations and special cash."""

from copy import deepcopy
from datetime import date

import pytest
from screen_dividend_growth_rsi import StockAnalyzer as A

AS_OF = date(2026, 12, 20)


def quarterly(growth=1.15):
    return [
        {"date": f"{y}-{m:02d}-15", "dividend": growth ** (y - 2020) / 4}
        for y in range(2020, 2026)
        for m in (3, 6, 9, 12)
    ]


def test_future_year_declaration_cannot_change_completed_calendar_growth():
    rows = quarterly()
    original = deepcopy(rows)
    expected = A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF)
    rows.extend(
        [{"date": "2027-01-15", "dividend": 0.1}, {"date": "2026-12-25", "dividend": "bad"}]
    )
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == expected
    assert expected == (15.0, True, pytest.approx(1.15**5), 5)
    assert rows[: len(original)] == original


@pytest.mark.parametrize(
    "field,label",
    [
        ("frequency", "Special"),
        ("label", "supplemental"),
        ("label", "one-time"),
        ("label", "EXTRA"),
    ],
)
def test_special_cash_is_not_regular_growth(field, label):
    rows = quarterly(1.0)
    rows.append({"date": "2025-07-01", "dividend": 5, field: label})
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (0.0, True, 1.0, 5)


@pytest.mark.parametrize("value", [None, True, "bad", float("nan"), float("inf"), 0, -1, 10**400])
def test_bad_completed_regular_amount_is_unavailable(value):
    rows = quarterly()
    rows[-1]["dividend"] = value
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None, 0)


def test_missing_year_does_not_compress_three_year_cagr():
    rows = [r for r in quarterly() if not r["date"].startswith("2024")]
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None, 0)


def test_gap_before_latest_four_years_breaks_growth_streak():
    rows = [r for r in quarterly() if not r["date"].startswith("2021")]
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF)[3] == 3


def test_actual_cut_is_still_inconsistent():
    rows = quarterly()
    for r in rows:
        if r["date"].startswith("2025"):
            r["dividend"] = 0.05
    cagr, consistent, annual, streak = A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF)
    assert cagr < 0 and consistent is False and annual == 0.2 and streak == 0


def test_partial_current_calendar_year_not_used_even_on_december_31():
    rows = quarterly()
    rows.append({"date": "2026-01-01", "dividend": 100})
    assert A.analyze_dividend_growth(
        {"historical": rows}, as_of=date(2026, 12, 31)
    ) == A.analyze_dividend_growth({"historical": quarterly()}, as_of=AS_OF)


def test_real_growth_screening_ignores_next_year_declaration(monkeypatch):
    import screen_dividend_growth_rsi as mod
    from test_screening_flow import FakeFMP, _stock

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 12, 20)

    rows = quarterly()
    rows.append({"date": "2027-01-15", "dividend": 0.1})
    monkeypatch.setattr(
        FakeFMP, "registry", {"screen": [_stock("AAA")], "div": {"AAA": {"historical": rows}}}
    )
    monkeypatch.setattr(mod, "FMPClient", FakeFMP)
    monkeypatch.setattr(mod, "date", FixedDate)
    results = mod.screen_dividend_growth_pullbacks("offline-test-value")
    assert len(results) == 1
    assert results[0]["dividend_cagr_3y"] == 15.0
    assert results[0]["annual_dividend"] == 2.01
    assert results[0]["annual_dividend_basis"] == "regular_completed_calendar_year"


def test_growth_markdown_names_calendar_basis(tmp_path):
    from screen_dividend_growth_rsi import generate_markdown_report

    path = tmp_path / "report.md"
    generate_markdown_report(
        [], {"dividend_yield_min": 1.5, "dividend_cagr_min": 12, "rsi_max": 40}, str(path)
    )
    assert "latest available completed calendar year" in path.read_text()
