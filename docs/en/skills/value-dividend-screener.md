---
layout: default
title: "Value Dividend Screener"
grand_parent: English
parent: Skill Guides
nav_order: 64
lang_peer: /ja/skills/value-dividend-screener/
permalink: /en/skills/value-dividend-screener/
---

# Value Dividend Screener
{: .no_toc }

Screen US stocks for high-quality dividend opportunities combining value characteristics (P/E ratio under 20, P/B ratio under 2), attractive yields (3% or higher), and consistent growth (dividend/revenue/EPS trending up over 3 years). Supports two-stage screening using FINVIZ Elite API for efficient pre-filtering followed by FMP API for detailed analysis. Use when user requests dividend stock screening, income portfolio ideas, or quality value stocks with strong fundamentals.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span> <span class="badge badge-optional">FINVIZ Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/value-dividend-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/value-dividend-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill identifies high-quality dividend stocks that combine value characteristics, attractive income generation, and consistent growth using a **two-stage screening approach**:

1. **FINVIZ Elite API (Optional but Recommended)**: Pre-screen stocks with basic criteria (fast, cost-effective)
2. **Financial Modeling Prep (FMP) API**: Detailed fundamental analysis of candidates

Screen US equities based on quantitative criteria including valuation ratios, dividend metrics, financial health, and profitability. Generate comprehensive reports ranking stocks by composite quality scores with detailed fundamental analysis.

**Efficiency Advantage**: Using FINVIZ pre-screening can reduce FMP API calls by 90%, making this approach ideal for free-tier API users.

---

## 2. When to Use

Invoke this skill when the user requests:
- "Find high-quality dividend stocks"
- "Screen for value dividend opportunities"
- "Show me stocks with strong dividend growth"
- "Find income stocks trading at reasonable valuations"
- "Screen for sustainable high-yield stocks"
- Any request combining dividend yield, valuation metrics, and fundamental analysis

---

## 3. Prerequisites

- **FMP API key** required (`FMP_API_KEY` environment variable)
- **FINVIZ Elite** optional (improves performance)
- Financial Modeling Prep API
- Python 3.9+ recommended

---

## 4. Quick Start

```bash
# Two-stage screening (RECOMMENDED - 70-80% faster)
python3 value-dividend-screener/scripts/screen_dividend_stocks.py --use-finviz

# FMP-only screening (no FINVIZ required)
python3 value-dividend-screener/scripts/screen_dividend_stocks.py

# Custom parameters
python3 value-dividend-screener/scripts/screen_dividend_stocks.py \
  --use-finviz \
  --top 50 \
  --output custom_results.json
```

---

## 5. Workflow

### Step 1: Verify API Key Availability

**For Two-Stage Screening (Recommended):**

Check if both API keys are available:

```python
import os
fmp_api_key = os.environ.get('FMP_API_KEY')
finviz_api_key = os.environ.get('FINVIZ_API_KEY')
```

If not available, ask user to provide API keys or set environment variables:
```bash
export FMP_API_KEY=your_fmp_key_here
export FINVIZ_API_KEY=your_finviz_key_here
```

**For FMP-Only Screening:**

Check if FMP API key is available:

```python
import os
api_key = os.environ.get('FMP_API_KEY')
```

If not available, ask user to provide API key or set environment variable:
```bash
export FMP_API_KEY=your_key_here
```

**FINVIZ Elite API Key:**
- Requires FINVIZ Elite subscription (~$40/month or ~$330/year)
- Provides access to CSV export of pre-screened results
- Highly recommended for reducing FMP API usage

Provide instructions from `references/fmp_api_guide.md` if needed.

### Step 2: Execute Screening Script

Run the screening script with appropriate parameters:

#### **Two-Stage Screening (RECOMMENDED)**

Uses FINVIZ for pre-screening, then FMP for detailed analysis:

**Default execution (Top 20 stocks):**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz
```

**With explicit API keys:**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz \
  --fmp-api-key $FMP_API_KEY \
  --finviz-api-key $FINVIZ_API_KEY
```

**Custom top N:**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz --top 50
```

**Custom output location:**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz --output /path/to/results.json
```

**Script behavior (Two-Stage):**
1. FINVIZ Elite pre-screening:
   - Market cap: Mid-cap or higher
   - Dividend yield: 3%+
   - Dividend growth (3Y): 5%+
   - EPS growth (3Y): Positive
   - P/B: Under 2
   - P/E: Under 20
   - Sales growth (3Y): Positive
   - Geography: USA
2. FMP detailed analysis of FINVIZ results (typically 20-50 stocks):
   - Dividend growth rate calculation (3-year CAGR)
   - Revenue and EPS trend analysis
   - Dividend sustainability assessment (payout ratios, FCF coverage)
   - Financial health metrics (debt-to-equity, current ratio)
   - Quality scoring (ROE, profit margins)
3. Composite scoring and ranking
4. Output top N stocks to JSON file

**Expected runtime (Two-Stage):** 2-3 minutes for 30-50 FINVIZ candidates (much faster than FMP-only)

#### **FMP-Only Screening (Original Method)**

Uses only FMP Stock Screener API (higher API usage):

**Default execution:**
```bash
python3 scripts/screen_dividend_stocks.py
```

**With explicit API key:**
```bash
python3 scripts/screen_dividend_stocks.py --fmp-api-key $FMP_API_KEY
```

**Script behavior (FMP-Only):**
1. Initial screening using FMP Stock Screener API (dividend yield >=3.0%, P/E <=20, P/B <=2)
2. Detailed analysis of candidates (typically 100-300 stocks):
   - Same detailed analysis as two-stage approach
3. Composite scoring and ranking
4. Output top N stocks to JSON file

**Expected runtime (FMP-Only):** 5-15 minutes for 100-300 candidates (rate limiting applies)

**API Usage Comparison:**
- Two-Stage: ~50-100 FMP API calls (FINVIZ pre-filters to ~30 stocks)
- FMP-Only: ~500-1500 FMP API calls (analyzes all screener results)

### Step 3: Parse and Analyze Results

Read the generated JSON file:

```python
import json

with open('dividend_screener_results.json', 'r') as f:
    data = json.load(f)

metadata = data['metadata']
stocks = data['stocks']
```

**Key data points per stock:**
- Basic info: `symbol`, `company_name`, `sector`, `market_cap`, `price`
- Valuation: `dividend_yield`, `pe_ratio`, `pb_ratio`
- Growth metrics: `dividend_cagr_3y`, `revenue_cagr_3y`, `eps_cagr_3y`
- Sustainability: `payout_ratio`, `fcf_payout_ratio`, `dividend_sustainable`
- Financial health: `debt_to_equity`, `current_ratio`, `financially_healthy`
- Quality: `roe`, `profit_margin`, `quality_score`
- Overall ranking: `composite_score`

### Step 4: Generate Markdown Report

Create structured markdown report for user with following sections:

#### Report Structure

```markdown
# Value Dividend Stock Screening Report

**Generated:** [Timestamp]
**Screening Criteria:**
- Dividend Yield: >= 3.5%
- P/E Ratio: <= 20
- P/B Ratio: <= 2
- Dividend Growth (3Y CAGR): >= 5%
- Revenue Trend: Positive over 3 years
- EPS Trend: Positive over 3 years

**Total Results:** [N] stocks

---

---

## 6. Resources

**References:**

- `skills/value-dividend-screener/references/fmp_api_guide.md`
- `skills/value-dividend-screener/references/screening_methodology.md`

**Scripts:**

- `skills/value-dividend-screener/scripts/screen_dividend_stocks.py`
