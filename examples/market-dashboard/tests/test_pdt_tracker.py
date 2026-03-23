# tests/test_pdt_tracker.py
import sys
import json
import tempfile
from pathlib import Path
from datetime import date, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learning.pdt_tracker import PDTTracker


def test_no_trades_returns_3_slots():
    with tempfile.TemporaryDirectory() as d:
        tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
        assert tracker.slots_remaining(date.today()) == 3


def test_record_and_count_day_trade():
    with tempfile.TemporaryDirectory() as d:
        tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
        today = date.today()
        tracker.record_day_trade("AAPL", today)
        assert tracker.day_trades_used(today) == 1


def test_rolling_5_business_days_excludes_older():
    with tempfile.TemporaryDirectory() as d:
        tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
        today = date(2026, 3, 20)  # Friday
        # 5 business days back from Friday 2026-03-20: Mon 16, Tue 17, Wed 18, Thu 19, Fri 20
        # A trade on Mon 2026-03-09 (10 business days ago) must not be counted
        old_trade_date = date(2026, 3, 9)  # Monday, well outside window
        tracker.record_day_trade("TSLA", old_trade_date)
        assert tracker.day_trades_used(today) == 0


def test_weekends_not_counted_as_business_days():
    with tempfile.TemporaryDirectory() as d:
        tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
        friday = date(2026, 3, 20)
        prior_monday = date(2026, 3, 16)
        tracker.record_day_trade("AAPL", prior_monday)
        tracker.record_day_trade("TSLA", friday)
        assert tracker.day_trades_used(friday) == 2


def test_slots_remaining_decrements_correctly():
    with tempfile.TemporaryDirectory() as d:
        tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
        today = date.today()
        assert tracker.slots_remaining(today) == 3
        tracker.record_day_trade("AAPL", today)
        assert tracker.slots_remaining(today) == 2
        tracker.record_day_trade("TSLA", today)
        assert tracker.slots_remaining(today) == 1
        tracker.record_day_trade("NVDA", today)
        assert tracker.slots_remaining(today) == 0


def test_get_allowed_tags_0_slots_empty_set():
    with tempfile.TemporaryDirectory() as d:
        tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
        today = date.today()
        for sym in ("A", "B", "C"):
            tracker.record_day_trade(sym, today)
        assert tracker.get_allowed_tags(today) == set()


def test_get_allowed_tags_1_slot_high_conviction_only():
    with tempfile.TemporaryDirectory() as d:
        tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
        today = date.today()
        for sym in ("A", "B"):
            tracker.record_day_trade(sym, today)
        tags = tracker.get_allowed_tags(today)
        assert tags == {"HIGH_CONVICTION"}


def test_corrupt_file_returns_3_slots():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "pdt_trades.json"
        f.write_text("NOT VALID JSON {{{{")
        tracker = PDTTracker(trades_file=f)
        assert tracker.slots_remaining(date.today()) == 3
