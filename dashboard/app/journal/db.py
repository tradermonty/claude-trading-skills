"""SQLite storage for the trade journal.

One file, journal.db, in JOURNAL_DIR. Screenshots sit next to it in
JOURNAL_DIR/screenshots. Backing up the journal = copying that folder, which the
nightly Proxmox backup of the CT already does.

Three ideas, three tables:
- instrument: WHAT you traded (a stock, one option contract, a coin)
- trade:      WHY you traded it (setup, reason, stop, grade, lesson)
- fill:       WHAT HAPPENED at the broker (side, quantity, price, fee, date)
P&L is always worked out from fills (see pnl.py), never typed in.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import pnl

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS instrument (
    id             INTEGER PRIMARY KEY,
    asset_class    TEXT NOT NULL CHECK (asset_class IN ('stock', 'option', 'crypto')),
    symbol         TEXT NOT NULL,          -- AAPL, "AAPL 2026-12-19 250 C", BTC-USD
    underlying     TEXT,                   -- options: AAPL
    expiry         TEXT,                   -- options: YYYY-MM-DD
    strike         TEXT,                   -- options: decimal as text
    "right"        TEXT CHECK ("right" IN ('call', 'put') OR "right" IS NULL),
    multiplier     TEXT NOT NULL DEFAULT '1',   -- 100 for a standard option
    quote_currency TEXT NOT NULL DEFAULT 'USD',
    UNIQUE (asset_class, symbol)
);

CREATE TABLE IF NOT EXISTS trade (
    id             INTEGER PRIMARY KEY,
    symbol         TEXT NOT NULL,          -- what the list shows: ticker or underlying
    setup          TEXT,
    reason         TEXT,
    planned_stop   TEXT,
    planned_target TEXT,
    grade          TEXT CHECK (grade IN ('A', 'B', 'C', 'D', 'F') OR grade IS NULL),
    lesson         TEXT,
    notes          TEXT,
    account        TEXT,                   -- a nickname like "Robinhood"; never an account number
    thesis_id      TEXT,                   -- optional link to a trader-memory-core thesis
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fill (
    id            INTEGER PRIMARY KEY,
    trade_id      INTEGER REFERENCES trade(id) ON DELETE CASCADE,
    instrument_id INTEGER NOT NULL REFERENCES instrument(id),
    side          TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity      TEXT NOT NULL,          -- exact decimal as text, always positive
    price         TEXT NOT NULL,
    fee           TEXT NOT NULL DEFAULT '0',
    fee_currency  TEXT NOT NULL DEFAULT 'USD',
    executed_at   TEXT NOT NULL,          -- UTC "YYYY-MM-DDTHH:MM:SSZ", or "YYYY-MM-DD" when only the date is known
    seq           INTEGER NOT NULL DEFAULT 0,  -- tie-breaker for fills on the same date
    source        TEXT NOT NULL DEFAULT 'manual',
    source_key    TEXT UNIQUE,            -- stops the same CSV row being imported twice
    note          TEXT
);
CREATE INDEX IF NOT EXISTS fill_trade ON fill(trade_id);

CREATE TABLE IF NOT EXISTS tag (
    id   INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('mistake')),
    name TEXT NOT NULL,
    UNIQUE (kind, name)
);

CREATE TABLE IF NOT EXISTS trade_tag (
    trade_id INTEGER NOT NULL REFERENCES trade(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (trade_id, tag_id)
);

CREATE TABLE IF NOT EXISTS attachment (
    id            INTEGER PRIMARY KEY,
    trade_id      INTEGER NOT NULL REFERENCES trade(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL UNIQUE,   -- random name on disk
    original_name TEXT,
    created_at    TEXT NOT NULL
);
"""

