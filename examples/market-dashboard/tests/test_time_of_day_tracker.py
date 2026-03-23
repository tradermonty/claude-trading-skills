import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def make_tracker(tmp: Path):
    from learning.time_of_day_tracker import TimeOfDayTracker
    return TimeOfDayTracker(stats_file=tmp / "time_of_day_stats.json")

def test_record_win_increments_win_count():
    with tempfile.TemporaryDirectory() as d:
        tracker = make_tracker(Path(d))
        tracker.record(10, "win")
        tracker.record(10, "win")
        stats = tracker.get_stats()
        assert stats["10"]["wins"] == 2
        assert stats["10"]["losses"] == 0

def test_record_loss_increments_loss_count():
    with tempfile.TemporaryDirectory() as d:
        tracker = make_tracker(Path(d))
        tracker.record(11, "loss")
        stats = tracker.get_stats()
        assert stats["11"]["losses"] == 1
        assert stats["11"]["wins"] == 0

def test_insufficient_data_returns_normal():
    with tempfile.TemporaryDirectory() as d:
        tracker = make_tracker(Path(d))
        for _ in range(9):
            tracker.record(10, "loss")  # 9 samples, all losses — still < 10
        assert tracker.get_confidence_adjustment(10) == "NORMAL"

def test_win_rate_30_to_40_pct_returns_high_conviction():
    with tempfile.TemporaryDirectory() as d:
        tracker = make_tracker(Path(d))
        # 3 wins, 7 losses = 30% win rate, n=10
        for _ in range(3):
            tracker.record(9, "win")
        for _ in range(7):
            tracker.record(9, "loss")
        assert tracker.get_confidence_adjustment(9) == "HIGH_CONVICTION"

def test_win_rate_below_30_pct_returns_blocked():
    with tempfile.TemporaryDirectory() as d:
        tracker = make_tracker(Path(d))
        # 2 wins, 8 losses = 20% win rate, n=10
        for _ in range(2):
            tracker.record(14, "win")
        for _ in range(8):
            tracker.record(14, "loss")
        assert tracker.get_confidence_adjustment(14) == "BLOCKED"

def test_win_rate_above_40_pct_returns_normal():
    with tempfile.TemporaryDirectory() as d:
        tracker = make_tracker(Path(d))
        # 5 wins, 5 losses = 50% win rate, n=10
        for _ in range(5):
            tracker.record(11, "win")
        for _ in range(5):
            tracker.record(11, "loss")
        assert tracker.get_confidence_adjustment(11) == "NORMAL"
