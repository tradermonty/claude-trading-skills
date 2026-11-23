"""Cadence must come from ex-date intervals, not per-row FMP frequency labels.

Row shapes are real FMP rows captured 2026-11-22 (date, dividend, frequency).
"""

from datetime import date

import pytest
from screen_dividend_stocks import StockAnalyzer as A

AS_OF = date(2026, 11, 22)

BTI = [
    ("2026-12-29", 0.83485, "Quarterly"),
    ("2026-10-02", 0.81807, "Quarterly"),
    ("2026-07-10", 0.82998, "Quarterly"),
    ("2026-03-27", 0.83402, "Quarterly"),
    ("2025-12-30", 0.82336, "Irregular"),
    ("2025-10-03", 0.74907, "Quarterly"),
    ("2025-06-27", 0.79742, "Quarterly"),
    ("2025-03-28", 0.80222, "Quarterly"),
    ("2024-12-20", 0.73044, "Quarterly"),
    ("2024-09-27", 0.7627, "Quarterly"),
    ("2024-06-28", 0.75375, "Quarterly"),
    ("2024-03-21", 0.73485, "Quarterly"),
    ("2023-12-21", 0.7318, "Quarterly"),
    ("2023-09-28", 0.71388, "Irregular"),
    ("2023-07-13", 0.7344, "Quarterly"),
    ("2023-03-23", 0.72387, "Quarterly"),
    ("2022-12-22", 0.66919, "Quarterly"),
    ("2022-09-29", 0.63554, "Irregular"),
    ("2022-07-07", 0.65552, "Quarterly"),
    ("2022-03-24", 0.68043, "Quarterly"),
    ("2021-12-22", 0.72989, "Quarterly"),
    ("2021-09-30", 0.72172, "Irregular"),
    ("2021-07-08", 0.73453, "Quarterly"),
    ("2021-03-25", 0.75762, "Quarterly"),
    ("2020-12-17", 0.71783, "Quarterly"),
    ("2020-10-01", 0.68959, "Irregular"),
    ("2020-07-09", 0.6889, "Quarterly"),
    ("2020-03-26", 0.6424, "Quarterly"),
    ("2019-12-26", 0.674, "Quarterly"),
    ("2019-10-03", 0.65214, "Quarterly"),
    ("2019-06-27", 0.67449, "Quarterly"),
    ("2019-03-21", 0.6597, "Quarterly"),
    ("2018-12-27", 0.679, "Quarterly"),
    ("2018-10-04", 0.62171, "Quarterly"),
    ("2018-06-28", 0.62815, "Quarterly"),
    ("2018-03-22", 0.66114, "Quarterly"),
    ("2017-12-28", 0.60687, "Quarterly"),
    ("2017-08-16", 0.75857, "Semi-Annual"),
    ("2017-03-15", 1.52394, "Semi-Annual"),
    ("2016-08-17", 1.33247, "Semi-Annual"),
]

HSBC = [
    ("2026-11-06", 0.5, "Quarterly"),
    ("2026-08-14", 0.5, "Quarterly"),
    ("2026-05-15", 0.5, "Quarterly"),
    ("2026-03-13", 2.25, "Quarterly"),
    ("2025-11-07", 0.5, "Quarterly"),
    ("2025-08-15", 0.5, "Quarterly"),
    ("2025-05-09", 0.5, "Quarterly"),
    ("2025-03-07", 1.8, "Quarterly"),
    ("2024-11-08", 0.5, "Quarterly"),
    ("2024-08-16", 0.5, "Quarterly"),
    ("2024-05-09", 1.05, "Special"),
    ("2024-05-09", 0.5, "Quarterly"),
    ("2024-03-07", 1.55, "Quarterly"),
    ("2023-11-09", 0.5, "Quarterly"),
    ("2023-08-10", 0.5, "Quarterly"),
    ("2023-05-11", 0.5, "Quarterly"),
    ("2023-03-02", 1.15, "Semi-Annual"),
    ("2022-08-18", 0.45, "Semi-Annual"),
    ("2022-03-10", 0.9, "Semi-Annual"),
    ("2021-08-19", 0.35, "Semi-Annual"),
    ("2021-03-11", 0.75, "Annual"),
    ("2020-02-27", 1.05, "Irregular"),
    ("2019-10-10", 0.5, "Quarterly"),
    ("2019-08-15", 0.5, "Quarterly"),
    ("2019-05-16", 0.5, "Quarterly"),
    ("2019-02-21", 1.05, "Quarterly"),
    ("2018-10-11", 0.5, "Quarterly"),
    ("2018-08-16", 0.5, "Quarterly"),
    ("2018-05-17", 0.5, "Quarterly"),
    ("2018-02-22", 1.05, "Quarterly"),
    ("2017-10-12", 0.5, "Quarterly"),
    ("2017-08-02", 0.5, "Quarterly"),
    ("2017-05-17", 0.5, "Quarterly"),
    ("2017-02-22", 1.05, "Quarterly"),
    ("2016-10-19", 0.5, "Quarterly"),
    ("2016-08-10", 0.5, "Quarterly"),
    ("2016-05-18", 0.5, "Quarterly"),
    ("2016-03-02", 1.05, "Quarterly"),
    ("2015-10-21", 0.5, "Quarterly"),
    ("2015-08-12", 0.5, "Semi-Annual"),
]