DEFAULT_MISTAKES = [
    "Chased the entry",
    "No stop / moved the stop",
    "Position too big",
    "Sold too early",
    "Held a loser too long",
    "Traded against the market",
    "FOMO (fear of missing out)",
    "Revenge trade",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init(conn: sqlite3.Connection) -> None:
    # WAL lets the page read while another request writes (gunicorn runs 2 workers).
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO tag(kind, name) VALUES ('mistake', ?)",
            [(m,) for m in DEFAULT_MISTAKES],
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


# ---------------------------------------------------------------- instruments


def instrument_id(
    conn: sqlite3.Connection,
    asset_class: str,
    symbol: str,
    underlying: str | None = None,
    expiry: str | None = None,
    strike: Decimal | None = None,
    right: str | None = None,
    multiplier: Decimal | None = None,
) -> int:
    if multiplier is None:
        multiplier = Decimal("100") if asset_class == "option" else Decimal("1")
    row = conn.execute(
        "SELECT id FROM instrument WHERE asset_class = ? AND symbol = ?", (asset_class, symbol)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        'INSERT INTO instrument(asset_class, symbol, underlying, expiry, strike, "right", multiplier)'
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            asset_class,
            symbol,
            underlying,
            expiry,
            None if strike is None else f"{strike:f}",
            right,
            f"{multiplier:f}",
        ),
    )
    return cur.lastrowid


def option_symbol(underlying: str, expiry: str, strike: Decimal, right: str) -> str:
    return f"{underlying.upper()} {expiry} {strike.normalize():f} {'C' if right == 'call' else 'P'}"


# ---------------------------------------------------------------- trades


def create_trade(conn: sqlite3.Connection, symbol: str, **fields: Any) -> int:
    stamp = now_utc()
    allowed = {k: v for k, v in fields.items() if k in TRADE_FIELDS}
    cols = ["symbol", "created_at", "updated_at", *allowed]
    vals = [symbol.upper(), stamp, stamp, *allowed.values()]
    cur = conn.execute(
        f"INSERT INTO trade({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals
    )
    return cur.lastrowid


TRADE_FIELDS = (
    "setup",
    "reason",
    "planned_stop",
    "planned_target",
    "grade",
    "lesson",
    "notes",
    "account",
    "thesis_id",
)


def update_trade(conn: sqlite3.Connection, trade_id: int, fields: dict[str, Any]) -> None:
    allowed = {k: (v if v not in ("",) else None) for k, v in fields.items() if k in TRADE_FIELDS}
    if not allowed:
        return
    sets = ", ".join(f"{k} = ?" for k in allowed)
    conn.execute(
        f"UPDATE trade SET {sets}, updated_at = ? WHERE id = ?",
        [*allowed.values(), now_utc(), trade_id],
    )


def add_fill(
    conn: sqlite3.Connection,
    trade_id: int | None,
    instrument: int,
    side: str,
    quantity: Decimal,
    price: Decimal,
    executed_at: str,
    fee: Decimal = pnl.ZERO,
    fee_currency: str = "USD",
    seq: int = 0,
    source: str = "manual",
    source_key: str | None = None,
    note: str | None = None,
) -> int | None:
    cur = conn.execute(
        "INSERT OR IGNORE INTO fill(trade_id, instrument_id, side, quantity, price, fee,"
        " fee_currency, executed_at, seq, source, source_key, note)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            trade_id,
            instrument,
            side,
            f"{quantity:f}",
            f"{price:f}",
            f"{fee:f}",
            fee_currency,
            executed_at,
            seq,
            source,
            source_key,
            note,
        ),
    )
    return cur.lastrowid if cur.rowcount else None


FILL_SELECT = """
SELECT f.*, i.asset_class, i.symbol, i.underlying, i.expiry, i.strike, i."right",
       i.multiplier, i.quote_currency
FROM fill f JOIN instrument i ON i.id = f.instrument_id
"""


