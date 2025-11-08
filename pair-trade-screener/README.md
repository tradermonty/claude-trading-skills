# Pair Trade Screener

Statistical arbitrage tool for identifying and analyzing pair trading opportunities using cointegration testing and mean-reversion analysis.

## Overview

The Pair Trade Screener finds statistically significant pair trading opportunities by:
- Testing for cointegration (long-term equilibrium relationships)
- Calculating hedge ratios (beta values)
- Measuring mean-reversion speed (half-life)
- Generating entry/exit signals based on z-score thresholds

**Market Neutral Strategy:** Profit from relative price movements regardless of overall market direction.

## Features

✅ **Sector-wide screening** - Analyze all stocks in a sector
✅ **Custom pair analysis** - Test specific stock combinations
✅ **Statistical rigor** - Cointegration tests (ADF), correlation analysis
✅ **Mean-reversion metrics** - Half-life calculation, z-score tracking
✅ **Trade signals** - Automatic entry/exit recommendations
✅ **FMP API integration** - Free tier sufficient for screening
✅ **JSON output** - Structured results for further analysis

## Installation

### Prerequisites

- Python 3.8+
- FMP API key (free tier: 250 requests/day)

### Install Dependencies

```bash
pip install pandas numpy scipy statsmodels requests
```

### Get FMP API Key

1. Visit: https://financialmodelingprep.com/developer/docs
2. Sign up for free account
3. Copy your API key
4. Set environment variable:

```bash
export FMP_API_KEY="your_key_here"
```

Or add to `~/.bashrc` / `~/.zshrc` for persistence.

## Usage

### Quick Start

```bash
# Screen Technology sector for pairs
python scripts/find_pairs.py --sector Technology

# Analyze specific pair
python scripts/analyze_spread.py --stock-a AAPL --stock-b MSFT
```

### Screening for Pairs

**Sector-Based Screening:**

```bash
# Screen entire sector
python scripts/find_pairs.py --sector Financials

# Adjust correlation threshold
python scripts/find_pairs.py --sector Energy --min-correlation 0.75

# Longer lookback period
python scripts/find_pairs.py --sector Healthcare --lookback-days 1095
```

**Custom Stock List:**

```bash
# Test specific stocks
python scripts/find_pairs.py --symbols AAPL,MSFT,GOOGL,META,NVDA

# Tech giants pair screening
python scripts/find_pairs.py --symbols JPM,BAC,WFC,C,GS,MS
```

**Full Options:**

```bash
python scripts/find_pairs.py \
  --sector Technology \
  --min-correlation 0.70 \
  --min-market-cap 10000000000 \
  --lookback-days 730 \
  --output tech_pairs.json \
  --api-key YOUR_KEY
```

### Analyzing Individual Pairs

**Basic Analysis:**

```bash
python scripts/analyze_spread.py --stock-a AAPL --stock-b MSFT
```

**Custom Parameters:**

```bash
python scripts/analyze_spread.py \
  --stock-a JPM \
  --stock-b BAC \
  --lookback-days 365 \
  --entry-zscore 2.0 \
  --exit-zscore 0.5 \
  --api-key YOUR_KEY
```

## Example Output

### Pair Screening Results

```
PAIR TRADING SCREEN SUMMARY
==========================================================================

Total pairs analyzed: 45
Cointegrated pairs: 12
Pairs with trade signals: 5

==========================================================================
ACTIVE TRADE SIGNALS
==========================================================================

Pair: XOM/CVX
  Signal: LONG
  Z-Score: -2.35
  Correlation: 0.9421
  P-Value: 0.0012
  Half-Life: 28.3 days
  Strength: ★★★
```

### Individual Pair Analysis

```
PAIR TRADE ANALYSIS: AAPL / MSFT
==========================================================================

[ PAIR STATISTICS ]
  Correlation: 0.8732
  Hedge Ratio (Beta): 1.1523
  Data Points: 365

[ COINTEGRATION TEST ]
  ADF Statistic: -3.8542
  P-value: 0.0028
  Result: ✅ COINTEGRATED (p < 0.05)
  Strength: ★★★ Very Strong

[ MEAN REVERSION ]
  Half-Life: 42.1 days
  Speed: Moderate (suitable for pair trading)

[ Z-SCORE ]
  Current Z-Score: -2.13
  Historical Range: [-3.45, 3.12]

[ TRADE SIGNAL ]
  Signal: 🔺 LONG SPREAD
  Action: Long AAPL, Short MSFT
  Rationale: Z-score = -2.13 → AAPL cheap relative to MSFT

[ POSITION SIZING ]
  Example Allocation: $10,000
  LONG AAPL: $5,000 (27 shares @ $185.50)
  SHORT MSFT: $5,762 (14 shares @ $411.25)

  Exit Conditions:
    - Primary: Z-score crosses 0 (mean reversion)
    - Stop Loss: Z-score > ±3.0
    - Time-based: No reversion after 90 days
```

## Understanding the Metrics

### Correlation
- **Range:** -1 to +1
- **Threshold:** ≥ 0.70 required
- **Interpretation:** Higher = stronger co-movement

### Cointegration P-Value
- **Range:** 0 to 1
- **Threshold:** < 0.05 required (statistically significant)
- **Interpretation:** Lower = stronger cointegration
  - p < 0.01: ★★★ Very strong
  - p 0.01-0.05: ★★ Moderate
  - p > 0.05: ☆ Not cointegrated (reject)

