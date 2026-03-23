# tests/test_earnings_blackout.py
import sys
import json
import tempfile
from pathlib import Path
from datetime import date, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learning.earnings_blackout import EarningsBlackout


def _write_calendar(cache_dir: Path, events: list) -> None:
    (cache_dir / "earnings-calendar.json").write_text(
        json.dumps({"events": events})
    )


def test_symbol_within_blackout_returns_true():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d)
        today = date(2026, 3, 22)
        earnings_in_3_days = (today + timedelta(days=3)).isoformat() + "T07:00:00"
        _write_calendar(cache, [{"symbol": "AAPL", "date": earnings_in_3_days}])
        eb = EarningsBlackout(cache_dir=cache)
        assert eb.is_blacked_out("AAPL", today, blackout_days=5) is True


def test_symbol_outside_blackout_returns_false():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d)
        today = date(2026, 3, 22)
        earnings_in_10_days = (today + timedelta(days=10)).isoformat() + "T07:00:00"
        _write_calendar(cache, [{"symbol": "AAPL", "date": earnings_in_10_days}])
        eb = EarningsBlackout(cache_dir=cache)
        assert eb.is_blacked_out("AAPL", today, blackout_days=5) is False


def test_disabled_at_0_days():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d)
        today = date(2026, 3, 22)
        tomorrow = (today + timedelta(days=1)).isoformat() + "T07:00:00"
        _write_calendar(cache, [{"symbol": "AAPL", "date": tomorrow}])
        eb = EarningsBlackout(cache_dir=cache)
        # blackout_days=0 means disabled — never block
        assert eb.is_blacked_out("AAPL", today, blackout_days=0) is False


def test_missing_cache_returns_false():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d)
        # No earnings-calendar.json written — must fail open
        eb = EarningsBlackout(cache_dir=cache)
        assert eb.is_blacked_out("AAPL", date.today(), blackout_days=5) is False


def test_symbol_not_in_calendar_returns_false():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d)
        today = date(2026, 3, 22)
        tomorrow = (today + timedelta(days=1)).isoformat() + "T07:00:00"
        _write_calendar(cache, [{"symbol": "TSLA", "date": tomorrow}])
        eb = EarningsBlackout(cache_dir=cache)
        # AAPL not in the calendar — must not be blocked
        assert eb.is_blacked_out("AAPL", today, blackout_days=5) is False