def fills_for(conn: sqlite3.Connection, trade_ids: Iterable[int]) -> dict[int, list[sqlite3.Row]]:
    ids = list(trade_ids)
    out: dict[int, list[sqlite3.Row]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = conn.execute(
        FILL_SELECT
        + f" WHERE f.trade_id IN ({', '.join('?' * len(ids))}) ORDER BY f.executed_at, f.seq, f.id",
        ids,
    ).fetchall()
    for r in rows:
        out[r["trade_id"]].append(r)
    return out


def to_pnl_fill(row: sqlite3.Row) -> pnl.Fill:
    return pnl.Fill(
        side=row["side"],
        quantity=pnl.dec(row["quantity"]),
        price=pnl.dec(row["price"]),
        fee=pnl.dec(row["fee"]),
        multiplier=pnl.dec(row["multiplier"], pnl.Decimal("1")),
        instrument=row["instrument_id"],
        executed_at=row["executed_at"],
        fee_in_quote=row["fee_currency"] == row["quote_currency"],
    )


def mistakes_for(conn: sqlite3.Connection, trade_ids: Iterable[int]) -> dict[int, list[str]]:
    ids = list(trade_ids)
    out: dict[int, list[str]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = conn.execute(
        "SELECT tt.trade_id, t.name FROM trade_tag tt JOIN tag t ON t.id = tt.tag_id"
        f" WHERE tt.trade_id IN ({', '.join('?' * len(ids))}) ORDER BY t.name",
        ids,
    ).fetchall()
    for r in rows:
        out[r["trade_id"]].append(r["name"])
    return out


def load_trades(conn: sqlite3.Connection, trade_id: int | None = None) -> list[dict[str, Any]]:
    """Trades with their fills and computed P&L, newest activity first."""
    if trade_id is None:
        rows = conn.execute("SELECT * FROM trade").fetchall()
    else:
        rows = conn.execute("SELECT * FROM trade WHERE id = ?", (trade_id,)).fetchall()
    ids = [r["id"] for r in rows]
    fills = fills_for(conn, ids)
    mistakes = mistakes_for(conn, ids)
    trades = []
    for r in rows:
        t = dict(r)
        t["fills"] = fills[r["id"]]
        res = pnl.compute(to_pnl_fill(f) for f in t["fills"])
        t["result"] = res
        t["status"] = res.status
        t["net"] = res.net
        t["fees"] = res.fees
        t["direction"] = "short" if res.first_side == "sell" else "long"
        t["opened_at"] = res.opened_at
        t["closed_at"] = res.closed_at
        t["mistakes"] = mistakes[r["id"]]
        t["asset_classes"] = sorted({f["asset_class"] for f in t["fills"]})
        t["r"] = _r_for(t)
        trades.append(t)
    trades.sort(key=lambda t: (t["closed_at"] or "9999", t["opened_at"] or ""), reverse=True)
    return trades


def _r_for(t: dict[str, Any]) -> Decimal | None:
    """R-multiple for single-instrument trades that have a planned stop."""
    fills = t["fills"]
    if not fills or len({f["instrument_id"] for f in fills}) != 1 or t["status"] != "closed":
        return None
    first = fills[0]
    opening = [f for f in fills if f["side"] == first["side"]]
    qty = sum((pnl.dec(f["quantity"]) for f in opening), pnl.ZERO)
    if qty == 0:
        return None
    entry = sum((pnl.dec(f["quantity"]) * pnl.dec(f["price"]) for f in opening), pnl.ZERO) / qty
    return pnl.r_multiple(
        t["net"], entry, pnl.dec(t["planned_stop"], None), qty, pnl.dec(first["multiplier"])
    )


def set_mistakes(conn: sqlite3.Connection, trade_id: int, names: Iterable[str]) -> None:
    conn.execute("DELETE FROM trade_tag WHERE trade_id = ?", (trade_id,))
    for name in {n.strip() for n in names if n and n.strip()}:
        conn.execute("INSERT OR IGNORE INTO tag(kind, name) VALUES ('mistake', ?)", (name,))
        tag = conn.execute(
            "SELECT id FROM tag WHERE kind = 'mistake' AND name = ?", (name,)
        ).fetchone()
        conn.execute("INSERT OR IGNORE INTO trade_tag VALUES (?, ?)", (trade_id, tag["id"]))


def all_mistakes(conn: sqlite3.Connection) -> list[str]:
    return [
        r["name"] for r in conn.execute("SELECT name FROM tag WHERE kind = 'mistake' ORDER BY name")
    ]


def all_setups(conn: sqlite3.Connection) -> list[str]:
    return [
        r["setup"]
        for r in conn.execute(
            "SELECT DISTINCT setup FROM trade WHERE setup IS NOT NULL AND setup != '' ORDER BY setup"
        )
    ]


def merge_trades(conn: sqlite3.Connection, keep_id: int, other_id: int) -> None:
    """Move the other trade's fills, screenshots and mistakes into keep_id (for spreads)."""
    conn.execute("UPDATE fill SET trade_id = ? WHERE trade_id = ?", (keep_id, other_id))
    conn.execute("UPDATE attachment SET trade_id = ? WHERE trade_id = ?", (keep_id, other_id))
    conn.execute(
        "INSERT OR IGNORE INTO trade_tag SELECT ?, tag_id FROM trade_tag WHERE trade_id = ?",
        (keep_id, other_id),
    )
    conn.execute("DELETE FROM trade WHERE id = ?", (other_id,))
    conn.execute("UPDATE trade SET updated_at = ? WHERE id = ?", (now_utc(), keep_id))


# ---------------------------------------------------------------- import


def _open_qty(conn: sqlite3.Connection, trade_id: int, instrument: int) -> Decimal:
    total = pnl.ZERO
    for r in conn.execute(
        "SELECT side, quantity FROM fill WHERE trade_id = ? AND instrument_id = ?",
        (trade_id, instrument),
    ):
        q = pnl.dec(r["quantity"])
        total += q if r["side"] == "buy" else -q
    return total


def _open_trade_for(conn: sqlite3.Connection, instrument: int) -> tuple[int, Decimal] | None:
    """The newest trade still holding this instrument, and its signed open quantity."""
    rows = conn.execute(
        "SELECT DISTINCT trade_id FROM fill WHERE instrument_id = ? AND trade_id IS NOT NULL"
        " ORDER BY trade_id DESC",
        (instrument,),
    ).fetchall()
    for r in rows:
        qty = _open_qty(conn, r["trade_id"], instrument)
        if qty != 0:
            return r["trade_id"], qty
    return None


def import_fills(
    conn: sqlite3.Connection, parsed: list, account: str = "Robinhood"
) -> dict[str, Any]:
    """Store parsed CSV fills and group them into trades.

    A trade starts when a position goes from flat to open and ends when it's flat
    again. Each option contract is its own trade at first; use Merge on the trade
    page to combine the legs of a spread.
    """
    added = duplicates = 0
    new_trades: set[int] = set()
    notes: list[str] = []
    seq_base = (conn.execute("SELECT COALESCE(MAX(seq), 0) FROM fill").fetchone()[0] or 0) + 1
    for p in parsed:
        if conn.execute("SELECT 1 FROM fill WHERE source_key = ?", (p.source_key,)).fetchone():
            duplicates += 1
            continue
        inst = instrument_id(
            conn,
            p.asset_class,
            p.symbol,
            underlying=p.underlying,
            expiry=p.expiry,
            strike=p.strike,
            right=p.right,
            multiplier=p.multiplier,
        )
        current = _open_trade_for(conn, inst)
        side = p.side
        qty = p.quantity
        if side == "close":
            if current is None:
                notes.append(
                    f"{p.symbol}: {p.note or 'closed'} on {p.executed_at} but no open position, skipped"
                )
                continue
            side = "sell" if current[1] > 0 else "buy"
            qty = min(qty, abs(current[1]))
        if current is None:
            trade_id = create_trade(conn, p.underlying or p.symbol, account=account)
            new_trades.add(trade_id)
        else:
            trade_id, open_qty = current
            signed = qty if side == "buy" else -qty
            # A sell bigger than the position flips it: close this trade, open a new one.
            if (open_qty > 0) != (signed > 0) and abs(signed) > abs(open_qty):
                add_fill(
                    conn,
                    trade_id,
                    inst,
                    side,
                    abs(open_qty),
                    p.price,
                    p.executed_at,
                    fee=p.fee,
                    seq=seq_base + p.seq,
                    source="robinhood",
                    source_key=p.source_key + ":a",
                    note=p.note,
                )
                qty = abs(signed) - abs(open_qty)
                trade_id = create_trade(conn, p.underlying or p.symbol, account=account)
                new_trades.add(trade_id)
                add_fill(
                    conn,
                    trade_id,
                    inst,
                    side,
                    qty,
                    p.price,
                    p.executed_at,
                    seq=seq_base + p.seq,
                    source="robinhood",
                    source_key=p.source_key,
                    note=p.note,
                )
                added += 1
                continue
        add_fill(
            conn,
            trade_id,
            inst,
            side,
            qty,
            p.price,
            p.executed_at,
            fee=p.fee,
            seq=seq_base + p.seq,
            source="robinhood",
            source_key=p.source_key,
            note=p.note,
        )
        added += 1
    conn.commit()
    return {"added": added, "duplicates": duplicates, "new_trades": len(new_trades), "notes": notes}
