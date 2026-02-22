---
name: kanchi-dividend-sop
description: Convert Kanchi-style dividend investing into a repeatable US-stock operating procedure. Use when users ask for かんち式配当投資, dividend screening, dividend growth quality checks, PERxPBR adaptation for US sectors, pullback limit-order planning, or one-page stock memo creation. Covers screening, deep dive, entry planning, and post-purchase monitoring cadence.
---

# Kanchi Dividend Sop

## Overview

Implement Kanchi's 5-step method as a deterministic workflow for US dividend investing.
Prioritize safety and repeatability over aggressive yield chasing.

## When to Use

Use this skill when the user needs:
- Kanchi-style dividend stock selection adapted for US equities.
- A repeatable screening and pullback-entry process instead of ad-hoc picks.
- One-page underwriting memos with explicit invalidation conditions.
- A handoff package for monitoring and tax/account-location workflows.

## Prerequisites

Prepare one of the following inputs before running the workflow:
1. Output from `skills/value-dividend-screener/scripts/screen_dividend_stocks.py`.
2. Output from `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py`.
3. User-provided ticker list (broker export or manual list).

For deterministic artifact generation, provide tickers to:

```bash
python3 skills/kanchi-dividend-sop/scripts/build_sop_plan.py \
  --tickers "JNJ,PG,KO" \
  --output-dir reports/
```

For Step 5 entry timing artifacts:

```bash
python3 skills/kanchi-dividend-sop/scripts/build_entry_signals.py \
  --tickers "JNJ,PG,KO" \
  --alpha-pp 0.5 \
  --output-dir reports/
```

## Workflow

### 1) Define mandate before screening

Collect and lock the parameters first:
- Objective: current cash income vs dividend growth.
- Max positions and position-size cap.
- Allowed instruments: stock only, or include REIT/BDC/ETF.
- Preferred account type context: taxable vs IRA-like accounts.

Load `skills/kanchi-dividend-sop/references/default-thresholds.md` and apply baseline
settings unless the user overrides.

### 2) Build the investable universe

Start with a quality-biased universe:
- Core bucket: long dividend growth names (for example, Dividend Aristocrats style quality set).
- Satellite bucket: higher-yield sectors (utilities, telecom, REITs) in a separate risk bucket.

Use explicit source priority for ticker collection:
1. `skills/value-dividend-screener/scripts/screen_dividend_stocks.py` output (FMP/FINVIZ).
2. `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py` output.
3. User-provided broker export or manual ticker list when APIs are unavailable.

Return a ticker list grouped by bucket before moving forward.

### 3) Apply Kanchi Step 1 (yield filter with trap flag)

Primary rule:
- `forward_dividend_yield >= 3.5%`

Trap controls:
- Flag extreme yield (`>= 8%`) as `deep-dive-required`.
- Flag sudden jump in payout as potential special dividend artifact.

Output:
- `PASS` or `FAIL` per ticker.
- `deep-dive-required` flag for potential yield traps.

### 4) Apply Kanchi Step 2 (growth and safety)

Require:
- Revenue and EPS trend positive on multi-year horizon.
- Dividend trend non-declining over the review period.

Add safety checks:
- Payout ratio and FCF payout ratio in reasonable range.
- Debt burden and interest coverage not deteriorating.

When trend is mixed but not broken, classify as `HOLD-FOR-REVIEW` instead of hard reject.

### 5) Apply Kanchi Step 3 (valuation) with US sector mapping

Use `skills/kanchi-dividend-sop/references/valuation-and-one-off-checks.md` and apply
sector-specific valuation logic:
- Financials: `PER x PBR` can remain primary.
- REITs: use `P/FFO` or `P/AFFO` instead of plain `P/E`.
- Asset-light sectors: combine forward `P/E`, `P/FCF`, and historical range.

Always report which valuation method was used for each ticker.

### 6) Apply Kanchi Step 4 (one-off event filter)

Reject or downgrade names where recent profits rely on one-time effects:
- Asset sale gains, litigation settlement, tax effect spikes.
- Margin spike unsupported by sales trend.
- Repeated "one-time/non-recurring" adjustments.

Record one-line evidence for each `FAIL` to keep auditability.

### 7) Apply Kanchi Step 5 (buy on weakness with rules)

Set entry triggers mechanically:
- Yield trigger: current yield above 5y average yield + alpha (default `+0.5pp`).
- Valuation trigger: target multiple reached (`P/E`, `P/FFO`, or `P/FCF`).

Execution pattern:
- Split orders: `40% -> 30% -> 30%`.
- Require one-sentence sanity check before each add: "thesis intact vs structural break".

### 8) Produce standardized outputs

Always produce three artifacts:
1. Screening table (`PASS`, `HOLD-FOR-REVIEW`, `FAIL` with evidence).
2. One-page stock memo (use `skills/kanchi-dividend-sop/references/stock-note-template.md`).
3. Limit-order plan with split sizing and invalidation condition.

## Output

Return and/or generate:
1. SOP screening summary in markdown.
2. Underwriting memo set based on
`skills/kanchi-dividend-sop/references/stock-note-template.md`.
3. Optional plan artifact file generated by
`skills/kanchi-dividend-sop/scripts/build_sop_plan.py` in `reports/`.
4. Optional Step 5 entry-signal artifacts generated by
`skills/kanchi-dividend-sop/scripts/build_entry_signals.py` in `reports/`.

## Cadence

Use this minimum rhythm:
- Weekly (15 min): check dividend and business-news changes only.
- Monthly (30 min): rerun screening and refresh order levels.
- Quarterly (60 min): deep safety review using latest filings/earnings.

## Multi-Skill Handoff

Run this skill first, then hand off outputs:
1. To `kanchi-dividend-review-monitor` for daily/weekly/quarterly anomaly detection.
2. To `kanchi-dividend-us-tax-accounting` for account-location and tax classification planning.

## Guardrails

- Do not issue blind buy calls without Step 4 and safety checks.
- Do not treat high yield as value before validating coverage quality.
- Keep assumptions explicit when data is missing.

## Resources

- `skills/kanchi-dividend-sop/scripts/build_sop_plan.py`: deterministic SOP plan generator.
- `skills/kanchi-dividend-sop/scripts/tests/test_build_sop_plan.py`: tests for plan generation.
- `skills/kanchi-dividend-sop/scripts/build_entry_signals.py`: Step 5 target-buy calculator (`5y avg yield + alpha`).
- `skills/kanchi-dividend-sop/scripts/tests/test_build_entry_signals.py`: tests for signal calculations.
- `skills/kanchi-dividend-sop/references/default-thresholds.md`: baseline thresholds and profile tuning.
- `skills/kanchi-dividend-sop/references/valuation-and-one-off-checks.md`: sector valuation map and one-off checklist.
- `skills/kanchi-dividend-sop/references/stock-note-template.md`: one-page memo template for each candidate.
