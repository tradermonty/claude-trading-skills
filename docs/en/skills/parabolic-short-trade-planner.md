---
layout: default
title: "Parabolic Short Trade Planner"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/parabolic-short-trade-planner/
permalink: /en/skills/parabolic-short-trade-planner/
---

# Parabolic Short Trade Planner
{: .no_toc }

Screen US equities for parabolic exhaustion patterns and generate conditional pre-market short plans. Daily 5-factor scorer (MA extension / acceleration / volume climax / range expansion / liquidity) plus per-candidate plans for ORL break, first-red 5-min, and VWAP fail triggers. Borrow inventory, SSR (Rule 201), and manual-confirmation gating are surfaced explicitly so the trader knows what to verify at the broker before entry. MVP covers Phase 1 (daily screener) and Phase 2 (pre-market plan); intraday trigger detection is left to a follow-up skill.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/parabolic-short-trade-planner){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Generate Qullamaggie-style Parabolic Short watchlists and conditional
pre-market plans for US equities. The skill never sends orders. It emits
JSON + Markdown that a human reviews against their broker before entry.

Two phases:

- **Phase 1 (`screen_parabolic.py`)**: pulls EOD bars + company profile
  from FMP, applies hard invalidation rules (mode-aware), scores
  survivors on 5 factors (weights 30/25/20/15/10), and assigns A/B/C/D
  grades.
- **Phase 2 (`generate_pre_market_plan.py`)**: takes the Phase 1 JSON,
  filters by `--tradable-min-grade` (default `B`), checks Alpaca short
  inventory (or `ManualBrokerAdapter`), evaluates SEC Rule 201 SSR
  state from the inherited prior-day close, and renders three trigger
  plans per candidate.

---

## 2. When to Use

Invoke this skill when the user wants to:

- Build a daily Parabolic Short watchlist from S&P 500 (or a custom CSV).
- Translate a watchlist into pre-market trade plans with explicit
  borrow / SSR / state-cap gating.
- Audit a candidate's blocking vs advisory manual-confirmation reasons
  before placing an order at Alpaca.

Do NOT invoke for:

- Long-side momentum screening — use vcp-screener or canslim-screener.
- Intraday trigger monitoring (1-min ORL etc.) — that's the v0.5 follow-up.
- Live order routing — this skill is plan-only by design.

---

## 3. Prerequisites

- **API Key:** None required
- **Python 3.9+** recommended

---

## 4. Quick Start

```bash
python3 skills/parabolic-short-trade-planner/scripts/screen_parabolic.py \
     --mode safe_largecap --as-of 2026-04-30 --output-dir reports/
```

---

## 5. Workflow

### Phase 1 — daily screener

1. Confirm `FMP_API_KEY` is set (env var or `--api-key`).
2. Run with the safer-by-default mode:
   ```bash
   python3 skills/parabolic-short-trade-planner/scripts/screen_parabolic.py \
     --mode safe_largecap --as-of 2026-04-30 --output-dir reports/
   ```
3. Inspect `reports/parabolic_short_<date>.md` — the watchlist is grouped
   by grade (A→D).
4. Promote interesting names to Phase 2.

For small-cap blow-offs, switch to `--mode classic_qm` (looser market
cap and ADV floors, higher 5-day ROC threshold).

For testing without the API, run `--dry-run --fixture <path>` against a
JSON fixture (one is shipped at `scripts/tests/fixtures/dry_run_minimal.json`).

### Phase 2 — pre-market plan generator

1. Optional: set `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` for live borrow
   checks. Without them the planner falls back to `ManualBrokerAdapter`,
   which marks every candidate as `borrow_inventory_unavailable` /
   `plan_status: watch_only`.
2. Run:
   ```bash
   python3 skills/parabolic-short-trade-planner/scripts/generate_pre_market_plan.py \
     --candidates-json reports/parabolic_short_2026-04-30.json \
     --account-size 100000 --risk-bps 50 --output-dir reports/
   ```
3. Output: `reports/parabolic_short_plan_<date>.json`. Each plan contains
   three entry plans (5min ORL break, first red 5-min, VWAP fail) with
   `entry_hint` / `stop_hint` formula strings (no baked-in shares — the
   trader computes shares at trigger time from the `shares_formula`).

### Reviewing a plan before entry

Read three top-level fields per ticker:

- `plan_status`: `actionable` (manual gates can be cleared) or
  `watch_only` (hard blockers — borrow unavailable or SSR active).
- `blocking_manual_reasons`: must all be resolved before pulling the
  trigger.
- `advisory_manual_reasons`: heads-up only, e.g.
  `manual_locate_required` (always set), `warning:too_early_to_short`.

---

## 6. Resources

**References:**

- `skills/parabolic-short-trade-planner/references/broker_capability_matrix.md`
- `skills/parabolic-short-trade-planner/references/intraday_trigger_playbook.md`
- `skills/parabolic-short-trade-planner/references/parabolic_short_methodology.md`
- `skills/parabolic-short-trade-planner/references/short_invalidation_rules.md`
- `skills/parabolic-short-trade-planner/references/short_risk_management.md`

**Scripts:**

- `skills/parabolic-short-trade-planner/scripts/bar_normalizer.py`
- `skills/parabolic-short-trade-planner/scripts/broker_short_inventory_adapter.py`
- `skills/parabolic-short-trade-planner/scripts/fmp_client.py`
- `skills/parabolic-short-trade-planner/scripts/generate_pre_market_plan.py`
- `skills/parabolic-short-trade-planner/scripts/invalidation_rules.py`
- `skills/parabolic-short-trade-planner/scripts/manual_reasons.py`
- `skills/parabolic-short-trade-planner/scripts/math_helpers.py`
- `skills/parabolic-short-trade-planner/scripts/parabolic_report_generator.py`
- `skills/parabolic-short-trade-planner/scripts/parabolic_scorer.py`
- `skills/parabolic-short-trade-planner/scripts/screen_parabolic.py`
- `skills/parabolic-short-trade-planner/scripts/size_recipe_builder.py`
- `skills/parabolic-short-trade-planner/scripts/ssr_state_tracker.py`
- `skills/parabolic-short-trade-planner/scripts/state_caps.py`
