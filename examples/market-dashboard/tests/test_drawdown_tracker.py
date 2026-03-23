# tests/test_drawdown_tracker.py
import sys
import json
import tempfile
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learning.drawdown_tracker import DrawdownTracker


def test_weekly_limit_not_breached_when_above_threshold():
    with tempfile.TemporaryDirectory() as d:
        tracker = DrawdownTracker(state_file=Path(d) / "drawdown_state.json")
        monday = date(2026, 3, 16)  # a Monday
        tracker.update(10000.0, monday)
        # 9100 is only a 9% drop — under the 10% limit
        assert tracker.is_weekly_limit_breached(9100.0, max_pct=10.0) is False


def test_weekly_limit_breached_when_below_threshold():
    with tempfile.TemporaryDirectory() as d:
        tracker = DrawdownTracker(state_file=Path(d) / "drawdown_state.json")
        monday = date(2026, 3, 16)
        tracker.update(10000.0, monday)
        # 8900 is an 11% drop — over the 10% limit
        assert tracker.is_weekly_limit_breached(8900.0, max_pct=10.0) is True


def test_disabled_at_100_pct():
    with tempfile.TemporaryDirectory() as d:
        tracker = DrawdownTracker(state_file=Path(d) / "drawdown_state.json")
        monday = date(2026, 3, 16)
        tracker.update(10000.0, monday)
        # Even a catastrophic drop must not block when max_pct=100
        assert tracker.is_weekly_limit_breached(1.0, max_pct=100.0) is False
        assert tracker.is_daily_limit_breached(1.0, max_pct=100.0) is False


def test_daily_limit_breached():
    with tempfile.TemporaryDirectory() as d:
        tracker = DrawdownTracker(state_file=Path(d) / "drawdown_state.json")
        today = date(2026, 3, 22)  # a Saturday — not Monday, so only day_start is set
        tracker.update(10000.0, today)
        # 9400 is a 6% drop — over the 5% daily limit
        assert tracker.is_daily_limit_breached(9400.0, max_pct=5.0) is True


def test_week_start_resets_on_monday():
    with tempfile.TemporaryDirectory() as d:
        state_file = Path(d) / "drawdown_state.json"
        tracker = DrawdownTracker(state_file=state_file)
        friday = date(2026, 3, 20)
        tracker.update(10000.0, friday)
        monday = date(2026, 3, 23)
        tracker.update(9500.0, monday)
        # week_start_value is now 9500 — a further 10% drop to 8550 should breach
        assert tracker.is_weekly_limit_breached(8550.0, max_pct=10.0) is True
        # But 8600 is only ~9.5% — should not breach
        assert tracker.is_weekly_limit_breached(8600.0, max_pct=10.0) is False


def test_missing_state_file_returns_false():
    with tempfile.TemporaryDirectory() as d:
        tracker = DrawdownTracker(state_file=Path(d) / "does_not_exist.json")
        # No history = no block (fail open)
        assert tracker.is_weekly_limit_breached(1.0, max_pct=5.0) is False
        assert tracker.is_daily_limit_breached(1.0, max_pct=5.0) is False
