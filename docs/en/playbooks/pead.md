---
layout: default
title: PEAD Trade Playbook
grand_parent: English
parent: Playbooks
nav_order: 14
lang_peer: /ja/playbooks/pead/
permalink: /en/playbooks/pead/
---

# PEAD — Post-Earnings Announcement Drift Playbook

A usage guide for the whole PEAD workflow, not for `pead-screener` in isolation. It walks a candidate from earnings-gap screening through the red-weekly-candle pullback, the breakout entry, sizing, and registration in `trader-memory-core`, to closing the trade. Read this before running `pead-screener` on its own.

> **Manual, not automated.** No skill in this pipeline places, cancels, or monitors an order, and there is no realtime monitor. Every order is placed by hand at the broker.

---

## The idea in one paragraph

Post-Earnings Announcement Drift is the tendency for stocks that gap up on a positive earnings surprise to keep drifting higher for weeks afterward — a well-documented market underreaction (Ball & Brown 1968; Bernard & Thomas 1989). This playbook trades it with a specific, defined-risk pattern on **weekly** candles, not the earnings-day gap itself: wait for an orderly red-weekly-candle pullback after the gap, then enter only when a green weekly candle closes back above that red candle's high. The hold is **2-6 weeks**, not the single-digit sessions of the [Stockbee Momentum Burst playbook]({{ '/en/playbooks/stockbee-momentum-burst/' | relative_url }}) — don't mix the two cohorts.

---

## When to run it

- After `earnings-trade-analyzer` has already screened recent earnings reactions (Mode B below), or directly against the FMP earnings calendar (Mode A).
- Weekly, to check for stage transitions (`MONITORING` → `SIGNAL_READY` → `BREAKOUT`) on names already on your watchlist.
- Within the 5-week (default, configurable) monitoring window from the earnings date — PEAD's effect is strongest in weeks 1-3 and fades by weeks 4-5.

## When not to run it

