#!/usr/bin/env python3
"""Run a strategy spec through manifoldbt and emit what ``backtest-expert`` scores.

    python3 run_backtest.py --spec strategy.json --data bars.csv --symbol BTCUSDT

Reads OHLCV bars, runs the spec, pairs the fill log into round trips, and prints
the eight inputs the quality framework asks for plus the ready-to-run command
that feeds them to it.

The engine is imported inside ``main`` rather than at module scope, so the
pairing and bridging modules stay testable without an engine installed, which is
how this repository's test job runs.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bridge import build_evaluation_inputs, format_evaluate_command  # noqa: E402
from round_trips import pair_round_trips, summarize_round_trips  # noqa: E402
from spec import count_parameters, describe_warnings, validate_spec  # noqa: E402

REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def load_bars(path: str):
    """Read OHLCV bars from CSV or Parquet, and refuse anything ambiguous."""
    import pandas as pd

    p = Path(path)
    if not p.exists():
        raise SystemExit(f"data file not found: {path}")

    df = pd.read_parquet(p) if p.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(p)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(
            f"data is missing required column(s): {', '.join(missing)}. "
            f"Found: {', '.join(map(str, df.columns))}"
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # Sorting is not a courtesy: the pairing walks the fill log in order, and an
    # out-of-order bar would produce round trips that close before they open.
    df = df.sort_values("timestamp").reset_index(drop=True)
    if df["timestamp"].duplicated().any():
        raise SystemExit(
            "duplicate timestamps in the data; deduplicate before backtesting, "
            "otherwise one bar is simulated twice"
        )
    return df


def build_strategy(cfg: dict[str, Any], bt, expr_mod, ind_mod):
    """Turn a validated spec into an engine strategy."""
    col, lit, when = expr_mod.col, expr_mod.lit, expr_mod.when
    builders = {"sma": ind_mod.sma, "ema": ind_mod.ema, "rsi": ind_mod.rsi}
    columns = {
        "close": ind_mod.close,
        "open": ind_mod.open,
        "high": ind_mod.high,
        "low": ind_mod.low,
    }

    strategy = bt.Strategy.create(cfg["name"])
    for name, body in cfg["indicators"].items():
        source = columns[body["source"]]
        strategy = strategy.signal(name, builders[body["type"]](source, body["period"]))

    def operand(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return lit(float(v))
        return col(v) if v in cfg["indicators"] else col(v)

    left, right = operand(cfg["entry"]["left"]), operand(cfg["entry"]["right"])
    comparators = {
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
    }
    condition = comparators[cfg["entry"]["op"]](left, right)
    strategy = strategy.size(when(condition, lit(cfg["size"]), lit(0.0)))

    if cfg["stop_loss_pct"] is not None:
        strategy = strategy.stop_loss(pct=cfg["stop_loss_pct"])
    if cfg["take_profit_pct"] is not None:
        strategy = strategy.take_profit(pct=cfg["take_profit_pct"])
    return strategy


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", required=True, help="Strategy spec, JSON")
    ap.add_argument("--data", required=True, help="OHLCV bars, CSV or Parquet")
    ap.add_argument("--symbol", default="ASSET", help="Symbol label for the store")
    ap.add_argument("--interval", default="1m", help="Bar interval (default 1m)")
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--json-out", help="Write the full result to this path")
    args = ap.parse_args()

    raw_spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    cfg = validate_spec(raw_spec)
    num_parameters = count_parameters(raw_spec)

    try:
        import manifoldbt as bt
        from manifoldbt import expr as expr_mod
        from manifoldbt import indicators as ind_mod
        from manifoldbt.helpers import Interval, Slippage
    except ImportError:
        raise SystemExit("manifoldbt is not installed. Install it with: pip install manifoldbt")

    df = load_bars(args.data)
    tmp = tempfile.mkdtemp(prefix="mbt-skill-")
    store = bt.import_dataframe(
        df,
        symbol=args.symbol,
        symbol_id=1,
        interval=args.interval,
        data_root=tmp,
        metadata_db=str(Path(tmp) / "meta.sqlite"),
    )

    start = int(df["timestamp"].iloc[0].value)
    end = int(df["timestamp"].iloc[-1].value)
    units = {"1m": Interval.minutes(1), "1h": Interval.hours(1), "1d": Interval.days(1)}
    if args.interval not in units:
        raise SystemExit(f"unsupported interval '{args.interval}'; use one of {list(units)}")

    config = bt.BacktestConfig(
        universe=[1],
        time_range_start=start,
        # The engine's range end is exclusive, so the last bar needs one extra
        # unit or it is silently dropped from the simulation.
        time_range_end=end + 86_400_000_000_000,
        bar_interval=units[args.interval],
        initial_capital=args.capital,
        execution=bt.ExecutionConfig(
            signal_delay=cfg["signal_delay"],
            execution_price="AtClose",
            max_position_pct=1.0,
            allow_short=False,
            position_sizing_mode="FractionOfEquity",
        ),
        # One rate on both sides of the book. A crossover strategy takes
        # liquidity in and out, so charging the taker rate throughout is the
        # honest default; splitting maker and taker would need a fill model the
        # spec does not carry.
        fees=(
            bt.FeeConfig.zero()
            if cfg["fees_bps"] == 0
            else bt.FeeConfig(maker_fee_bps=cfg["fees_bps"], taker_fee_bps=cfg["fees_bps"])
        ),
        slippage=(
            Slippage.none() if cfg["slippage_bps"] == 0 else Slippage.fixed_bps(cfg["slippage_bps"])
        ),
        warmup_bars=0,
    )

    strategy = build_strategy(cfg, bt, expr_mod, ind_mod)
    result = bt.run(strategy, config, store)

    fills = result.trades_df().to_dict("records")
    trips = pair_round_trips(fills)
    summary = summarize_round_trips(trips)

    inputs = build_evaluation_inputs(
        result.metrics,
        summary,
        start_ns=start,
        end_ns=end,
        num_parameters=num_parameters,
        slippage_tested=bool(cfg["slippage_bps"] or cfg["fees_bps"]),
    )
    command = format_evaluate_command(inputs)

    print(f"Strategy : {cfg['name']}")
    print(f"Bars     : {len(df):,}   Fills: {len(fills):,}   Round trips: {len(trips):,}")
    print(
        f"Win rate : {inputs['win_rate']}%   "
        f"Avg win: {inputs['avg_win_pct']}%   Avg loss: {inputs['avg_loss_pct']}%"
    )
    print(
        f"Max DD   : {inputs['max_drawdown_pct']}%   "
        f"Years: {inputs['years_tested']}   Parameters: {inputs['num_parameters']}"
    )

    for w in describe_warnings(raw_spec) + inputs["warnings"]:
        print(f"  [warn] {w}")

    print("\nHand off to backtest-expert:\n  " + command)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "spec": cfg,
                    "evaluation_inputs": inputs,
                    "round_trips": len(trips),
                    "command": command,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nWrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
