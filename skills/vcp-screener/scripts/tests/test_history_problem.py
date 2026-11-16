"""history_problem() must count distinct, ordered, dated sessions (PR #724 review)."""

from datetime import date, timedelta

import pytest
from coverage_client import MIN_SCREEN_HISTORY, history_problem


def bars(n=MIN_SCREEN_HISTORY, start=date(2026, 11, 13)):
    """Most-recent-first calendar-day bars; only distinctness and order matter."""
    return [
        {
            "date": (start - timedelta(days=i)).isoformat(),
            "close": 100.0,
            "high": 102.0,
            "low": 98.0,
            "volume": 10000,
        }
        for i in range(n)
    ]


@pytest.mark.parametrize("benchmark", [False, True])
def test_valid_distinct_descending_history_passes(benchmark):
    assert history_problem(bars(), benchmark=benchmark) is None


@pytest.mark.parametrize("benchmark", [False, True])
def test_repeated_single_date_is_not_253_sessions(benchmark):
    rows = [dict(bars(1)[0]) for _ in range(MIN_SCREEN_HISTORY)]
    assert history_problem(rows, benchmark=benchmark) == "duplicate_sessions"


def test_one_duplicate_date_invalidates_history():
    rows = bars()
    rows[100]["date"] = rows[99]["date"]
    assert history_problem(rows) == "duplicate_sessions"


@pytest.mark.parametrize("benchmark", [False, True])
def test_undated_rows_are_missing_data(benchmark):
    rows = bars()
    for row in rows:
        del row["date"]
    assert history_problem(rows, benchmark=benchmark) == "missing_data"


def test_single_undated_row_is_missing_data():
    rows = bars()
    rows[50]["date"] = None
    assert history_problem(rows) == "missing_data"


@pytest.mark.parametrize("bad", ["not-a-date", "2026-13-40", 20261113, "", "2026/11/13"])
def test_unparseable_date_is_invalid_data(bad):
    rows = bars()
    rows[10]["date"] = bad
    assert history_problem(rows) == "invalid_data"


@pytest.mark.parametrize("bad", [0, -5.0, float("nan"), float("inf"), True, "100"])
@pytest.mark.parametrize("benchmark", [False, True])
def test_invalid_close_is_invalid_data(bad, benchmark):
    rows = bars()
    rows[7]["close"] = bad
    assert history_problem(rows, benchmark=benchmark) == "invalid_data"


def test_oldest_first_history_is_unordered():
    assert history_problem(list(reversed(bars()))) == "unordered_history"


def test_single_swapped_pair_is_unordered():
    rows = bars()
    rows[20], rows[21] = rows[21], rows[20]
    assert history_problem(rows, benchmark=True) == "unordered_history"


def test_short_history_still_insufficient():
    assert history_problem(bars(MIN_SCREEN_HISTORY - 1)) == "insufficient_history"


def test_problem_codes_do_not_echo_row_content():
    rows = bars()
    rows[3]["date"] = "SECRET-TOKEN"
    assert "SECRET" not in history_problem(rows)
