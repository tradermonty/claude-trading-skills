"""Alpaca implementation of the broker short-inventory adapter.

Uses ``requests`` against the public Alpaca Asset endpoint
(``GET /v2/assets/{symbol}``) so this skill stays compatible with the
existing portfolio-manager skill (which already takes the same approach)
and avoids adding the ``alpaca-py`` SDK as a dependency.

Important Alpaca-specific facts that the contract reflects:

- New shorts are only permitted on **ETB (Easy-To-Borrow)** names.
  Hard-to-borrow names cannot be opened on Alpaca regardless of locate.
- Alpaca does NOT publish a borrow-fee schedule via API. ETB names are
  effectively 0% but anything not ETB is "manual check required".
- Alpaca does not support self-service locate. A non-ETB name simply
  cannot be opened, so ``manual_locate_required`` is always True (the
  trader must confirm at the broker even for ETB symbols).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    import requests
except ImportError as e:  # pragma: no cover - environment check
    raise RuntimeError("alpaca_inventory_adapter requires the `requests` package") from e

from broker_short_inventory_adapter import (
    BrokerNotConfiguredError,
    BrokerShortInventoryAdapter,
)

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
LIVE_BASE_URL = "https://api.alpaca.markets"


class AlpacaInventoryAdapter(BrokerShortInventoryAdapter):
    """Read-only adapter that calls ``/v2/assets/{symbol}`` on Alpaca."""

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        if not self.api_key or not self.secret_key:
            raise BrokerNotConfiguredError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set (env vars or constructor args)."
            )
        self.paper = paper
        self.base_url = PAPER_BASE_URL if paper else LIVE_BASE_URL
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    def get_inventory_status(self, symbol: str) -> dict:
        url = f"{self.base_url}/v2/assets/{symbol}"
        response = requests.get(url, headers=self._headers(), timeout=self.timeout)
        response.raise_for_status()
        data = response.json()

        shortable = bool(data.get("shortable"))
        etb = bool(data.get("easy_to_borrow"))
        # Alpaca: new shorts only on ETB names. Treat HTB-but-shortable as
        # ``not openable`` so Phase 2 surfaces a blocking reason.
        can_open = shortable and etb
        return {
            "shortable": shortable,
            "easy_to_borrow": etb,
            "can_open_new_short": can_open,
            "borrow_fee_apr": 0.0 if etb else None,
            "borrow_fee_manual_check_required": not etb,
            "manual_locate_required": True,
            "source": "alpaca_v2_assets",
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
