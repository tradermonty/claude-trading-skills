---
name: value-dividend-screener
description: Screen US stocks for high-quality dividend opportunities combining value characteristics (P/E ratio under 20, P/B ratio under 2), attractive yields (3% or higher), and consistent growth (dividend/revenue/EPS trending up over 3 years). Supports two-stage screening using FINVIZ Elite API for efficient pre-filtering followed by FMP API for detailed analysis. Use when user requests dividend stock screening, income portfolio ideas, or quality value stocks with strong fundamentals.
---

# Value Dividend Screener

## Overview

This skill identifies high-quality dividend stocks that combine value characteristics, attractive income generation, and consistent growth using a **two-stage screening approach**:

1. **FINVIZ Elite API (Optional but Recommended)**: Pre-screen stocks with basic criteria (fast, cost-effective)
2. **Financial Modeling Prep (FMP) API**: Detailed fundamental analysis of candidates

Screen US equities based on quantitative criteria including valuation ratios, dividend metrics, financial health, and profitability. Generate comprehensive reports ranking stocks by composite quality scores with detailed fundamental analysis.

**Efficiency Advantage**: Using FINVIZ pre-screening can reduce FMP API calls by 90%, making this approach ideal for free-tier API users.

## When to Use

Invoke this skill when the user requests:
- "Find high-quality dividend stocks"
- "Screen for value dividend opportunities"
- "Show me stocks with strong dividend growth"
- "Find income stocks trading at reasonable valuations"
- "Screen for sustainable high-yield stocks"
- Any request combining dividend yield, valuation metrics, and fundamental analysis

## Prerequisites

- **FMP API key:** Required. Set `FMP_API_KEY` or pass `--fmp-api-key`.
- **FINVIZ Elite API key:** Recommended, not required. Set `FINVIZ_API_KEY` or pass `--finviz-api-key` and use `--use-finviz` for two-stage screening. Without it the screener runs FMP-only and uses more API calls.
- **Python:** 3.9+ with `requests>=2.31.0` (see `requirements.txt`).

## Workflow

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
- Sustainability: `payout_ratio`, `fcf_payout_ratio`, `fcf_amount`, `fcf_status`, `fcf_coverage_status`, `sustainability_basis`, `dividend_sustainable`, `sustainability_bonus`, `sustainability_note`
- Financial health: `debt_to_equity`, `current_ratio`, `financially_healthy`
- Quality: `roe`, `profit_margin`, `quality_score`
- Overall ranking: `composite_score`

### Step 4: Generate Markdown Report

Create structured markdown report for user with following sections:

#### Report Structure

Read `references/report_template.md` for the full markdown report template.

In the human report, keep observed FCF and dividend coverage separate. Negative FCF means an observed shortfall; zero FCF means no cash coverage; `MISSING_DATA` means the source fields were unavailable. None proves a future dividend cut. `AT_LIMIT` means FCF equals dividends with no buffer and earns no bonus. For confirmed REITs, use FFO as the decision basis and show FCF status as context even when it is negative; do not apply FFO treatment to a company solely because its sector is Real Estate. Copy `sustainability_note` into the explanation rather than replacing an unknown status with a sustainability claim.

### Step 5: Provide Context and Methodology

Reference screening methodology when explaining results:

**Key concepts to explain:**
- Why these specific thresholds (3.5% yield, P/E 20, P/B 2)
- Importance of dividend growth vs. static high yield
- How composite score balances value, growth, and quality
- Dividend sustainability vs. dividend trap distinction
- Financial health metrics significance

Load `references/screening_methodology.md` to provide detailed explanations of:
- Phase 1: Initial quantitative filters
- Phase 2: Growth quality filters
- Phase 3: Sustainability and quality analysis
- Composite scoring system
- Investment philosophy and limitations

### Step 6: Answer Follow-up Questions

Read `references/follow_up_questions.md` for answers to common follow-up questions.

## Resources

Read `references/resource_descriptions.md` for the description of the screening script and of each reference file.

## Advanced Usage

Read `references/advanced_usage.md` to customize criteria, screen a sector, exclude REITs and financials or export CSV.

## Troubleshooting

### "ERROR: requests library not found"
**Solution:** Install requests library
```bash
pip install requests
```

### "ERROR: FMP API key required"
**Solution:** Set environment variable or provide via command-line
```bash
export FMP_API_KEY=your_key_here
# OR
python3 scripts/screen_dividend_stocks.py --fmp-api-key your_key_here
```

### "ERROR: FINVIZ API key required when using --use-finviz"
**Solution:** Set environment variable or provide via command-line
```bash
export FINVIZ_API_KEY=your_key_here
# OR
python3 scripts/screen_dividend_stocks.py --use-finviz --finviz-api-key your_key_here
```

**Note:** FINVIZ Elite subscription required (~$40/month or ~$330/year)

### "ERROR: FINVIZ API authentication failed"
**Possible causes:**
1. Invalid FINVIZ API key
2. FINVIZ Elite subscription expired
3. API key format incorrect

**Solution:**
- Verify FINVIZ Elite subscription is active
- Check API key for typos (should be alphanumeric string)
- Log into FINVIZ Elite account and verify API key in settings
- Try accessing FINVIZ Elite screener manually to confirm subscription

### "ERROR: FINVIZ pre-screening failed or returned no results"
**Possible causes:**
1. FINVIZ API connection issue
2. Screening criteria too restrictive (no stocks match)
3. Market conditions (bear market may yield fewer results)

**Solution:**
- Check internet connection
- Verify FINVIZ Elite website is accessible
- Try FMP-only method as fallback:
  ```bash
  python3 scripts/screen_dividend_stocks.py
  ```

### "WARNING: Rate limit exceeded"
**Solution:** Script automatically retries after 60 seconds. If persistent:
- Wait until next day (free tier resets daily)
- Reduce number of stocks analyzed (modify line 394 limit)
- Consider upgrading to paid FMP tier

### "No stocks found matching all criteria"
**Solution:** Criteria may be too restrictive
- Relax P/E threshold (increase from 20)
- Lower dividend yield requirement (decrease from 3.5%)
- Reduce dividend growth requirement (decrease from 5%)
- Check market conditions (bear markets may have fewer qualifiers)

### Script runs slowly
**Expected behavior:** Script includes 0.3s delay between API calls for rate limiting
- 100 stocks analyzed = ~8-10 minutes
- First 20-30 qualifying stocks usually found within first 50-70 analyzed

## Performance & Cost Optimization

Read `references/performance_and_cost.md` for API call comparison and cost analysis.

## Version History

- **v1.1** (November 2025): Added FINVIZ Elite integration for two-stage screening
- **v1.0** (November 2025): Initial release with comprehensive multi-phase screening


## Shared FMP client

FMP data access uses the bundled generated `scripts/fmp_client.py`. Existing CLI
key/environment precedence, financial calculations and successful output shapes
are preserved. The migrated paths use stable endpoints only; a denied or failed
stable request does not fall back to retired v3 URLs. The shared client masks raw
and URL-encoded key echoes, retries malformed JSON once, and retries a 429 once
with a 60-second wait before stopping on a repeated rate limit. FINVIZ, where
used, remains a separate client.
