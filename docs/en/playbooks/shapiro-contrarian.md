---
layout: default
title: Shapiro COT Contrarian Playbook
parent: English
nav_order: 20
lang_peer: /ja/playbooks/shapiro-contrarian/
permalink: /en/playbooks/shapiro-contrarian/
---

# Shapiro COT Contrarian — Weekly Playbook

A usage guide for the whole `shapiro-contrarian` workflow, not for the individual skills. It walks the pipeline end to end: when to run it, the six steps in order, how the gate decides, how the position is sized, and how the fade is registered in your trade memory. Read this before you run any of the six skills in isolation.

> **This is Experiment Kit v1.** The goal is to *start* running a Shapiro-style contrarian experiment as a disciplined weekly routine — not to prove it is profitable. Orders and monitoring are manual. There is no auto-execution, and position monitoring is a separate skill that ships later.

---

## The idea in one paragraph

Jason Shapiro's contrarian method fades **crowded speculative positioning** in futures — but crowding alone is never a trade. The edge appears only when the crowd is *also* wrong: price fails to follow news that should help the crowded side, and the weekly chart is already turning against them. This pipeline enforces that discipline. It screens the COT report for crowding, then requires two independent confirmations — a news-reaction failure and a weekly price-action reversal — before a fail-closed gate lets you size anything. You fade the crowd only where all three line up.

---

## When to run it

- **Weekly**, after the CFTC Commitment of Traders report publishes (Friday ~3:30pm ET, carrying Tuesday's positioning).
- Treat the crowding read as **end-of-Tuesday**, not live — COT data is three days lagged.

## When not to run it

- **Not intraday, not more than weekly.** The edge is positioning-driven; COT updates once a week.
- **Never on a crowding extreme alone.** The gate must reach `READY_FOR_PLAN` — crowding, news failure, and price action all confirmed — before any sizing.
- **Equities are out of scope.** This covers CFTC futures markets only.

---

## The pipeline at a glance

```
1  cot-contrarian-detector        →  cot_crowding_report            (screen 3-yr COT-index extremes)
2  news-reaction-failure-analyzer →  news_failure_verdict           (price ignores crowd-favorable news)
3  technical-analyst              →  price_action_confirmation_report (weekly reversal against the crowd)
4  contrarian-setup-gate          →  contrarian_setup_gate_report   (READY_FOR_PLAN only; fail-closed)
5  futures-position-sizer         →  futures_position_size          (contracts; pure calculation)
6  trader-memory-core             →  contrarian_thesis_entry        (register the fade thesis)
```

Steps 1–4 and 6 are **decision gates**: each one can stop a candidate from advancing. Step 5 is pure calculation. A market that fails any gate simply drops out — that is the point.

---

## The weekly runbook

Set a working date **once**, in a shell variable, before step 1. Every step below reads or writes a filename keyed off it, so the evidence chain stays connected end to end — this is what keeps steps 2–6 from silently reading yesterday's (or nobody's) report.

```bash
export RUN_DATE=2026-07-15
```

The examples below fade a crowded market called `B6`.

### Step 1 — Screen COT crowding

```bash
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py \
  --core --as-of "$RUN_DATE" --output-dir reports/
```

Produces `reports/cot_crowding_$RUN_DATE.json` (`cot_crowding_report`). Carry forward only the markets at a 3-year COT-index extreme (`CROWDED_LONG` / `CROWDED_SHORT`). Crowding is a **precondition, never a signal** — do not act on this alone.

### Step 2 — Check for a news-reaction failure

```bash
python3 skills/news-reaction-failure-analyzer/scripts/analyze_news_reaction.py \
  --symbol B6 --detector-json "reports/cot_crowding_$RUN_DATE.json" \
  --events-json "reports/nrf_events_B6_$RUN_DATE.json" \
  --as-of "$RUN_DATE" --output-dir reports/
```

Produces `reports/nrf_B6_$RUN_DATE.json` (`news_failure_verdict`). The events file must be curated from **primary / wire sources with real URLs** — never fabricated. Keep only `CONFIRMED` markets; `NOT_CONFIRMED` and `INSUFFICIENT_EVIDENCE` stop here.

