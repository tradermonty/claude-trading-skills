---
name: pre-trade-discipline-gate
description: Evaluate a local pre-trade checklist before manual order entry, blocking planless, oversized, revenge-risk, market-regime-blocked, or circuit-breaker-blocked entries while journaling the decision for trader-memory-core review.
---

# Pre-Trade Discipline Gate

## Overview

Evaluate whether a planned manual order should proceed before it is placed at the broker. This skill reads a local checklist plus optional market-regime, circuit-breaker, and trader-memory-core artifacts. It produces a `pre_trade_discipline_decision` artifact and can link that artifact back to the related thesis without changing the thesis review schedule.

The gate is intentionally offline. It does not place orders, cancel orders, call a broker API, or fetch market data.

## When to Use

- Immediately before placing any manual entry order
- When a candidate has passed chart validation and position sizing
- After a recent loss, to avoid revenge trades during the cooldown window
- When the workflow has an upstream `exposure_decision` and `circuit_breaker_decision`
- When you want checklist adherence to be visible in later trader-memory-core reviews

## Prerequisites

- Python 3.9+
- A local JSON or YAML answers file with candidate-level checklist answers
- Optional trader-memory-core thesis state under `state/theses/`
- Optional `exposure_decision` JSON from market-regime-daily / exposure-coach
- Optional `circuit_breaker_decision` JSON from drawdown-circuit-breaker

## Workflow

### Step 1: Prepare the Checklist

Create a JSON or YAML file with candidate answers. Only actionable manual-order intents are gated. Watchlist and ignore intents are journaled as `NO_ACTIONABLE_ORDERS`.

```json
{
  "candidates": [
    {
      "symbol": "AAPL",
      "thesis_id": "th_aapl_gm_20260703_0001",
      "order_intent": "ENTRY_READY",
      "entry_in_written_plan": true,
      "stop_predefined": true,
      "size_within_plan": true,
      "planned_risk_dollars": 500,
      "actual_risk_dollars": 500,
      "notes": "Entry matches the journaled breakout plan."
    }
  ]
}
```

Actionable intents are `ENTRY_READY`, `ACTIONABLE`, `ACTIONABLE_DAY1`, and `MANUAL_ORDER`. Non-actionable intents such as `WATCHLIST`, `DELAYED_EP_WATCH`, `PEAD_HANDOFF`, `IGNORE`, and `REJECTED` are recorded but do not create an order permission.

Provide both `planned_risk_dollars` and `actual_risk_dollars` for every actionable candidate. Use a finite, non-negative number or numeric string; zero is valid. Treat missing values, booleans, non-numeric strings, `NaN`, infinities, and negative values as `REVIEW_REQUIRED` inputs and review them before placing an order.

### Step 2: Run the Gate

```bash
python3 skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py \
  --answers-file state/manual-entry-checklist.json \
  --state-dir state/theses \
  --market-regime-decision reports/exposure_decision_latest.json \
  --circuit-breaker-decision reports/circuit_breaker_decision_latest.json \
  --output-dir reports/pre-trade-discipline \
  --journal-dir state/journal/pre-trade-discipline
```

Set `--as-of` for deterministic testing or backfills:

```bash
python3 skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py \
  --answers-file state/manual-entry-checklist.json \
  --as-of 2026-07-03T12:00:00-04:00
```

### Step 3: Interpret the Decision

| Decision | Meaning |
|---|---|
| `GO` | All actionable manual-order candidates passed the checklist and upstream gates |
| `REVIEW_REQUIRED` | Inputs are missing, unknown, or journaling failed; an approved-rule acknowledgement is missing or records an exception; or the approved-rule ledger could not be read. Do not place orders until reviewed |
| `NO_GO` | At least one actionable candidate violated a discipline rule |
| `NO_ACTIONABLE_ORDERS` | The file contains no actionable manual orders; nothing should be placed |

By default the CLI exits `0` for every valid decision and exits `1` only for input or runtime errors. Use `--fail-on-non-go` when a shell pipeline should return `2` for any non-`GO` decision.

## Approved Operating Rules (optional)

Rules a human approved in the monthly review can be carried into the pre-trade check through a local ledger. The gate never evaluates a rule against a trade; it lists each applicable rule and requires a recorded acknowledgement. The acknowledgement is recorded, not verified.

### Ledger lifecycle

The ledger is a local JSON file, `state/rules/approved_rules.json` by default. It is a single-user file: writes are atomic, but concurrent writers are not supported. Manage it with `scripts/manage_approved_rules.py`:

```bash
# Activate approved rules from a monthly rule-changes artifact (both artifact shapes are accepted)
python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py activate \
  --rule-changes reports/06_rule_changes_for_next_month.yaml \
  --effective-date 2026-06-01 --review-after 2026-06-30 --confirm-activation

# Also activate the postmortem-driven trade_rule_changes (opt-in; needed when the coach step was skipped)
python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py activate \
  --rule-changes reports/06_rule_changes_for_next_month.yaml \
  --effective-date 2026-06-01 --review-after 2026-06-30 \
  --include-trade-rule-changes --source-review-id monthly_2026-05 --confirm-activation

python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py list --as-of 2026-06-15
python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py extend \
  --rule-id rule_3f9a1c2b7d10 --review-after 2026-08-31 --reason "keep another month"
python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py retire \
  --rule-id rule_3f9a1c2b7d10 --reason "no longer relevant"
python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py restore \
  --rule-id rule_3f9a1c2b7d10 --reason "retired by mistake"
python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py supersede \
  --rule-id rule_3f9a1c2b7d10 --text "Wait for the confirmed pivot close" \
  --effective-date 2026-06-15 --review-after 2026-07-31 --reason "sharper wording" --confirm
```

