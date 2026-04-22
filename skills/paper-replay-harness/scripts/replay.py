#!/usr/bin/env python3
"""Paper Replay Harness: deterministic historical replay of the trade loop.

Reuses rank_signals + run_loop sizing helpers, but never touches Alpaca.
Fills bracket orders against local OHLCV CSV bars.

Usage:
    python3 replay.py \
      --bars-dir data/bars/ \
      --candidates-dir data/historical_candidates/ \
      --from 2026-03-01 --to 2026-03-31 \
      --output-dir reports/replay/
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("error: pyyaml not installed", file=sys.stderr)
    sys.exit(3)


REPO_ROOT = Path(__file__).resolve().parents[3]

# Reuse orchestrator helpers
sys.path.insert(0, str(REPO_ROOT / "skills" / "trade-loop-orchestrator" / "scripts"))
from rank_signals import rank_and_dedupe  # noqa: E402
from run_loop import (  # noqa: E402
    load_sector_map,
    load_yaml,
    size_position,
    sector_of,
    would_breach_sector_cap,
)

DEFAULT_CONFIG = REPO_ROOT / "config" / "trading_params.yaml"
DEFAULT_WEIGHTS = REPO_ROOT / "config" / "screener_weights.yaml"
DEFAULT_SECTOR_MAP = REPO_ROOT / "config" / "sector_map.yaml"


# ---------- Bar loading ----------

def load_bars(bars_dir: Path, ticker: str) -> dict[dt.date, dict[str, float]]:
    """Load a ticker's CSV into {date: {open, high, low, close, volume}}."""
    path = bars_dir / f"{ticker.upper()}.csv"
    if not path.exists():
        return {}
    bars: dict[dt.date, dict[str, float]] = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                d = dt.date.fromisoformat(row["date"])
                bars[d] = {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0)),
                }
            except (KeyError, ValueError):
                continue
    return bars


def trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    out: list[dt.date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += dt.timedelta(days=1)
    return out


# ---------- Candidates ----------

def load_candidates_for_day(candidates_dir: Path, day: dt.date) -> list[dict[str, Any]]:
    path = candidates_dir / f"candidates_{day.isoformat()}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict) and "candidates" in data:
        return data["candidates"]
    if isinstance(data, list):
        return data
    return []


# ---------- Sim broker ----------

class SimBroker:
    """Deterministic bracket-order fill engine."""

    def __init__(self, starting_cash: float):
        self.cash = starting_cash
        self.positions: dict[str, dict[str, Any]] = {}  # ticker -> {qty, entry, stop, target, screener, entry_date}
        self.pending_buys: list[dict[str, Any]] = []  # filled at next bar open
        self.closed_trades: list[dict[str, Any]] = []
        self.equity_curve: list[dict[str, Any]] = []

    def submit_bracket(self, ticker: str, qty: int, entry_price: float,
                       stop: float, target: float, screener: str) -> None:
        self.pending_buys.append({
            "ticker": ticker, "qty": qty, "intended_entry": entry_price,
            "stop": stop, "target": target, "screener": screener,
        })

    def _open_fill_pending(self, day: dt.date, open_price_of: dict[str, float]) -> None:
        remaining: list[dict[str, Any]] = []
        for o in self.pending_buys:
            tkr = o["ticker"]
            px = open_price_of.get(tkr)
            if px is None:
                # No bar that day — carry order forward one day (simple rule)
                remaining.append(o)
                continue
            notional = px * o["qty"]
            if notional > self.cash:
                # Cash-constrained: skip
                continue
            self.cash -= notional
            self.positions[tkr] = {
                "qty": o["qty"], "entry": px, "stop": o["stop"],
                "target": o["target"], "screener": o["screener"],
                "entry_date": day.isoformat(), "intended_entry": o["intended_entry"],
            }
        self.pending_buys = remaining

    def _check_exits(self, day: dt.date,
                     bars_of: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
        """Close positions whose bar touched stop (first) or target."""
        closed_today: list[dict[str, Any]] = []
        for tkr, pos in list(self.positions.items()):
            bar = bars_of.get(tkr)
            if bar is None:
                continue
            # Conservative: if both stop and target hit, stop wins
            exit_px: float | None = None
            exit_reason: str | None = None
            if bar["low"] <= pos["stop"]:
                exit_px = pos["stop"]
                exit_reason = "stop_hit"
            elif bar["high"] >= pos["target"]:
                exit_px = pos["target"]
                exit_reason = "target_hit"

            if exit_px is not None:
                proceeds = exit_px * pos["qty"]
                self.cash += proceeds
                risk_per_share = abs(pos["entry"] - pos["stop"])
                pnl_per_share = exit_px - pos["entry"]
                pnl_dollars = pnl_per_share * pos["qty"]
                r_mult = (pnl_per_share / risk_per_share) if risk_per_share > 0 else 0
                rec = {
                    "ticker": tkr, "entry_date": pos["entry_date"],
                    "exit_date": day.isoformat(),
                    "entry_price": round(pos["entry"], 4),
                    "exit_price": round(exit_px, 4),
                    "qty": pos["qty"],
                    "pnl_dollars": round(pnl_dollars, 2),
                    "r_multiple": round(r_mult, 3),
                    "exit_reason": exit_reason,
                    "screener": pos["screener"],
                }
                self.closed_trades.append(rec)
                closed_today.append(rec)
                del self.positions[tkr]
        return closed_today

    def mark_to_market(self, close_of: dict[str, float]) -> float:
        mv = 0.0
        for tkr, pos in self.positions.items():
            px = close_of.get(tkr, pos["entry"])
            mv += px * pos["qty"]
        return self.cash + mv

    def snapshot(self, day: dt.date, equity: float) -> None:
        self.equity_curve.append({
            "date": day.isoformat(),
            "equity": round(equity, 2),
            "cash": round(self.cash, 2),
            "positions": len(self.positions),
        })


# ---------- Iteration ----------

def plan_entries(
    candidates: list[dict[str, Any]],
    broker: SimBroker,
    profile: dict[str, Any],
    weights: dict[str, Any],
    sector_map: dict[str, str],
    regime: str,
    risk_on: float,
    exposure_scale: float,
    current_equity: float,
) -> list[dict[str, Any]]:
    """Return list of bracket order dicts to submit on this iteration."""
    # Filter out held tickers
    held = set(broker.positions.keys())
    candidates = [c for c in candidates if c["ticker"] not in held]

    ranked = rank_and_dedupe(candidates, weights, regime=regime,
                             risk_on_score=risk_on)
    max_positions = int(profile["max_positions"])
    allowed_total = int(math.floor(max_positions * exposure_scale))
    budget = max(allowed_total - len(held), 0)

    sector_exposures: dict[str, float] = defaultdict(float)
    for tkr, pos in broker.positions.items():
        s = sector_of(tkr, None, sector_map)
        sector_exposures[s] += pos["qty"] * pos["entry"]

    submits: list[dict[str, Any]] = []
    for cand in ranked:
        if len(submits) >= budget:
            break
        qty, _ = size_position(
            cand["entry_price"], cand["stop_loss"], profile, exposure_scale)
        if qty <= 0:
            continue
        sector = sector_of(cand["ticker"], cand.get("sector"), sector_map)
        notional = qty * cand["entry_price"]
        if would_breach_sector_cap(
            cand["ticker"], sector, notional, sector_exposures,
            current_equity, profile["max_sector_exposure_pct"],
        ):
            continue
        submits.append({
            "ticker": cand["ticker"],
            "qty": qty,
            "intended_entry": cand["entry_price"],
            "stop": cand["stop_loss"],
            "target": cand["target"],
            "screener": cand["primary_screener"],
            "sector": sector,
        })
        sector_exposures[sector] += notional
    return submits


# ---------- Aggregation ----------

def aggregate_stats(broker: SimBroker, starting_equity: float,
                    ending_equity: float) -> dict[str, Any]:
    trades = broker.closed_trades
    if trades:
        wins = [t for t in trades if t["pnl_dollars"] > 0]
        win_rate = round(len(wins) / len(trades), 4)
        avg_r = round(sum(t["r_multiple"] for t in trades) / len(trades), 3)
    else:
        win_rate = None
        avg_r = None

    equity = [row["equity"] for row in broker.equity_curve]
    if equity:
        peak = equity[0]
        max_dd = 0.0
        for v in equity:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
    else:
        max_dd = 0.0

    by_strategy: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"trades": 0, "wins": 0, "pnl_dollars": 0.0, "r_sum": 0.0}
    )
    for t in trades:
        s = t["screener"]
        bucket = by_strategy[s]
        bucket["trades"] += 1
        if t["pnl_dollars"] > 0:
            bucket["wins"] += 1
        bucket["pnl_dollars"] += t["pnl_dollars"]
        bucket["r_sum"] += t["r_multiple"]
    for s, b in by_strategy.items():
        n = b["trades"]
        b["win_rate"] = round(b["wins"] / n, 4) if n else None
        b["avg_r_multiple"] = round(b["r_sum"] / n, 3) if n else None
        b["pnl_dollars"] = round(b["pnl_dollars"], 2)
        del b["r_sum"]

    return {
        "trades_count": len(trades),
        "win_rate": win_rate,
        "avg_r_multiple": avg_r,
        "max_drawdown_pct": round(max_dd, 3),
        "total_return_pct": round(
            (ending_equity - starting_equity) / starting_equity * 100, 3)
        if starting_equity else 0,
        "by_strategy": dict(by_strategy),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Replay — {payload['from']} → {payload['to']}",
        "",
        f"**Starting equity:** ${payload['starting_equity']:,.2f}",
        f"**Ending equity:** ${payload['ending_equity']:,.2f}",
        f"**Total return:** {payload['total_return_pct']:+.2f}%",
        f"**Max drawdown:** {payload['max_drawdown_pct']:.2f}%",
        f"**Trades:** {payload['trades_count']} "
        f"| Win rate: {payload['win_rate'] if payload['win_rate'] is not None else '—'}"
        f" | Avg R: {payload['avg_r_multiple'] if payload['avg_r_multiple'] is not None else '—'}",
        "",
        "## Strategy Breakdown",
        "",
        "| Screener | Trades | Win rate | Avg R | P&L |",
        "|---|---|---|---|---|",
    ]
    for s, b in sorted(payload.get("by_strategy", {}).items()):
        lines.append(f"| {s} | {b['trades']} | {b['win_rate']} | "
                     f"{b['avg_r_multiple']} | ${b['pnl_dollars']:,.2f} |")
    return "\n".join(lines) + "\n"


