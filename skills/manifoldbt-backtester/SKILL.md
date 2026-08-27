---
name: manifoldbt-backtester
description: Runs a declarative strategy spec over OHLCV bars with the manifoldbt Rust engine, pairs the fill log into round trips, and emits the eight inputs the backtest-expert skill scores. Use when the user wants to execute a backtest, measure a rule they have described, obtain win rate / average win / average loss / max drawdown from real bars, or feed backtest-expert with measured numbers instead of estimates.
---

# manifoldbt Backtester Skill

## Purpose

Execute what `backtest-expert` teaches. That skill grades a backtest on five
dimensions, and its prerequisites say "metrics are user-provided": it scores
numbers it never produces. This skill produces them. It runs a strategy over
real bars and returns the eight inputs its evaluator asks for.

The two chain in one direction: spec, run, evaluate.

## When to Use This Skill

- A user describes a rule and wants it measured
- `backtest-expert` is about to run and the numbers do not exist yet
- A win rate, average winner, average loser or drawdown must come from bars
- A strategy's parameter count must be established for scoring

Leave the verdict to `backtest-expert`. It owns the thresholds and the red
flags, and this skill does not duplicate them.

## Prerequisites

- Python 3.9+
- `pip install manifoldbt` (Apache 2.0 with Commons Clause; the free tier covers
  everything this skill does)
- OHLCV bars as CSV or Parquet with columns `timestamp, open, high, low, close, volume`
- No API key required

## Workflow

### 1. Write the strategy spec

A spec names indicators and one entry condition. Keep it to the smallest rule
that states the hypothesis. Every added knob makes an in-sample fit easier to
reach by accident, and the evaluator penalises the count.

```json
{
  "name": "sma_cross_costed",
  "indicators": {
    "fast": { "type": "sma", "period": 20 },
    "slow": { "type": "sma", "period": 60 }
  },
  "entry": { "left": "fast", "op": ">", "right": "slow" },
  "size": 1.0,
  "stop_loss_pct": 1.5,
  "fees_bps": 5.0,
  "slippage_bps": 2.0
}
```

Field reference: `references/strategy_spec.md`.

Set `fees_bps` and `slippage_bps` to realistic values before you read any
result. A frictionless run scores 0 on execution realism, and over short holding
periods costs decide whether an edge survives.

### 2. Run it

```bash
python3 scripts/run_backtest.py \
  --spec strategy.json \
  --data bars.csv \
  --symbol BTCUSDT \
  --json-out result.json
```

The script validates the spec before it touches the data, so you see a spec
mistake in a second instead of after a long load.

### 3. Read the warnings before the numbers

The run prints warnings that change how you should read the result: a sample
under 30 trades, a span under a year, no friction modelled, or a gap between the
engine's win rate and the paired one. Each one is a reason to fix the setup and
run again.

Three conditions stop the handoff instead of producing a score: no completed
round trips, missing or non-finite maximum drawdown, and scratch trades. The
evaluator has no scratch input, so passing a population that contains them would
make its derived expectancy disagree with the completed trades.

### 4. Hand off to backtest-expert

The run ends with a command you can paste. Run it, or invoke the
`backtest-expert` skill with the same figures:

```bash
python3 skills/backtest-expert/scripts/evaluate_backtest.py \
  --total-trades 3854 --win-rate 20.24 \
  --avg-win-pct 0.2917 --avg-loss-pct 0.2342 \
  --max-drawdown-pct 99.2893 --years-tested 0 \
  --num-parameters 3 --slippage-tested
```

## Four conversions that fail without an error

Between an engine's output and the evaluator's inputs sit four conversions. Each
one yields a plausible number and scores the strategy wrongly. None of them
raises.

**A fill is one execution, a round trip is two.** The raw trade count runs at
about twice the number of round trips. Feed fills to the sample-size dimension
and you double the apparent sample, which can lift a thin backtest over a
threshold it should not clear.

**Buy and sell alternate only in the simplest case.** That holds for a
single-symbol long-only strategy that never scales a position. Shorting breaks
it, because a sell can open. Scaling breaks it, because one exit answers several
entries. A universe breaks it, because fills interleave. This skill tracks
position per symbol and closes a trip when it crosses back through flat. Entry
and exit quantities and cash values accumulate across that whole lifecycle;
their weighted-average prices are display values, while PnL comes from the cash
flows themselves.

**Costs decide small trades.** At 7 bps a side, a trade that gains 0.1% on price
loses money. Expectancy comes from the win rate and the average winner together,
so a gross win rate beside net averages misstates the edge. Percentages here are
net of fees, and `gross_return_pct` sits alongside for inspection.

**The engine signs drawdown negative.** The evaluator wants a positive
magnitude. Pass the raw value and a 38% fall scores as a flawless run.

## Scope

Supported: `sma`, `ema`, `rsi` over any OHLC column; one entry condition using
`>`, `<`, `>=`, `<=` against another indicator, a price column or a number;
optional stop-loss and take-profit; fees and slippage in basis points;
long-only.

Refused: multi-condition entries, shorting, multi-asset universes, and
indicators outside the three above. The engine does all of these. This skill
covers the shapes a one-sentence hypothesis produces, and rejects the rest
instead of half-handling it.

## Reference Files

- `references/strategy_spec.md` covers every spec field, its default, and what
  validation refuses
- `references/metric_bridge.md` covers the eight inputs, how each is derived,
  and the trap in each conversion

## Scripts

- `scripts/run_backtest.py` runs a spec against bars
- `scripts/spec.py` validates a spec and counts its parameters
- `scripts/round_trips.py` pairs fills into round trips with net returns
- `scripts/bridge.py` assembles the evaluator's eight inputs

`spec.py`, `round_trips.py` and `bridge.py` carry no dependencies and import
without the engine, so you can test the logic without running a backtest.
