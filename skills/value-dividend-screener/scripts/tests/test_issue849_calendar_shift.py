"""Bounded exception for corroborated semiannual ex-date calendar shifts."""

from copy import deepcopy
from datetime import date

import pytest
from screen_dividend_stocks import StockAnalyzer as A

AS_OF = date(2026, 11, 22)

# FMP DEO date/amount/frequency rows captured 2026-11-22. The ADR ex-dates
# 2024-08-30 and 2025-10-17 are also reported by Diageo's annual reports.
DEO = [
    ("2023-03-02", 1.54218),
    ("2023-08-24", 2.39281),
    ("2024-02-29", 1.62),
    ("2024-08-30", 2.5192),
    ("2025-02-28", 1.62),
    ("2025-10-17", 2.5192),
    ("2026-04-17", 0.8),
    ("2026-10-16", 1.2),
]


def history():
    return [{"date": day, "dividend": amount, "frequency": "Semi-Annual"} for day, amount in DEO]


@pytest.mark.parametrize("reverse", [False, True])
def test_deo_calendar_shift_keeps_equal_payment_buckets_and_actual_cut(reverse):
    rows = history()
    if reverse:
        rows.reverse()
    cagr, consistent, annual = A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF)
    assert cagr == pytest.approx(((2.0 / (1.54218 + 2.39281)) ** (1 / 3) - 1) * 100)
    assert consistent is False
    assert annual == 2.0


def test_calendar_shift_does_not_turn_flat_payer_into_growth():
    rows = history()
    for row in rows:
        row["dividend"] = 1.0
    rows += [
        {"date": "2025-07-01", "dividend": 100, "frequency": "Special"},
        {"date": "2027-04-16", "dividend": 100, "frequency": "Semi-Annual"},
    ]
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (0.0, True, 2.0)


@pytest.mark.parametrize("frequency", [None, "", "Irregular", "Quarterly", True])
def test_exception_requires_corroborating_semiannual_metadata(frequency):
    rows = history()
    rows[4]["frequency"] = frequency
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None)


@pytest.mark.parametrize("mode", ["missing", "extra", "duplicate", "wrong_year", "bad_value"])
def test_exception_rejects_incomplete_or_ambiguous_history(mode):
    rows = deepcopy(history())
    if mode == "missing":
        # Keep eight rows overall, but leave 2024 incomplete.
        rows.pop(3)
        rows.insert(0, {"date": "2022-08-25", "dividend": 1, "frequency": "Semi-Annual"})
    elif mode == "extra":
        rows.append({"date": "2025-07-01", "dividend": 100, "frequency": "Semi-Annual"})
    elif mode == "duplicate":
        rows.append(dict(rows[-1]))
    elif mode == "wrong_year":
        rows[2]["date"] = "2023-12-29"
    else:
        rows[3]["dividend"] = 0
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None)


def test_exception_keeps_stale_last_payment_guard():
    assert A.analyze_dividend_growth({"historical": history()}, as_of=date(2027, 8, 1)) == (
        None,
        False,
        None,
    )


@pytest.mark.parametrize("frequency", ["semiannual", "SEMI_ANNUAL", "Semi Annual", "2", 2])
def test_calendar_exception_accepts_equivalent_explicit_frequency(frequency):
    rows = history()
    for row in rows:
        row["frequency"] = frequency
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF)[2] == 2.0


def test_calendar_exception_does_not_hide_extra_row_before_selected_window():
    rows = history()
    rows.append({"date": "2023-01-03", "dividend": 100, "frequency": "Semi-Annual"})
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None)


def test_calendar_exception_still_requires_supported_individual_gaps():
    rows = history()
    rows[-1]["date"] = "2026-05-01"
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None)


def test_calendar_exception_does_not_expand_annual_cadence():
    rows = [
        {"date": day, "dividend": 1, "frequency": "Annual"}
        for day in ("2023-08-24", "2024-08-30", "2025-10-17", "2026-10-16")
    ]
    assert A.analyze_dividend_growth({"historical": rows}, as_of=AS_OF) == (None, False, None)
