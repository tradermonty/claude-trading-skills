"""Read Robinhood's account activity CSV into journal fills.

Where the file comes from: Robinhood app or website > Account > Reports and
statements > Reports > generate an account activity report (CSV).

Columns we use: Activity Date, Instrument, Description, Trans Code, Quantity,
Price, Amount. The file lists newest rows first and has no time of day, only a
date, so rows are reversed into time order and keep their position as a
tie-breaker for trades on the same day.

Trans codes:
- Buy / Sell: stocks and ETFs
- BTO / STC: buy to open / sell to close an option (a long option)
- STO / BTC: sell to open / buy to close an option (a short option)
- OEXP / OASGN / OEXCS: option expired, was assigned, or was exercised. The
  option is closed at $0; the stock side of an assignment shows up as its own
  Buy or Sell row.
Everything else (dividends, deposits, interest, fees, transfers) is skipped and
counted so the import page can show what was left out.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from .pnl import ZERO, dec

STOCK_CODES = {"Buy": "buy", "Sell": "sell"}
OPTION_CODES = {"BTO": "buy", "BTC": "buy", "STC": "sell", "STO": "sell"}
OPTION_CLOSE_CODES = {"OEXP": "expired", "OASGN": "assigned", "OEXCS": "exercised"}

# "AAPL 12/19/2026 Call $250.00" (also found inside "Option Expiration for ...")
OPTION_RE = re.compile(
    r"(?P<under>[A-Z][A-Z0-9.\-]*)\s+(?P<exp>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<right>Call|Put)\s+\$?(?P<strike>[\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
REQUIRED = {"Activity Date", "Instrument", "Trans Code", "Quantity", "Price"}


@dataclass
class ParsedFill:
    asset_class: str  # stock | option
    symbol: str
    side: str  # buy | sell | close (close = expiry/assignment, side decided later)
    quantity: Decimal
    price: Decimal
    fee: Decimal
    executed_at: str  # YYYY-MM-DD
    seq: int
    source_key: str
    underlying: str | None = None
    expiry: str | None = None
    strike: Decimal | None = None
    right: str | None = None
    multiplier: Decimal = Decimal("1")
    note: str | None = None


@dataclass
class ParseResult:
    fills: list[ParsedFill] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class NotRobinhoodCSV(ValueError):
    pass


def _date(text: str) -> str | None:
    text = (text or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _quantity(text: str) -> Decimal | None:
    # Short option rows can read "1S"; keep the number only.
    cleaned = re.sub(r"[^0-9.\-]", "", text or "")
    return dec(cleaned, None)


def parse_option(description: str) -> dict | None:
    m = OPTION_RE.search(description or "")
    if not m:
        return None
    expiry = _date(m.group("exp"))
    if not expiry:
        return None
    under = m.group("under").upper()
    right = m.group("right").lower()
    strike = dec(m.group("strike"), None)
    symbol = f"{under} {expiry} {strike:f} {'C' if right == 'call' else 'P'}"
    return {
        "underlying": under,
        "expiry": expiry,
        "right": right,
        "strike": strike,
        "symbol": symbol,
    }


def parse(data: bytes | str) -> ParseResult:
    text = data.decode("utf-8-sig", errors="replace") if isinstance(data, bytes) else data
    reader = csv.DictReader(io.StringIO(text))
    headers = {h.strip() for h in (reader.fieldnames or []) if h}
    if not REQUIRED <= headers:
        missing = ", ".join(sorted(REQUIRED - headers))
        raise NotRobinhoodCSV(
            f"This doesn't look like a Robinhood activity CSV (missing: {missing})."
        )

    rows = []
    for raw in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in raw.items() if k})
    rows.reverse()  # oldest first

    result = ParseResult()
    seen: dict[str, int] = {}
    for seq, row in enumerate(rows):
        code = row.get("Trans Code", "")
        if not code:
            continue  # blank lines and the disclaimer footer
        if code not in STOCK_CODES and code not in OPTION_CODES and code not in OPTION_CLOSE_CODES:
            result.skipped[code] = result.skipped.get(code, 0) + 1
            continue
        line = f"row {len(rows) - seq + 1}"
        day = _date(row.get("Activity Date", ""))
        qty = _quantity(row.get("Quantity", ""))
        if not day or qty is None or qty == 0:
            result.errors.append(f"{line}: couldn't read the date or quantity, skipped")
            continue
        qty = abs(qty)

        # Same row content twice in one file (two identical fills) must stay two fills,
        # but importing the same file again must not duplicate anything.
        base = "|".join(
            row.get(k, "")
            for k in (
                "Activity Date",
                "Instrument",
                "Description",
                "Trans Code",
                "Quantity",
                "Price",
                "Amount",
            )
        )
        seen[base] = seen.get(base, 0) + 1
        source_key = "rh:" + hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()[:32]

        amount = dec(row.get("Amount"), None)
        price = dec(row.get("Price"), ZERO) or ZERO
        if code in STOCK_CODES:
            symbol = row.get("Instrument", "").upper()
            if not symbol:
                result.errors.append(f"{line}: no symbol, skipped")
                continue
            fill = ParsedFill(
                asset_class="stock",
                symbol=symbol,
                side=STOCK_CODES[code],
                quantity=qty,
                price=price,
                fee=ZERO,
                executed_at=day,
                seq=seq,
                source_key=source_key,
            )
        else:
            opt = parse_option(row.get("Description", ""))
            if not opt:
                result.errors.append(f"{line}: couldn't read the option contract, skipped")
                continue
            if code in OPTION_CLOSE_CODES:
                side, price, note = "close", ZERO, OPTION_CLOSE_CODES[code]
            else:
                side, note = OPTION_CODES[code], None
            fill = ParsedFill(
                asset_class="option",
                side=side,
                quantity=qty,
                price=price,
                fee=ZERO,
                executed_at=day,
                seq=seq,
                source_key=source_key,
                multiplier=Decimal("100"),
                note=note,
                **opt,
            )
        # Robinhood's Amount already has fees taken out. Gross minus Amount = fee.
        if amount is not None and fill.side in ("buy", "sell"):
            gross = fill.quantity * fill.price * fill.multiplier
            fee = (-amount - gross) if fill.side == "buy" else (gross - amount)
            fill.fee = max(fee, ZERO).quantize(Decimal("0.01"))
        result.fills.append(fill)
    return result
