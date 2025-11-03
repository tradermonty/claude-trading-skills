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

## Top 20 Stocks Ranked by Composite Score

| Rank | Symbol | Company | Yield | P/E | Div Growth | Score |
|------|--------|---------|-------|-----|------------|-------|
| 1 | [TICKER] | [Name] | [%] | [X.X] | [%] | [XX.X] |
| ... |

---

## Detailed Analysis

### 1. [SYMBOL] - [Company Name] (Score: XX.X)

**Sector:** [Sector Name]
**Market Cap:** $[X.XX]B
**Current Price:** $[XX.XX]

**Valuation Metrics:**
- Dividend Yield: [X.X]%
- P/E Ratio: [XX.X]
- P/B Ratio: [X.X]

**Growth Profile (3-Year):**
- Dividend CAGR: [X.X]% [✓ Consistent / ⚠ One cut]
- Revenue CAGR: [X.X]%
- EPS CAGR: [X.X]%

**Dividend Sustainability:**
- Payout Ratio: [XX]%
- FCF Payout Ratio: [XX]%
- Status: [✓ Sustainable / ⚠ Monitor / ❌ Risk]

**Financial Health:**
- Debt-to-Equity: [X.XX]
- Current Ratio: [X.XX]
- Status: [✓ Healthy / ⚠ Caution]

**Quality Metrics:**
- ROE: [XX]%
- Net Profit Margin: [XX]%
- Quality Score: [XX]/100

**Investment Considerations:**
- [Key strength 1]
- [Key strength 2]
- [Risk factor or consideration]

---

[Repeat for other top stocks]

---

## Portfolio Construction Guidance

**Diversification Recommendations:**
- Sector breakdown of top 20 results
- Suggested allocation strategy
- Concentration risk warnings

**Monitoring Recommendations:**
- Key metrics to track quarterly
- Warning signs for each position
- Rebalancing triggers

