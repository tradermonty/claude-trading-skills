import json
from pathlib import Path

LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_FILE = LEARNING_DIR / "time_of_day_stats.json"


class TimeOfDayTracker:
    """Tracks win rates per hour of the trading day (ET). Hours 9-15."""

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

    def record(self, entry_hour_et: int, outcome: str) -> None:
        """Record outcome for an hour. outcome must be 'win' or 'loss'."""
        if outcome not in ("win", "loss"):
            return
        data = self._load()
        key = str(entry_hour_et)
        bucket = data.get(key, {"wins": 0, "losses": 0})
        if outcome == "win":
            bucket["wins"] = bucket.get("wins", 0) + 1
        else:
            bucket["losses"] = bucket.get("losses", 0) + 1
        data[key] = bucket
        self._save(data)

    def get_confidence_adjustment(self, hour_et: int) -> str:
        """Returns required min confidence tag for this hour.
        'NORMAL' if < 10 samples or win_rate >= 40%
        'HIGH_CONVICTION' if win_rate 30-40% and n >= 10
        'BLOCKED' if win_rate < 30% and n >= 10
        """
        try:
            data = self._load()
            bucket = data.get(str(hour_et), {})
            wins = bucket.get("wins", 0)
            losses = bucket.get("losses", 0)
            n = wins + losses
            if n < 10:
                return "NORMAL"
            win_rate = wins / n
            if win_rate < 0.30:
                return "BLOCKED"
            elif win_rate < 0.40:
                return "HIGH_CONVICTION"
            return "NORMAL"
        except Exception:
            return "NORMAL"

    def get_stats(self) -> dict:
        """Returns all hour stats for the /stats page."""
        return self._load()
