"""A deliberately tiny, read-only Alpaca client.

It can only send GET requests to two endpoints: the account and open positions.
There is no code path that places, changes or cancels an order.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any
from urllib.request import Request, urlopen

PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"


class AlpacaError(RuntimeError):
    pass


class AlpacaReadOnly:
    def __init__(
        self,
        key_id: str,
        secret: str,
        paper: bool = True,
        timeout: int = 10,
        cache_seconds: int = 60,
    ) -> None:
        self._key_id = key_id
        self._secret = secret
        self.paper = paper
        self.base_url = PAPER_URL if paper else LIVE_URL
        self._timeout = timeout
        self._cache_seconds = cache_seconds
        self._cached: tuple[float, dict[str, Any]] | None = None

    def _get(self, path: str) -> Any:
        req = Request(
            self.base_url + path,
            method="GET",
            headers={
                "APCA-API-KEY-ID": self._key_id,
                "APCA-API-SECRET-KEY": self._secret,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:  # network, HTTP 4xx/5xx, bad JSON
            # Never echo headers: they hold the keys.
            raise AlpacaError(f"Alpaca request to {path} failed: {type(exc).__name__}") from None

    def account(self) -> dict[str, Any]:
        return self._get("/v2/account")

    def positions(self) -> list[dict[str, Any]]:
        return self._get("/v2/positions")

    def snapshot(self) -> dict[str, Any]:
        """Account + positions, cached briefly so page reloads don't hammer the API."""
        now = time.monotonic()
        if self._cached and now - self._cached[0] < self._cache_seconds:
            return self._cached[1]
        try:
            snap = {"account": self.account(), "positions": self.positions(), "error": None}
        except AlpacaError as exc:
            snap = {"account": None, "positions": [], "error": str(exc)}
        snap["paper"] = self.paper
        self._cached = (now, snap)
        return snap


def from_env(env: Mapping[str, str]) -> AlpacaReadOnly | None:
    key = env.get("ALPACA_API_KEY", "").strip()
    secret = env.get("ALPACA_SECRET_KEY", "").strip()
    if not key or not secret:
        return None
    return AlpacaReadOnly(key, secret, paper=is_paper(env))


def is_paper(env: Mapping[str, str]) -> bool:
    """ALPACA_ENV=paper|live decides. Anything other than an explicit "live" stays paper.

    ALPACA_PAPER=false (the repo's older convention) is honored only when ALPACA_ENV is unset.
    """
    mode = env.get("ALPACA_ENV", "").strip().lower()
    if mode:
        return mode != "live"
    return env.get("ALPACA_PAPER", "true").strip().lower() not in {"false", "0", "no"}
