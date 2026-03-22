from __future__ import annotations

import json
from datetime import date
from pathlib import Path

LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_FILE = LEARNING_DIR / "drawdown_state.json"


class DrawdownTracker:
    def __init__(self, state_file: Path = DEFAULT_STATE_FILE):
        self._state_file = Path(state_file)

    def _load(self) -> dict:
        if not self._state_file.exists():
            return {}
        try:
            return json.loads(self._state_file.read_text())
        except Exception:
            return {}

    def _save(self, state: dict) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(state, indent=2))

    def update(self, portfolio_value: float, as_of_date: date) -> None:
        state = self._load()
        today_str = as_of_date.isoformat()

        # Reset week_start on Monday (weekday 0)
        if as_of_date.weekday() == 0 and state.get("week_start_date") != today_str:
            state["week_start_value"] = portfolio_value
            state["week_start_date"] = today_str

        # Set week_start if never recorded
        if "week_start_value" not in state:
            state["week_start_value"] = portfolio_value
            state["week_start_date"] = today_str

        # Update day_start whenever date changes
        if state.get("day_start_date") != today_str:
            state["day_start_value"] = portfolio_value
            state["day_start_date"] = today_str

        self._save(state)

    def is_weekly_limit_breached(self, portfolio_value: float, max_pct: float) -> bool:
        if max_pct >= 100:
            return False
        state = self._load()
        if "week_start_value" not in state:
            return False
        ref = state["week_start_value"]
        if ref <= 0:
            return False
        drop_pct = (ref - portfolio_value) / ref * 100
        return drop_pct >= max_pct

    def is_daily_limit_breached(self, portfolio_value: float, max_pct: float) -> bool:
        if max_pct >= 100:
            return False
        state = self._load()
        if "day_start_value" not in state:
            return False
        ref = state["day_start_value"]
        if ref <= 0:
            return False
        drop_pct = (ref - portfolio_value) / ref * 100
        return drop_pct >= max_pct
