from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_TRADES_FILE = LEARNING_DIR / "pdt_trades.json"


class PDTTracker:
    def __init__(self, trades_file: Path = DEFAULT_TRADES_FILE):
        self._trades_file = Path(trades_file)

    def _load(self) -> dict:
        if not self._trades_file.exists():
            return {"trades": []}
        try:
            return json.loads(self._trades_file.read_text())
        except Exception:
            return {"trades": []}

    def _save(self, data: dict) -> None:
        self._trades_file.parent.mkdir(parents=True, exist_ok=True)
        self._trades_file.write_text(json.dumps(data, indent=2))

    def _business_days_window(self, as_of_date: date, n: int = 5) -> list[date]:
        """Return the n most recent business days on or before as_of_date, plus
        as_of_date itself unconditionally (so trades recorded on a weekend are
        still counted within the rolling window)."""
        result = []
        current = as_of_date
        while len(result) < n:
            if current.weekday() < 5:
                result.append(current)
            elif current == as_of_date:
                # Always include as_of_date regardless of weekday so that trades
                # recorded on a non-business day are still captured.
                result.append(current)
            current -= timedelta(days=1)
        return result

    def record_day_trade(self, symbol: str, trade_date: date) -> None:
        data = self._load()
        data["trades"].append({"symbol": symbol, "date": trade_date.isoformat()})
        self._save(data)

    def day_trades_used(self, as_of_date: date) -> int:
        try:
            data = self._load()
            window = set(d.isoformat() for d in self._business_days_window(as_of_date))
            return sum(1 for t in data.get("trades", []) if t.get("date") in window)
        except Exception:
            return 0

    def slots_remaining(self, as_of_date: date) -> int:
        return max(0, 3 - self.day_trades_used(as_of_date))

    def get_allowed_tags(self, as_of_date: date) -> set[str]:
        slots = self.slots_remaining(as_of_date)
        if slots == 0:
            return set()
        if slots == 1:
            return {"HIGH_CONVICTION"}
        if slots == 2:
            return {"HIGH_CONVICTION", "CLEAR"}
        return {"HIGH_CONVICTION", "CLEAR", "UNCERTAIN"}
