---
layout: default
title: Stockbee Momentum Burst Playbook
grand_parent: English
parent: Playbooks
nav_order: 12
lang_peer: /ja/playbooks/stockbee-momentum-burst/
permalink: /en/playbooks/stockbee-momentum-burst/
---

# Stockbee Momentum Burst — Short-Term Swing Playbook

A usage guide for the whole momentum-burst workflow, not for `stockbee-momentum-burst-screener` in isolation. It walks a candidate from screening through chart validation, sizing, and registration in `trader-memory-core`, to closing the trade. Read this before running the screener on its own.

> **Manual, not automated.** No skill in this pipeline places, cancels, or monitors an order, and there is no realtime monitor. Every order is placed by hand at the broker; every screener output is a candidate list to review, not a signal to trade blindly.

---

## The idea in one paragraph

Stockbee-style Momentum Burst looks for a short, sharp price-and-volume burst breaking out of a range-contracted base — a 4% breakout, a dollar breakout, or a range expansion, always above a liquidity floor. Volume above the prior day is also required for the 4% breakout and the range expansion; the dollar breakout needs only the liquidity floor, not volume expansion. This is a **2-5 session swing**, not a long-term trend trade and not a PEAD earnings-drift trade. The screener is a candidate-generation and setup-quality tool, not a signal service: a bare 4% move is never enough by itself, survivors still need a chart check, and only actual broker fills — never planned entries — become `ACTIVE` in trade memory.

---

## When to run it

- After confirming the market regime allows new swing risk — run `market-regime-daily` (or at minimum `drawdown-circuit-breaker`) first, or explicitly mark the screen `--market-gate restrictive` / manual-review-only if you skip that check.
- Any of three input modes: `--fmp-universe` (Mode A, live universe scan), `--symbols` (Mode B, explicit list), or `--prices-json` (Mode C, fully offline).
- The default entry reference is the latest close, because the screener is primarily an end-of-day / near-close tool. If you run it intraday, treat the entry reference as indicative and confirm the breakout is still valid near your intended order time.

## When not to run it

