"""Broker-agnostic short-inventory interface.

Phase 2 needs four answers from the broker before it can render a trade
plan: can we open a new short, what is the borrow fee, do we know the
fee, and is a manual locate needed. Different brokers expose this with
very different APIs (Alpaca: shortable / easy_to_borrow flags;
Interactive Brokers: locate API + borrow rate sheet), so the screener
talks to a thin adapter layer instead of a specific broker SDK.

Contract:

    {
        "shortable": bool,
        "easy_to_borrow": bool,
        "can_open_new_short": bool,           # alias for shortable AND ETB
        "borrow_fee_apr": float | None,       # 0.0 for ETB on Alpaca; None
                                              # if the broker can't quote
        "borrow_fee_manual_check_required": bool,
        "manual_locate_required": bool,       # always True for Alpaca short
        "source": str,                        # e.g. "alpaca_v2_assets"
        "checked_at": str,                    # ISO 8601 UTC
    }

Adapters MUST raise ``BrokerNotConfiguredError`` if their credentials are
missing — the CLI uses that to flip to ``--broker none`` (manual checklist)
instead of crashing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BrokerNotConfiguredError(RuntimeError):
    """Raised when a broker adapter is invoked without required credentials."""


class BrokerShortInventoryAdapter(ABC):
    """Interface every broker adapter must implement."""

    @abstractmethod
    def get_inventory_status(self, symbol: str) -> dict:
        """Return the contract dict described in the module docstring."""
        raise NotImplementedError

    def can_open_new_short(self, symbol: str) -> bool:
        """Convenience: True iff ``get_inventory_status`` says yes."""
        return bool(self.get_inventory_status(symbol).get("can_open_new_short"))


class ManualBrokerAdapter(BrokerShortInventoryAdapter):
    """Sentinel adapter used when ``--broker none`` is passed.

    Returns a dict that flags every gate as ``manual_check_required`` so
    the Phase 2 plan output explicitly tells the trader to verify locate
    and shortability at the broker before entering.
    """

    def get_inventory_status(self, symbol: str) -> dict:
        from datetime import datetime, timezone

        return {
            "shortable": None,
            "easy_to_borrow": None,
            "can_open_new_short": False,  # default-deny: tell Phase 2 to block
            "borrow_fee_apr": None,
            "borrow_fee_manual_check_required": True,
            "manual_locate_required": True,
            "source": "manual",
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