- **Not as an earnings-day chase.** This playbook never enters on the gap day itself — it requires a red weekly candle to form first, then a breakout above it. A "gap-and-go" that never pulls back is not an entry candidate here: with no red weekly candle, the screener holds it at `MONITORING` (watchlist) within the monitoring window (default 5 weeks) — after which it becomes `EXPIRED` — and it isn't actionable because there's no defined risk yet.
- **Not offline.** Both input modes require an FMP API key — see [Network requirement](#network-requirement-both-modes) below. There is no equivalent to Momentum Burst's `--prices-json` offline mode here.
- **Not mixed with Momentum Burst results.** A stock that also shows up in a Momentum Burst scan is a different, shorter-horizon thesis — see [Don't confuse this with Momentum Burst](#dont-confuse-this-with-momentum-burst).

---

## The pipeline at a glance

```
1  earnings-trade-analyzer                    →  earnings_trade_analyzer_report (5-factor scored earnings reactions; network required)
2  pead-screener (Mode B)                     →  pead_screener_report           (stage classification; network required)
3  manual gap-direction check                 →  gap_pct > 0 confirmed per candidate (the screener does not enforce this — see below)
4  technical-analyst                          →  chart validation on BREAKOUT candidates (image-based, no CLI)
5  position-sizer                             →  position size                  (shares; pure calculation)
6  trader-memory-core (ingest --source pead-screener) →  IDEA thesis            (dedicated fail-closed adapter)
7  trader-memory-core (link_report, via uv run)       →  linked evidence on the thesis (screener + chart-review reports)
8  trader-memory-core (store transition ENTRY_READY)  →  ready-to-order thesis
9  pre-trade-discipline-gate                          →  GO / REVIEW_REQUIRED / NO_GO
10 [GO only] manual order at the broker
11 trader-memory-core (store open-position)            →  ACTIVE thesis          (actual fill only)
```

Steps 3, 6, 8, and 9 are decision points that can stop a candidate from advancing. Step 5 is pure calculation.

### Network requirement (both modes)

Unlike Momentum Burst's Mode C, **there is no offline entry point for the screener stage of this pipeline.** `screen_pead.py` unconditionally constructs an `FMPClient` before doing anything else, in both Mode A and Mode B, and exits 1 immediately if `FMP_API_KEY` is missing. The subsequent `get_historical_prices()` call needed for every candidate's weekly-candle analysis is also a live network call in both modes. Only the `trader-memory-core` ingest/link/transition/sizing steps below (6-11) can be exercised fully offline against a hand-written fixture — this playbook's Phase 4 verification did exactly that; the screener commands themselves require a real `FMP_API_KEY` and were not run offline.

---

## The runbook

Set a working date once, before step 1, so downstream filenames, `link_report()` calls, and journal entries stay traceable to the same session:

```bash
export RUN_DATE=2026-07-15
```

### Step 1 — Screen recent earnings reactions

```bash
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --min-gap 3.0 --lookback-days 3 --top 20 \
  --output-dir reports/
```

`--min-gap 3.0` matters here: it is an `abs(gap_pct)` magnitude filter (`analyze_earnings_trades.py`), so **pass it explicitly** — in the Mode B / chained path this is the only gap-size floor there is, and even it does not check direction. Downstream, `screen_pead.py`'s own `abs(gap_pct) < args.min_gap` filter (line ~491) only runs in Mode A, and Mode B relies entirely on this upstream filter plus the manual check in step 3 below. No `stage` value — `MONITORING`, `SIGNAL_READY`, or `BREAKOUT` — proves `gap_pct > 0` on its own.

### Step 2 — Screen for the red-candle pullback pattern

```bash
# Mode A: FMP earnings calendar (requires FMP_API_KEY)
python3 skills/pead-screener/scripts/screen_pead.py \
  --lookback-days 14 --watch-weeks 5 --min-gap 3.0 \
  --output-dir reports/

# Mode B: chained from earnings-trade-analyzer output (recommended for a US-equity watchlist)
python3 skills/pead-screener/scripts/screen_pead.py \
  --candidates-json reports/earnings_trade_analyzer_YYYY-MM-DD_HHMMSS.json \
  --min-grade B --output-dir reports/
```

Prefer Mode B for a pre-market US-equity routine — Mode A pulls the global FMP earnings calendar and can spend the API budget on non-US symbols before reaching the intended watchlist.

Each result carries a `stage`:

| Stage | Meaning | Action |
|---|---|---|
| `MONITORING` | Post-earnings gap within the window; no red weekly candle yet | Watchlist; check weekly for a red candle |
| `SIGNAL_READY` | A red weekly candle has formed | Set an alert at the red candle's high; prepare the order |
| `BREAKOUT` | Current weekly candle is green and closes above the red candle's high | Actionable — proceed to chart validation and sizing |
| `EXPIRED` | Beyond the monitoring window (default 5 weeks) | Drop from the watchlist |

**Mid-week stages can be provisional.** `weekly_candle_calculator.py` classifies `SIGNAL_READY`/`BREAKOUT` off the most recent weekly candle (`weekly_candles[0]`) without checking whether that week is still open — partial weeks are marked elsewhere in the same module but that flag isn't consulted here. Run this mid-week and a `SIGNAL_READY` or `BREAKOUT` result can be based on an unclosed weekly bar. Wait for the Friday weekly close and do a manual chart check before treating either stage as final.

### Step 3 — Manually confirm the gap direction (the code does not)

**This step is required, and it is not automated anywhere in the pipeline.** `screen_pead.py`'s `abs(gap_pct) < args.min_gap` filter only runs in Mode A (`mode == "A"` — Mode B skips it entirely), and even where it runs it checks *magnitude*, never *sign*. The setup-quality scorer scores a negative `gap_pct` too: any gap below 3% — including a negative one — falls into the `else: score += 10` branch rather than being excluded. In practice this means a Mode B run can hand you a "PEAD candidate" that actually gapped **down** on earnings.

Before treating any `SIGNAL_READY` or `BREAKOUT` result as a PEAD candidate:

1. Confirm you passed `--min-gap 3.0` (or higher) to `analyze_earnings_trades.py` upstream, for magnitude.
2. **Manually check `gap_pct > 0` for every individual candidate** in the screener's own output — do not assume it from the upstream filter.
3. Treat this as a hard requirement, not a nice-to-have: the screener does not guarantee gap direction at any stage of either mode.

### Step 4 — Chart and liquidity validation on BREAKOUT candidates

Send `BREAKOUT` candidates to `technical-analyst` for a manual chart check, and independently verify all three liquidity gates before sizing — a candidate that passes only 1 or 2 of the 3 gates scores far lower and should not be treated as tradable:

| Gate | Threshold |
|---|---|
| ADV20 (20-day average dollar volume) | ≥ $25M |
| Average share volume | ≥ 1M shares |
| Stock price | ≥ $10 |

Also confirm: a clear red weekly candle (not a doji or inside bar), breakout-week volume above the 4-week average, and the earnings date is within 5 weeks.

### Step 5 — Size the position

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 118.40 --stop 109.75 --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/
```

Entry is at or slightly above the red candle's high; stop is below the red candle's low; the standard target is entry + 2R.

### Step 6 — Register the IDEA thesis (dedicated `pead-screener` adapter)

`trader-memory-core` has a dedicated adapter for this source — unlike Momentum Burst, you don't hand-build the ingest record, you feed it the screener's own `{"results": [...]}` JSON:

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source pead-screener --input reports/pead_screener_YYYY-MM-DD_HHMMSS.json \
  --state-dir state/theses/
```

It prints `Registered N thesis(es): th_...`. Export the ID for the candidate you're taking:

```bash
export THESIS_ID=th_peady_ern_20260715_xxxx  # paste the printed id
```

The adapter reads the screener's real field names — `stage` and `stop_price` — not `status`/`stop_loss`, which never appear in a real record. `thesis_type` is fixed to `earnings_drift` for every PEAD registration, but that value isn't unique to PEAD either: the `earnings-trade-analyzer` and `edge-candidate-agent` adapters also assign `earnings_drift` to their own theses. A PEAD thesis is identified by `origin.skill == pead-screener` (its dedicated adapter), not by `thesis_type` alone — `store list --type earnings_drift` will return earnings-trade-analyzer theses too, the same way `list --type growth_momentum` mixes in CANSLIM.

**The adapter is fail-closed on `BREAKOUT` candidates.** A `stage == "BREAKOUT"` record with a missing, non-numeric, `NaN`, `Infinity`, zero, or negative `stop_price` is refused outright — not registered with no stop, not registered with a garbage stop. Verified directly against a hand-written fixture for this playbook: an isolated `BREAKOUT` record with no `stop_price` field produced

```text
ERROR: Adapter error for pead-screener: PEAD record for 'PEADZ' is stage=BREAKOUT (actionable) but stop_price is
missing/non-numeric/non-finite/non-positive (None) — refusing to register an actionable thesis without a valid stop
No theses registered.
```

and exited **1**. This exact behavior is also covered by the existing regression test `test_ingest_pead_breakout_rejects_invalid_stop_fail_closed` in `skills/trader-memory-core/scripts/tests/test_thesis_ingest.py`, parametrized over seven cases (`None`/non-numeric/`NaN`/`+Infinity`/`−Infinity`/zero/negative). `MONITORING` and `SIGNAL_READY` candidates register fine with `exit.stop_loss` left unset — they have no real stop yet by design, and the adapter never fills that gap with an invalid placeholder.

### Step 7 — Link the upstream evidence

`link_report()` is a Python function, not a CLI subcommand — it imports `thesis_store` directly instead of going through `trader_memory_cli.py`, so it needs trader-memory-core's dependencies (`pyyaml`, `jsonschema`) available. Run it through `uv` (or any environment where they are installed). Link the earnings screen, the PEAD screen, and the chart-validation report so the thesis's evidence chain is auditable — the paths below are examples, matching each skill's own documented output-filename convention, not files this run is asserted to have actually produced:

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
    ("earnings-trade-analyzer", f"reports/earnings_trade_analyzer_{run_date}_090000.json"),
    ("pead-screener", f"reports/pead_screener_{run_date}_093000.json"),
    ("technical-analyst", f"reports/PEADY_technical_analysis_{run_date}.md"),
]:
    thesis_store.link_report(state_dir, thesis_id, skill, path, run_date)
    print(f"linked {skill} -> {path}")
PYEOF
```

### Step 8 — Transition to `ENTRY_READY`

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ transition "$THESIS_ID" ENTRY_READY \
  --reason "BREAKOUT confirmed, liquidity gates checked, sizing verified"
```

The thesis stays `IDEA` → `ENTRY_READY` — never `ACTIVE` — until an actual broker fill is recorded in step 11. Verified directly against the fixture above: after `transition ENTRY_READY`, `store list --ticker PEADY` reports `"status": "ENTRY_READY"`.

### Step 9 — Run the pre-trade discipline gate

```bash
python3 skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py \
  --answers-file state/manual-entry-checklist.json \
  --state-dir state/theses/ \
  --market-regime-decision reports/exposure_decision_latest.json \
  --circuit-breaker-decision reports/circuit_breaker_decision_latest.json \
  --output-dir reports/pre-trade-discipline
```

Only place the order on a `GO` decision.

### Step 10 — Place the order manually

No skill in this pipeline touches a broker. Enter the order yourself, sized as computed in step 5.

### Step 11 — Record the actual fill

```bash
export FILL_DATE=2026-07-16  # the real broker fill date

python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ open-position "$THESIS_ID" \
  --actual-price 118.55 --actual-date "$FILL_DATE" --shares 115
```

Only now does the thesis become `ACTIVE`. A planned entry is never treated as a fill.

---

## Holding rules and exits

Stop is the red weekly candle's low; target is entry + 2R. The core hold is **2-6 weeks**:

- After 1R of profit, move the stop to breakeven.
- After 1.5R, trail the stop.
- **2R is a decision point, not a forced full exit** — take partial profit, raise the stop, or let the position run, depending on how the weekly trend looks.
- If the position hasn't reached the target within roughly 4 weeks of entry, treat that as a scratch or small-loss exit rather than holding indefinitely.
- The PEAD effect meaningfully decays by 6-8 weeks post-earnings — don't hold on the original PEAD thesis past that window.
- Exit on a weekly-close stop failure, a thesis invalidation, or time decay — not on a fixed day count alone; check the weekly trend and stop level, not a calendar.

## What not to do

- Don't describe this as chasing the earnings-day gap — it is explicitly not that. The entry is the breakout above a red weekly candle, weeks after the gap.
- Don't call a gap-and-go with no red candle a PEAD entry — there is no defined risk without the red candle's low as a stop.
- Don't mix PEAD results into Momentum Burst statistics, or vice versa — they are separate cohorts with separate `thesis_type` values.
- Don't hold mechanically on a fixed day count — check the weekly trend and stop level, not a calendar.
- Don't promise a return. PEAD has historically shown a 55-65% win rate with winners 1.5-2.5x larger than losers in the studies this method is based on — that is not a guarantee for any specific trade.

## Don't confuse this with Momentum Burst

| | PEAD | Momentum Burst |
|---|---|---|
| Catalyst | An actual earnings gap-up, confirmed by hand | Price/volume breakout — no earnings requirement |
| Entry pattern | Green weekly close above a red weekly candle's high | 4% breakout / dollar breakout / range expansion off a tight base |
| Hold | 2-6 weeks | 2-5 sessions |
| `thesis_type` | `earnings_drift` (shared type; dedicated `pead-screener` adapter) | `growth_momentum` (shared with CANSLIM) |
| Ingest path | `--source pead-screener`, dedicated fail-closed adapter | `--source manual`, no dedicated adapter |
| Offline verification | Adapter/sizing steps only — the screener itself requires `FMP_API_KEY` | Fully offline, including the screener (Mode C) |

Stockbee's Episodic Pivot classifier (`analyze_ep.py`) can flag a `pead_handoff` candidate on an earnings/guidance catalyst — but that flag alone does not make it a PEAD entry. It is **flagged, not yet qualified**: the candidate still has to independently form a red weekly candle and then break above it under this playbook's own rules before it's actionable here. See the [Stockbee Momentum Burst playbook]({{ '/en/playbooks/stockbee-momentum-burst/' | relative_url }}) for how the same classifier's `momentum_handoff` flag feeds that playbook instead.

---

## Related

- No *dedicated* `workflows/*.yaml` manifest exists for this exact playbook. `pead-screener` already appears in the broader [`stockbee-ep-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/stockbee-ep-daily.yaml) workflow alongside `stockbee-momentum-burst-screener`, but there is no standalone PEAD flow — Trading Skills Navigator routing to a dedicated flow is out of scope until one is added.
- Skill reference: [PEAD Screener]({{ '/en/skills/pead-screener/' | relative_url }})
- The skills used: `earnings-trade-analyzer`, `pead-screener`, `technical-analyst`, `position-sizer`, `trader-memory-core`, `pre-trade-discipline-gate`
- See also: [Stockbee Momentum Burst Playbook]({{ '/en/playbooks/stockbee-momentum-burst/' | relative_url }})