**Risk Considerations:**
- Market cap concentration
- Sector biases in results
- Economic sensitivity warnings
```

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

Anticipate common user questions:

**"Why did [stock] not make the list?"**
- Check which criteria it failed (yield, valuation, growth, sustainability)
- Explain the specific filter that excluded it

**"Can I screen for specific sectors?"**
- Filtering capability exists in script (modify line 383-388)
- Suggest re-running with sector parameter additions

**"What if I want higher/lower yield threshold?"**
- Script parameters are adjustable
- Trade-offs between yield and growth
- Recommend re-screening with new parameters

**"How often should I re-run this screen?"**
- Quarterly recommended (aligns with earnings cycles)
- Semi-annually sufficient for long-term holders
- Market conditions may warrant more frequent checks

**"How many stocks should I buy?"**
- Diversification guidance: minimum 10-15 for dividend portfolio
- Sector balance considerations
- Position sizing based on risk tolerance

## Resources

### scripts/screen_dividend_stocks.py

Comprehensive screening script that:
- Interfaces with FMP API for data retrieval
- Implements multi-phase filtering logic
- Calculates growth rates (CAGR) over 3-year periods
- Evaluates dividend sustainability via payout ratios and FCF coverage
- Assesses financial health (debt-to-equity, current ratio)
- Computes quality scores (ROE, profit margins)
- Ranks stocks by composite scoring system
- Outputs structured JSON results

**Dependencies:** `requests` library (install via `pip install requests`)

**Rate limiting:** Built-in delays to respect FMP API limits (250 requests/day free tier)

**Error handling:** Graceful degradation for missing data, rate limit retries, API errors

### references/screening_methodology.md

Comprehensive documentation of screening approach:

**Phase 1: Initial Quantitative Filters**
- Dividend yield >= 3.5% rationale and calculation
- P/E ratio <= 20 threshold justification
- P/B ratio <= 2 valuation logic

**Phase 2: Growth Quality Filters**
- Dividend growth (3-year CAGR >= 5%)
- Revenue positive trend analysis
- EPS positive trend analysis

**Phase 3: Quality & Sustainability Analysis**
- Dividend sustainability metrics (payout ratios, FCF coverage)
- Financial health indicators (D/E, current ratio)
- Quality scoring methodology (ROE, profit margins)

**Composite Scoring System (0-100 points)**
- Score component breakdown and weighting
- Interpretation guidelines

**Investment Philosophy**
- Why this approach works
- What this strategy avoids (dividend traps, value traps)
- Ideal candidate profile

**Usage Notes & Limitations**
- Best practices for portfolio construction
- When to sell criteria
- Historical context for threshold selection

### references/fmp_api_guide.md

Complete guide for Financial Modeling Prep API:

**API Key Setup**
- Obtaining free API key
- Setting environment variables
- Free tier limits (250 requests/day)

**Key Endpoints Used**
- Stock Screener API
- Income Statement API
- Balance Sheet API
- Cash Flow Statement API
- Key Metrics API
- Historical Dividend API

**Rate Limiting Strategy**
- Built-in protection in script
- Request budget management
- Best practices for free tier

**Error Handling**
- Common errors and solutions
- Debugging techniques

**Data Quality Considerations**
- Data freshness and gaps
- Data accuracy caveats
- When to verify with SEC filings

## Advanced Usage

### Customizing Screening Criteria

Modify thresholds in `scripts/screen_dividend_stocks.py`:

**Line 383-388** - Initial screening parameters:
```python
candidates = client.screen_stocks(
    dividend_yield_min=3.5,  # Adjust yield threshold
    pe_max=20,               # Adjust P/E threshold
    pb_max=2,                # Adjust P/B threshold
    market_cap_min=2_000_000_000  # Minimum $2B market cap
)
```

**Line 423** - Dividend CAGR threshold:
```python
if not div_cagr or div_cagr < 5.0:  # Adjust growth threshold
```

### Sector-Specific Screening

Add sector filtering after initial screening:

```python
# Filter for specific sectors
target_sectors = ['Consumer Defensive', 'Utilities', 'Healthcare']
candidates = [s for s in candidates if s.get('sector') in target_sectors]
```

### Excluding REITs and Financials

REITs and financial stocks have different dividend characteristics (higher payouts, different metrics):

```python
# Exclude REITs and Financials
exclude_sectors = ['Real Estate', 'Financial Services']
candidates = [s for s in candidates if s.get('sector') not in exclude_sectors]
```

### Exporting to CSV

Convert JSON results to CSV for Excel analysis:

```python
import json
import csv

with open('dividend_screener_results.json', 'r') as f:
    data = json.load(f)

stocks = data['stocks']

with open('screening_results.csv', 'w', newline='') as csvfile:
    if stocks:
        fieldnames = stocks[0].keys()
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stocks)
```

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

### API Call Comparison

**Two-Stage Screening (FINVIZ + FMP):**
- FINVIZ: 1 API call
- FMP Quote API: ~30-50 calls (one per pre-screened symbol)
- FMP Financial Data: ~150-250 calls (5 endpoints × 30-50 symbols)
- **Total FMP calls: ~180-300**

**FMP-Only Screening:**
- FMP Stock Screener: 1 call (returns 100-1000 stocks)
- FMP Financial Data: ~500-5000 calls (5 endpoints × 100-1000 symbols)
- **Total FMP calls: ~500-5000**

**Savings: 60-94% reduction in FMP API usage**

### Cost Analysis

**FINVIZ Elite:**
- Monthly: $39.99
- Annual: $329.99 (~$27.50/month)

**FMP API:**
- Free tier: 250 calls/day (sufficient for two-stage screening)
- Starter tier: $29.99/month for 750 calls/day
- Professional tier: $79.99/month for 2000 calls/day

**Recommendation:**
- **For free FMP tier users**: Use two-stage screening (FINVIZ + FMP free tier)
- **For paid FMP tier users**: Either approach works; two-stage is faster
- **Budget option**: FMP-only with free tier (run screening every few days)
- **Optimal option**: FINVIZ Elite ($330/year) + FMP free tier = Complete solution

## Version History

- **v1.1** (November 2025): Added FINVIZ Elite integration for two-stage screening
- **v1.0** (November 2025): Initial release with comprehensive multi-phase screening
