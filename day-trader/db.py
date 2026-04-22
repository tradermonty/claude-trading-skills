"""SQLite trade history and transaction log."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,            -- buy | sell | short | cover
                qty REAL NOT NULL,
                price REAL NOT NULL,
                order_id TEXT,
                strategy TEXT,
                risk_mode TEXT,
                pnl REAL DEFAULT 0,
                notes TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL,            -- signal | entry | exit | stop | margin_call | error | info
                symbol TEXT,
                message TEXT NOT NULL,
                risk_mode TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS session_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(ts DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC)")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def record_trade(
    symbol: str,
    side: str,
    qty: float,
    price: float,
    order_id: str | None = None,
    strategy: str | None = None,
    risk_mode: str | None = None,
    pnl: float = 0.0,
    notes: str | None = None,
) -> int:
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO trades(ts, symbol, side, qty, price, order_id, strategy, risk_mode, pnl, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.utcnow().isoformat(), symbol, side, qty, price,
             order_id, strategy, risk_mode, pnl, notes),
        )
        return cur.lastrowid or 0


def log_event(kind: str, message: str, symbol: str | None = None, risk_mode: str | None = None) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO events(ts, kind, symbol, message, risk_mode) VALUES (?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), kind, symbol, message, risk_mode),
        )


def get_trades(limit: int = 200) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_events(limit: int = 200) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def set_state(key: str, value: str) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO session_state(key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, value, datetime.utcnow().isoformat()),
        )


def get_state(key: str, default: str | None = None) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT value FROM session_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def trade_stats() -> dict[str, Any]:
    with _conn() as c:
        row = c.execute("""
            SELECT
              COUNT(*) AS total_trades,
              SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS winners,
              SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losers,
              COALESCE(SUM(pnl), 0) AS total_pnl,
              COALESCE(AVG(pnl), 0) AS avg_pnl,
              COALESCE(MAX(pnl), 0) AS best_trade,
              COALESCE(MIN(pnl), 0) AS worst_trade
            FROM trades
            WHERE pnl != 0
        """).fetchone()
        return dict(row) if row else {}
