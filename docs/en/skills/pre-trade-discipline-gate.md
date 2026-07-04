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

---

## 4. Decisions

| Decision | Meaning |
|---|---|
| `GO` | All actionable manual-order candidates passed |
| `REVIEW_REQUIRED` | Missing, unknown, or failed journaling inputs need review |
| `NO_GO` | A discipline or upstream gate rule blocked an actionable order |
| `NO_ACTIONABLE_ORDERS` | The file contains no broker order to place |

Use `--fail-on-non-go` when shell automation should return exit code `2` for non-`GO` decisions.

---

## 5. Trader Memory Link

When a candidate has `thesis_id` and `--state-dir` is supplied, the generated JSON report is added to the thesis `linked_reports` list. The skill does not call `mark_reviewed`, so monitoring review dates are not advanced.

The JSON report and JSONL journal keep each candidate's `checklist_answers`, including written-plan, stop, size, risk-dollar, and notes fields, so later reviews can audit what was answered before the order.
