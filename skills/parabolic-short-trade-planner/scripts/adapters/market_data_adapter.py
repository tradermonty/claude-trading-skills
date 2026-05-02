"""Abstract base for intraday bar fetchers used by Phase 3.

Two concrete implementations live alongside this file:

- ``FixtureBarsAdapter`` reads a JSON file mapping ``ticker -> [bars]``
  and is used in every unit test.
- ``AlpacaMarketDataAdapter`` calls
  ``data.alpaca.markets/v2/stocks/{symbol}/bars`` and is the live data
  source.

The Phase 3 FSM evaluators are pure functions — they never touch an
adapter directly. The CLI (`monitor_intraday_trigger.py`) instantiates
the right adapter based on ``--bars-source`` and passes the bar list
into ``intraday_state_machine.step_one_plan``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class MarketDataAdapter(ABC):
    """Contract every Phase 3 bar fetcher must satisfy."""

    @abstractmethod
    def get_bars_5min(
        self,
        symbol: str,
        *,
        session_date: str,
        until_et: datetime,
    ) -> list[dict]:
        """Return 5-min bars for the regular session of ``session_date``.

        Returned bars MUST be:
          - chronological (oldest first),
          - all from the regular cash session (09:30–16:00 ET) of
            ``session_date``,
          - filtered to **confirmed** bars only: a bar with ``ts_et =
            T`` covers ``[T, T+5min)`` and is confirmed at ``T+5min``,
            so the bar is included iff ``T + 5min <= until_et``.
            Implementations MUST NOT include unconfirmed (still-open)
            bars even if Alpaca returns them with the current minute's
            timestamp,
          - in this dict shape exactly:
              {"ts_et": <ISO 8601 with America/New_York tz; bar-open>,
               "o": float, "h": float, "l": float, "c": float,
               "v": int}

        Implementations MUST return ``[]`` (not raise) when:
          - the symbol is not in the universe (e.g. delisted, paper
            account doesn't have it),
          - the session hasn't opened yet,
          - it's a weekend / market holiday.

        ``session_date`` is the ET wall-clock date (``YYYY-MM-DD``),
        NOT a UTC date. Use ``market_clock.session_date_for(now_et)``
        to compute it.
        """
        raise NotImplementedError
