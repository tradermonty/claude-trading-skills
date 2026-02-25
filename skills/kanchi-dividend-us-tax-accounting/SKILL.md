---
name: kanchi-dividend-us-tax-accounting
description: Provide US dividend tax and account-location workflow for Kanchi-style income portfolios. Use when users ask about qualified vs ordinary dividends, 1099-DIV interpretation, REIT/BDC distribution treatment, holding-period checks, or taxable-vs-IRA account placement decisions for dividend assets.
---

# Kanchi Dividend Us Tax Accounting

## Overview

Apply a practical US-tax workflow for dividend investors while keeping decisions auditable.
Focus on account placement and classification, not legal/tax advice replacement.

## When to Use

Use this skill when the user needs:
- US dividend tax classification planning (qualified vs ordinary assumptions).
- Holding-period checks before year-end tax planning.
- Account-location decisions for stock/REIT/BDC/MLP income holdings.
- A standardized annual dividend tax memo format.

## Prerequisites

Prepare holding-level inputs:
- `ticker`
- `instrument_type`
- `account_type`
- `hold_days_in_window` (if available)

For deterministic output artifacts, provide JSON input and run:

```bash
python3 skills/kanchi-dividend-us-tax-accounting/scripts/build_tax_planning_sheet.py \
  --input /path/to/tax_input.json \
  --output-dir reports/
```

## Guardrail

Always state this clearly: tax outcomes depend on individual facts and jurisdiction.
Treat this skill as planning support, then escalate final filing decisions to a tax professional.

## Workflow

### 1) Classify each distribution stream

For each holding, classify expected cash flow into:
- Potential qualified dividend.
- Ordinary dividend/non-qualified distribution.
- REIT/BDC-specific distribution components where applicable.

Use `references/qualified-dividend-checklist.md`
for holding-period and classification checks.

### 2) Validate holding-period eligibility assumptions

For potential qualified treatment:
- Check ex-dividend date windows.
- Check required minimum holding days in the measurement window.
- Flag positions at risk of failing holding-period requirement.

If data is incomplete, mark status as `ASSUMPTION-REQUIRED`.

### 3) Map to reporting fields

Map planning assumptions to expected tax-form buckets:
- Ordinary dividend total.
- Qualified dividend subset.
- REIT-related components when reported separately.

Use form terminology consistently so year-end reconciliation is straightforward.

### 4) Build account-location recommendation

Use `references/account-location-matrix.md` to place
assets by tax profile:
- Taxable account for holdings likely to remain qualified-focused.
- Tax-advantaged account for higher ordinary-income style distributions.

When constraints conflict (liquidity, strategy, concentration), explain the tradeoff explicitly.

### 5) Produce annual planning memo

Use `references/annual-tax-memo-template.md` and include:
- Assumptions used.
- Distribution classification summary.
- Placement actions taken.
- Open items for CPA/tax-advisor review.

## Output

Always output:
1. Holding-level distribution classification table.
2. Account-location recommendation table with rationale.
3. Open-risk checklist for unresolved tax assumptions.
4. Optional generated artifacts from
`skills/kanchi-dividend-us-tax-accounting/scripts/build_tax_planning_sheet.py`.

## Multi-Skill Handoff

- Receive candidate and holding list from `kanchi-dividend-sop`.
- Receive risk-event context (`WARN/REVIEW`) from `kanchi-dividend-review-monitor`.
- Return account-location constraints back to `kanchi-dividend-sop` before new entries.

## Resources

- `skills/kanchi-dividend-us-tax-accounting/scripts/build_tax_planning_sheet.py`: tax planning sheet generator.
- `skills/kanchi-dividend-us-tax-accounting/scripts/tests/test_build_tax_planning_sheet.py`: tests for tax planning outputs.
- `references/qualified-dividend-checklist.md`: classification and holding-period checks.
- `references/account-location-matrix.md`: placement matrix by account type and instrument.
- `references/annual-tax-memo-template.md`: reusable memo structure.
