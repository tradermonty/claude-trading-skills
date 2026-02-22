---
name: kanchi-dividend-review-monitor
description: Monitor dividend portfolios with Kanchi-style forced-review triggers (T1-T5) and convert anomalies into OK/WARN/REVIEW states without auto-selling. Use when users ask for 減配検知, 8-Kガバナンス監視, 配当安全性モニタリング, REVIEWキュー自動化, or periodic dividend risk checks.
---

# Kanchi Dividend Review Monitor

## Overview

Detect abnormal dividend-risk signals and route them into a human review queue.
Treat automation as anomaly detection, not automated trade execution.

## When to Use

Use this skill when the user needs:
- Daily/weekly/quarterly anomaly detection for dividend holdings.
- Forced review queueing for T1-T5 risk triggers.
- 8-K/governance keyword scans tied to portfolio tickers.
- Deterministic `OK/WARN/REVIEW` output before manual decision making.

## Prerequisites

Provide normalized input JSON that follows:
- `skills/kanchi-dividend-review-monitor/references/input-schema.md`

If upstream data is unavailable, provide at least:
- `ticker`
- `instrument_type`
- `dividend.latest_regular`
- `dividend.prior_regular`

## Non-Negotiable Rule

Never auto-sell based only on machine triggers.
Always create `WARN` or `REVIEW` evidence for human confirmation first.

## State Machine

- `OK`: no action.
- `WARN`: add to next check cycle and pause optional adds.
- `REVIEW`: immediate human review ticket + pause adds.

Use `skills/kanchi-dividend-review-monitor/references/trigger-matrix.md` for trigger thresholds and actions.

## Monitoring Cadence

- Daily:
  - T1 dividend cut/suspension.
  - T4 SEC filing keyword scan (8-K oriented).
- Weekly:
  - T3 proxy credit stress checks.
- Quarterly:
  - T2 coverage deterioration and T5 structural decline scoring.

## Workflow

### 1) Normalize input dataset

Collect per ticker fields in one JSON document:
- Dividend points (latest regular, prior regular, missing/zero flag).
- Coverage fields (FCF or FFO or NII, dividends paid, ratio history).
- Balance-sheet trend fields (net debt, interest coverage, buybacks/dividends).
- Filing text snippets (especially recent 8-K or equivalent alert text).
- Operations trend fields (revenue CAGR, margin trend, guidance trend).

Use `skills/kanchi-dividend-review-monitor/references/input-schema.md` for field definitions
and sample payload.

### 2) Run the rule engine

Run:

```bash
python3 skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py \
  --input /path/to/monitor_input.json \
  --output /path/to/review_queue.json \
  --markdown /path/to/review_queue.md
```

The script maps each ticker to `OK/WARN/REVIEW` based on T1-T5.

### 3) Prioritize and deduplicate

If multiple triggers fire:
- Keep all findings for audit trail.
- Escalate final state to highest severity only.
- Store trigger reasons as single-line evidence.

### 4) Generate human review tickets

For each `REVIEW` ticker, include:
- Trigger IDs and evidence.
- Suspected failure mode.
- Required manual checks for next decision.

Use `skills/kanchi-dividend-review-monitor/references/review-ticket-template.md` output format.

## SEC Filing Guardrail

When implementing live SEC fetchers:
- Include a compliant `User-Agent` string (name + email).
- Use caching and throttling.
- Respect SEC fair-access guidance.

## Output Contract

Always return:
1. Queue JSON with summary counts and ticker-level findings.
2. Markdown dashboard for quick triage.
3. List of immediate `REVIEW` tickets.

## Multi-Skill Handoff

- Consume ticker universe and baseline assumptions from `kanchi-dividend-sop`.
- Feed `REVIEW` results back to `kanchi-dividend-sop` for re-underwriting and position-size review.
- Share account-type context with `kanchi-dividend-us-tax-accounting` when risk events imply account relocation decisions.

## Resources

- `scripts/build_review_queue.py`: local rule engine for T1-T5.
- `scripts/tests/test_build_review_queue.py`: unit tests for T1-T5 and report rendering.
- `skills/kanchi-dividend-review-monitor/references/trigger-matrix.md`: trigger definitions, cadence, and actions.
- `skills/kanchi-dividend-review-monitor/references/input-schema.md`: normalized input schema and sample JSON.
- `skills/kanchi-dividend-review-monitor/references/review-ticket-template.md`: standardized manual-review ticket layout.
