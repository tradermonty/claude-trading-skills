"""Fixture-driven MarketDataAdapter for offline testing.

A fixture file is a JSON object mapping ticker symbol → list of bars:

    {
      "AAPL": [
        {"ts_et": "2026-05-05T09:30:00-04:00",
         "o": 150.0, "h": 150.4, "l": 149.8, "c": 150.2, "v": 1200000},
        ...
      ],
      "NVDA": [...]
    }

Bars in the fixture should be pre-sorted chronological and use
**bar-open** semantics for ``ts_et`` (matching Alpaca wire). The
adapter only returns *confirmed* bars: a bar with ``ts_et = T``
covers ``[T, T+5min)`` and is confirmed at ``T+5min``, so it is
included only when ``T + 5min <= until_et``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from market_data_adapter import MarketDataAdapter

BAR_DURATION = timedelta(minutes=5)


class FixtureBarsAdapter(MarketDataAdapter):
    def __init__(self, fixture_path: str | Path) -> None:
        self._path = Path(fixture_path)
        self._cache: dict[str, list[dict]] | None = None

    def _load(self) -> dict[str, list[dict]]:
        if self._cache is None:
            with self._path.open(encoding="utf-8") as fh:
                self._cache = json.load(fh)
            if not isinstance(self._cache, dict):
                raise ValueError(
                    f"Fixture {self._path} must be a JSON object "
                    f"{{ticker: [bars]}}, got {type(self._cache).__name__}"
                )
        return self._cache

    def get_bars_5min(
        self,
        symbol: str,
        *,
        session_date: str,
        until_et: datetime,
    ) -> list[dict]:
        if until_et.tzinfo is None:
            raise ValueError("until_et must be timezone-aware")

        all_bars = self._load().get(symbol, [])
        if not all_bars:
            return []

        out: list[dict] = []
        for bar in all_bars:
            ts = datetime.fromisoformat(bar["ts_et"])
            if ts.tzinfo is None:
                # Defensive: a fixture writer might forget the offset.
                raise ValueError(f"Fixture bar for {symbol} is missing tz: {bar['ts_et']}")
            # Filter to the requested session date (ET wall-clock) and to
            # bars that have CLOSED at or before until_et (bar_open + 5
            # min — Alpaca-compatible bar-open semantics, see module
            # docstring).
            if ts.date().isoformat() != session_date:
                continue
            bar_close = ts + BAR_DURATION
            if bar_close > until_et:
                continue
            out.append(bar)
        return out