# ---------- Driver ----------

def run_replay(args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(args.config)
    weights = load_yaml(args.weights) if args.weights.exists() else {"screeners": {}}
    profile = cfg["profiles"][cfg["active_profile"]]
    sector_map = load_sector_map(args.sector_map)

    starting_equity = float(profile["account_size_usd"])
    broker = SimBroker(starting_cash=starting_equity)

    days = trading_days(args.from_date, args.to_date)
    # Pre-load all bars we'll need: walk candidates first for efficiency,
    # but easier: lazy-load per ticker.
    bars_cache: dict[str, dict[dt.date, dict[str, float]]] = {}

    def get_bar(ticker: str, day: dt.date) -> dict[str, float] | None:
        if ticker not in bars_cache:
            bars_cache[ticker] = load_bars(args.bars_dir, ticker)
        return bars_cache[ticker].get(day)

    for idx, day in enumerate(days):
        # 1. Fill any pending orders at THIS day's open
        open_of: dict[str, float] = {}
        for o in broker.pending_buys:
            bar = get_bar(o["ticker"], day)
            if bar is not None:
                open_of[o["ticker"]] = bar["open"]
        broker._open_fill_pending(day, open_of)

        # 2. Check exits using THIS day's high/low
        bars_today: dict[str, dict[str, float]] = {}
        for tkr in list(broker.positions.keys()):
            b = get_bar(tkr, day)
            if b is not None:
                bars_today[tkr] = b
        broker._check_exits(day, bars_today)

        # 3. Mark-to-market at close
        close_of: dict[str, float] = {
            t: get_bar(t, day)["close"]  # type: ignore[index]
            for t in broker.positions
            if get_bar(t, day) is not None
        }
        equity = broker.mark_to_market(close_of)

        # 4. Plan new entries from today's candidates for tomorrow's open
        candidates = load_candidates_for_day(args.candidates_dir, day)
        submits = plan_entries(
            candidates, broker, profile, weights, sector_map,
            regime=args.regime, risk_on=args.risk_on,
            exposure_scale=args.exposure_scale,
            current_equity=equity,
        )
        for s in submits:
            broker.submit_bracket(
                s["ticker"], s["qty"], s["intended_entry"],
                s["stop"], s["target"], s["screener"],
            )

        broker.snapshot(day, equity)

    # Finalize: close remaining positions at last day's close
    ending_equity = broker.equity_curve[-1]["equity"] if broker.equity_curve else starting_equity

    agg = aggregate_stats(broker, starting_equity, ending_equity)
    payload = {
        "from": args.from_date.isoformat(),
        "to": args.to_date.isoformat(),
        "starting_equity": starting_equity,
        "ending_equity": ending_equity,
        "equity_curve": broker.equity_curve,
        "closed_trades": broker.closed_trades,
        "open_positions_at_end": list(broker.positions.keys()),
        **agg,
    }
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bars-dir", type=Path, required=True)
    ap.add_argument("--candidates-dir", type=Path, required=True)
    ap.add_argument("--from", dest="from_date",
                    type=lambda s: dt.date.fromisoformat(s), required=True)
    ap.add_argument("--to", dest="to_date",
                    type=lambda s: dt.date.fromisoformat(s), required=True)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    ap.add_argument("--sector-map", type=Path, default=DEFAULT_SECTOR_MAP)
    ap.add_argument("--regime", default="GOLDILOCKS")
    ap.add_argument("--risk-on", type=float, default=70.0)
    ap.add_argument("--exposure-scale", type=float, default=1.0)
    ap.add_argument("--output-dir", type=Path,
                    default=REPO_ROOT / "reports" / "replay")
    args = ap.parse_args()

    payload = run_replay(args)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{args.from_date}_{args.to_date}"
    (args.output_dir / f"replay_{tag}.json").write_text(
        json.dumps(payload, indent=2, default=str))
    (args.output_dir / f"replay_{tag}.md").write_text(render_markdown(payload))

    print(f"Replay {tag}: trades={payload['trades_count']} "
          f"win_rate={payload['win_rate']} "
          f"total_return={payload['total_return_pct']}%", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
