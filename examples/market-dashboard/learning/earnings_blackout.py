from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path


class EarningsBlackout:
    def __init__(self, cache_dir: Path):
        self._cache_dir = Path(cache_dir)

    def is_blacked_out(self, symbol: str, as_of_date: date, blackout_days: int) -> bool:
        """Returns True if symbol has earnings within blackout_days calendar days.
        Returns False if blackout_days == 0 or cache missing/corrupt (fail open).
        """
        if blackout_days == 0:
            return False
        calendar_file = self._cache_dir / "earnings-calendar.json"
        if not calendar_file.exists():
            return False
        try:
            data = json.loads(calendar_file.read_text())
        except Exception:
            return False
        end_date = as_of_date + timedelta(days=blackout_days - 1)
        for event in data.get("events", []):
            try:
                if event.get("symbol", "").upper() != symbol.upper():
                    continue
                event_date = datetime.fromisoformat(event["date"]).date()
                if as_of_date <= event_date <= end_date:
                    return True
            except Exception:
                continue
        return False
