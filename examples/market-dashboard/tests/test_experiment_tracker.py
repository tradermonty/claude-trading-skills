import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def make_tracker(tmp: Path, is_paper: bool = True):
    from learning.experiment_tracker import ExperimentTracker
    return ExperimentTracker(
        experiments_file=tmp / "experiments.json",
        is_paper=is_paper,
    )

def test_should_experiment_always_false_in_live_mode():
    with tempfile.TemporaryDirectory() as d:
        tracker = make_tracker(Path(d), is_paper=False)
        results = [tracker.should_experiment() for _ in range(200)]
        assert all(r is False for r in results)

def test_should_experiment_returns_true_roughly_10_pct_in_paper_mode():
    with tempfile.TemporaryDirectory() as d:
        tracker = make_tracker(Path(d), is_paper=True)
        results = [tracker.should_experiment() for _ in range(1000)]
        rate = sum(results) / len(results)
        # Allow wide margin: 5-20% range
        assert 0.05 <= rate <= 0.20

def test_get_variation_returns_valid_dict():
    with tempfile.TemporaryDirectory() as d:
        tracker = make_tracker(Path(d))
        variation = tracker.get_variation()
        assert "stop_pct" in variation
        assert "partial_exit_at_r" in variation
        assert "min_volume_ratio" in variation
        assert variation["stop_pct"] in [2.5, 3.0, 3.5]
        assert variation["partial_exit_at_r"] in [0.75, 1.0, 1.25, 1.5]
        assert variation["min_volume_ratio"] in [1.25, 1.5, 1.75, 2.0]

def test_record_experiment_saves_to_file():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tracker = make_tracker(tmp)
        variation = {"stop_pct": 2.5, "partial_exit_at_r": 1.0, "min_volume_ratio": 1.5}
        tracker.record_experiment("exp_001", variation, "win", 2.1)
        data = json.loads((tmp / "experiments.json").read_text())
        assert "experiments" in data
        assert len(data["experiments"]) >= 1

def test_should_promote_true_when_variation_beats_control_by_5pct_with_n10():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tracker = make_tracker(tmp)
        variation = {"stop_pct": 2.5, "partial_exit_at_r": 1.0, "min_volume_ratio": 1.5}
        # Record 10 wins for variation → 100% win rate
        for i in range(10):
            tracker.record_experiment(f"exp_{i}", variation, "win", 2.0)
        # Control: 50% win rate
        data = json.loads((tmp / "experiments.json").read_text())
        data["control"] = {"wins": 5, "losses": 5}
        (tmp / "experiments.json").write_text(json.dumps(data))
        data = json.loads((tmp / "experiments.json").read_text())
        var_key = list(data["experiments"].keys())[0]
        assert tracker.should_promote(var_key) is True

def test_should_promote_false_with_insufficient_data():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tracker = make_tracker(tmp)
        variation = {"stop_pct": 2.5, "partial_exit_at_r": 1.0, "min_volume_ratio": 1.5}
        # Only 9 samples — below threshold
        for i in range(9):
            tracker.record_experiment(f"exp_{i}", variation, "win", 2.0)
        data = json.loads((tmp / "experiments.json").read_text())
        var_key = list(data["experiments"].keys())[0]
        assert tracker.should_promote(var_key) is False