TGT = [
    ("2026-11-10", 1.16, "Quarterly"),
    ("2026-08-12", 1.16, "Quarterly"),
    ("2026-05-13", 1.14, "Quarterly"),
    ("2026-02-11", 1.14, "Quarterly"),
    ("2025-11-12", 1.14, "Quarterly"),
    ("2025-08-13", 1.14, "Quarterly"),
    ("2025-05-14", 1.12, "Quarterly"),
    ("2025-02-12", 1.12, "Quarterly"),
    ("2024-11-20", 1.12, "Quarterly"),
    ("2024-08-21", 1.12, "Quarterly"),
    ("2024-05-14", 1.1, "Quarterly"),
    ("2024-02-20", 1.1, "Monthly"),
    ("2023-11-14", 1.1, "Quarterly"),
    ("2023-08-15", 1.1, "Quarterly"),
    ("2023-05-16", 1.08, "Quarterly"),
    ("2023-02-14", 1.08, "Quarterly"),
    ("2022-11-15", 1.08, "Irregular"),
    ("2022-08-16", 1.08, "Quarterly"),
    ("2022-05-17", 0.9, "Quarterly"),
    ("2022-02-15", 0.9, "Quarterly"),
    ("2021-11-16", 0.9, "Quarterly"),
    ("2021-08-17", 0.9, "Quarterly"),
    ("2021-05-18", 0.68, "Quarterly"),
    ("2021-02-16", 0.68, "Quarterly"),
    ("2020-11-17", 0.68, "Quarterly"),
    ("2020-08-18", 0.68, "Quarterly"),
    ("2020-05-19", 0.66, "Quarterly"),
    ("2020-02-18", 0.66, "Quarterly"),
    ("2019-11-19", 0.66, "Quarterly"),
    ("2019-08-20", 0.66, "Quarterly"),
    ("2019-05-14", 0.64, "Quarterly"),
    ("2019-02-19", 0.64, "Quarterly"),
    ("2018-11-20", 0.64, "Quarterly"),
    ("2018-08-14", 0.64, "Quarterly"),
    ("2018-05-15", 0.62, "Quarterly"),
    ("2018-02-20", 0.62, "Quarterly"),
    ("2017-11-14", 0.62, "Quarterly"),
    ("2017-08-14", 0.62, "Quarterly"),
    ("2017-05-15", 0.6, "Quarterly"),
    ("2017-02-13", 0.6, "Quarterly"),
]

