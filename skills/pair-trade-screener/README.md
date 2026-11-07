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
✅ **FMP API integration** - Requires an FMP key; plan access to each endpoint is unverified
✅ **JSON output** - Structured results for further analysis

## Installation

### Prerequisites

- Python 3.9+
- FMP API key with access to the company screener and historical price endpoints (plan limits and tiers are not verified here)

### Install Dependencies

```bash
uv run --with 'statsmodels>=0.14,<0.15' python --version
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
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/find_pairs.py \
  --sector Technology \
  --output /tmp/pair-trade/technology.json

# Analyze specific pair
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/analyze_spread.py \
  --stock-a AAPL \
  --stock-b MSFT
```

The screener creates the requested output parent directory and writes a JSON
object with `metadata` and `pairs`. The analyzer writes its report to stdout.
Invalid thresholds, duplicate symbols, insufficient lookback, missing
`statsmodels`, and file-system errors exit nonzero with a concise message.

### Screening for Pairs

**Sector-Based Screening:**

```bash
# Screen entire sector
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/find_pairs.py --sector Financials --output /tmp/pair-trade/financials.json

# Adjust correlation threshold
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/find_pairs.py --sector Energy --min-correlation 0.75 --output /tmp/pair-trade/energy.json

# Longer lookback period
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/find_pairs.py --sector Healthcare --lookback-days 1095 --output /tmp/pair-trade/healthcare.json
```

**Custom Stock List:**

```bash
# Test specific stocks
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/find_pairs.py --symbols AAPL,MSFT,GOOGL,META,NVDA --output /tmp/pair-trade/technology-leaders.json

# Tech giants pair screening
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/find_pairs.py --symbols JPM,BAC,WFC,C,GS,MS --output /tmp/pair-trade/banks.json
```

**Full Options:**

```bash
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/find_pairs.py \
  --sector Technology \
  --min-correlation 0.70 \
  --min-market-cap 10000000000 \
  --lookback-days 730 \
  --output /tmp/pair-trade/technology.json
```

### Analyzing Individual Pairs

**Basic Analysis:**

```bash
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/analyze_spread.py --stock-a AAPL --stock-b MSFT
```

**Custom Parameters:**

```bash
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/analyze_spread.py \
  --stock-a JPM \
  --stock-b BAC \
  --lookback-days 365 \
  --entry-zscore 2.0 \
  --exit-zscore 0.5
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
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/find_pairs.py --sector Technology --output /tmp/pair-trade/technology.json

# Review top pairs in JSON output
jq '.pairs[] | select(.signal != "NONE")' /tmp/pair-trade/technology.json

# Detailed analysis on top candidates
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/analyze_spread.py --stock-a AAPL --stock-b MSFT
```

### 2. Sector Rotation Pairs

```bash
# Screen multiple sectors
for sector in Technology Financials Healthcare Energy; do
  uv run --with 'statsmodels>=0.14,<0.15' python \
    skills/pair-trade-screener/scripts/find_pairs.py \
    --sector "$sector" \
    --output "/tmp/pair-trade/${sector}_pairs.json"
  sleep 5
done

# Find pairs with strongest signals
jq '.pairs[] | select(.current_zscore | . > 2 or . < -2)' /tmp/pair-trade/*_pairs.json
```

### 3. Monitor Existing Pairs

```bash
# Update z-scores for current positions
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/analyze_spread.py --stock-a XOM --stock-b CVX
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/analyze_spread.py --stock-a JPM --stock-b BAC
uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/analyze_spread.py --stock-a GOOGL --stock-b META
```

## API Usage & Rate Limits

**Request budget (plan limits unverified):**
- About 1 request per stock for price data, more when the dividend-adjusted endpoint is unavailable and the fallback path is used
- Daily quota depends on your FMP plan; check your account

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
- Wait for your plan's daily quota to reset
- Cache screening results (JSON files)
- Upgrade your FMP plan (see FMP pricing)

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
- Historical Price API: `/stable/historical-price-eod/dividend-adjusted` (preferred, `adjClose`), falling back to `/stable/historical-price-eod/full` (unadjusted `close`) and v3
- Stock Screener API: `/stable/company-screener`

**Academic Papers:**
- Engle & Granger (1987): "Co-Integration and Error Correction"
- Gatev et al. (2006): "Pairs Trading: Performance of a Relative-Value Arbitrage Rule"

## License

Educational and research use. Trade at your own risk. Past performance does not guarantee future results.

---

**Version:** 1.0
**Last Updated:** 2025-11-08
**Dependencies:** Python 3.9+, pandas, numpy, scipy, requests, `statsmodels>=0.14,<0.15`
**API:** FMP API (key required; plan access unverified)
