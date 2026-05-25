---
name: trade-performance-coach
description: >-
  Review closed trades, partial exits, and monthly trade aggregates for process
  adherence, risk discipline, execution quality, and evidence-based trading
  behavior patterns. Use after trader-memory-core and signal-postmortem have
  produced records, or when the user asks for a post-trade coach, risk-manager
  style review, rule-adherence review, next-session operating rules, or
  psychology-aware trading behavior feedback. This skill does not provide buy/sell
  advice, therapy, or broker execution.
---

# Trade Performance Coach

## Overview

Trade Performance Coach reviews recorded trade outcomes and journal evidence to
help a human trader improve their decision process. It converts closed-trade
records, postmortem findings, risk rules, and optional market-regime context into
an evidence-based coaching report covering:

- process adherence
- risk discipline
- execution quality
- possible trading-behavior patterns
- next-session operating rules
- coach questions for reflection

This skill is intended to fill the support role that a risk manager, desk lead,
or trading coach might provide in a professional trading environment. It is
strictly a process-review skill: it never recommends entering, exiting, buying,
selling, shorting, holding, or sizing a specific security.

## When to Use

Use this skill when any of the following are true:

- A trade has been closed and the user wants a post-trade coaching review.
- A partial close occurred and the user wants to inspect sizing, stop, or exit behavior.
- The user has `trader-memory-core` thesis records and `signal-postmortem` findings and wants next-session operating rules.
- The user wants a monthly review of recurring process, risk, execution, or behavior patterns.
- The user asks for a risk-manager style review of their own recorded trades.
- The user asks whether a loss was a process error, execution error, market environment issue, or acceptable variance.
- The user wants possible FOMO, revenge-trade, overconfidence, hesitation, stop-moving, or size-creep patterns flagged with evidence.

## When Not to Use

Do not use this skill to:

- Pick stocks or rank trade candidates.
- Approve or reject a live trade as financial advice.
- Place orders or draft broker instructions.
- Provide therapy, mental-health diagnosis, or personality assessment.
- Infer private psychological traits beyond the trade evidence supplied.
- Shame the user for losses or rule violations.
- Replace `trader-memory-core`; this skill consumes journal/thesis records and produces coaching findings.

If the input is incomplete, default to `REVIEW_REQUIRED` or `journal_only` mode and ask for missing records rather than inventing evidence.

## Prerequisites

Recommended upstream records:

- `trader-memory-core` closed thesis record or journal entry
- `signal-postmortem` postmortem findings
- original trade plan or trade ticket
- actual entry / exit / partial-close actions
- user-defined risk plan, if available
- optional `market-regime-daily` / `exposure-coach` context

No paid API key is required. The deterministic script works from local JSON/YAML-like records.

## Inputs

Minimum useful input is one recorded trade or one monthly aggregate.

Preferred fields:

```yaml
review_type: single_trade | partial_close | monthly_aggregate
trade_id: string
ticker: string
outcome: win | loss | breakeven | mixed
planned:
  thesis: string
  entry: number
  stop: number
  target: number
  risk_r: number
  thesis_recorded_before_entry: boolean
  setup_confirmed: boolean
  market_regime: allowed | restrictive | cash_priority | unknown
actual:
  entry: number
  exit: number
  risk_r: number
  portfolio_heat_r: number
  stop_moved: boolean
  stop_move_planned: boolean
  entry_before_confirmation: boolean
  traded_against_regime: boolean
risk_plan:
  max_risk_per_trade_r: number
  max_portfolio_heat_r: number
  max_weekly_loss_r: number
postmortem:
  root_cause: thesis_quality | execution | risk_sizing | market_environment | rule_violation | randomness | unknown
  notes: [string]
journal:
  reflection: string
  emotions: [string]
monthly:
  trades: [object]
  consecutive_losses: number
  rule_violations: number
```

The script tolerates partial records. Missing evidence is marked as `unclear`.

## Workflow

### Step 1 — Collect source records

Collect the most recent closed trade record, postmortem, risk plan, and journal notes.

