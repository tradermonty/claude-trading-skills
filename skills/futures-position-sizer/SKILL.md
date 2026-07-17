---
name: futures-position-sizer
description: Calculate contract-based futures position sizes from a direction, entry, and stop-loss, using verified per-symbol contract specs (multiplier, tick size, tick value). Use when the user asks how many futures contracts to trade, wants to size a futures position (ES, NQ, ZB, GC, CL, 6E/E6, VX, BT, ...), or is handing off a contrarian-setup-gate READY_FOR_PLAN direction/invalidation_level for sizing. Pure, offline calculation -- no API keys, no network.
---

# Futures Position Sizer

## Overview

Shapiro pipeline step 4: convert a direction, entry price, and stop-loss into a contract count, given an account risk budget and a verified contract spec (multiplier, tick size, tick value). This is a NEW, separate skill from `position-sizer` -- futures contracts are leveraged, multiplier-based instruments with wildly different dollar-per-point values (a $0.25 move is $12.50 on ES but $5.00 on NQ and $31.25 on ZB); reusing the equity share-count sizer for futures would silently produce wrong position sizes.

Two ways to size a trade:

- **Mode A (explicit)**: supply `--symbol --direction --entry --stop` directly.
- **Mode B (gate handoff)**: supply `--gate-json <contrarian-setup-gate report> --entry`. Direction and stop (the gate's `invalidation_level`) come from the gate's `READY_FOR_PLAN` report -- the sizer never sizes a setup the gate has not confirmed as READY, and never accepts an explicit `--direction`/`--stop` alongside `--gate-json` (the gate is authoritative when provided).

`--entry` is ALWAYS required, in both modes -- neither this skill nor the gate ever derives an entry price; the operator supplies it.

## When to Use

- After `contrarian-setup-gate` reaches `READY_FOR_PLAN` and you need a contract count for the confirmed direction and stop
- User asks "how many ES/NQ/GC/CL/... contracts should I trade?"
- User has a futures trade idea with a known entry and stop and wants risk-based sizing
- User wants to check the verified contract spec (multiplier/tick size/tick value) for a symbol before sizing (`--list-specs`)

## Prerequisites

- Python 3.9+, standard library only -- no API keys, fully offline
- A direction, entry, and stop (mode A), or a `contrarian-setup-gate` JSON report with `setup_status: READY_FOR_PLAN` (mode B)
- For a symbol outside the verified 23-market core table: its multiplier, tick size, and quote currency (all three, together)

## Workflow

### Step 1: Size the Position

**Mode A -- explicit:**

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --symbol ES --direction LONG --entry 5000.25 --stop 4980.00 \
  --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/ --format both
```

**Mode B -- gate handoff:**

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --gate-json reports/contrarian_setup_gate_B6_2026-07-15.json \
  --entry 1.3400 \
  --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/ --format both
```

`--symbol` may be omitted in mode B -- it is taken from the gate report. If both are given, they must match (`gate_symbol_mismatch` otherwise). `--direction`/`--stop` are rejected alongside `--gate-json` (usage error, exit 2) -- pass one mode or the other, never both.

### Step 2: Read the Result

| `sizing_status` | Meaning |
|---|---|
| `SIZED` | `contracts` >= 1; `total_risk_usd`/`risk_pct_of_account` are the actual risk taken |
| `NO_TRADE` | Never a crash -- always carries `no_trade_reason`. See the reason glossary below |

A `NO_TRADE` result from `risk_below_one_contract` still reports the full risk math (risk per contract, risk budget, stop distance) -- the account simply cannot afford one contract at this risk percentage and stop distance; widen the stop, increase risk %, or skip the trade.

### Step 3: Check Warnings

`warnings` (top-level list) never blocks sizing -- it flags audit-worthy conditions: `risk_pct_above_2` (risk above the 2% guideline), `off_tick_grid_entry`/`off_tick_grid_stop` (a non-bond symbol's price is not exactly on the tick grid -- legitimate for a mid-quote, but worth a second look).

### Step 4: Inspect the Verified Contract Spec Table

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py --list-specs
```

Prints the full 23-market core table (multiplier, tick size, tick value, currency, exchange) sourced from official exchange contract-spec pages -- see `references/futures-contract-specs.md` for the per-row source URLs and verification dates.

## Worked Example: Bond Off-Grid Guard (32nds -> Decimal)

Bond/note futures (ZT, ZF, ZN, ZB) quote in fractions of a point (32nds, or 32nds-of-32nds), commonly written with an apostrophe: `110'16` means `110 + 16/32 = 110.50`. Typing `110.16` instead -- reading the digits after the apostrophe as if they were decimal cents -- is a classic, silent, wrong-money-math mistake: `110.16` is not on the ZB tick grid (`0.03125` = 1/32) at all.

```bash
# WRONG -- 110.16 is not on the 1/32 grid; this is almost certainly a
# mistyped "110'16" (which means 110.50). Exits 2, no report written:
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --symbol ZB --direction LONG --entry 110.16 --stop 108.00 \
  --account-size 100000 --risk-pct 1.0

# CORRECT -- decimal points, not the raw 32nds digits:
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --symbol ZB --direction LONG --entry 110.50 --stop 108.00 \
  --account-size 100000 --risk-pct 1.0
```

Every other symbol in the table quotes in plain decimal points -- an off-grid price there (a mid-quote, for instance) is only a soft `off_tick_grid_*` warning, never a rejection.

## Output Contract

Writes `futures_position_size_<SYMBOL>_<as-of>.json` to `--output-dir` when `--format json|both`; `--format text|both` prints a formatted summary to stdout. `--as-of` defaults to today (this is an operator-time sizing tool, not a backtest tool).

```yaml
schema_version: "1.0"
symbol: ES
direction: LONG
sizing_status: SIZED | NO_TRADE
no_trade_reason: null | risk_below_one_contract | gate_not_ready | gate_symbol_mismatch | ...
entry: 5000.25
stop: 4980.00
stop_distance_points: 20.25
stop_distance_ticks: 81
contract_spec: {multiplier: 50, tick_size: 0.25, tick_value: 12.5, currency: USD, source: cme, verified: "2026-07-17"}
risk_per_contract_usd: 1012.50
risk_budget_usd: 2000.00
contracts: 1
total_risk_usd: 1012.50
risk_pct_of_account: 1.01
max_contracts_cap_applied: false
fx_rate_used: 1.0
margin_note: "Exchange margin requirements are broker/time-dependent and NOT computed here; verify initial/maintenance margin with your broker."
gate: {report_path, setup_status, gate_confidence, warnings}   # mode B only
warnings: []
run_context: {symbol, as_of, schema_version, skill}
```

## Guardrails

1. **Never sizes a position without an explicit stop.** `--stop` is required in mode A; mode B refuses to size (`gate_not_ready`) until the gate itself reports `READY_FOR_PLAN` with a valid `invalidation_level`.
2. **Floor, never round up -- exact by construction, no epsilon.** `contracts = floor(risk_budget / risk_per_contract)` is computed with exact rational arithmetic (Python's `Fraction`, not float division), so `contracts * risk_per_contract <= risk_budget` holds by construction -- no epsilon nudge, no float-representation edge case, and no risk of ever exceeding the budget. Also rejected outright if the resulting count is economically implausible (an absurd input like a denormal-scale multiplier override). Zero contracts is a legitimate, fail-closed `NO_TRADE` outcome, not an error.
3. **Two fail-closed classes, matched to who supplied the bad value.** An operator-caused problem (an explicit `--stop` on the wrong side of `--entry`, a stop closer than one tick, a bond price typed off the tick grid) is a usage error: exit 2, no report written. The identical class of problem on a value that came from the untrusted gate-report file (mode B's stop) is instead a fail-closed `NO_TRADE` result: exit 0, a report IS written, naming the reason -- this never crashes on a bad or not-yet-ready gate file, matching every other skill in this pipeline.
4. **Bond-family off-grid prices are a hard rejection, not a warning.** ZT/ZF/ZN/ZB quote in 32nds/64ths notation; a price that doesn't land on the tick grid is almost certainly a notation mistype and would silently produce wrong money math if sized. Every other symbol only warns.
5. **Margin is never computed.** `margin_note` is a static, never-stale reminder -- margin requirements are broker- and time-dependent; this skill does not estimate them.
6. **Currency-aware.** Every core-table symbol is USD-quoted (confirmed by a table-wide unit test), including the CME FX futures whose contract SIZE is denominated in a foreign currency (e.g. B6's GBP 62,500) but which trade and settle in USD. A symbol quoted in a non-USD currency (via `--contract-currency` override) requires an explicit `--fx-rate` -- there is no silent default.
7. **Not investment advice.** This skill performs risk-based arithmetic on operator-supplied or gate-confirmed inputs; it does not recommend a trade, a direction, or an entry.

## Resources

- `scripts/futures_position_sizer.py` -- CLI: argument parsing, hardened gate-json loading (unreadable / parse_error incl. RecursionError / non_finite via an iterative whole-file scan), report generation
- `scripts/futures_sizing.py` -- Pure sizing core: numeric validators, the verified 23-market contract-spec table, risk math, the floor algorithm, tick-grid guards, and gate-report shape normalization
- `references/futures-contract-specs.md` -- The verified contract-spec table with per-row official source URLs and verification dates
- `references/sizing-methodology.md` -- Formulas, the exact-rational floor algorithm's rationale, the fail-closed exit-code convention, and worked examples (ES long, B6 short via gate handoff)
