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
- `references/input-schema.md`

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

Use `references/trigger-matrix.md` for trigger thresholds and actions.

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

Use `references/input-schema.md` for field definitions
and sample payload.

### 2) Run the rule engine

Run:

```bash
python3 skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py \
  --input /path/to/monitor_input.json \
  --output-dir reports/
```

The script maps each ticker to `OK/WARN/REVIEW` based on T1-T5.
Output files are saved to the specified directory with dated filenames (e.g., `review_queue_20260227.json` and `.md`).

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

Use `references/review-ticket-template.md` output format.

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

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `dividend_review` | `DividendReview` | Dividend anomaly findings (T1-T5) and review queue |

Schema: `schemas/json/dividend_review.json`

## Resources

- `scripts/build_review_queue.py`: local rule engine for T1-T5.
- `scripts/tests/test_build_review_queue.py`: unit tests for T1-T5 and report rendering.
- `references/trigger-matrix.md`: trigger definitions, cadence, and actions.
- `references/input-schema.md`: normalized input schema and sample JSON.
- `references/review-ticket-template.md`: standardized manual-review ticket layout.

## Data Gaps

This skill operates with or without FMP API access. Behavior when data is unavailable:

| Scenario | Severity | Behavior |
|----------|----------|----------|
| `FMP_API_KEY` not set | MEDIUM | Fall back to offline mode or manual CSV; note limitation in output |
| FMP returns empty response | MEDIUM | Warn; use cached or user-supplied data if available |
| Individual ticker data missing | LOW | Skip ticker; list under `data_gaps[]` in output |
| Fewer than 10 data points | HIGH | Halt analysis for that instrument; do not extrapolate |

## Manual Review Gate

This skill produces review tickets, not trading decisions. For each T1-T5 anomaly flagged:

1. T1 (dividend cut) or T2 (yield spike >30%) — defer all additional buys until resolved manually
2. T3 (price drop >15%) — review full thesis before any buy or hold decision
3. T4 (payout ratio >90%) — flag for human judgment; do not auto-exclude
4. T5 (volume/liquidity change) — verify data quality before acting on signal

No review ticket implies automatic action — all decisions require the trader's explicit approval.