### Half-Life
- **Meaning:** Time for spread to revert halfway to mean
- **Fast:** < 30 days (ideal for short-term trading)
- **Moderate:** 30-60 days (standard pair trading)
- **Slow:** > 60 days (long-term positions)

### Z-Score
- **Calculation:** (Current Spread - Mean) / Std Dev
- **Entry Signals:**
  - Z > +2.0: Short spread (Short A, Long B)
  - Z < -2.0: Long spread (Long A, Short B)
- **Exit:** Z crosses 0 (mean reversion)
- **Stop:** |Z| > 3.0 (extreme divergence)

### Hedge Ratio (Beta)
- **Meaning:** Dollar amount of Stock B per $1 of Stock A
- **Example:** Beta = 1.2 → Short $1,200 of B for every $1,000 long in A
- **Purpose:** Market-neutral positioning (net beta ≈ 0)

## Common Workflows

### 1. Weekly Pair Screening

```bash
# Monday: Screen for new opportunities
python scripts/find_pairs.py --sector Technology --output tech_pairs.json

# Review top pairs in JSON output
cat tech_pairs.json | jq '.pairs[] | select(.signal != "NONE")'

# Detailed analysis on top candidates
python scripts/analyze_spread.py --stock-a AAPL --stock-b MSFT
```

### 2. Sector Rotation Pairs

```bash
# Screen multiple sectors
for sector in Technology Financials Healthcare Energy; do
  python scripts/find_pairs.py --sector $sector --output ${sector}_pairs.json
  sleep 5
done

# Find pairs with strongest signals
cat *_pairs.json | jq '.pairs[] | select(.current_zscore | . > 2 or . < -2)'
```

### 3. Monitor Existing Pairs

```bash
# Update z-scores for current positions
python scripts/analyze_spread.py --stock-a XOM --stock-b CVX
python scripts/analyze_spread.py --stock-a JPM --stock-b BAC
python scripts/analyze_spread.py --stock-a GOOGL --stock-b META
```

## API Usage & Rate Limits

**Free Tier:**
- 250 API requests/day
- ~2 requests per stock for price data
- Can screen ~60 stocks/day (= 1,770 pairs)

**Screening Costs:**
```
Sector screening (30 stocks):
  - Fetch 30 stock prices = 30 requests
  - Analyze 435 pairs (30 choose 2) = 0 additional requests
  - Total: 30 requests

Individual pair analysis:
  - Fetch 2 stock prices = 2 requests
```

**Tips:**
- Run sector screens once/week (not daily)
- Cache results in JSON files
- Monitor specific pairs daily (2 requests each)
- Upgrade to paid plan if screening multiple sectors daily

## Interpretation Guide

### When to Trade

✅ **Strong Pair (Enter):**
- Correlation > 0.80
- P-value < 0.03
- Half-life 20-60 days
- |Z-score| > 2.0
- Economic linkage (same sector/industry)

⚠️ **Marginal Pair (Caution):**
- Correlation 0.70-0.80
- P-value 0.03-0.05
- Half-life > 60 days
- |Z-score| 1.5-2.0

❌ **Weak Pair (Avoid):**
- Correlation < 0.70
- P-value > 0.05
- Half-life > 90 days or undefined
- No economic linkage

### Exit Conditions

**Primary Exit:**
- Z-score crosses 0 (spread reverts to mean)
- Close both legs simultaneously

**Stop Loss:**
- |Z-score| > 3.0 (extreme divergence, possible structural break)
- -5% loss on spread
- Exit immediately

**Time-Based:**
- No mean reversion after 90 days (or 3× half-life)
- Free capital for better opportunities

## Troubleshooting

### No pairs found

**Solutions:**
- Lower `--min-correlation` to 0.65
- Expand stock universe (try different sector)
- Increase `--lookback-days` to 1095 (3 years)

### API rate limit exceeded

**Solutions:**
- Wait 24 hours (free tier resets daily)
- Cache screening results (JSON files)
- Upgrade to paid plan ($14/mo Starter tier)

### All z-scores near zero

**Normal:** Pairs in equilibrium, no trade signals
**Action:** Check back later or expand universe

### Pair correlation broke down

**Causes:** Corporate events, M&A, business model changes
**Detection:** Recent correlation << historical correlation
**Action:** Exit pair, remove from watchlist

## Integration with Other Skills

**Backtest Expert:**
- Test pair trading strategies historically
- Optimize entry/exit thresholds
- Validate robustness

**Sector Analyst:**
- Identify sectors in rotation
- Screen for pairs within leading sectors

**Technical Analyst:**
- Confirm individual stock trends
- Check support/resistance before entry

**Portfolio Manager:**
- Track multiple pair positions
- Monitor overall market-neutral exposure

## Resources

**Documentation:**
- `references/methodology.md` - Statistical arbitrage theory
- `references/cointegration_guide.md` - Cointegration testing guide

**FMP API:**
- API Docs: https://financialmodelingprep.com/developer/docs
- Historical Price API: `/v3/historical-price-full/{symbol}`
- Stock Screener API: `/v3/stock-screener`

**Academic Papers:**
- Engle & Granger (1987): "Co-Integration and Error Correction"
- Gatev et al. (2006): "Pairs Trading: Performance of a Relative-Value Arbitrage Rule"

## License

Educational and research use. Trade at your own risk. Past performance does not guarantee future results.

---

**Version:** 1.0
**Last Updated:** 2025-11-08
**Dependencies:** Python 3.8+, pandas, numpy, scipy, statsmodels, requests
**API:** FMP API (free tier sufficient)