### Step 3 — Confirm a weekly price-action reversal

```bash
python3 skills/technical-analyst/scripts/check_weekly_price_action.py \
  --symbol B6 --detector-json "reports/cot_crowding_$RUN_DATE.json" \
  --as-of "$RUN_DATE" --output-dir reports/
```

Produces `reports/ta_confirmation_B6_$RUN_DATE.json` (`price_action_confirmation_report`). `--detector-json` is what supplies the crowd's direction from step 1 — without it (or an explicit `--direction`) the script has nothing to confirm a reversal *against* and exits with `no_direction_provided` instead of a verdict. Looking for a reversal against the crowd on the weekly chart — a key reversal, failed breakout, or failed extreme — with a **defined swing stop**. Reject `NOT_CONFIRMED` / `INSUFFICIENT_DATA`.

### Step 4 — Synthesize the gate

```bash
python3 skills/contrarian-setup-gate/scripts/run_contrarian_setup_gate.py \
  --symbol B6 \
  --detector-json "reports/cot_crowding_$RUN_DATE.json" \
  --news-json "reports/nrf_B6_$RUN_DATE.json" \
  --price-action-json "reports/ta_confirmation_B6_$RUN_DATE.json" \
  --as-of "$RUN_DATE" --output-dir reports/
```

Produces `reports/contrarian_setup_gate_B6_$RUN_DATE.json` (`contrarian_setup_gate_report`). `--as-of` is **required** — the gate uses it to check every upstream report for staleness, so it exits 2 without it. The gate is **fail-closed** and evaluates the steps in order. Only a `READY_FOR_PLAN` status proceeds to sizing. `CROWDED`, `WATCHING_PRICE`, `REJECTED`, and `INSUFFICIENT_EVIDENCE` all stop here. The gate hands three things forward — `symbol`, `direction`, and `invalidation_level` — and nothing else.

### Step 5 — Size the futures position

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --gate-json "reports/contrarian_setup_gate_B6_$RUN_DATE.json" \
  --entry 1.3820 --account-size 200000 --risk-pct 1.0 \
  --as-of "$RUN_DATE" --output-dir reports/ --format both
```

Produces `reports/futures_position_size_B6_$RUN_DATE.json` (`futures_position_size`). Direction and stop come from the gate. **`--entry`, `--account-size`, and `--risk-pct` are always operator-supplied** — neither the gate nor the sizer derives them, so gather them before you run this. Only a `SIZED` result advances; a `NO_TRADE` result stops here. Verify the contract count and per-contract risk, and confirm total portfolio heat is within budget, before any order.

### Step 6 — Register the contrarian thesis

Step 6 is where the plan becomes an auditable record in your trade memory. Run the operations **in this exact order** — `attach-futures-position` attaches to an *existing* thesis (it never creates one), and `open-position` requires `ENTRY_READY` (it refuses `IDEA`).

1. **Create the IDEA thesis** (manual ingest or `register()`). `idea.json` needs only `ticker` / `thesis_type` / `thesis_statement`; anything else — like `entry_price` below — is kept for the record in `origin.raw_provenance`, not treated as an authoritative price:

   ```json
   {
     "ticker": "B6",
     "thesis_type": "mean_reversion",
     "thesis_statement": "B6 crowded-long COT extreme with a confirmed news-reaction failure and weekly reversal — fade the crowd short.",
     "entry_price": 1.3820
   }
   ```

   ```bash
   python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
     --source manual --input idea.json --state-dir state/theses/
   ```

   It prints `Registered 1 thesis(es): th_...`. Export that ID — the
   remaining steps need it:

   ```bash
   export THESIS_ID=th_b6_mean_reversion_20260715_xxxx  # paste the printed id
   ```

2. **Attach the SIZED report** (works while the thesis is still `IDEA`) — this persists contracts, direction, multiplier, USD currency, and risk onto the thesis position:

   ```bash
   python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
     --state-dir state/theses/ attach-futures-position "$THESIS_ID" \
     --report "reports/futures_position_size_B6_$RUN_DATE.json"
   ```

3. **Link the upstream evidence.** `link_report()` is a Python function, not a CLI subcommand. It imports `thesis_store` directly instead of going through `trader_memory_cli.py`, so it needs trader-memory-core's dependencies (`pyyaml`, `jsonschema`) available — run it through `uv` (or any environment where they are installed). Link the four upstream reports so the fade's full evidence chain is auditable:

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
       ("cot-contrarian-detector", f"reports/cot_crowding_{run_date}.json"),
       ("news-reaction-failure-analyzer", f"reports/nrf_B6_{run_date}.json"),
       ("technical-analyst", f"reports/ta_confirmation_B6_{run_date}.json"),
       ("contrarian-setup-gate", f"reports/contrarian_setup_gate_B6_{run_date}.json"),
   ]:
       thesis_store.link_report(state_dir, thesis_id, skill, path, run_date)
       print(f"linked {skill} -> {path}")
   PYEOF
   ```

