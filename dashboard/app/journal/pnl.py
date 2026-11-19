"""P&L math for the trade journal.

Pure functions, no database. Money and quantities are Decimal, never float, so
0.00012345 BTC and penny rounding stay exact.

How a trade's P&L is worked out:
- Fills are grouped by instrument (one stock, one option contract, one coin).
- Each instrument is matched FIFO (first in, first out): a sell closes the oldest
  open buy first. Shorts work the same way in reverse.
- Realized P&L = (close price - open price) x quantity x multiplier for every
  matched piece, minus all fees. The multiplier is 100 for a normal option.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

ZERO = Decimal("0")


def dec(value: Any, default: Decimal | None = ZERO) -> Decimal | None:
    """Turn user or CSV text into a Decimal. Strips $, commas and spaces."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace("$", "").replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if not text:
        return default
    try:
        number = Decimal(text)
    except InvalidOperation:
        return default
    return -number if negative else number


@dataclass
class Fill:
    side: str  # "buy" or "sell"
    quantity: Decimal  # always positive
    price: Decimal
    fee: Decimal = ZERO
    multiplier: Decimal = Decimal("1")
    instrument: Any = "default"  # anything hashable that names the instrument
    executed_at: str = ""
    fee_in_quote: bool = True  # False when the fee was paid in the coin itself

    @property
    def signed_qty(self) -> Decimal:
        return self.quantity if self.side == "buy" else -self.quantity

    @property
    def fee_value(self) -> Decimal:
        # A fee paid in coin is worth fee x that fill's price in dollars.
        return self.fee if self.fee_in_quote else self.fee * self.price


@dataclass
class LegResult:
    instrument: Any
    open_qty: Decimal = ZERO  # signed: positive long, negative short
    realized: Decimal = ZERO  # before fees
    bought_qty: Decimal = ZERO
    bought_value: Decimal = ZERO
    sold_qty: Decimal = ZERO
    sold_value: Decimal = ZERO


@dataclass
class TradeResult:
    legs: list[LegResult] = field(default_factory=list)
    realized_gross: Decimal = ZERO
    fees: Decimal = ZERO
    first_side: str | None = None
    opened_at: str | None = None
    last_fill_at: str | None = None

    @property
    def net(self) -> Decimal:
        return self.realized_gross - self.fees

    @property
    def is_open(self) -> bool:
        return any(leg.open_qty != 0 for leg in self.legs)

    @property
    def status(self) -> str:
        if not self.legs:
            return "empty"
        return "open" if self.is_open else "closed"

    @property
    def closed_at(self) -> str | None:
        return None if self.is_open or not self.legs else self.last_fill_at


def compute(fills: Iterable[Fill]) -> TradeResult:
    """FIFO-match fills (already in time order) and total up the P&L."""
    result = TradeResult()
    lots: dict[Any, deque[list[Decimal]]] = {}
    legs: dict[Any, LegResult] = {}
    for f in fills:
        if f.quantity <= 0:
            continue
        if result.first_side is None:
            result.first_side = f.side
            result.opened_at = f.executed_at or None
        result.last_fill_at = f.executed_at or result.last_fill_at
        leg = legs.setdefault(f.instrument, LegResult(instrument=f.instrument))
        book = lots.setdefault(f.instrument, deque())
        result.fees += f.fee_value
        value = f.quantity * f.price * f.multiplier
        if f.side == "buy":
            leg.bought_qty += f.quantity
            leg.bought_value += value
        else:
            leg.sold_qty += f.quantity
            leg.sold_value += value

        remaining = f.signed_qty
        # Close opposite-signed lots first (FIFO), then open a new lot with what's left.
        while remaining != 0 and book and (book[0][0] > 0) != (remaining > 0):
            lot_qty, lot_price = book[0]
            matched = min(abs(lot_qty), abs(remaining))
            # Long lot closed by a sell: (sell - buy). Short lot closed by a buy: (sell - buy) too.
            if lot_qty > 0:
                leg.realized += (f.price - lot_price) * matched * f.multiplier
            else:
                leg.realized += (lot_price - f.price) * matched * f.multiplier
            lot_qty += matched if lot_qty < 0 else -matched
            remaining += matched if remaining < 0 else -matched
            if lot_qty == 0:
                book.popleft()
            else:
                book[0][0] = lot_qty
        if remaining != 0:
            book.append([remaining, f.price])
        leg.open_qty = sum((lot[0] for lot in book), ZERO)
    result.legs = list(legs.values())
    result.realized_gross = sum((leg.realized for leg in result.legs), ZERO)
    return result


def r_multiple(
    net: Decimal, entry: Decimal | None, stop: Decimal | None, qty: Decimal, multiplier: Decimal
) -> Decimal | None:
    """P&L in units of planned risk. 1R = what you'd lose if the stop was hit."""
    if entry is None or stop is None or qty == 0:
        return None
    risk = abs(entry - stop) * qty * multiplier
    if risk == 0:
        return None
    return net / risk


def summarize(closed: list[dict]) -> dict[str, Any]:
    """Stats over closed trades. Each item needs 'net' (Decimal)."""
    wins = [t["net"] for t in closed if t["net"] > 0]
    losses = [t["net"] for t in closed if t["net"] < 0]
    total = sum((t["net"] for t in closed), ZERO)
    gross_win = sum(wins, ZERO)
    gross_loss = -sum(losses, ZERO)
    count = len(closed)
    return {
        "count": count,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (Decimal(len(wins)) / count * 100) if count else None,
        "net": total,
        "avg_win": (gross_win / len(wins)) if wins else None,
        "avg_loss": (-gross_loss / len(losses)) if losses else None,
        "profit_factor": (gross_win / gross_loss) if gross_loss else None,
        "expectancy": (total / count) if count else None,
        "best": max(wins) if wins else None,
        "worst": min(losses) if losses else None,
    }
