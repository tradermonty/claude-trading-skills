---
name: dividend-growth-pullback-screener
description: "Use when the user asks about dividend stocks to buy, income investing opportunities, undervalued dividend payers, dividend aristocrats on sale, passive income stocks, DGI strategies, or finding dividend growth stocks during pullbacks. Finds high-quality dividend growth stocks (12%+ annual dividend growth, 1.5%+ yield) experiencing temporary pullbacks via RSI oversold conditions (RSI ≤40). Combines fundamental dividend analysis with technical timing indicators to identify buying opportunities in strong dividend growers during short-term weakness."
---

# Dividend Growth Pullback Screener

## Overview

Screens for dividend growth stocks with strong fundamentals but temporary technical weakness — exceptional dividend growth rates (12%+ CAGR) pulled back to RSI oversold levels (≤40), creating entry opportunities for long-term dividend growth investors.

## When to Use

- Dividend growth stocks with 12%+ dividend CAGR during pullbacks
- Entry opportunities in quality names during market weakness or sector rotations
- Total return focus over 5-10 years, accepting lower current yields (1.5-3%)

**Do NOT use for:** high current income needs (use value-dividend-screener), yields >3%, deep value plays, or short-term trading (<6 months)

## Screening Workflow

### Step 1: Set API Keys

#### Two-Stage Approach (RECOMMENDED)

For optimal performance, use FINVIZ Elite API for pre-screening + FMP API for detailed analysis:

```bash
# Set both API keys as environment variables
export FMP_API_KEY=your_fmp_key_here
export FINVIZ_API_KEY=your_finviz_key_here
```

**Why Two-Stage?**
- **FINVIZ**: Fast pre-screening with RSI filter (1 API call → ~10-50 candidates)
- **FMP**: Detailed fundamental analysis only on pre-screened candidates
- **Result**: Analyze more stocks with fewer FMP API calls (stays within free tier limits)

#### FMP-Only Approach (Original Method)

If you don't have FINVIZ Elite access:

```bash
export FMP_API_KEY=your_key_here
```

**Limitation**: FMP free tier (250 requests/day) limits analysis to ~40 stocks. Use `--max-candidates 40` to stay within limits.

### Step 2: Execute Screening

**Two-Stage Screening (RECOMMENDED):**

```bash
cd dividend-growth-pullback-screener/scripts
python3 screen_dividend_growth_rsi.py --use-finviz
```

This executes:
1. FINVIZ pre-screen: Dividend yield 0.5-3%, Dividend growth 10%+, EPS growth 5%+, Sales growth 5%+, RSI <40
2. FMP detailed analysis: Verify 12%+ dividend CAGR, calculate exact RSI, analyze fundamentals

**FMP-Only Screening:**

```bash
python3 screen_dividend_growth_rsi.py --max-candidates 40
```

**Customization Options:**

```bash
# Two-stage with custom parameters
python3 screen_dividend_growth_rsi.py --use-finviz --min-yield 2.0 --min-div-growth 15.0 --rsi-max 35

# FMP-only with custom parameters
python3 screen_dividend_growth_rsi.py --min-yield 2.0 --min-div-growth 10.0 --max-candidates 30

# Provide API keys as arguments (instead of environment variables)
python3 screen_dividend_growth_rsi.py --use-finviz --fmp-api-key YOUR_FMP_KEY --finviz-api-key YOUR_FINVIZ_KEY
```

### Step 3: Review Results

The script generates two outputs:

1. **JSON file:** `dividend_growth_pullback_results_YYYY-MM-DD.json`
   - Structured data with all metrics for further analysis
   - Includes dividend growth rates, RSI values, financial health metrics

2. **Markdown report:** `dividend_growth_pullback_screening_YYYY-MM-DD.md`
   - Human-readable analysis with stock profiles
   - Scenario-based probability assessments
   - Entry timing recommendations

### Step 4: Analyze Qualified Stocks

For each qualified stock, the report includes:

**Dividend Growth Profile:**
- Current yield and annual dividend
- 3-year dividend CAGR and consistency
- Payout ratio and sustainability assessment

**Technical Timing:**
- Current RSI value (≤40 = oversold)
- RSI context (extreme oversold <30 vs. early pullback 30-40)
- Price action relative to recent trend

**Quality Metrics:**
- Revenue and EPS growth (confirms business momentum)
- Financial health (debt levels, liquidity ratios)
- Profitability (ROE, profit margins)

**Investment Recommendation:**
- Entry timing assessment (immediate vs. wait for confirmation)
- Risk factors specific to the stock
- Upside scenarios based on dividend growth compounding

## Screening Criteria Details

### Phase 1: Fundamental Screening (FMP API)

**Initial Filter:**
- Dividend Yield ≥ 1.5% (calculated from actual dividend payments)
- Market Cap ≥ $2 billion (liquidity and stability)
- Exchange: NYSE, NASDAQ (excludes OTC/pink sheets)

**Dividend Growth Analysis:**
- 3-Year Dividend CAGR ≥ 12% (doubles dividend in 6 years)
- Dividend Consistency: No cuts in past 4 years
- Payout Ratio < 100% (sustainability check)

**Financial Health:**
- Positive revenue growth over 3 years
- Positive EPS growth over 3 years
- Debt-to-Equity < 2.0 (manageable leverage)
- Current Ratio > 1.0 (liquidity)

### Phase 2: Technical Screening (RSI Calculation)

**RSI Calculation:**
- 14-period RSI using daily closing prices
- Formula: RSI = 100 - (100 / (1 + RS))
  - RS = Average Gain / Average Loss over 14 periods
- Data source: FMP historical prices (past 30 days)

