---
name: parabolic-short-trade-planner
description: Screen US equities for parabolic exhaustion patterns and generate conditional pre-market short plans, then evaluate intraday trigger fires from live 5-min bars. Phase 1 daily 5-factor scorer (MA extension / acceleration / volume climax / range expansion / liquidity), Phase 2 per-candidate plans for ORL break / first-red 5-min / VWAP fail with explicit borrow / SSR / manual-confirmation gating, Phase 3 one-shot intraday FSM that detects trigger fires and resolves concrete share counts. Covers Phase 1 + Phase 2 + Phase 3.
---

## Overview

Generate Qullamaggie-style Parabolic Short watchlists and conditional
pre-market plans for US equities. The skill never sends orders. It emits
JSON + Markdown that a human reviews against their broker before entry.

Three phases:

- **Phase 1 (`screen_parabolic.py`)**: pulls EOD bars + company profile
  from FMP, applies hard invalidation rules (mode-aware), scores
  survivors on 5 factors (weights 30/25/20/15/10), and assigns A/B/C/D
  grades.
- **Phase 2 (`generate_pre_market_plan.py`)**: takes the Phase 1 JSON,
  filters by `--tradable-min-grade` (default `B`), checks Alpaca short
  inventory (or `ManualBrokerAdapter`), evaluates SEC Rule 201 SSR
  state from the inherited prior-day close, and renders three trigger
  plans per candidate.
- **Phase 3 (`monitor_intraday_trigger.py`)**: reads the Phase 2 plan,
  fetches 5-min bars (Alpaca live or fixture), walks each plan's FSM
  forward by one step, persists per-plan state, and writes an
  `intraday_monitor` JSON with `state`, `entry_actual`, `stop_actual`,
  and `shares_actual` (when triggered). One-shot — trader runs it
  every 1–5 min via `watch` or cron; replay-deterministic so re-runs
  are byte-identical.

## When to Use

Invoke this skill when the user wants to:

- Build a daily Parabolic Short watchlist from S&P 500 (or a custom CSV).
- Translate a watchlist into pre-market trade plans with explicit
  borrow / SSR / state-cap gating.
- Audit a candidate's blocking vs advisory manual-confirmation reasons
  before placing an order at Alpaca.

Do NOT invoke for:

- Long-side momentum screening — use vcp-screener or canslim-screener.
- 1-minute / sub-minute intraday signals — Phase 3 evaluates 5-min
  bars only.
- Live order routing — this skill is detection-only by design;
  Phase 3 emits a `triggered` state with concrete entry/stop/share
  count, but the trader fires the order manually.

## Workflow

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

### Phase 3 — intraday trigger monitor

1. Confirm `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` are set (Phase 3
   uses Alpaca market data; `data.alpaca.markets` works for both
   paper and live accounts).
2. During US regular session, run one-shot per cadence — typical is
   every 60 s during the first 30 min, then every 5 min:
   ```bash
   python3 skills/parabolic-short-trade-planner/scripts/monitor_intraday_trigger.py \
     --plans-json reports/parabolic_short_plan_2026-05-05.json \
     --bars-source alpaca \
     --state-dir state/parabolic_short/ \
     --output-dir reports/
   ```
   Or wrap in `watch -n 60 'python3 ...'` / cron.
3. Output: `reports/parabolic_short_intraday_<date>.json` lists every
   monitored plan with `state` (`armed` / `triggered` / `invalidated`
   / FSM-specific), bar-derived transition timestamps, and
   `size_recipe_resolved` (concrete `shares_actual`) when triggered.
4. For testing without the API, use `--bars-source fixture
   --bars-fixture <path>` against a JSON fixture
   (`scripts/tests/fixtures/intraday_bars/`).

Phase 3 is **idempotent**: each run replays the full session bars
from open up to `now_et` (or `--now-et` override), so re-running
during the same minute produces the same state. `prior_state` is
used only for diff/notification display; it never advances the FSM.

### Reviewing a plan before entry

Read three top-level fields per ticker:

- `plan_status`: `actionable` (manual gates can be cleared) or
  `watch_only` (hard blockers — borrow unavailable or SSR active).
- `blocking_manual_reasons`: must all be resolved before pulling the
  trigger.
- `advisory_manual_reasons`: heads-up only, e.g.
  `manual_locate_required` (always set), `warning:too_early_to_short`.

## Output Format

Phase 1 JSON: `parabolic_short_<as_of>.json` (schema_version 1.0).
Phase 2 JSON: `parabolic_short_plan_<as_of>.json` (schema_version 1.0).
Phase 3 JSON: `parabolic_short_intraday_<as_of>.json` (schema_version 1.0,
phase = `intraday_monitor`).
The contract is pinned by `tests/test_schema_contract.py` plus
`tests/test_monitor_intraday_smoke.py` for Phase 3.

## Resources

- `references/parabolic_short_methodology.md` — Qullamaggie's 3-trigger
  framework and exhaustion signals.
- `references/short_invalidation_rules.md` — mode-aware exclusion rules.
- `references/short_risk_management.md` — Rule 201, ETB vs HTB, locate.
- `references/intraday_trigger_playbook.md` — detail on each trigger
  type, the FSM transitions Phase 3 implements, and same-bar tie-break
  semantics.
- `references/broker_capability_matrix.md` — what each broker exposes
  through its API for short inventory.
