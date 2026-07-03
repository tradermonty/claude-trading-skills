---
layout: default
title: "Drawdown Circuit Breaker"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/drawdown-circuit-breaker/
permalink: /en/skills/drawdown-circuit-breaker/
generated: false
---

# Drawdown Circuit Breaker
{: .no_toc }

Evaluate account-level drawdown circuit breaker rules from trader-memory-core state and decide whether new trade risk is allowed today. Uses realized P&L, losing-streak cooldowns, and weekly/monthly drawdown limits without any external API.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/drawdown-circuit-breaker){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Evaluate whether the trader should take new trade risk today based on account-level realized P&L and recent terminal trade outcomes. This skill reads trader-memory-core thesis YAML files only. It produces a `circuit_breaker_decision` artifact that complements the market-side `exposure_decision` from exposure-coach.

The circuit breaker is a recommendation and recordkeeping tool. It does not replace human judgment, and it does not enforce broker-side blocks or automated order rejection.

---

## 2. When to Use

- Before screening or sizing any new swing trade candidate
- After a losing trade or partial trim to check whether a cooldown is active
- During daily planning when trader-memory-core contains recent closed or partially closed positions
- As a workflow gate before swing-opportunity-daily proceeds to candidate generation
- When reviewing whether daily, weekly, or monthly loss limits have been breached

---

## 3. Prerequisites

- Python 3.9+
- Local trader-memory-core thesis YAML files, usually under `state/theses/`
- Account size in dollars
- No API keys or network access required

---

## 4. Quick Start

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --state-dir state/theses \
  --account-size 100000 \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Read Trader Memory State

Point the script at the thesis state directory:

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --state-dir state/theses \
  --account-size 100000 \
  --output-dir reports/
```

The script scans every `th_*.yaml` file and reads realized P&L from each thesis `status_history[]` ledger entry. It does not use `_index.json` for P&L, because the index is a lightweight lookup file and does not contain the required realized-P&L ledger.

If the state directory is missing or empty, the skill returns `TRADING_ALLOWED` with `data_quality: EMPTY_STATE` so a new user is not blocked by the absence of history.

### Step 2: Evaluate Circuit Breaker Rules

The default rules are:

| Rule | Default | Triggered State | Release |
|------|---------|-----------------|---------|
| Max daily loss | 2.0% of account | HALTED | Next ET weekday |
| Losing streak cooldown | 2 terminal losing theses | COOLDOWN | 24 hours after latest loss exit |
| Weekly drawdown halt | 5.0% of account | HALTED | Next Monday ET |
| Monthly drawdown halt | 8.0% of account | HALTED | First day of next month ET |

Day, week, and month boundaries use `America/New_York`. Date-only producer
timestamps from `trader-memory-core` are counted on the named ET date. Set
`--as-of` for deterministic evaluation; date-only `--as-of` values cover the
full ET day, while timestamp values exclude future events after that time:

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --state-dir state/theses \
  --account-size 100000 \
  --as-of 2026-07-02T12:00:00-04:00 \
  --output-dir reports/
```

### Step 3: Override Thresholds When Needed

Override individual thresholds on the CLI:

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --account-size 100000 \
  --max-daily-loss-pct 1.5 \
  --losing-streak-n 3 \
  --cooldown-hours 48 \
  --weekly-drawdown-pct 4 \
  --monthly-drawdown-pct 6
```

Or provide a JSON config file:

```json
{
  "max_daily_loss_pct": 1.5,
  "losing_streak_n": 3,
  "cooldown_hours": 48,
  "weekly_drawdown_pct": 4.0,
  "monthly_drawdown_pct": 6.0
}
```

CLI arguments override config-file values.

### Step 4: Interpret the Decision

Use the generated decision as a gate for new trade risk:

| Recommendation | Meaning |
|----------------|---------|
| TRADING_ALLOWED | No circuit breaker rule is active; new trade risk may proceed through the rest of the workflow |
| COOLDOWN | Do not open new positions; continue managing existing positions and review the recent losses |
| HALTED | Stop new entries and focus on review until the active halt expires |

Existing position management remains a human decision. The circuit breaker is designed to prevent new risk escalation after realized damage, not to force liquidation.

---

## 6. Resources

**References:**

- `skills/drawdown-circuit-breaker/references/circuit_breaker_framework.md`

**Scripts:**

- `skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py`
