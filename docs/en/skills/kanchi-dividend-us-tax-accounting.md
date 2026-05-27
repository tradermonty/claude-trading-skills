---
layout: default
title: "Kanchi Dividend US Tax Accounting"
grand_parent: English
parent: Skill Guides
nav_order: 36
lang_peer: /ja/skills/kanchi-dividend-us-tax-accounting/
permalink: /en/skills/kanchi-dividend-us-tax-accounting/
---

# Kanchi Dividend US Tax Accounting
{: .no_toc }

Provide US dividend tax and account-location workflow for Kanchi-style income portfolios. Use when users ask about qualified vs ordinary dividends, 1099-DIV interpretation, REIT/BDC distribution treatment, holding-period checks, or taxable-vs-IRA account placement decisions for dividend assets.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/kanchi-dividend-us-tax-accounting.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/kanchi-dividend-us-tax-accounting){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Apply a practical US-tax workflow for dividend investors while keeping decisions auditable.
Focus on account placement and classification, not legal/tax advice replacement.

---

## 2. When to Use

Use this skill when the user needs:
- US dividend tax classification planning (qualified vs ordinary assumptions).
- Holding-period checks before year-end tax planning.
- Account-location decisions for stock/REIT/BDC/MLP income holdings.
- A standardized annual dividend tax memo format.

---

## 3. Prerequisites

Prepare holding-level inputs:
- `ticker`
- `instrument_type`
- `account_type`
- `hold_days_in_window` (if available)

### Expected JSON Input Format

```json
{
  "holdings": [
    {
      "ticker": "JNJ",
      "instrument_type": "stock",
      "account_type": "taxable",
      "security_type": "common",
      "hold_days_in_window": 75
    },
    {
      "ticker": "O",
      "instrument_type": "reit",
      "account_type": "ira",
      "hold_days_in_window": 100
    }
  ]
}
```

For deterministic output artifacts, provide JSON input and run:

```bash
python3 skills/kanchi-dividend-us-tax-accounting/scripts/build_tax_planning_sheet.py \
  --input /path/to/tax_input.json \
  --output-dir reports/
```

---

## 4. Quick Start

### 1) Classify each distribution stream

For each holding, classify expected cash flow into:
- Potential qualified dividend.
- Ordinary dividend/non-qualified distribution.
- REIT/BDC-specific distribution components where applicable.

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/kanchi-dividend-us-tax-accounting/references/account-location-matrix.md`
- `skills/kanchi-dividend-us-tax-accounting/references/annual-tax-memo-template.md`
- `skills/kanchi-dividend-us-tax-accounting/references/qualified-dividend-checklist.md`

**Scripts:**

- `skills/kanchi-dividend-us-tax-accounting/scripts/build_tax_planning_sheet.py`
