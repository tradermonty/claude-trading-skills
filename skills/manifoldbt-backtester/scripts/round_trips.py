#!/usr/bin/env python3
"""Pair a fill log into round trips carrying percent returns.

A backtest engine reports *fills*: one row per execution. The quality
framework in ``skills/backtest-expert`` asks for *round trips*: average winner
and average loser expressed in percent. Those are not the same number, and the
gap between them is where most hand-rolled evaluations go wrong.

Zipping consecutive rows and assuming buy and sell alternate holds for one
case: a single-symbol long-only strategy that never scales a position. Three
things break it, and none of them raises. Each produces percentages that look
plausible and are wrong:

* shorting is enabled, so a sell can *open* rather than close;
* the position is scaled in or out, so one exit answers several entries;
* the universe has more than one symbol, so fills interleave.

So this module tracks position per symbol instead of pattern-matching rows. A
fill in the direction of the running position opens or increases it, while a
fill against it reduces or closes it. Entry and exit cash flows accumulate for
the whole flat-to-flat lifecycle, so scaling out and then back in cannot mix the
remaining position's average entry with earlier exits. A round trip is emitted
when the position crosses back through flat, and a fill that flips the sign in
one go is split into the part that closes and the part that opens.

Deliberately dependency-free: plain dicts in, plain dicts out. It runs under the
repository's test job, which installs no dataframe library, and it lets the
pairing be tested without a backtest engine present.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

__all__ = ["pair_round_trips", "summarize_round_trips", "SIDE_BUY", "SIDE_SELL"]

# Engine convention in the fill log: 1 buys, 2 sells. Which of the two *opens* a
# position depends on the position at that moment, never on the code alone,
# which is the whole reason this module tracks state.
SIDE_BUY = 1
SIDE_SELL = 2

# Positions below this magnitude count as flat. Sizing in fraction-of-equity
# terms leaves float dust behind on a close, and dust must not read as an open
# position or every subsequent round trip is attributed to the wrong entry.
_FLAT_EPS = 1e-9


def _signed_quantity(fill: dict[str, Any]) -> float:
    """Fill quantity, positive for a buy and negative for a sell."""
    qty = abs(float(fill.get("quantity", 0.0)))
    side = int(fill.get("side", SIDE_BUY))
    return qty if side == SIDE_BUY else -qty


def _close_trip(symbol: Any, p: dict[str, Any], ts: Any) -> dict[str, Any]:
    """Emit one completed round trip from a position that has returned to flat.

    Fees are charged against the notional put at risk, so the percentage answers
    "what did this position return net of costs", which is the only figure a
    trader can spend.
    """
    entry_avg = p["entry_value"] / p["entry_qty"] if p["entry_qty"] else 0.0
    exit_avg = p["exit_value"] / p["exit_qty"] if p["exit_qty"] else 0.0
    side_label = "long" if p["entry_sign"] > 0 else "short"
    gross_pnl = (
        p["exit_value"] - p["entry_value"]
        if side_label == "long"
        else p["entry_value"] - p["exit_value"]
    )
    net_pnl = gross_pnl - p["fees"]
    gross_return = gross_pnl / p["entry_value"] if p["entry_value"] else 0.0
    net_return = net_pnl / p["entry_value"] if p["entry_value"] else 0.0

    return {
        "symbol_id": symbol,
        "direction": side_label,
        "quantity": p["entry_qty"],
        "entry_qty": p["entry_qty"],
        "exit_qty": p["exit_qty"],
        "entry_value": p["entry_value"],
        "exit_value": p["exit_value"],
        "entry_price": entry_avg,
        "exit_price": exit_avg,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "gross_return_pct": gross_return * 100.0,
        "return_pct": net_return * 100.0,
        "fees": p["fees"],
        "total_fees": p["fees"],
        "entry_timestamp": p["opened_at"],
        "exit_timestamp": ts,
    }


def pair_round_trips(fills: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn a chronological fill log into a list of round trips.

    Each fill must carry ``side``, ``quantity`` and ``fill_price``. ``symbol_id``,
    ``fees`` and ``execution_timestamp`` are used when present. Fills are assumed
    to be in execution order, which is how every engine in this repository emits
    them; they are not re-sorted, because a timestamp tie would then reorder
    entries and exits arbitrarily.

    Returns one dict per completed round trip:

    ``symbol_id``, ``direction`` (``"long"`` / ``"short"``), cumulative entry
    and exit quantities / values, their display-average prices, gross and net
    PnL / returns, fees, and the entry / exit timestamps.

    ``return_pct`` is **net of fees**, signed by direction, expressed against the
    notional put at risk. Gross would be the easier number to compute and the
    wrong one to report: at 7 bps a side, a trade that gains 0.1% on price is a
    net loser, so a gross win rate counts as winners a population that lost
    money. Since the quality framework derives expectancy from the win rate and
    the average winner together, mixing a gross rate with net averages misstates
    the edge. ``gross_return_pct`` is kept alongside for inspection.

    An open position at the end of the log is dropped. It has no exit, so it has no
    return, and counting it inflates the trade count the quality framework
    scores.
    """
    # Per symbol: running signed quantity, lifecycle entry/exit cash flows,
    # accrued fees, and the timestamp the position opened.
    state: dict[Any, dict[str, Any]] = {}
    closed: list[dict[str, Any]] = []

    for fill in fills:
        symbol = fill.get("symbol_id", 0)
        price = float(fill.get("fill_price", 0.0))
        fee = float(fill.get("fees", 0.0) or 0.0)
        ts = fill.get("execution_timestamp")
        delta = _signed_quantity(fill)
        if delta == 0.0:
            continue

        p = state.setdefault(
            symbol,
            {
                "qty": 0.0,
                "entry_qty": 0.0,
                "entry_value": 0.0,
                "entry_sign": 0.0,
                "fees": 0.0,
                "opened_at": None,
                "exit_qty": 0.0,
                "exit_value": 0.0,
            },
        )

        remaining = delta
        # A fill that flips the sign closes the old position first and opens the
        # new one with what is left. Handling it as one event would book an entry
        # price that never existed.
        if p["qty"] != 0.0 and (p["qty"] > 0) != (remaining > 0):
            closing = min(abs(remaining), abs(p["qty"]))
            p["exit_qty"] += closing
            p["exit_value"] += closing * price
            p["fees"] += fee * (closing / abs(delta))
            p["qty"] += closing if p["qty"] < 0 else -closing
            remaining += closing if remaining < 0 else -closing

            if abs(p["qty"]) <= _FLAT_EPS:
                closed.append(_close_trip(symbol, p, ts))
                p.update(
                    {
                        "qty": 0.0,
                        "entry_qty": 0.0,
                        "entry_value": 0.0,
                        "entry_sign": 0.0,
                        "fees": 0.0,
                        "opened_at": None,
                        "exit_qty": 0.0,
                        "exit_value": 0.0,
                    }
                )

        if remaining != 0.0:
            if abs(p["qty"]) <= _FLAT_EPS:
                p["entry_qty"] = abs(remaining)
                p["entry_value"] = abs(remaining) * price
                p["qty"] = remaining
                p["entry_sign"] = 1.0 if remaining > 0 else -1.0
                p["opened_at"] = ts
                p["fees"] += fee * (abs(remaining) / abs(delta))
            else:
                # Keep the whole lifecycle's entry basis. Re-weighting only the
                # remaining inventory here loses the basis of shares already
                # sold and makes earlier exits incomparable with the entry.
                p["entry_qty"] += abs(remaining)
                p["entry_value"] += price * abs(remaining)
                p["qty"] += remaining
                p["fees"] += fee * (abs(remaining) / abs(delta))

    return closed


def summarize_round_trips(trips: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate round trips into the shape the quality framework scores.

    A zero-return trip counts as neither a win nor a loss: it is a scratch. It
    still belongs in the win-rate denominator because it is a completed trade
    that did not win. The downstream evaluator has no scratch input, so the
    bridge refuses to hand off a population containing scratches rather than
    silently treating them as ordinary losses.
    """
    gagnants = [t["return_pct"] for t in trips if t["return_pct"] > 0]
    perdants = [t["return_pct"] for t in trips if t["return_pct"] < 0]
    decides = len(gagnants) + len(perdants)

    return {
        "total_trades": len(trips),
        "wins": len(gagnants),
        "losses": len(perdants),
        "scratches": len(trips) - decides,
        # A scratch is not a win. Keeping it in the denominator makes the
        # standalone summary honest even though it is not a loss either.
        "win_rate_pct": (100.0 * len(gagnants) / len(trips)) if trips else 0.0,
        "avg_win_pct": (sum(gagnants) / len(gagnants)) if gagnants else 0.0,
        # Positive by convention: the quality framework asks for the magnitude.
        "avg_loss_pct": abs(sum(perdants) / len(perdants)) if perdants else 0.0,
        "total_fees": sum(t["fees"] for t in trips),
    }