4. **Transition to `ENTRY_READY`** once you've confirmed the sizing and are ready to place the order:

   ```bash
   python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
     --state-dir state/theses/ transition "$THESIS_ID" ENTRY_READY \
     --reason "READY_FOR_PLAN confirmed and sizing verified"
   ```

5. **Transition to `ACTIVE` only after a real broker fill**, with the actual fill price and date. Use a separate `FILL_DATE`: `entry.actual_date` drives the holding period and postmortem, so it must be the real fill date, not the analysis date — the two differ whenever the order fills on a later day. `--contracts` / `--multiplier` / `--direction` can be omitted — they're already on the thesis from step 2:

   ```bash
   export FILL_DATE=2026-07-16  # the real broker fill date; equals $RUN_DATE if filled same day

   python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
     --state-dir state/theses/ open-position "$THESIS_ID" \
     --actual-price 1.3835 --actual-date "$FILL_DATE"
   ```

Produces `contrarian_thesis_entry`. It flows downstream to `trade-memory-loop` and `monthly-performance-review`.

---

## Discipline and guardrails

- **Crowding is a precondition, never a trade signal.** Require the news-failure *and* price-action confirmations before sizing.
- **The gate is the safety.** Nothing gets sized unless the gate independently reaches `READY_FOR_PLAN`.
- **Planned entry is not an actual fill.** `attach-futures-position` does not populate `entry.actual_price`. On manual ingest the planned entry is kept in `origin.raw_provenance.entry_price`; never write it to `entry.actual_price` before the order fills.
- **No auto-execution.** Every order is placed manually at the broker.
- **Monitoring is manual for now.** COT normalization, stop, and thesis invalidation are watched by hand until `contrarian-position-monitor` (tracked in [#243](https://github.com/tradermonty/claude-trading-skills/issues/243)) ships.
- **USD-only trade-memory handoff.** The sizer itself *can* size a non-USD contract — pass `--fx-rate` (contract-currency-to-USD) and it converts. It's the `attach-futures-position` handoff into trade memory that is USD-only today: a non-USD SIZED report is refused there rather than silently mis-recorded.
- **Margin is not computed.** Futures margin is broker- and time-dependent — verify initial and maintenance margin with the broker before trading.

---

## What "done" means here

The experiment kit is **6 of 6 skills complete** and merged: you can start running the Shapiro-style contrarian experiment as a disciplined weekly routine today. The full lifecycle including automated position monitoring is **6 of 7** — the monitor is deferred by design until there is live or shadow experience to design it against.

This kit lets you *start the experiment*. It does not claim the strategy is profitable — that is what the weekly routine, the trade-memory record, and the monthly review are for.

---

## Related

- Workflow manifest: [`workflows/shapiro-contrarian.yaml`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/shapiro-contrarian.yaml) (the source of truth)
- Auto-generated reference: [Workflows]({{ site.baseurl }}/en/workflows/#shapiro-contrarian)
- The six skills: `cot-contrarian-detector`, `news-reaction-failure-analyzer`, `technical-analyst`, `contrarian-setup-gate`, `futures-position-sizer`, `trader-memory-core`
