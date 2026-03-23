import sys, json, tempfile, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def make_store(tmp: Path):
    from learning.stop_distance_store import StopDistanceStore
    return StopDistanceStore(stats_file=tmp / "stop_distance_stats.json")

def test_returns_seed_when_below_min_samples():
    from learning.stop_distance_store import SEED_STOP_PCT
    with tempfile.TemporaryDirectory() as d:
        store = make_store(Path(d))
        assert store.get_stop_pct("vcp+CLEAR+bull") == SEED_STOP_PCT

def test_returns_median_of_winning_stops_when_enough_samples():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(Path(d))
        wins = [2.5, 2.7, 2.8, 3.0, 3.1, 3.3, 3.5]
        for pct in wins:
            store.record("vcp+CLEAR+bull", pct, "win")
        for pct in [1.5, 2.0, 4.0]:
            store.record("vcp+CLEAR+bull", pct, "loss")
        result = store.get_stop_pct("vcp+CLEAR+bull")
        # median of sorted wins [2.5,2.7,2.8,3.0,3.1,3.3,3.5] = 3.0
        assert result == 3.0

def test_record_appends_correctly():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        store = make_store(tmp)
        store.record("vcp+CLEAR+bull", 3.0, "win")
        store.record("vcp+CLEAR+bull", 2.5, "loss")
        data = json.loads((tmp / "stop_distance_stats.json").read_text())
        assert data["vcp+CLEAR+bull"]["stop_pcts"] == [3.0, 2.5]
        assert data["vcp+CLEAR+bull"]["outcomes"] == ["win", "loss"]

def test_corrupt_file_returns_seed_default():
    from learning.stop_distance_store import SEED_STOP_PCT
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "stop_distance_stats.json").write_text("not valid json")
        store = make_store(tmp)
        assert store.get_stop_pct("vcp+CLEAR+bull") == SEED_STOP_PCT

def test_unknown_bucket_returns_seed_default():
    from learning.stop_distance_store import SEED_STOP_PCT
    with tempfile.TemporaryDirectory() as d:
        store = make_store(Path(d))
        assert store.get_stop_pct("nonexistent+bucket+key") == SEED_STOP_PCT
