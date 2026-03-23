import json
import statistics
from pathlib import Path

LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_FILE = LEARNING_DIR / "stop_distance_stats.json"
SEED_STOP_PCT = 3.0
MIN_SAMPLES = 10


class StopDistanceStore:
    """Learns optimal stop distance per bucket key."""

    def __init__(self, stats_file: Path = DEFAULT_FILE):
        self._file = stats_file

    def _load(self) -> dict:
        if not self._file.exists():
            return {}
        try:
            return json.loads(self._file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(data, indent=2))

    def record(self, bucket_key: str, stop_pct: float, outcome: str) -> None:
        """Record a trade's stop distance and outcome."""
        data = self._load()
        bucket = data.get(bucket_key, {"stop_pcts": [], "outcomes": []})
        bucket["stop_pcts"].append(stop_pct)
        bucket["outcomes"].append(outcome)
        data[bucket_key] = bucket
        self._save(data)

    def get_stop_pct(self, bucket_key: str) -> float:
        """Returns learned optimal stop %. Falls back to SEED_STOP_PCT if < MIN_SAMPLES."""
        try:
            data = self._load()
            if bucket_key not in data:
                return SEED_STOP_PCT
            bucket = data[bucket_key]
            stop_pcts = bucket.get("stop_pcts", [])
            outcomes = bucket.get("outcomes", [])
            if len(stop_pcts) < MIN_SAMPLES:
                return SEED_STOP_PCT
            winning_stops = [pct for pct, outcome in zip(stop_pcts, outcomes) if outcome == "win"]
            if not winning_stops:
                return SEED_STOP_PCT
            return statistics.median(winning_stops)
        except Exception:
            return SEED_STOP_PCT
