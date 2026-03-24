---
name: value-dividend-screener
description: "Screen US stocks for high-quality dividend opportunities combining value characteristics (P/E ratio under 20, P/B ratio under 2), attractive yields (3% or higher), and consistent growth (dividend/revenue/EPS trending up over 3 years). Supports two-stage screening using FINVIZ Elite API for efficient pre-filtering followed by FMP API for detailed analysis. Use when user requests dividend stock screening, income portfolio ideas, or quality value stocks with strong fundamentals."
---

# Value Dividend Screener

## Overview

Identify high-quality dividend stocks combining value, income, and growth using a **two-stage screening approach**:

1. **FINVIZ Elite API (Optional)**: Pre-screen stocks with basic criteria — reduces FMP API calls by ~90%
2. **Financial Modeling Prep (FMP) API**: Detailed fundamental analysis of candidates

Generate reports ranking stocks by composite quality scores across valuation ratios, dividend metrics, financial health, and profitability.

## When to Use

Invoke this skill when the user requests:
- "Find high-quality dividend stocks"
- "Screen for value dividend opportunities"
- "Show me stocks with strong dividend growth"
- "Find income stocks trading at reasonable valuations"
- "Screen for sustainable high-yield stocks"
- Any request combining dividend yield, valuation metrics, and fundamental analysis

## Workflow

### Step 1: Verify API Key Availability

Check available API keys to determine screening mode:

```python
import os
fmp_api_key = os.environ.get('FMP_API_KEY')
finviz_api_key = os.environ.get('FINVIZ_API_KEY')  # Optional but recommended
```

If keys are missing, prompt the user:
```bash
export FMP_API_KEY=your_fmp_key_here       # Required
export FINVIZ_API_KEY=your_finviz_key_here  # Optional (~$40/month subscription)
```

Refer to `references/fmp_api_guide.md` for setup details.

### Step 2: Execute Screening Script

**Two-Stage (recommended when FINVIZ key available):**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz
python3 scripts/screen_dividend_stocks.py --use-finviz --top 50 --output /path/to/results.json
```

**FMP-Only (fallback):**
```bash
python3 scripts/screen_dividend_stocks.py
```

**Explicit API keys (if not set as env vars):**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz \
  --fmp-api-key $FMP_API_KEY --finviz-api-key $FINVIZ_API_KEY
```

**Screening pipeline:**
1. **Pre-filter** (FINVIZ or FMP screener): Market cap mid+, yield 3%+, div growth 5%+ (3Y), EPS growth positive, P/B < 2, P/E < 20, sales growth positive, USA only
2. **Detailed FMP analysis**: Dividend CAGR (3Y), revenue/EPS trends, payout ratios, FCF coverage, debt-to-equity, current ratio, ROE, profit margins
3. **Composite scoring and ranking**
4. **Output** top N stocks to JSON

**Performance comparison:**

| Mode | FMP API Calls | Runtime |
|------|--------------|---------|
| Two-Stage (FINVIZ + FMP) | ~50-100 | 2-3 min |
| FMP-Only | ~500-1500 | 5-15 min |

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

Create a structured report with these sections:

1. **Header**: Timestamp, screening criteria summary, total results count
2. **Top 20 Table**: Rank, Symbol, Company, Yield, P/E, Div Growth, Composite Score
3. **Detailed Analysis** (per stock): Valuation metrics, growth profile (3Y), dividend sustainability status, financial health status, quality metrics, investment considerations (strengths + risks)
4. **Portfolio Construction Guidance**: Sector breakdown, diversification recommendations, monitoring triggers

Use one stock as a worked example; apply the same format to remaining stocks.

### Step 5: Provide Context and Methodology

Reference `references/screening_methodology.md` to explain:
- Threshold rationale (3.5% yield, P/E 20, P/B 2)
- Dividend growth vs static high yield distinction
- Composite score weighting (value, growth, quality)
- Dividend sustainability vs dividend trap identification

### Step 6: Answer Follow-up Questions

Common follow-ups and approaches:
- **"Why did [stock] not make the list?"** — Check which criterion excluded it
- **"Can I screen specific sectors?"** — Filter candidates by sector post-screening (line 383-388)
- **"Adjust yield/valuation thresholds?"** — Re-run with modified parameters; explain trade-offs
- **"How often to re-run?"** — Quarterly (earnings cycles) or semi-annually for long-term holders
- **"How many stocks to buy?"** — Minimum 10-15 for dividend portfolio diversification; balance sectors

## Resources

### scripts/screen_dividend_stocks.py

Screening script that interfaces with FMP/FINVIZ APIs, implements multi-phase filtering, calculates 3-year CAGR metrics, evaluates dividend sustainability, and outputs ranked JSON results.

**Dependencies:** `requests` (`pip install requests`)
**Rate limiting:** Built-in delays respecting FMP free tier (250 requests/day)
**Error handling:** Graceful degradation for missing data, rate limit retries, API errors

### references/screening_methodology.md

Detailed documentation of the three-phase screening approach, composite scoring system (0-100), investment philosophy, threshold justification, and usage limitations.

### references/fmp_api_guide.md

FMP API setup guide covering key registration, environment variables, endpoints used (Stock Screener, Income Statement, Balance Sheet, Cash Flow, Key Metrics, Historical Dividend), rate limiting strategy, error handling, and data quality considerations.

## Advanced Usage

For customization options (threshold adjustment, sector filtering, REIT/financial exclusion, CSV export), see inline comments in `scripts/screen_dividend_stocks.py` around lines 383-430.

## Troubleshooting

| Error | Solution |
|-------|----------|
| `requests library not found` | `pip install requests` |
| `FMP API key required` | `export FMP_API_KEY=your_key` or pass `--fmp-api-key` |
| `FINVIZ API key required` | `export FINVIZ_API_KEY=your_key` or pass `--finviz-api-key`; requires Elite subscription |
| `FINVIZ API authentication failed` | Verify Elite subscription is active; check key format |
| `FINVIZ pre-screening returned no results` | Check connection; fall back to FMP-only mode |
| `Rate limit exceeded` | Script auto-retries after 60s; wait for daily reset or reduce candidate count |
| `No stocks found matching criteria` | Relax thresholds (raise P/E, lower yield/growth requirements) |
| Script runs slowly | Expected: ~0.3s delay per API call for rate limiting; two-stage mode is 3-5x faster |

## Version History

- **v1.1** (November 2025): Added FINVIZ Elite integration for two-stage screening
- **v1.0** (November 2025): Initial release with comprehensive multi-phase screening
