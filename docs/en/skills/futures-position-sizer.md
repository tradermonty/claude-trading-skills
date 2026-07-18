---
layout: default
title: "Futures Position Sizer"
grand_parent: English
parent: Skill Guides
nav_order: 33
lang_peer: /ja/skills/futures-position-sizer/
permalink: /en/skills/futures-position-sizer/
generated: true
---

# Futures Position Sizer
{: .no_toc }

Calculate contract-based futures position sizes from a direction, entry, and stop-loss, using verified per-symbol contract specs (multiplier, tick size, tick value). Use when the user asks how many futures contracts to trade, wants to size a futures position (ES, NQ, ZB, GC, CL, 6E/E6, VX, BT, ...), or is handing off a contrarian-setup-gate READY_FOR_PLAN direction/invalidation_level for sizing. Pure, offline calculation -- no API keys, no network.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/futures-position-sizer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/futures-position-sizer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Shapiro pipeline step 4: convert a direction, entry price, and stop-loss into a contract count, given an account risk budget and a verified contract spec (multiplier, tick size, tick value). This is a NEW, separate skill from `position-sizer` -- futures contracts are leveraged, multiplier-based instruments with wildly different dollar-per-point values (a $0.25 move is $12.50 on ES but $5.00 on NQ and $31.25 on ZB); reusing the equity share-count sizer for futures would silently produce wrong position sizes.

Two ways to size a trade:

- **Mode A (explicit)**: supply `--symbol --direction --entry --stop` directly.
- **Mode B (gate handoff)**: supply `--gate-json <contrarian-setup-gate report> --entry`. Direction and stop (the gate's `invalidation_level`) come from the gate's `READY_FOR_PLAN` report -- the sizer never sizes a setup the gate has not confirmed as READY, and never accepts an explicit `--direction`/`--stop` alongside `--gate-json` (the gate is authoritative when provided).

`--entry` is ALWAYS required, in both modes -- neither this skill nor the gate ever derives an entry price; the operator supplies it.

---

## 2. When to Use

- After `contrarian-setup-gate` reaches `READY_FOR_PLAN` and you need a contract count for the confirmed direction and stop
- User asks "how many ES/NQ/GC/CL/... contracts should I trade?"
- User has a futures trade idea with a known entry and stop and wants risk-based sizing
- User wants to check the verified contract spec (multiplier/tick size/tick value) for a symbol before sizing (`--list-specs`)

---

## 3. Prerequisites

- Python 3.9+, standard library only -- no API keys, fully offline
- A direction, entry, and stop (mode A), or a `contrarian-setup-gate` JSON report with `setup_status: READY_FOR_PLAN` (mode B)
- For a symbol outside the verified 23-market core table: its multiplier, tick size, and quote currency (all three, together)

---

## 4. Quick Start

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --symbol ES --direction LONG --entry 5000.25 --stop 4980.00 \
  --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/ --format both
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/futures-position-sizer/references/futures-contract-specs.md`
- `skills/futures-position-sizer/references/sizing-methodology.md`

**Scripts:**

- `skills/futures-position-sizer/scripts/futures_position_sizer.py`
- `skills/futures-position-sizer/scripts/futures_sizing.py`
