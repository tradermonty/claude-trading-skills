---
layout: default
title: "Pre-Trade Discipline Gate"
grand_parent: English
parent: Skill Guides
nav_order: 64
lang_peer: /ja/skills/pre-trade-discipline-gate/
permalink: /en/skills/pre-trade-discipline-gate/
generated: false
---

# Pre-Trade Discipline Gate
{: .no_toc }

Check a local pre-trade discipline checklist before manual broker entry, blocking planless, oversized, revenge-risk, market-regime-blocked, or circuit-breaker-blocked orders while journaling the result.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/pre-trade-discipline-gate){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Pre-Trade Discipline Gate runs after a candidate has been validated, sized, and journaled, but before any manual broker order is placed. It produces a `pre_trade_discipline_decision` artifact with a candidate-by-candidate checklist result.

The skill is offline and advisory. It does not place orders.

---

## 2. Quick Start

```bash
python3 skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py \
  --answers-file state/manual-entry-checklist.json \
  --state-dir state/theses \
  --market-regime-decision reports/exposure_decision_latest.json \
  --circuit-breaker-decision reports/circuit_breaker_decision_latest.json \
  --output-dir reports/pre-trade-discipline \
  --journal-dir state/journal/pre-trade-discipline
```

---

## 3. Checklist Input

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
      "actual_risk_dollars": 500
    }
  ]
}
```

Actionable intents are `ENTRY_READY`, `ACTIONABLE`, `ACTIONABLE_DAY1`, and `MANUAL_ORDER`. Watchlist or ignored candidates are recorded as `NO_ACTIONABLE_ORDERS`.

Both `planned_risk_dollars` and `actual_risk_dollars` are required for actionable candidates. Each accepts a finite, non-negative number or numeric string, including zero. Missing values, booleans, non-numeric strings, `NaN`, infinities, and negative values produce `REVIEW_REQUIRED` and are recorded as JSON `null`. When both values are valid, actual risk above planned risk produces `NO_GO`.

---

## 4. Decisions

| Decision | Meaning |
|---|---|
| `GO` | All actionable manual-order candidates passed |
| `REVIEW_REQUIRED` | Missing, unknown, or failed journaling inputs need review; also a missing approved-rule acknowledgement, a recorded exception, or an unreadable rule ledger |
| `NO_GO` | A discipline or upstream gate rule blocked an actionable order |
| `NO_ACTIONABLE_ORDERS` | The file contains no broker order to place |

Use `--fail-on-non-go` when shell automation should return exit code `2` for non-`GO` decisions.

---

## 5. Trader Memory Link

When a candidate has `thesis_id` and `--state-dir` is supplied, the generated JSON report is added to the thesis `linked_reports` list. The skill does not call `mark_reviewed`, so monitoring review dates are not advanced.

The JSON report and JSONL journal keep each candidate's `checklist_answers`, including written-plan, stop, size, risk-dollar, and notes fields, so later reviews can audit what was answered before the order. Invalid risk values are stored as JSON `null`. Valid JSON decimals that cannot round-trip through a binary float are retained as numeric strings so their exact value reaches the comparison and audit record.

---

## 6. Approved Operating Rules (optional)

Rules a human approved in the monthly review can be carried into the pre-trade check through a local ledger. Rules are free text: the gate lists each applicable rule and requires a recorded acknowledgement, but it does not verify compliance.

```bash
# Activate approved rules from the monthly rule-changes artifact (replay and sample shapes are both accepted)
python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py activate \
  --rule-changes reports/06_rule_changes_for_next_month.yaml \
  --effective-date 2026-06-01 --review-after 2026-06-30 --confirm-activation

# Show every rule with its computed state, then run the gate against the ledger
python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py list --as-of 2026-06-15
python3 skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py \
  --answers-file state/manual-entry-checklist.json \
  --approved-rules-ledger state/rules/approved_rules.json
```

Add one acknowledgement per applied rule to each actionable candidate:

```json
"approved_rule_checks": [{"rule_id": "rule_3f9a1c2b7d10", "status": "followed", "note": ""}]
```

| Answer | Effect |
|---|---|
| `followed`, `not_applicable` | none |
| `exception` with a non-empty `note` | `REVIEW_REQUIRED` carrying the note |
| missing entry, `exception` without a note, unknown status, or malformed value | `REVIEW_REQUIRED` |

An `exception` is a terminal `REVIEW_REQUIRED` for that run, because the gate cannot approve an exception. Either do not place the order, or change the ledger (`retire`, `supersede`) and rerun. `NO_GO` still outranks it.

Lifecycle commands are `activate`, `list`, `supersede`, `retire`, `extend`, and `restore`. A rule's ID comes from its normalized text, so approving the same rule again renews it, and re-running a file from the same review changes nothing. History is append-only. Computed state, using the America/New_York date, decides what the gate applies:

| State | Applied |
|---|---|
| `effective` (through `review_after`, inclusive) | yes |
| `review_due` (after `review_after`) | yes, with a warning |
| `not_yet_effective`, `expired` (after `expires_on`), `superseded`, `retired` | no |

The ledger is a single-user local file; concurrent writers are not supported. State is computed from the current stored status, so a past `--as-of` does not reconstruct an earlier ledger. If the ledger cannot be read, actionable candidates become `REVIEW_REQUIRED` and the report and journal are still written. Without `--approved-rules-ledger` the output is unchanged.