**RSI Filter:**
- RSI ≤ 40 (oversold/pullback condition)
- RSI interpretation:
  - < 30: Extreme oversold (potential reversal)
  - 30-40: Early pullback (uptrend correction)
  - > 40: Not oversold (excluded)

### Phase 3: Ranking and Output

**Composite Scoring (0-100):**
- Dividend Growth (40%): Reward higher CAGR and consistency
- Financial Quality (30%): ROE, profit margins, debt levels
- Technical Setup (20%): Lower RSI = better entry opportunity
- Valuation (10%): P/E and P/B for context (not exclusionary)

Stocks ranked by composite score. Top scorers combine exceptional dividend growth with attractive technical entry points.

## Understanding the Results

### Interpreting RSI Levels

**RSI 25-30 (Extreme Oversold):**
- Often indicates panic selling or negative news
- Higher risk but potentially highest reward
- Recommended: Wait for RSI to turn up (sign of stabilization)
- Entry: Scale in with 50% position, add on RSI >30

**RSI 30-35 (Strong Oversold):**
- Normal correction in strong uptrend
- Lower risk than extreme oversold
- Recommended: Can initiate position immediately
- Entry: Full position acceptable, set stop loss 5-8% below

**RSI 35-40 (Early Pullback):**
- Mild weakness in uptrend
- Lowest risk of further decline
- Recommended: Conservative entry for high conviction stocks
- Entry: Full position, tight stop loss 3-5% below

## Troubleshooting

### No Results Found

**Possible Causes:**
1. **Market conditions:** Strong bull market with few oversold stocks
2. **Criteria too strict:** 12% dividend growth is rare (5-10 stocks typically qualify)
3. **RSI threshold too low:** Consider raising to RSI ≤45 for more candidates

**Solutions:**
- Relax RSI threshold: `--rsi-max 45` (early pullback phase)
- Lower dividend growth: `--min-div-growth 10.0` (still excellent growth)
- Lower minimum yield: `--min-yield 1.0` (capture more growth stocks)

### API Rate Limit Reached

**FMP Free Tier Limits:**
- 250 requests/day
- Each stock analyzed requires 6 API calls (quote, dividend, prices, income, balance, cashflow, metrics)
- Maximum ~40 stocks per day in FMP-only mode

**Solutions:**

**1. Use FINVIZ Two-Stage Approach (RECOMMENDED)**
```bash
python3 screen_dividend_growth_rsi.py --use-finviz
```
- FINVIZ pre-screening: 1 API call → 10-50 candidates (already filtered by RSI)
- FMP analysis: 6 calls × 10-50 stocks = 60-300 FMP calls
- **Advantage**: FINVIZ RSI filter dramatically reduces candidates, staying within FMP limits

**2. Limit FMP-Only Candidates**
```bash
python3 screen_dividend_growth_rsi.py --max-candidates 40
```

**3. Wait 24 Hours for Rate Limit Reset**
- FMP resets at UTC midnight

**4. Upgrade to FMP Paid Plan**
- Starter ($14/month): 500 requests/day
- Professional ($29/month): 1,000 requests/day

**Note:** FINVIZ Elite subscription ($40/month) + FMP free tier is more cost-effective than FMP paid plans for this use case.

### RSI Calculation Errors

**Issue:** "Insufficient price data for RSI calculation"

**Cause:** Stock has less than 30 days of trading history (IPO or inactive)

**Solution:** Script automatically skips stocks with insufficient data. No action needed.

## Combining with Other Skills

**Pre-Screening Context:**
1. **Market News Analyst** → Identify sector rotations or market pullbacks
2. **Breadth Chart Analyst** → Confirm broader market oversold conditions
3. **Economic Calendar Fetcher** → Check for upcoming rate decisions or macro events

**Post-Screening Analysis:**
1. **Technical Analyst** → Analyze individual stock charts for qualified candidates
2. **US Stock Analysis** → Deep dive on specific stocks before entry
3. **Backtest Expert** → Validate RSI + dividend growth strategy historically

**Example Workflow:**
```
1. Market News Analyst: "Market pulled back 5% this week on Fed hawkish comments"
2. Breadth Chart Analyst: Confirms market oversold (S&P breadth weak)
3. Dividend Growth Pullback Screener: Finds 8 quality dividend growers with RSI <35
4. Technical Analyst: Analyze top 3 candidates for support levels and entry timing
5. Execute: Enter scaled positions with 6-12 month time horizon
```

## Resources

### scripts/

**screen_dividend_growth_rsi.py** - Main screening script
- Integrates FMP API for fundamental data
- Calculates 14-period RSI from historical prices
- Applies multi-phase filtering and ranking
- Outputs JSON and markdown reports

### references/

**rsi_oversold_strategy.md** - RSI indicator explanation
- How RSI identifies oversold conditions
- Difference between extreme oversold (<30) vs. early pullback (30-40)
- Combining RSI with fundamental analysis
- False positive management and risk mitigation

**dividend_growth_compounding.md** - Dividend growth mathematics
- Power of 12%+ dividend CAGR over time
- Yield vs. growth trade-offs
- Historical examples (MSFT, V, MA, AAPL)
- Quality characteristics of dividend growth stocks

**fmp_api_guide.md** - API usage documentation
- API key setup and management
- Endpoint documentation for screening
- Rate limiting strategies
- Error handling and troubleshooting

---

**Disclaimer:** This screening tool is for informational purposes only. Past dividend growth does not guarantee future performance. Conduct thorough due diligence before making investment decisions. RSI oversold conditions do not guarantee price reversals - stocks can remain oversold for extended periods.