MAIN = [
    ("2027-03-08", 0.27, "Monthly"),
    ("2027-02-05", 0.27, "Monthly"),
    ("2027-01-08", 0.27, "Monthly"),
    ("2026-12-18", 0.3, "Irregular"),
    ("2026-12-08", 0.265, "Monthly"),
    ("2026-11-06", 0.265, "Monthly"),
    ("2026-10-08", 0.265, "Monthly"),
    ("2026-09-21", 0.3, "Irregular"),
    ("2026-09-08", 0.265, "Monthly"),
    ("2026-08-07", 0.265, "Monthly"),
    ("2026-07-08", 0.265, "Monthly"),
    ("2026-06-22", 0.3, "Irregular"),
    ("2026-06-08", 0.26, "Monthly"),
    ("2026-05-08", 0.26, "Monthly"),
    ("2026-04-08", 0.26, "Monthly"),
    ("2026-03-20", 0.3, "Irregular"),
    ("2026-03-06", 0.26, "Monthly"),
    ("2026-02-06", 0.26, "Monthly"),
    ("2026-01-08", 0.26, "Monthly"),
    ("2025-12-22", 0.3, "Irregular"),
    ("2025-12-08", 0.255, "Monthly"),
    ("2025-11-07", 0.255, "Monthly"),
    ("2025-10-08", 0.255, "Monthly"),
    ("2025-09-19", 0.3, "Irregular"),
    ("2025-09-08", 0.255, "Monthly"),
    ("2025-08-08", 0.255, "Monthly"),
    ("2025-07-08", 0.255, "Monthly"),
    ("2025-06-20", 0.3, "Irregular"),
    ("2025-06-06", 0.25, "Monthly"),
    ("2025-05-08", 0.25, "Monthly"),
    ("2025-04-08", 0.25, "Monthly"),
    ("2025-03-20", 0.3, "Irregular"),
    ("2025-03-07", 0.25, "Monthly"),
    ("2025-02-07", 0.25, "Monthly"),
    ("2025-01-08", 0.25, "Monthly"),
    ("2024-12-20", 0.3, "Irregular"),
    ("2024-12-06", 0.245, "Monthly"),
    ("2024-11-08", 0.245, "Monthly"),
    ("2024-10-08", 0.245, "Monthly"),
    ("2024-09-20", 0.3, "Irregular"),
    ("2024-09-06", 0.245, "Monthly"),
    ("2024-08-08", 0.245, "Monthly"),
    ("2024-07-08", 0.245, "Monthly"),
    ("2024-06-21", 0.3, "Special"),
    ("2024-06-07", 0.24, "Monthly"),
    ("2024-05-07", 0.24, "Monthly"),
    ("2024-04-05", 0.24, "Monthly"),
    ("2024-03-19", 0.3, "Special"),
    ("2024-03-07", 0.24, "Monthly"),
    ("2024-02-07", 0.24, "Monthly"),
    ("2024-01-04", 0.24, "Irregular"),
    ("2023-12-19", 0.275, "Special"),
    ("2023-12-07", 0.235, "Special"),
    ("2023-11-07", 0.235, "Monthly"),
    ("2023-10-05", 0.235, "Monthly"),
    ("2023-09-19", 0.275, "Special"),
    ("2023-09-07", 0.23, "Monthly"),
    ("2023-08-07", 0.23, "Monthly"),
    ("2023-07-06", 0.23, "Monthly"),
    ("2023-06-20", 0.225, "Special"),
    ("2023-06-07", 0.225, "Monthly"),
    ("2023-05-05", 0.225, "Monthly"),
    ("2023-04-05", 0.225, "Monthly"),
    ("2023-03-20", 0.175, "Special"),
    ("2023-03-07", 0.225, "Monthly"),
    ("2023-02-07", 0.225, "Monthly"),
    ("2023-01-05", 0.225, "Monthly"),
    ("2022-12-19", 0.1, "Special"),
    ("2022-12-07", 0.22, "Monthly"),
    ("2022-11-07", 0.22, "Monthly"),
    ("2022-10-06", 0.22, "Monthly"),
    ("2022-09-19", 0.1, "Special"),
    ("2022-09-01", 0.215, "Monthly"),
    ("2022-08-01", 0.215, "Monthly"),
    ("2022-07-01", 0.215, "Monthly"),
    ("2022-06-21", 0.075, "Monthly"),
    ("2022-06-01", 0.215, "Monthly"),
    ("2022-05-02", 0.215, "Monthly"),
    ("2022-04-01", 0.215, "Monthly"),
    ("2022-03-21", 0.075, "Special"),
    ("2022-03-01", 0.215, "Monthly"),
    ("2022-02-01", 0.215, "Monthly"),
    ("2022-01-03", 0.215, "Monthly"),
    ("2021-12-21", 0.1, "Special"),
    ("2021-11-23", 0.21, "Monthly"),
    ("2021-10-28", 0.21, "Monthly"),
    ("2021-09-28", 0.21, "Monthly"),
    ("2021-08-26", 0.205, "Monthly"),
    ("2021-07-28", 0.205, "Monthly"),
    ("2021-06-28", 0.205, "Monthly"),
]

