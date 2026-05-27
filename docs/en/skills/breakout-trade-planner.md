---
layout: default
title: "Breakout Trade Planner"
grand_parent: English
parent: Skill Guides
nav_order: 13
lang_peer: /ja/skills/breakout-trade-planner/
permalink: /en/skills/breakout-trade-planner/
---

# Breakout Trade Planner
{: .no_toc }

Generate Minervini-style breakout trade plan templates from VCP screener output with worst-case risk calculation, portfolio heat management, and Alpaca-compatible order templates for manual entry (stop-limit bracket for pre-placement, limit bracket for post-confirmation). All plans require manual review and broker entry — no orders are placed automatically. Use when user has VCP screener results and wants decision-support trade plans with entry/stop/target levels and position sizing.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/breakout-trade-planner.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/breakout-trade-planner){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Breakout Trade Planner

---

## 2. When to Use

- User has VCP screener JSON output and wants trade plans
- User asks for breakout entry/stop/target calculation
- User wants Alpaca-compatible order templates for manual entry of VCP breakout candidates
- User needs position sizing with portfolio heat management

---

## 3. Prerequisites

- VCP screener JSON output with `schema_version: "1.0"`
- No API keys required (works with local JSON files)
- No external skill dependencies (position sizing is built-in)

---

## 4. Quick Start

```bash
python3 skills/breakout-trade-planner/scripts/plan_breakout_trades.py \
  --input reports/vcp_screener_YYYY-MM-DD.json \
  --account-size 100000 \
  --risk-pct 0.5 \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Generate Trade Plans

Run the planner with VCP screener output:

```bash
python3 skills/breakout-trade-planner/scripts/plan_breakout_trades.py \
  --input reports/vcp_screener_YYYY-MM-DD.json \
  --account-size 100000 \
  --risk-pct 0.5 \
  --output-dir reports/
```

### Step 2: Review Output

Read the generated JSON and Markdown reports. Present:

1. **Evaluation Candidates** — Pre-breakout candidates with order templates for manual broker entry
2. **Revalidation** — Breakout-state candidates needing live confirmation
3. **Watchlist** — Developing VCP candidates to monitor
4. **Rejected/Deferred/Constrained** — Candidates filtered by Gate or portfolio limits
### Step 3: Explain Trade Plans

For each evaluation candidate, explain:
- Entry levels (signal vs worst-case) and stop-loss placement
- R-multiple targets and reward-risk ratio
- Two execution modes: pre_place (stop-limit) vs post_confirm (limit after 5min confirmation)
- Portfolio risk contribution and cumulative heat

---

## 6. Resources

**References:**

- `skills/breakout-trade-planner/references/minervini_entry_rules.md`

**Scripts:**

- `skills/breakout-trade-planner/scripts/order_builder.py`
- `skills/breakout-trade-planner/scripts/plan_breakout_trades.py`
- `skills/breakout-trade-planner/scripts/risk_calculator.py`
