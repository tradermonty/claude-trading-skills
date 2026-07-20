---
name: contrarian-setup-gate
description: Synthesize the three Jason Shapiro contrarian-pipeline verdicts (COT crowding, news-reaction failure, weekly price-action confirmation) into one actionable setup_status via a fail-closed precedence state machine. Pure, offline synthesis -- no network, no API keys, no computation beyond validation and precedence.
---

# Contrarian Setup Gate

## Overview

Synthesize the outputs of Jason Shapiro's 3-step contrarian process into one actionable state. cot-contrarian-detector (step 1) flags crowded positioning, news-reaction-failure-analyzer (step 2) tests whether the market failed to react to news favorable to the crowd, and technical-analyst's contrarian-confirmation mode (step 3) confirms weekly price-action evidence of a reversal. This gate reads those three report JSONs and applies an explicit, exhaustively-tested precedence rule set to produce one `setup_status`, with a fail-closed reason attached to every input that could not be confirmed.

The gate does no fetching, no API calls, and no computation beyond validating and combining the three inputs it is given. It is the pipeline's synthesis center, not a data source.

## When to Use

- After running cot-contrarian-detector (always required -- this is the pipeline's entry point)
- Mid-pipeline, with only the detector report, to see the CROWDED state and what steps remain
- After running news-reaction-failure-analyzer, to see whether the setup advances to WATCHING_PRICE or is REJECTED
- After running technical-analyst's contrarian-confirmation mode, to see whether the setup reaches READY_FOR_PLAN
- Before handing a symbol's direction and stop level to a position-sizing skill

## Prerequisites

- Python 3.9+
- No API keys -- this skill is fully offline
- A cot-contrarian-detector JSON report for the symbol under evaluation (required)
- Optionally, a news-reaction-failure-analyzer JSON report for the same symbol (step 2)
- Optionally, a technical-analyst contrarian-confirmation JSON report for the same symbol (step 3)

## Workflow

### Step 1: Run the Gate

```bash
python3 skills/contrarian-setup-gate/scripts/run_contrarian_setup_gate.py \
  --symbol B6 \
  --detector-json reports/cot_crowding_2026-07-12.json \
  --news-json reports/nrf_B6_2026-07-12.json \
  --price-action-json reports/ta_confirmation_B6_2026-07-12.json \
  --as-of 2026-07-15 \
  --output-dir reports/
```

`--symbol` and `--detector-json` are required; `--news-json` and `--price-action-json` are optional -- omit either to see the state at that pipeline stage. `--as-of` is required (no implicit "today"): staleness is always evaluated against an explicit reference date so reruns are deterministic.

Exit behavior is intentionally asymmetric: a missing or malformed `--as-of` (or any other CLI usage error) is an operator config mistake, so the CLI exits `2` with usage text and writes no report. A problem with one of the three untrusted report files -- unreadable, malformed, stale, inconsistent -- is always handled fail-closed instead: the CLI exits `0` and writes a report naming the reason, exactly like every other skill in this pipeline.

### Step 2: Read the Setup Status

| Status | Meaning | Next Step |
|---|---|---|
| `READY_FOR_PLAN` | All three steps confirmed; direction, entry_trigger, and invalidation_level are populated | Hand `direction` and `invalidation_level` to a position-sizing skill |
| `WATCHING_PRICE` | Crowding + news confirmed; price action still pending | Run technical-analyst's contrarian-confirmation mode |
| `CROWDED` | Crowding confirmed; news and/or price still pending | Run news-reaction-failure-analyzer |
| `REJECTED` | Crowding is NOT_CONFIRMED (classification NEUTRAL), or news/price came back NOT_CONFIRMED | Stop -- do not run further steps for this symbol/direction |
| `INSUFFICIENT_EVIDENCE` | A required input is missing, unreadable, stale, inconsistent, or could not itself reach a verdict | Stop -- fix or regenerate the named input before rerunning |

`missing_confirmations` lists every step still blocking, with its `state` and `reason`. `warnings` never change the status -- they flag audit-worthy conditions such as a MEDIUM-confidence confirming signal or a near-stale input.

### Step 3: Act on READY_FOR_PLAN Only

At `READY_FOR_PLAN`, `direction` (SHORT/LONG, the fade side of the crowd), `entry_trigger` (a factual echo of the confirming weekly signal), and `invalidation_level` (the stop reference from the price-action report) are populated. `gate_confidence` is the weaker of the news and price-action confidences (HIGH/MEDIUM/LOW -- `LOW` is a token both upstream skills document as reserved but never actually emit; the gate accepts it and ranks it weakest rather than rejecting it as unknown). Position sizing is the next pipeline stage (not yet built as of this skill's release -- see the roadmap in the repository's workflow docs); this gate never places or recommends an order.

## Precedence (Summary)

Each step is evaluated in strict pipeline order -- crowding, then news, then price-action -- and each step fully settles before the next step's file is even consulted. An earlier step's definitive verdict is never softened by a later step's problem.

1. Crowding is evaluated first and exclusively: INVALID/INSUFFICIENT crowding is always `INSUFFICIENT_EVIDENCE`; a NOT_CONFIRMED (NEUTRAL) classification is always `REJECTED`, regardless of any downstream file's state or corruption.
2. With crowding CONFIRMED, news is evaluated next, on its own: INVALID (unreadable, malformed, stale, symbol mismatch, direction mismatch, unsupported schema) forces `INSUFFICIENT_EVIDENCE`; NOT_CONFIRMED forces `REJECTED`; INSUFFICIENT forces `INSUFFICIENT_EVIDENCE` -- in every one of these cases, price-action is never even inspected for the decision.
3. Once news is CONFIRMED (or PENDING, for out-of-order use), price-action is evaluated last, with the same four-way settlement. Running price-action before news (out-of-order pipeline use) caps the status at `CROWDED` with a warning -- a NOT_CONFIRMED price-action verdict still REJECTs even out of order, since price-action is still fully evaluated in that branch.
4. Crowding confirmed, both downstream steps pending -> `CROWDED`.
5. Crowding + news confirmed, price-action pending -> `WATCHING_PRICE`.
6. All three confirmed -> `READY_FOR_PLAN`.

See `references/gate-decision-table.md` for the full decision table (every reachable {crowding} x {news} x {price-action} state combination), the reason-token glossary, and worked examples.

## Output Contract

The script writes `contrarian_setup_gate_<SYMBOL>_<as-of>.json` and `.md` to `--output-dir`:

```yaml
symbol: B6
setup_status: READY_FOR_PLAN | WATCHING_PRICE | CROWDED | REJECTED | INSUFFICIENT_EVIDENCE
direction: SHORT | LONG | null
gate_confidence: HIGH | MEDIUM | LOW | null
entry_trigger: string | null
invalidation_level: number | null
missing_confirmations: [{step, state, reason}, ...]
warnings: [string, ...]
inputs:
  crowding: {state, classification, data_date, age_days, report_path}
  news_failure: {state, verdict, confidence, verdict_reason, as_of, age_days, report_path}
  price_action: {state, verdict, confidence, verdict_reason, stop_reference, as_of, age_days, report_path}
run_context: {symbol, as_of, max_detector_age_days, max_report_age_days, schema_version, skill}
```

Every input's `state` is one of `CONFIRMED`, `NOT_CONFIRMED`, `INSUFFICIENT`, `PENDING` (report not provided), or `INVALID` (a report was provided but is unusable -- unreadable, malformed, stale, or inconsistent with the other inputs; always carries a named reason).

## Guardrails

1. **Never places or recommends orders.** `READY_FOR_PLAN` is the furthest state this skill reaches. Order entry and position sizing are separate, downstream decisions.
2. **INSUFFICIENT_EVIDENCE and REJECTED never advance.** No warning, confidence, or partial input ever pushes the status past what the precedence rules allow.
3. **Fail closed on every input, always.** An unreadable, malformed, stale, symbol-mismatched, or unknown-enum report is never treated as a pass -- it is named and blocks or downgrades the status. This includes the price-action report's `verdict_reason` (allowlisted against technical-analyst's actual confirming-signal vocabulary, not merely type-checked) and its `stop_reference` (must be a finite, positive number -- never non-finite, zero, negative, or a boolean). Before any of the three report files reaches this validation, the CLI also rejects a file outright (reason `<input>_non_finite`) if it contains a non-finite number (`Infinity`/`-Infinity`/`NaN`, including an ordinary-looking number like `1e309` that overflows on parse) ANYWHERE in it, not just in a field the gate reads -- this is what keeps every report a valid, complete JSON file even under adversarial input.
4. **`READY_FOR_PLAN` always carries a usable plan.** `entry_trigger` is guaranteed non-empty and `invalidation_level` is guaranteed a finite positive number whenever the status is `READY_FOR_PLAN` -- enforced both by input validation and by a defensive invariant check.
5. **Not investment advice.** `entry_trigger` and `invalidation_level` are factual echoes of the upstream price-action report, not recommendations.

## Resources

- `scripts/run_contrarian_setup_gate.py` -- CLI: hardened JSON loading (unreadable / parse_error incl. RecursionError / non_finite via an iterative whole-file scan), report generation
- `scripts/gate_logic.py` -- Pure synthesis core: normalization (incl. malformed-shape detection), consistency checks, the precedence state machine
- `references/gate-decision-table.md` -- Full decision table, reason-token glossary, worked examples (including the real B6 REJECTED case)