```bash
python3 skills/trade-performance-coach/scripts/review_trade_performance.py \
  --input reports/trade_memory/closed_thesis_EXMPL.json \
  --output-dir reports/trade-performance-coach
```

### Step 2 — Evaluate process adherence

Compare actual actions against the user's documented plan and rules. Check for:

- missing pre-entry thesis
- setup confirmation skipped
- trade taken against market-regime gate
- stop moved without a pre-defined rule
- exit / partial close inconsistent with plan
- incomplete record quality

### Step 3 — Evaluate risk discipline

Compare actual risk and heat against the risk plan. Check for:

- per-trade risk above max
- portfolio heat above max
- weekly loss or consecutive-loss escalation
- oversized trade after a winner or loser
- correlated exposure if provided

### Step 4 — Evaluate execution quality

Classify entry, stop, exit, add, trim, and review behavior. Separate clean-process losses from execution mistakes.

### Step 5 — Detect possible behavior patterns

Use evidence from journal notes and action flags to tag possible trading behavior patterns. Always tie a tag to evidence and use non-diagnostic language.

Supported MVP tags:

- `fomo_entry`
- `revenge_trade`
- `premature_exit`
- `overconfidence_after_winner`
- `stop_moved`
- `size_creep`
- `hesitation`
- `rule_drift`
- `no_pattern_detected`

### Step 6 — Produce next-session operating rules

Convert findings into temporary, concrete guardrails. Examples:

- require thesis record and screenshot before the next entry
- cap risk at 0.5R for the next two trades after a rule violation
- switch to review-only mode after repeated revenge-trade evidence
- do not chase a missed entry; add to watchlist for the next valid setup

### Step 7 — Human decision gate

End every report with a human decision gate. The default action is `journal_only`.

Allowed actions:

```text
accept_rules / modify_rules / defer / journal_only
```

## Output

The skill produces a JSON report and optionally a Markdown report.

Required top-level JSON fields:

- `schema_version`
- `review_type`
- `review_id`
- `overall_verdict`
- `summary`
- `scores`
- `process_adherence_findings`
- `risk_manager_notes`
- `execution_quality_assessment`
- `behavioral_pattern_tags`
- `next_session_operating_rules`
- `coach_questions`
- `human_decision_gate`
- `disclaimer`

Verdicts:

| Verdict | Meaning |
|---|---|
| `OK` | No material process violation found. Outcome appears compatible with the plan. |
| `WARN` | Minor process or record-quality concern. |
| `REVIEW_REQUIRED` | Meaningful process, risk, or behavior finding before next similar trade. |
| `RULE_VIOLATION` | Explicit user rule appears to have been broken. |
| `COOL_DOWN` | Repeated violations, drawdown/revenge pattern, or escalation suggests review-only mode. |

## Example Command

```bash
python3 skills/trade-performance-coach/scripts/review_trade_performance.py \
  --input skills/trade-performance-coach/scripts/tests/fixtures/single_trade_rule_violation_loss.json \
  --output-dir reports/trade-performance-coach \
  --markdown
```

## Resources

Read these selectively when invoked:

- `references/review-framework.md` — five-axis review model, scoring, verdicts
- `references/behavior-tags.md` — behavior tag definitions and evidence rules
- `references/risk-review-checklist.md` — risk manager checklist and severity rules
- `references/output-contract.md` — JSON output contract and schema notes
- `references/hermes-integration.md` — suggested Hermes `/post-trade-coach` and monthly coaching integration
- `assets/performance_coach_report.schema.json` — machine-readable output schema
- `scripts/review_trade_performance.py` — deterministic local reviewer

## Guardrails

- This is process-review support, not financial advice.
- Do not recommend buying, selling, shorting, holding, or sizing a specific security.
- Do not provide therapy or mental-health diagnosis.
- Do not infer personality traits.
- Do not shame or moralize the user.
- Tie every behavior tag to evidence.
- Use "possible pattern" language for behavior tags.
- Always include a human decision gate.
- Default to journal/review mode when data is incomplete.