KO = [
    ("2026-12-01", 0.53, "Quarterly"),
    ("2026-09-15", 0.53, "Quarterly"),
    ("2026-06-15", 0.53, "Quarterly"),
    ("2026-03-13", 0.53, "Quarterly"),
    ("2025-12-01", 0.51, "Quarterly"),
    ("2025-09-15", 0.51, "Quarterly"),
    ("2025-06-13", 0.51, "Quarterly"),
    ("2025-03-14", 0.51, "Quarterly"),
    ("2024-11-29", 0.485, "Quarterly"),
    ("2024-09-13", 0.485, "Quarterly"),
    ("2024-06-14", 0.485, "Quarterly"),
    ("2024-03-14", 0.485, "Quarterly"),
    ("2023-11-30", 0.46, "Quarterly"),
    ("2023-09-14", 0.46, "Quarterly"),
    ("2023-06-15", 0.46, "Quarterly"),
    ("2023-03-16", 0.46, "Quarterly"),
    ("2022-11-30", 0.44, "Quarterly"),
    ("2022-09-15", 0.44, "Quarterly"),
    ("2022-06-14", 0.44, "Quarterly"),
    ("2022-03-14", 0.44, "Quarterly"),
    ("2021-11-30", 0.42, "Quarterly"),
    ("2021-09-14", 0.42, "Quarterly"),
    ("2021-06-14", 0.42, "Quarterly"),
    ("2021-03-12", 0.42, "Quarterly"),
]


def hist(rows):
    return {"historical": [{"date": a, "dividend": b, "frequency": c} for a, b, c in rows]}


@pytest.mark.parametrize("rows", [BTI, HSBC, TGT, KO], ids=["BTI", "HSBC", "TGT", "KO"])
def test_mislabelled_rows_do_not_veto_interval_supported_cadence(rows):
    cagr, _, annual = A.analyze_dividend_growth(hist(rows), as_of=AS_OF)
    assert cagr is not None and annual > 0


def test_bti_mislabel_value_is_quarterly_sum():
    _, _, annual = A.analyze_dividend_growth(hist(BTI), as_of=AS_OF)
    assert annual == pytest.approx(0.83402 + 0.82998 + 0.81807 + 0.82336, abs=0.01)


def main_like_rows():
    """MAIN's real shape: monthly 0.265 rows plus a 0.30 'Irregular' extra each quarter."""
    rows = []
    for year in range(2022, 2027):
        for month in range(1, 13):
            if (year, month) > (2026, 11):
                break
            rows.append((f"{year}-{month:02d}-08", 0.265, "Monthly"))
            if month % 3 == 0:
                rows.append((f"{year}-{month:02d}-20", 0.30, "Irregular"))
    return rows


def test_irregular_supplementals_retry_and_record_diagnostics():
    diag = {}
    cagr, _, annual = A.analyze_dividend_growth(
        hist(main_like_rows()), as_of=AS_OF, diagnostics=diag
    )
    assert cagr == 0.0
    assert diag["supplementals_excluded"] == 19
    assert annual == pytest.approx(12 * 0.265)  # the 0.30 extras are not in the annual sum


def test_real_main_rows_stay_fail_closed_on_genuine_data_gap():
    # FMP lacks the Dec 2023 / Jan 2024 ex-dates (a 92-day hole), so even without
    # the Irregular extras the intervals do not support a monthly cadence.
    assert A.analyze_dividend_growth(hist(MAIN), as_of=AS_OF) == (None, False, None)


def test_clean_payer_records_no_supplementals():
    diag = {}
    A.analyze_dividend_growth(hist(KO), as_of=AS_OF, diagnostics=diag)
    assert diag.get("supplementals_excluded", 0) == 0


def test_irregular_retry_still_fails_closed_when_cadence_unsupported():
    rows = [(f"2026-{m:02d}-{d:02d}", 1.0, "Irregular") for m in range(1, 11) for d in (1, 15)]
    assert A.analyze_dividend_growth(hist(rows), as_of=AS_OF) == (None, False, None)
