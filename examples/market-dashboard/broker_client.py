"""Shared broker interface. Both AlpacaClient and IBKRClient implement this Protocol."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BrokerClient(Protocol):
    """Interface all broker clients must satisfy.

    place_bracket_order must return a dict containing at minimum:
      - "id": str           — primary order ID
      - "stop_order_id": str — ID of the stop-loss leg (used by trailing stop logic)
    """

    @property
    def is_configured(self) -> bool: ...

    def get_account(self) -> dict: ...

    def get_positions(self) -> list[dict]: ...

    def get_last_price(self, symbol: str) -> float: ...

    def get_current_volume(self, symbol: str) -> int: ...

    def place_bracket_order(
        self,
        symbol: str,
        qty: int,
        limit_price: float,
        stop_price: float,
        take_profit_price: float | None = None,
    ) -> dict: ...

    def place_market_sell(self, symbol: str, qty: int) -> dict: ...

    def replace_order_stop(self, order_id: str, new_stop_price: float) -> dict: ...

    async def subscribe_bars(self, symbols: list[str], callback) -> None: ...
