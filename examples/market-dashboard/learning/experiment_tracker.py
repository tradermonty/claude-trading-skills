import json
import random
from pathlib import Path

LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_FILE = LEARNING_DIR / "experiments.json"
EXPLORATION_RATE = 0.10


class ExperimentTracker:
    """Paper trading only. Tries parameter variations 10% of the time."""

    def __init__(self, experiments_file: Path = DEFAULT_FILE, is_paper: bool = True):
        self._file = experiments_file
        self._is_paper = is_paper

    def _load(self) -> dict:
        if not self._file.exists():
            return {"experiments": {}, "control": {"wins": 0, "losses": 0}}
        try:
            return json.loads(self._file.read_text())
        except (json.JSONDecodeError, OSError):
            return {"experiments": {}, "control": {"wins": 0, "losses": 0}}

    def _save(self, data: dict) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(data, indent=2))

    def should_experiment(self) -> bool:
        """Returns True 10% of the time, only in paper mode."""
        if not self._is_paper:
            return False
        return random.random() < EXPLORATION_RATE

    def get_variation(self) -> dict:
        """Returns a random parameter variation dict."""
        return {
            "stop_pct": round(random.choice([2.5, 3.0, 3.5]), 1),
            "partial_exit_at_r": round(random.choice([0.75, 1.0, 1.25, 1.5]), 2),
            "min_volume_ratio": round(random.choice([1.25, 1.5, 1.75, 2.0]), 2),
        }

    def record_experiment(self, experiment_id: str, variation: dict, outcome: str, achieved_rr: float) -> None:
        """Record the outcome of an experiment."""
        data = self._load()
        variation_key = "&".join(f"{k}={v}" for k, v in sorted(variation.items()))
        if variation_key not in data["experiments"]:
            data["experiments"][variation_key] = {
                "wins": 0, "losses": 0, "achieved_rr": [], "variation": variation
            }
        exp = data["experiments"][variation_key]
        if outcome == "win":
            exp["wins"] += 1
        else:
            exp["losses"] += 1
        exp["achieved_rr"].append(achieved_rr)
        self._save(data)

    def should_promote(self, variation_key: str) -> bool:
        """Returns True if variation consistently outperforms control (win_rate + 5%, n>=10)."""
        try:
            data = self._load()
            if variation_key not in data.get("experiments", {}):
                return False
            exp = data["experiments"][variation_key]
            n = exp["wins"] + exp["losses"]
            if n < 10:
                return False
            exp_win_rate = exp["wins"] / n
            control = data.get("control", {})
            control_n = control.get("wins", 0) + control.get("losses", 0)
            if control_n == 0:
                return False
            control_win_rate = control["wins"] / control_n
            return exp_win_rate >= control_win_rate + 0.05
        except Exception:
            return False

    def get_stats(self) -> dict:
        """Returns all experiment stats for the /stats page."""
        return self._load()
