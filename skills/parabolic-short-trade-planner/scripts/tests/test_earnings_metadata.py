"""Unit tests for the earnings-calendar helpers in screen_parabolic.

Pins behavior of:

* :func:`_count_trading_days` — XNYS session counting.
* :func:`_resolve_market_data_as_of` — latest-bar-date probe with FMP
  recent-first input.
* :func:`_index_earnings_events` — defensive parser tolerating shape
  drift in the FMP earnings_calendar response.
* :func:`_compute_earnings_metadata` — last/next earnings detection and
  the unit split (trading days backward / calendar days forward).
"""

from datetime import date

from screen_parabolic import (
    _bars_on_or_before,
    _compute_earnings_metadata,
    _count_trading_days,
    _index_earnings_events,
    _resolve_market_data_as_of,
)


class TestCountTradingDays:
    def test_same_day_zero(self):
        d = date(2026, 5, 8)  # Friday
        assert _count_trading_days(d, d) == 0

    def test_friday_to_monday_is_one(self):
        # Friday → Monday: counts only Monday (Sat/Sun skipped).
        assert _count_trading_days(date(2026, 5, 8), date(2026, 5, 11)) == 1

    def test_wednesday_to_friday_is_two(self):
        # Wed (2026-05-06) → Fri (2026-05-08): Thu + Fri = 2 trading days.
        assert _count_trading_days(date(2026, 5, 6), date(2026, 5, 8)) == 2

    def test_full_week_is_five(self):
        # Mon → next Mon: 4 weekday gaps + the next Monday = 5 trading days.
        assert _count_trading_days(date(2026, 5, 4), date(2026, 5, 11)) == 5

    def test_good_friday_is_not_a_trading_day(self):
        assert _count_trading_days(date(2026, 4, 2), date(2026, 4, 6)) == 1

    def test_end_before_start_is_negative(self):
        assert _count_trading_days(date(2026, 5, 8), date(2026, 5, 6)) < 0


class TestResolveMarketDataAsOf:
    def test_returns_latest_bar_date_when_recent_first(self):
        bars = [
            {"date": "2026-05-08", "close": 24.0},
            {"date": "2026-05-07", "close": 22.5},
        ]
        assert _resolve_market_data_as_of(bars) == "2026-05-08"

    def test_truncates_datetime_to_yyyy_mm_dd(self):
        bars = [{"date": "2026-05-08T16:00:00-04:00", "close": 1.0}]
        assert _resolve_market_data_as_of(bars) == "2026-05-08"

    def test_empty_bars_returns_none(self):
        assert _resolve_market_data_as_of([]) is None

    def test_missing_date_returns_none(self):
        assert _resolve_market_data_as_of([{"close": 1.0}]) is None

    def test_future_and_invalid_bars_are_removed_by_as_of_ceiling(self):
        bars = [
            {"date": "2026-05-09", "close": 3.0},
            {"date": "invalid", "close": 2.0},
            {"date": "2026-05-08", "close": 1.0},
        ]
        assert _bars_on_or_before(bars, date(2026, 5, 8)) == [bars[2]]


class TestIndexEarningsEvents:
    def test_groups_by_symbol_and_sorts_by_date(self):
        events = [
            {"symbol": "AAPL", "date": "2026-04-30"},
            {"symbol": "FLNC", "date": "2026-05-06"},
            {"symbol": "AAPL", "date": "2026-01-29"},
        ]
        out = _index_earnings_events(events)
        assert set(out.keys()) == {"AAPL", "FLNC"}
        assert [e["date"] for e in out["AAPL"]] == ["2026-01-29", "2026-04-30"]
        assert [e["date"] for e in out["FLNC"]] == ["2026-05-06"]

    def test_uppercases_symbol(self):
        out = _index_earnings_events([{"symbol": "flnc", "date": "2026-05-06"}])
        assert "FLNC" in out
        assert "flnc" not in out

    def test_skips_rows_missing_symbol_or_date(self):
        out = _index_earnings_events(
            [
                {"symbol": "OK", "date": "2026-05-06"},
                {"date": "2026-05-06"},  # missing symbol
                {"symbol": "MISSING_DATE"},  # missing date
                {},  # empty
                None,  # not a dict
            ]
        )
        assert list(out.keys()) == ["OK"]

    def test_skips_unparsable_dates(self):
        out = _index_earnings_events(
            [
                {"symbol": "GOOD", "date": "2026-05-06"},
                {"symbol": "BAD", "date": "not-a-date"},
            ]
        )
        assert "GOOD" in out
        assert "BAD" not in out

    def test_accepts_alternate_field_names(self):
        # Some FMP variants use ``ticker`` / ``fiscalDateEnding``.
        out = _index_earnings_events([{"ticker": "ALT", "fiscalDateEnding": "2026-05-06"}])
        assert "ALT" in out

    def test_empty_input_returns_empty_dict(self):
        assert _index_earnings_events([]) == {}
        assert _index_earnings_events(None) == {}


class TestComputeEarningsMetadata:
    def test_only_past_event_sets_last_only(self):
        events = [{"date": "2026-05-06"}]
        meta = _compute_earnings_metadata(events, date(2026, 5, 8))
        assert meta["last_earnings_date"] == "2026-05-06"
        assert meta["next_earnings_date"] is None
        # 2026-05-06 (Wed) → 2026-05-08 (Fri): Thu + Fri = 2 trading days.
        assert meta["trading_days_since_earnings"] == 2
        assert meta["earnings_within_days"] is None

    def test_only_future_event_sets_next_only(self):
        events = [{"date": "2026-05-12"}]
        meta = _compute_earnings_metadata(events, date(2026, 5, 8))
        assert meta["last_earnings_date"] is None
        assert meta["next_earnings_date"] == "2026-05-12"
        assert meta["trading_days_since_earnings"] is None
        # Calendar days, not trading days.
        assert meta["earnings_within_days"] == 4

    def test_event_on_reference_day_counts_as_last(self):
        # An event dated exactly on ``market_data_as_of`` is treated as the
        # most recent past event (boundary inclusive).
        events = [{"date": "2026-05-08"}]
        meta = _compute_earnings_metadata(events, date(2026, 5, 8))
        assert meta["last_earnings_date"] == "2026-05-08"
        assert meta["next_earnings_date"] is None
        assert meta["trading_days_since_earnings"] == 0

    def test_picks_max_past_and_min_future(self):
        events = [
            {"date": "2025-11-24"},
            {"date": "2026-02-04"},
            {"date": "2026-05-06"},
            {"date": "2026-08-10"},
        ]
        meta = _compute_earnings_metadata(events, date(2026, 5, 8))
        assert meta["last_earnings_date"] == "2026-05-06"
        assert meta["next_earnings_date"] == "2026-08-10"

    def test_no_events_returns_all_none(self):
        meta = _compute_earnings_metadata([], date(2026, 5, 8))
        assert meta == {
            "last_earnings_date": None,
            "next_earnings_date": None,
            "trading_days_since_earnings": None,
            "earnings_within_days": None,
        }

    def test_skips_unparsable_event_dates(self):
        events = [{"date": "2026-05-06"}, {"date": "garbage"}]
        meta = _compute_earnings_metadata(events, date(2026, 5, 8))
        assert meta["last_earnings_date"] == "2026-05-06"