- **Not as a stand-alone buy list.** A 4% trigger alone is not enough — require setup quality (base length, base width, close location) and a manageable risk distance to stop.
- **Not for earnings-driven gaps.** An earnings-day gap-up is PEAD's territory, not this playbook's — see [Don't confuse this with PEAD](#dont-confuse-this-with-pead) below.
- **Never wired to auto-execution.** The screener has no broker integration and never will inside this pipeline.

---

## The pipeline at a glance

```
1  market-regime-daily / drawdown-circuit-breaker →  market_gate                    (confirms or restricts new swing risk)
2  stockbee-momentum-burst-screener                →  stockbee_momentum_burst_report (candidates; 5-state classification)
3  technical-analyst                                →  chart validation               (image-based, no CLI)
4  position-sizer                                    →  position size                  (shares; pure calculation)
5  trader-memory-core (ingest --source manual)        →  IDEA thesis                    (no dedicated adapter)
6  trader-memory-core (link_report, via uv run)        →  linked evidence on the thesis  (screener + chart-review reports)
7  trader-memory-core (store transition ENTRY_READY)  →  ready-to-order thesis
8  pre-trade-discipline-gate                          →  GO / REVIEW_REQUIRED / NO_GO
9  [GO only] manual order at the broker
10 trader-memory-core (store open-position)            →  ACTIVE thesis                  (actual fill only)
```

Steps 2, 7, 8, and 10 are decision points. Step 4 is pure calculation. Step 3 is chart-based and has no CLI.

---

## The runbook

Set a working date once, before step 2, so downstream filenames and journal entries stay traceable to the same session:

```bash
export RUN_DATE=2026-07-15
```

The examples below screen a candidate called `ZBRK`.

### Step 1 — Confirm the market regime allows new risk

Run `market-regime-daily` (or at minimum `drawdown-circuit-breaker`) before screening. If the regime is restrictive, either skip new entries or pass `--market-gate restrictive` to the screener in step 2 — any candidate that still scores high enough gets downgraded to `MANUAL_REVIEW_ONLY` rather than `ACTIONABLE_DAY1`.

### Step 2 — Screen for Momentum Burst candidates

```bash
# Mode A: FMP universe scan (requires FMP_API_KEY for historical prices)
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --fmp-universe --max-symbols 300 \
  --market-gate allowed \
  --output-dir reports/

# Mode B: explicit symbols (requires FMP_API_KEY for historical prices)
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --symbols ZBRK NVDA SMCI \
  --market-gate allowed \
  --output-dir reports/

# Mode C: fully offline (no FMP client is constructed at all)
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --prices-json data/daily_ohlcv.json \
  --market-gate allowed \
  --output-dir reports/
```

Modes A and B both build an `FMPClient` before screening and need `FMP_API_KEY`; only Mode C (`--prices-json`) is fully offline.

Produces `stockbee_momentum_burst_<timestamp>.json`. Each candidate lands in one of five `state` values, driven by `setup_score` and the `--market-gate` you passed:

| State | Condition | Typical rating |
|---|---|---|
| `ACTIONABLE_DAY1` | score ≥ 80, market gate not restrictive | A / A- |
| `MANUAL_REVIEW` | 70 ≤ score < 80, market gate not restrictive | B |
| `MANUAL_REVIEW_ONLY` | score ≥ 70 **and** `--market-gate restrictive` | A / A- / B |
| `WATCH_ONLY` | 55 ≤ score < 70 | Watch |
| `REJECTED` | score < 55, or a hard reject (below min price/volume, no trigger tag, insufficient history, `entry_reference <= stop_reference`, or risk-to-stop wider than `--max-risk-pct-to-stop`) | Reject |

`MANUAL_REVIEW_ONLY` is a distinct fifth state, not a synonym for `MANUAL_REVIEW` — it exists so that a high-scoring candidate never becomes auto-actionable while the broader market gate itself is restrictive. Treat it the same as `MANUAL_REVIEW` for sizing purposes: a full manual chart review is required either way, nothing here is ever auto-actionable.

This screening pass has been run end-to-end against an offline fixture for this playbook: a 20-day tight base followed by a 7.5% breakout on 5x volume scored 86 (`ACTIONABLE_DAY1`, rating A-) with `entry_reference` at the trigger-day close and `stop_reference` at the trigger-day low.

### Step 3 — Chart validation

Send only `A` / `A-` candidates to `technical-analyst` for a manual chart check. `B` candidates go to a watchlist or a smaller-risk review; `Watch`-rated candidates stay in the model book without a planned trade unless the chart review upgrades them; `Reject` candidates are kept only for post-analysis calibration, never for execution.

### Step 4 — Size the position

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 54.05 --stop 50.38 --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/
```

`entry_reference` and `stop_reference` come straight from the screener's candidate row (latest close and trigger-day low, respectively) — the screener does not decide the final share count, it only hands off these two reference fields. If `risk_pct_to_stop` is too wide for your account's risk policy, that is a **NO TRADE**, not a signal to size down further.

### Step 5 — Register the IDEA thesis (manual ingest, no dedicated adapter)

There is no `stockbee-momentum-burst-screener` adapter in `trader-memory-core` — candidates are registered through the generic `--source manual` path:

```json
{
  "ticker": "ZBRK",
  "thesis_type": "growth_momentum",
  "setup_type": "stockbee_momentum_burst",
  "thesis_statement": "ZBRK 4pct_breakout on a 20-day tight base, ACTIONABLE_DAY1 score 86 (A-). Stockbee Momentum Burst short-term swing (2-5 sessions) — not a long-term or PEAD thesis.",
  "entry_price": 54.05,
  "stop_price": 50.38
}
```

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source manual --input idea.json --state-dir state/theses/
```

It prints `Registered 1 thesis(es): th_...`. Export that ID for the remaining steps:

```bash
export THESIS_ID=th_zbrk_grw_20260715_xxxx  # paste the printed id
```

**Be precise about `thesis_type` here.** `trader-memory-core` has exactly five fixed values (`dividend_income`, `growth_momentum`, `mean_reversion`, `earnings_drift`, `pivot_breakout`); `growth_momentum` is simply the closest fit by elimination for Momentum Burst, not a label reserved for it. The `canslim-screener` adapter also registers `growth_momentum` theses. The `list` subcommand only filters by `--type` (`thesis_type`) — there is no `--setup-type` flag — so `trader_memory_cli.py store list --type growth_momentum` will mix Momentum Burst candidates together with CANSLIM ones. The `setup_type: stockbee_momentum_burst` field above is what actually distinguishes the two cohorts today, and separating them still means reading that field back out of each thesis by hand, not filtering for it on the command line.

### Step 6 — Link the upstream evidence

`link_report()` is a Python function, not a CLI subcommand — it imports `thesis_store` directly instead of going through `trader_memory_cli.py`, so it needs trader-memory-core's dependencies (`pyyaml`, `jsonschema`) available. Run it through `uv` (or any environment where they are installed). Link the screener output and the chart-validation report so the thesis's evidence chain is auditable — the paths below are examples, matching each skill's own documented output-filename convention, not files this run is asserted to have actually produced:

```bash
uv run --project . python - <<PYEOF
import sys
sys.path.insert(0, "skills/trader-memory-core/scripts")
from pathlib import Path
import thesis_store

state_dir = Path("state/theses/")
thesis_id = "$THESIS_ID"
run_date = "$RUN_DATE"
for skill, path in [
    ("stockbee-momentum-burst-screener", f"reports/stockbee_momentum_burst_{run_date}_101500.json"),
    ("technical-analyst", f"reports/ZBRK_technical_analysis_{run_date}.md"),
]:
    thesis_store.link_report(state_dir, thesis_id, skill, path, run_date)
    print(f"linked {skill} -> {path}")
PYEOF
```

### Step 7 — Transition to `ENTRY_READY`

Once the chart review and sizing both check out:

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ transition "$THESIS_ID" ENTRY_READY \
  --reason "ACTIONABLE_DAY1 confirmed, sizing verified"
```

The thesis stays `IDEA` → `ENTRY_READY` — never `ACTIVE` — until an actual broker fill is recorded in step 10. Verified directly against this fixture: after `transition ENTRY_READY`, `store list --ticker ZBRK` reports `"status": "ENTRY_READY"`, and only flips to `"status": "ACTIVE"` after `open-position` runs with a real fill price and date.

### Step 8 — Run the pre-trade discipline gate

```bash
python3 skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py \
  --answers-file state/manual-entry-checklist.json \
  --state-dir state/theses/ \
  --market-regime-decision reports/exposure_decision_latest.json \
  --circuit-breaker-decision reports/circuit_breaker_decision_latest.json \
  --output-dir reports/pre-trade-discipline
```

`ACTIONABLE_DAY1` is one of the gate's recognized actionable `order_intent` values (alongside `ENTRY_READY`, `ACTIONABLE`, and `MANUAL_ORDER`). The gate is entirely offline — it does not place, cancel, or monitor orders, only journals the decision. **Only place the order on a `GO` decision.** `REVIEW_REQUIRED` or `NO_GO` means: don't trade yet.

### Step 9 — Place the order manually

No skill in this pipeline touches a broker. Enter the order yourself, sized as computed in step 4.

### Step 10 — Record the actual fill

```bash
export FILL_DATE=2026-07-16  # the real broker fill date

python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ open-position "$THESIS_ID" \
  --actual-price 54.10 --actual-date "$FILL_DATE" --shares 272
```

Only now does the thesis become `ACTIVE`. A planned entry is never treated as a fill.

---

## Holding rules and exits

`references/entry_exit_rules.md` on the skill itself keeps the exit template deliberately loose: stop out if the trigger-day low fails, **review after 3-5 sessions**, protect gains on an abnormally fast move (especially 10%+ in one session), and treat a full signal reversal or a lack of follow-through after several sessions as a failed burst. That is the entire reference text — it does not name specific session numbers as hard checkpoints.

This playbook adds the following concrete operational reading on top of that guidance. Treat it as **this playbook's interpretation, not a quote from the skill's own rules**:

- Typical hold: 2-3 sessions.
- **Session 3** — do a follow-through review: is the burst still confirming (holding above the trigger-day low, volume not collapsing)?
- **Session 5** — treat this as the hard deadline for the thesis as a Momentum Burst position. If it hasn't resolved by then, close it rather than let a 2-5-session swing quietly drift into an open-ended hold.
- Exit regardless of session count on: a trigger-day-low failure, a full signal reversal, or no follow-through after several sessions.
- A 10%+ single-session advance is a cue to protect gains (trail the stop, take partial profit) — not necessarily an immediate exit.
- If you genuinely want to hold past session 5, don't just let the Momentum Burst thesis run long. Close it (or mark it converted in your notes) and register the continuation as a **separate thesis** under a different `setup_type` — an Episodic Pivot or general swing thesis, for example — so `trader-memory-core`'s Momentum Burst cohort statistics stay honest.

## What not to do

- Don't treat a bare 4% move as a buy signal by itself — score, setup quality, and a manageable risk distance all matter.
- Don't wire screener output into any auto-order system. None exists in this pipeline, and none should be improvised.
- Don't take a candidate whose `risk_pct_to_stop` is too wide for your risk policy — that's a **NO TRADE**, not a smaller position.
- Don't relabel a failed 2-5-session burst as a "long-term investment" to avoid booking the loss.

## Don't confuse this with PEAD

Both playbooks screen liquid US stocks for swing entries out of `trader-memory-core`, but they are separate cohorts:

| | Momentum Burst | PEAD |
|---|---|---|
| Catalyst | Price/volume breakout — no earnings requirement | An actual earnings gap-up, confirmed by hand |
| Entry pattern | 4% breakout / dollar breakout / range expansion off a tight base | Green weekly close above a red weekly candle's high |
| Hold | 2-5 sessions | 2-6 weeks |
| `thesis_type` | `growth_momentum` (shared with CANSLIM) | `earnings_drift` (shared type; dedicated `pead-screener` adapter) |
| Ingest path | `--source manual`, no dedicated adapter | `--source pead-screener`, dedicated fail-closed adapter |
| Stop reference | Trigger-day low | Red weekly candle's low |

Stockbee's Episodic Pivot classifier (`analyze_ep.py`) sits upstream of both: it flags `momentum_handoff` candidates (day gain ≥ 4%, not rejected) for this playbook — but only `ACTIONABLE_DAY1` state candidates get registered here as an editorial choice, other states stay watch-only — and separately flags `pead_handoff` candidates (earnings/guidance catalyst) as PEAD-eligible. A `pead_handoff` flag is not itself a PEAD entry: the candidate still has to independently satisfy PEAD's own red-candle-pullback-then-breakout contract before the [PEAD entry rules]({{ '/en/playbooks/pead/' | relative_url }}) apply.

---

## Related

- No *dedicated* `workflows/*.yaml` manifest exists for this exact playbook. `stockbee-momentum-burst-screener` already appears in the broader [`stockbee-ep-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/stockbee-ep-daily.yaml) and [`swing-opportunity-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/swing-opportunity-daily.yaml) workflows, but there is no standalone Momentum Burst flow — Trading Skills Navigator routing to a dedicated flow is out of scope until one is added.
- Skill reference: [Stockbee Momentum Burst Screener]({{ '/en/skills/stockbee-momentum-burst-screener/' | relative_url }})
- The skills used: `stockbee-momentum-burst-screener`, `technical-analyst`, `position-sizer`, `trader-memory-core`, `pre-trade-discipline-gate`
- See also: [PEAD Playbook]({{ '/en/playbooks/pead/' | relative_url }})
