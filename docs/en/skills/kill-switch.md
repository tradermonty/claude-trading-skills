---
layout: default
title: "Kill Switch"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/kill-switch/
permalink: /en/skills/kill-switch/
---

# Kill Switch
{: .no_toc }

Continuously watch Alpaca account state against the risk limits in trading_params.yaml and trigger a flatten-all when any hard limit is breached. Monitors daily P&L vs max_daily_loss_pct, position count vs max_positions, sector exposure vs max_sector_exposure_pct, correlated positions, and market-top distribution-day count. Run by the launchd watchdog every 2 minutes during market hours. Invoke when the user asks to "check kill-switch", "am I over limits", "what's my daily P&L".
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/kill-switch){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Kill-Switch

---

## 2. When to Use

- Every 2 minutes during market hours (launchd agent).
- Invoked on demand by the trade-loop-orchestrator before every loop iteration.
- When user asks "am I over my limit", "what's my daily P&L vs kill switch", "how
  close am I to being flattened".

---

## 3. Prerequisites

- Same env as alpaca-executor: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER`
- Access to `config/trading_params.yaml`
- Writable `state/` directory for the SOD snapshot and kill-switch state file

---

## 4. Quick Start

```bash
python3 skills/kill-switch/scripts/capture_sod.py \
  --output state/sod_$(date +%Y-%m-%d).json
```

---

## 5. Workflow

### Daily SOD Capture (09:30 ET)

```bash
python3 skills/kill-switch/scripts/capture_sod.py \
  --output state/sod_$(date +%Y-%m-%d).json
```

Pulls account equity at market open, writes to state.

### Continuous Watchdog (every 2 min, 09:30-16:00 ET)

```bash
python3 skills/kill-switch/scripts/check_limits.py \
  --sod state/sod_$(date +%Y-%m-%d).json \
  --output state/kill_switch_status.json
```

On breach, the script sets `status: TRIPPED`, writes the reason, and calls
`flatten_all.py` itself.

### Pre-loop Check (called by orchestrator)

```bash
python3 skills/kill-switch/scripts/check_limits.py --pre-loop \
  --output state/kill_switch_status.json
```

Same as watchdog but does NOT trigger flatten (the continuous watchdog owns
flattening). Orchestrator reads the output and skips the loop if TRIPPED.

### Reset (manual)

```bash
python3 skills/kill-switch/scripts/reset.py --reason "manual reset after review"
```

Requires explicit user confirmation. Clears the TRIPPED state and re-enables
the loop.

---

## 6. Resources

**Scripts:**

- `skills/kill-switch/scripts/capture_sod.py`
- `skills/kill-switch/scripts/check_limits.py`
- `skills/kill-switch/scripts/reset.py`
