"""Tests for parse_mt5_report: summary + balance-series (months/years/underwater)."""

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mt5_common import html_table_rows, read_text  # noqa: E402
from parse_mt5_report import (  # noqa: E402
    parse_report_file,
    parse_summary,
    timeseries_metrics,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "sample_report.htm"


def test_summary_fields():
    rows = html_table_rows(read_text(FIX))
    s = parse_summary(rows)
    assert s["net_profit"] == 7500.0
    assert s["deposit"] == 10000.0
    assert s["lr_correlation"] == 0.99
    assert s["profit_factor"] == 1.80
    assert s["total_trades"] == 30


def test_drawdown_is_worst_of_all_variants():
    rows = html_table_rows(read_text(FIX))
    s = parse_summary(rows)
    # max(2.50%, 3.10%) = 3.10
    assert s["drawdown_max_pct"] == 3.10


def test_timeseries_monotonic_balance():
    m = parse_report_file(FIX)
    assert m["deals_count"] == 16
    assert m["months_analyzed"] == 15
    assert m["pct_positive_months"] == 100.0
    assert m["all_years_positive"] is True
    assert m["max_months_to_new_high"] == 0
    assert m["profit_pct"] == 75.0


def test_timeseries_detects_underwater_gap():
    # Balance dips for two months, then recovers to a new high.
    points = [
        (dt.date(2020, 1, 31), 10000),
        (dt.date(2020, 2, 29), 10500),  # new high
        (dt.date(2020, 3, 31), 10200),  # under water (1)
        (dt.date(2020, 4, 30), 10300),  # under water (2)
        (dt.date(2020, 5, 31), 11000),  # new high, gap resets
    ]
    ts = timeseries_metrics(points, deposit=10000)
    assert ts["max_months_to_new_high"] == 2
    assert ts["all_years_positive"] is True


def test_negative_year_flagged():
    points = [
        (dt.date(2020, 6, 30), 10000),
        (dt.date(2020, 12, 31), 9000),  # 2020 ends down
        (dt.date(2021, 12, 31), 12000),  # 2021 up
    ]
    ts = timeseries_metrics(points, deposit=10000)
    assert ts["all_years_positive"] is False


def test_full_period_includes_leading_trailing_and_empty_year_months():
    points = [
        (dt.date(2020, 6, 30), 11000),
        (dt.date(2022, 2, 28), 12000),
    ]

    ts = timeseries_metrics(
        points,
        deposit=10000,
        period_start=dt.date(2020, 1, 1),
        period_end=dt.date(2022, 12, 31),
    )

    assert ts["months_analyzed"] == 36
    assert ts["positive_months"] == 2
    assert ts["pct_positive_months"] == pytest.approx(100 * 2 / 36)
    assert ts["yearly_pnl"] == {"2020": 1000, "2021": 0, "2022": 1000}
    assert ts["all_years_positive"] is False
    assert ts["max_months_to_new_high"] == 19


def test_report_parser_uses_explicit_test_period_boundaries():
    metrics = parse_report_file(FIX, "2019.12.01", "2021.03.31")

    assert metrics["months_analyzed"] == 16
    assert metrics["pct_positive_months"] < 100
