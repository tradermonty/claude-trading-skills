# Pre-Trade Discipline Gate Framework

## Purpose

The pre-trade discipline gate sits after thesis registration and before any manual broker order. It is designed to stop planless, oversized, revenge-risk, or upstream-blocked entries while leaving watchlist decisions recordable.

The skill is advisory and journal-focused. It does not automate execution.

## Decision Model

Overall decisions are ranked:

1. `GO`
2. `NO_ACTIONABLE_ORDERS`
3. `REVIEW_REQUIRED`
4. `NO_GO`

`NO_GO` outranks `REVIEW_REQUIRED` so explicit rule violations are visible even when another candidate only needs review.

## Actionable Intents

Manual-order gate applies to:

- `ENTRY_READY`
- `ACTIONABLE`
- `ACTIONABLE_DAY1`
- `MANUAL_ORDER`

The following intents are journaled but do not imply a broker order:

- `WATCHLIST`
- `DELAYED_EP_WATCH`
- `PEAD_HANDOFF`
- `IGNORE`
- `REJECTED`

If all candidates are non-actionable, the output is `NO_ACTIONABLE_ORDERS`.

## Blocking Rules

An actionable candidate is `NO_GO` when:

- `entry_in_written_plan` is not true
- `stop_predefined` is not true
- `size_within_plan` is not true
- `actual_risk_dollars` is greater than `planned_risk_dollars`
- A losing exit or partial trim exists inside the revenge window
- Market-regime recommendation is `REDUCE_ONLY` or `CASH_PRIORITY`
- Circuit-breaker recommendation is `COOLDOWN`, `HALTED`, or `TRADING_HALTED`

Market-regime recommendation `NEW_ENTRY_ALLOWED` and circuit-breaker recommendation `TRADING_ALLOWED` are the only explicit pass values. Unknown or missing upstream artifacts produce `REVIEW_REQUIRED` for actionable orders.

Both `planned_risk_dollars` and `actual_risk_dollars` are required for an actionable candidate. Each field accepts a finite, non-negative number or numeric string, including zero. A missing value, boolean, non-numeric string, `NaN`, infinity, or negative value produces `REVIEW_REQUIRED`; the audit copy is normalized to JSON `null`. When both fields are valid and actual risk exceeds planned risk, the candidate is `NO_GO`. An explicit `NO_GO` rule remains higher priority than a simultaneous invalid-risk review.

## Approved Operating Rules

With `--approved-rules-ledger`, the gate reads a local ledger of rules approved in a monthly review (managed with `manage_approved_rules.py`). Rules are free text. The gate does not evaluate them against the trade; it requires a human acknowledgement per applied rule and records it. Acknowledgement is recorded, not verified.

Computed state, using the America/New_York date of `--as-of`:

| State | Condition | Applied |
|---|---|---|
| `not_yet_effective` | active, date before `effective_date` | no |
| `effective` | active, `effective_date <= date <= review_after`, not expired | yes |
| `review_due` | active, date after `review_after`, not expired | yes, with a warning |
| `expired` | active, `expires_on` set and date after it | no, with a warning |
| `superseded`, `retired` | stored status | no |

A `review_due` rule keeps applying because the monthly review runs after the month ends; dropping rules on the review date would leave a gap in which the gate returns `GO` with no rules. `expires_on` is the optional hard stop. State is computed from the current stored status, so a past `--as-of` does not reconstruct an earlier ledger. The ledger is a single-user local file; concurrent writers are not supported.

Per actionable candidate and applied rule, `approved_rule_checks` entries behave as follows:

| Answer | Effect |
|---|---|
| `followed`, `not_applicable` | none |
| `exception` with a non-empty `note` | `REVIEW_REQUIRED` carrying the note |
| no entry, `exception` without note, unknown status | `REVIEW_REQUIRED`: not acknowledged |
| malformed `approved_rule_checks` | `REVIEW_REQUIRED`; nothing from the value is trusted |

An `exception` is a terminal `REVIEW_REQUIRED` for that run: the gate cannot approve an exception. Either do not place the order, or change the ledger explicitly (`retire`, `supersede`) and rerun. `NO_GO` still outranks `REVIEW_REQUIRED`. Non-actionable candidates are never required to acknowledge rules; supplied checks are validated and recorded. If the ledger is missing, unreadable, or invalid, every actionable candidate is `REVIEW_REQUIRED` and the report and journal are still written. Without the flag the output is unchanged.

## Trader Memory Integration

Revenge-risk detection reads trader-memory-core thesis YAML files:

- `status_history[].realized_pnl < 0` counts partial trims and terminal ledger events.
- Terminal theses with no ledger `realized_pnl` fall back to `outcome.pnl_dollars < 0` when a terminal date can be inferred.
- Date-only producer timestamps expanded to `YYYY-MM-DDT00:00:00+00:00` are counted on the named ET date, matching the drawdown-circuit-breaker behavior.
- Events after `--as-of` are ignored.

When `thesis_id` and `--state-dir` are provided, the skill links the generated JSON report with trader-memory-core `link_report`. It never uses `mark_reviewed`, because pre-trade checklist logging must not advance monitoring review dates.

The JSON report and JSONL journal retain candidate-level `checklist_answers` for `entry_in_written_plan`, `stop_predefined`, `size_within_plan`, `planned_risk_dollars`, `actual_risk_dollars`, and `notes`. Invalid risk-dollar values are stored as JSON `null`. Valid JSON decimals that cannot round-trip through a binary float are retained as numeric strings, preserving their exact value for the decision and audit record. This keeps GO decisions reviewable later instead of recording only failures.

## Workflow Integration

In `swing-opportunity-daily`, the gate runs after thesis registration and consumes same-workflow artifacts such as `candidate_journal_entry`, `position_sizing`, `trade_plans`, and `circuit_breaker_decision`.

In `stockbee-ep-daily`, the workflow first runs `drawdown-circuit-breaker` to produce `circuit_breaker_decision`, then runs this gate only for ACTIONABLE_DAY1 / ENTRY_READY manual-order candidates. Delayed EP, PEAD handoff, and ignored candidates are recorded as no-action orders.

`exposure_decision` remains a prerequisite workflow artifact. It should be supplied to the CLI by path; it is not listed under workflow `consumes` because strict workflow validation only permits artifacts produced earlier in the same workflow.
