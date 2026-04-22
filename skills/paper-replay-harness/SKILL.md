---
name: paper-replay-harness
description: Deterministic historical replay of the trade loop. Feeds pre-generated candidate files + local OHLCV bars through the same ranking, sizing, and bracket-fill logic used in production, without touching Alpaca. Use to validate a screener change, sanity-check a sizing tweak, or produce a walk-forward P&L curve before enabling execute mode. Invoke with "replay last 30 days", "backtest this screener", "dry-run the loop against april bars".
---

# Paper Replay Harness

Offline deterministic replay of the automated trading loop. Shares the same
ranking + sizing code paths as production (via `rank_signals` and the sizing
helpers in `run_loop`), but runs against local OHLCV bars and a synthetic
broker instead of Alpaca.

## When to Use

- Before turning on `execute` mode — replay the last 30 sessions and confirm
  the loop is well-behaved (no runaway entries, reasonable drawdown, stops
  actually fire).
- After changing screener weights, composite math, or sector caps.
- To produce a walk-forward P&L curve for strategy-review reports.

## Inputs

- **Bars directory** (`--bars-dir`): one CSV per ticker
  (`<TICKER>.csv`) with columns: `date,open,high,low,close,volume`.
  Date must be ISO `YYYY-MM-DD`. Missing days are skipped; the harness
  never fabricates bars.
- **Candidates directory** (`--candidates-dir`): one JSON per session day
  (`candidates_<YYYY-MM-DD>.json`) containing a list of Candidate dicts
  (same schema as the trade-loop orchestrator).
- **Config YAML** (`--config`): reuses `config/trading_params.yaml`.
- **Date range** (`--from`, `--to`): trading-day iteration span.

## Determinism

The harness is pure: same inputs produce byte-identical outputs. No
subprocess calls, no network, no clocks. Entry fills happen at the *next*
bar's open; stops fire at the session's low; targets at the session's high.
When both stop and target print in the same session, the stop wins
(conservative).

## Workflow

```bash
python3 skills/paper-replay-harness/scripts/replay.py \
  --bars-dir data/bars/ \
  --candidates-dir data/historical_candidates/ \
  --from 2026-03-01 --to 2026-03-31 \
  --output-dir reports/replay/
```

### Steps

1. Enumerate trading days in [from, to] (exclude weekends).
2. For each day:
   - Load any `candidates_<date>.json` file.
   - Filter out tickers we already hold.
   - Rank + dedupe via `rank_signals.rank_and_dedupe` (with a fixed
     GOLDILOCKS regime, risk_on=70 default, or the values passed via
     `--regime` / `--risk-on`).
   - Size each candidate (`run_loop.size_position`).
   - Sector cap / position count enforcement (per config).
   - Submit to the `SimBroker`: bracket orders queued for next day's fill.
3. After the loop iteration, advance bars:
   - Fill outstanding BUY orders at next day's open.
   - For each open position, check whether the bar touched stop or target;
     close at stop/target price if so.
   - Mark-to-market the remaining positions at close.
4. Record per-day portfolio snapshot (equity, positions, realized day P&L).
5. At the end: aggregate, write `replay_<from>_<to>.md` and `.json`.

## Output

```json
{
  "from": "2026-03-01", "to": "2026-03-31",
  "starting_equity": 100000.00,
  "ending_equity": 103250.00,
  "total_return_pct": 3.25,
  "max_drawdown_pct": 1.8,
  "trades_count": 42,
  "win_rate": 0.55,
  "avg_r_multiple": 0.7,
  "by_strategy": { "vcp-screener": {"trades": 18, "win_rate": 0.61} },
  "equity_curve": [
    {"date": "2026-03-01", "equity": 100000.0, "positions": 0},
    ...
  ],
  "closed_trades": [
    {"ticker": "AAPL", "entry_date": "...", "exit_date": "...",
     "entry_price": 185, "exit_price": 198, "r_multiple": 1.2,
     "screener": "vcp-screener"}
  ]
}
```

## Combining with Other Skills

- **trade-loop-orchestrator**: shares `rank_signals` + sizing helpers.
- **edge-strategy-reviewer**: feed replay reports into review pipeline.
- **backtest-expert**: complements by assessing strategy beyond the loop.
