---
layout: default
title: "Manifoldbt Backtester"
grand_parent: English
parent: Skill Guides
nav_order: 41
lang_peer: /ja/skills/manifoldbt-backtester/
permalink: /en/skills/manifoldbt-backtester/
generated: true
---

# Manifoldbt Backtester
{: .no_toc }

Runs a declarative strategy spec over OHLCV bars with the manifoldbt Rust engine, pairs the fill log into round trips, and emits the eight inputs the backtest-expert skill scores. Use when the user wants to execute a backtest, measure a rule they have described, obtain win rate / average win / average loss / max drawdown from real bars, or feed backtest-expert with measured numbers instead of estimates.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/manifoldbt-backtester.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/manifoldbt-backtester){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# manifoldbt Backtester Skill

---

## 2. When to Use

- A user describes a rule and wants it measured
- `backtest-expert` is about to run and the numbers do not exist yet
- A win rate, average winner, average loser or drawdown must come from bars
- A strategy's parameter count must be established for scoring

Leave the verdict to `backtest-expert`. It owns the thresholds and the red
flags, and this skill does not duplicate them.

---

## 3. Prerequisites

- Python 3.9+
- `pip install manifoldbt` (Apache 2.0 with Commons Clause; the free tier covers
  everything this skill does)
- OHLCV bars as CSV or Parquet with columns `timestamp, open, high, low, close, volume`
- No API key required

---

## 4. Quick Start

```bash
Field reference: `references/strategy_spec.md`.

Set `fees_bps` and `slippage_bps` to realistic values before you read any
result. A frictionless run scores 0 on execution realism, and over short holding
periods costs decide whether an edge survives.

### 2. Run it
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/manifoldbt-backtester/references/metric_bridge.md`
- `skills/manifoldbt-backtester/references/strategy_spec.md`

**Scripts:**

- `skills/manifoldbt-backtester/scripts/bridge.py`
- `skills/manifoldbt-backtester/scripts/round_trips.py`
- `skills/manifoldbt-backtester/scripts/run_backtest.py`
- `skills/manifoldbt-backtester/scripts/spec.py`