- `activate` reads the replay-shape artifact (`schema_version: 1` with `coach_rule_decision`, whose `accepted_rules` count only for `accept_rules` and `modify_rules`) or the sample-shape artifact (`schema_version: "1.0"` with `rules[]`, where only `ACCEPTED` entries count; it also needs `--source-review-id`). Deferred, journal-only, and rejected items are never activated. Without `--confirm-activation` it prints the plan and writes nothing, and any error leaves the ledger untouched.
- A rule's `rule_id` comes from its normalized text, so approving the same rule in a later month renews it instead of duplicating it. Re-running a file from the same review is a no-op.
- Status is `active`, `superseded`, or `retired`. History is append-only and nothing is deleted. `activated`, `renewed`, and `reactivated` events record the source review id and the source artifact hash (`null` for a manual `supersede`); `retired`, `extended`, `restored`, and `superseded` events record a reason only.
- A superseded rule and its successor chain are never both active. Reactivating or restoring a superseded rule is refused while any rule of its chain is active. A revived rule remembers its former chain in the history event, so restoring or reactivating one of those former successors is refused while the revived rule is active; retire the revived rule first. `activate` checks the whole batch, so the result does not depend on candidate order, and refuses the entire activation otherwise.
- Dates must be exact `YYYY-MM-DD` values (unquoted YAML dates are accepted); padded values are rejected. Rows in a sample-shape file whose status is not exactly `ACCEPTED` are skipped and listed in the output. Re-running a file from the same review with different dates changes nothing and prints a warning pointing to `extend`.
- Writes keep the file's permission bits and go through a symlinked ledger path to its target.
- `list` and the gate use a computed state. `effective` and `review_due` rules are applied; `not_yet_effective`, `expired`, `superseded`, and `retired` rules are not. `review_after` is inclusive, and a `review_due` rule still applies with a warning so the gate has no gap before the next monthly review. `expires_on` is an optional hard stop. Dates are America/New_York calendar dates.
- State is computed from the current stored status. A past `--as-of` does not reconstruct an earlier ledger.

### Gate integration

Pass `--approved-rules-ledger PATH` to the gate. For each actionable candidate, add one acknowledgement per applied rule:

```json
"approved_rule_checks": [{"rule_id": "rule_3f9a1c2b7d10", "status": "followed", "note": ""}]
```

- `followed` and `not_applicable` pass. `exception` needs a non-empty `note` and still yields `REVIEW_REQUIRED`, because the gate cannot approve an exception: either do not place the order, or change the ledger (`retire`, `supersede`) and rerun.
- A missing acknowledgement, an `exception` without a note, an unknown status, or a malformed `approved_rule_checks` value yields `REVIEW_REQUIRED`. `NO_GO` still outranks it.
- If the ledger cannot be read, actionable candidates become `REVIEW_REQUIRED` and the report and journal are still written.
- The result gains an `approved_rules` block and each candidate an `approved_rule_checks` list. Without the flag, output is unchanged.

## Rules

The gate blocks an actionable candidate when:

- The entry is not confirmed in the written plan
- The stop is not predefined
- The size is not confirmed within plan
- Either risk-dollar field is missing or is not a finite, non-negative number (`REVIEW_REQUIRED`)
- `actual_risk_dollars` exceeds `planned_risk_dollars`
- trader-memory-core has a losing exit or partial loss inside the revenge window
- exposure-coach recommendation is `REDUCE_ONLY` or `CASH_PRIORITY`
- drawdown-circuit-breaker recommendation is `COOLDOWN`, `HALTED`, or `TRADING_HALTED`

Missing or unreadable market-regime or circuit-breaker artifacts produce `REVIEW_REQUIRED` for actionable orders. If no actionable order exists, the result remains `NO_ACTIONABLE_ORDERS`.

## Outputs

The script writes:

- `pre_trade_discipline_decision_YYYY-MM-DD_HHMMSS.json`
- A matching markdown report unless `--json-only` is set
- A JSONL journal row under `state/journal/pre-trade-discipline/` when `--journal-dir` is provided

Each candidate result includes a `checklist_answers` object with the written-plan, stop, size, risk-dollar, and notes answers used for the decision, so later reviews can audit what was answered at order time. Invalid risk-dollar values are stored as JSON `null`. Valid JSON decimals that cannot round-trip through a binary float are retained as numeric strings so underflow or precision loss cannot change the gate decision.

If a candidate includes `thesis_id` and `--state-dir` is provided, the JSON report is linked into the thesis `linked_reports` list using trader-memory-core `link_report`. The skill does not call `mark_reviewed` and does not change monitoring review dates.

## Resources

- `scripts/check_pre_trade_discipline.py` - Main CLI and rule engine
- `scripts/manage_approved_rules.py` - Approved-rule ledger CLI (activate, list, supersede, retire, extend, restore)
- `scripts/approved_rules.py` - Ledger library (standard library only)
- `references/discipline_gate_framework.md` - Rule definitions and integration notes
- `skills/trader-memory-core/schemas/thesis.schema.json` - Thesis state schema

## Key Principles

1. **Manual execution only** - The output is a pre-broker checklist gate, not an order router.
2. **Written plan first** - No written entry plan, stop, or size confirmation means no manual entry.
3. **Producer-compatible state reading** - Revenge-risk detection follows trader-memory-core timestamp and outcome behavior.
4. **Journal without review side effects** - The gate links reports to theses without advancing review schedules.
