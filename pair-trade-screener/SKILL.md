---
name: pair-trade-screener
description: Statistical arbitrage tool for identifying and analyzing pair trading opportunities. Detects cointegrated stock pairs within sectors, analyzes spread behavior, calculates z-scores, and provides entry/exit recommendations for market-neutral strategies. Use when user requests pair trading opportunities, statistical arbitrage screening, mean-reversion strategies, or market-neutral portfolio construction. Supports correlation analysis, cointegration testing, and spread backtesting.
---

# Pair Trade Screener

## Overview

This skill identifies and analyzes statistical arbitrage opportunities through pair trading. Pair trading is a market-neutral strategy that profits from the relative price movements of two correlated securities, regardless of overall market direction. The skill uses rigorous statistical methods including correlation analysis and cointegration testing to find robust trading pairs.

**Core Methodology:**
- Identify pairs of stocks with high correlation and similar sector/industry exposure
- Test for cointegration (long-term statistical relationship)
- Calculate spread z-scores to identify mean-reversion opportunities
- Generate entry/exit signals based on statistical thresholds
- Provide position sizing for market-neutral exposure

**Key Advantages:**
- Market-neutral: Profits in up, down, or sideways markets
- Risk management: Limited exposure to broad market movements
- Statistical foundation: Data-driven, not discretionary
- Diversification: Uncorrelated to traditional long-only strategies

## When to Use This Skill

Use this skill when:
- User asks for "pair trading opportunities"
- User wants "market-neutral strategies"
- User requests "statistical arbitrage screening"
- User asks "which stocks move together?"
- User wants to hedge sector exposure
- User requests mean-reversion trade ideas
- User asks about relative value trading

Example user requests:
- "Find pair trading opportunities in the tech sector"
- "Which stocks are cointegrated?"
- "Screen for statistical arbitrage opportunities"
- "Find mean-reversion pairs"
- "What are good market-neutral trades right now?"

## Analysis Workflow

### Step 1: Define Pair Universe

**Objective:** Establish the pool of stocks to analyze for pair relationships.

**Option A: Sector-Based Screening (Recommended)**

Select a specific sector to screen:
- Technology
- Financials
- Healthcare
- Consumer Discretionary
- Industrials
- Energy
- Materials
- Consumer Staples
- Utilities
- Real Estate
- Communication Services

**Option B: Custom Stock List**

User provides specific tickers to analyze:
```
Example: ["AAPL", "MSFT", "GOOGL", "META", "NVDA"]
```

**Option C: Industry-Specific**

Narrow focus to specific industry within sector:
- Example: "Software" within Technology sector
- Example: "Regional Banks" within Financials

**Filtering Criteria:**
- Minimum market cap: $2B (mid-cap and above)
- Minimum average volume: 1M shares/day (liquidity requirement)
- Active trading: No delisted or inactive stocks
- Same exchange preference: Avoid cross-exchange complications

### Step 2: Retrieve Historical Price Data

**Objective:** Fetch price history for correlation and cointegration analysis.

**Data Requirements:**
- Timeframe: 2 years (minimum 252 trading days)
- Frequency: Daily closing prices
- Adjustments: Adjusted for splits and dividends
- Clean data: No gaps or missing values

**FMP API Endpoint:**
```
GET /v3/historical-price-full/{symbol}?apikey=YOUR_API_KEY
```

**Data Validation:**
- Verify consistent date ranges across all symbols
- Remove stocks with >10% missing data
- Fill minor gaps with forward-fill method
- Log data quality issues

**Script Execution:**
```bash
python scripts/fetch_price_data.py --sector Technology --lookback 730
```

### Step 3: Calculate Correlation and Beta

**Objective:** Identify candidate pairs with strong linear relationships.

**Correlation Analysis:**

For each pair of stocks (i, j) in the universe:
1. Calculate Pearson correlation coefficient (ρ)
2. Calculate rolling correlation (90-day window) for stability check
3. Filter pairs with ρ >= 0.70 (strong positive correlation)

**Correlation Interpretation:**
- ρ >= 0.90: Very strong correlation (best candidates)
- ρ 0.70-0.90: Strong correlation (good candidates)
- ρ 0.50-0.70: Moderate correlation (marginal)
- ρ < 0.50: Weak correlation (exclude)

**Beta Calculation:**

For each candidate pair (Stock A, Stock B):
```
Beta = Covariance(A, B) / Variance(B)
```

Beta indicates the hedge ratio:
- Beta = 1.0: Equal dollar amounts
- Beta = 1.5: $1.50 of B for every $1.00 of A
- Beta = 0.8: $0.80 of B for every $1.00 of A

**Correlation Stability Check:**
- Calculate correlation over multiple periods (6mo, 1yr, 2yr)
- Require correlation to be stable (not deteriorating)
- Flag pairs where recent correlation < historical correlation by >0.15

### Step 4: Cointegration Testing

**Objective:** Statistically validate long-term equilibrium relationship.

**Why Cointegration Matters:**
- Correlation measures short-term co-movement
- Cointegration proves long-term equilibrium relationship
- Cointegrated pairs mean-revert predictably
- Non-cointegrated pairs may diverge permanently

**Augmented Dickey-Fuller (ADF) Test:**

For each correlated pair:
1. Calculate spread: `Spread = Price_A - (Beta × Price_B)`
2. Run ADF test on spread series
3. Check p-value: p < 0.05 indicates cointegration (reject null hypothesis of unit root)
4. Extract ADF statistic for strength ranking

**Cointegration Interpretation:**
- p-value < 0.01: Very strong cointegration (★★★)
- p-value 0.01-0.05: Moderate cointegration (★★)
- p-value > 0.05: No cointegration (exclude)

**Half-Life Calculation:**

Estimate mean-reversion speed:
```
Half-Life = -log(2) / log(mean_reversion_coefficient)
```

- Half-life < 30 days: Fast mean-reversion (good for short-term trading)
- Half-life 30-60 days: Moderate speed (standard)
- Half-life > 60 days: Slow mean-reversion (long holding periods)

**Python Implementation:**
```python
from statsmodels.tsa.stattools import adfuller

# Calculate spread
spread = price_a - (beta * price_b)

# ADF test
result = adfuller(spread)
adf_stat = result[0]
p_value = result[1]

# Interpret
is_cointegrated = p_value < 0.05
```

### Step 5: Spread Analysis and Z-Score Calculation

**Objective:** Quantify current spread deviation from equilibrium.

**Spread Calculation:**

Two common methods:

**Method 1: Price Difference (Additive)**
```
Spread = Price_A - (Beta × Price_B)
```
Best for: Stocks with similar price levels

**Method 2: Price Ratio (Multiplicative)**
```
Spread = Price_A / Price_B
```
Best for: Stocks with different price levels, easier interpretation

**Z-Score Calculation:**

Measures how many standard deviations spread is from its mean:
```
Z-Score = (Current_Spread - Mean_Spread) / Std_Dev_Spread
```

**Z-Score Interpretation:**
- Z > +2.0: Stock A expensive relative to B (short A, long B)
- Z > +1.5: Moderately expensive (watch for entry)
- Z -1.5 to +1.5: Normal range (no trade)
- Z < -1.5: Moderately cheap (watch for entry)
- Z < -2.0: Stock A cheap relative to B (long A, short B)

**Historical Spread Analysis:**
- Calculate mean and std dev over 90-day rolling window
- Plot historical z-score distribution
- Identify maximum historical z-score deviations
- Check for structural breaks (spread regime change)

### Step 6: Generate Entry/Exit Recommendations

**Objective:** Provide actionable trading signals with clear rules.

**Entry Conditions:**

**Conservative Approach (Z ≥ ±2.0):**
```
LONG Signal:
- Z-score < -2.0 (spread 2+ std devs below mean)
- Spread is mean-reverting (cointegration p < 0.05)
- Half-life < 60 days
→ Action: Buy Stock A, Short Stock B (hedge ratio = beta)

SHORT Signal:
- Z-score > +2.0 (spread 2+ std devs above mean)
- Spread is mean-reverting (cointegration p < 0.05)
- Half-life < 60 days
→ Action: Short Stock A, Buy Stock B (hedge ratio = beta)
```

**Aggressive Approach (Z ≥ ±1.5):**
- Lower threshold for more frequent trades
- Higher win rate but smaller avg profit per trade
- Requires tighter risk management

**Exit Conditions:**

**Primary Exit: Mean Reversion (Z = 0)**
```
Exit when spread returns to mean (z-score crosses 0)
→ Close both legs simultaneously
```

**Secondary Exit: Partial Profit Take**
```
Exit 50% when z-score reaches ±1.0
Exit remaining 50% at z-score = 0
```

**Stop Loss:**
```
Exit if z-score extends beyond ±3.0 (extreme divergence)
Risk: Possible structural break in relationship
```

**Time-Based Exit:**
```
Exit after 90 days if no mean-reversion
Prevents holding broken pairs indefinitely
```

### Step 7: Position Sizing and Risk Management

**Objective:** Determine dollar amounts for market-neutral exposure.

**Market Neutral Sizing:**

For a pair (Stock A, Stock B) with beta = β:

**Equal Dollar Exposure:**
```
If portfolio size = $10,000 allocated to this pair:
- Long $5,000 of Stock A
- Short $5,000 × β of Stock B

Example (β = 1.2):
- Long $5,000 Stock A
- Short $6,000 Stock B
→ Market neutral, beta = 0
```

**Position Sizing Considerations:**
- Total pair allocation: 10-20% of portfolio per pair
- Maximum pairs: 5-8 active pairs for diversification
- Correlation across pairs: Avoid highly correlated pairs

**Risk Metrics:**
- Maximum loss per pair: 2-3% of total portfolio
- Stop loss trigger: Z-score > ±3.0 or -5% loss on spread
- Portfolio-level risk: Sum of all pair risks ≤ 10%

### Step 8: Generate Pair Analysis Report

**Objective:** Create structured markdown report with findings and recommendations.

**Report Sections:**

1. **Executive Summary**
   - Total pairs analyzed
   - Number of cointegrated pairs found
   - Top 5 opportunities ranked by statistical strength

2. **Cointegrated Pairs Table**
   - Pair name (Stock A / Stock B)
   - Correlation coefficient
   - Cointegration p-value
   - Current z-score
   - Trade signal (Long/Short/None)
   - Half-life

3. **Detailed Analysis (Top 10 Pairs)**
   - Pair description
   - Statistical metrics
   - Current spread position
   - Entry/exit recommendations
   - Position sizing
   - Risk assessment

4. **Spread Charts (Text-Based)**
   - Historical z-score plot (ASCII art)
   - Entry/exit levels marked
   - Current position indicator

5. **Risk Warnings**
   - Pairs with deteriorating correlation
   - Structural breaks detected
   - Low liquidity warnings

**File Naming Convention:**
```
pair_trade_analysis_[SECTOR]_[YYYY-MM-DD].md
```

Example: `pair_trade_analysis_Technology_2025-11-08.md`

## Quality Standards

### Statistical Rigor

**Minimum Requirements for Valid Pair:**
- ✓ Correlation ≥ 0.70 over 2-year period
- ✓ Cointegration p-value < 0.05 (ADF test)
- ✓ Spread stationarity confirmed
- ✓ Half-life < 90 days
- ✓ No structural breaks in recent 6 months

**Red Flags (Exclude Pair):**
- Correlation dropped >0.20 in recent 6 months
- Cointegration p-value > 0.05
- Half-life increasing over time (mean-reversion weakening)
- Significant corporate events (merger, spin-off, bankruptcy risk)
- Liquidity concerns (avg volume < 500K shares/day)

### Practical Considerations

**Transaction Costs:**
- Assume 0.1% round-trip cost per leg
- Total cost per pair = 0.4% (entry + exit, both legs)
- Minimum z-score threshold should exceed transaction costs

**Short Selling:**
- Verify stock is shortable (not hard-to-borrow)
- Factor in short interest costs (borrow fees)
- Monitor short squeeze risk

**Execution:**
- Enter/exit both legs simultaneously (avoid leg risk)
- Use limit orders to control slippage
- Pre-locate shorts before entry

## Available Scripts

### scripts/find_pairs.py

**Purpose:** Screen for cointegrated pairs within a sector or custom list.

**Usage:**
```bash
# Sector-based screening
python scripts/find_pairs.py --sector Technology --min-correlation 0.70

# Custom stock list
python scripts/find_pairs.py --symbols AAPL,MSFT,GOOGL,META --min-correlation 0.75

# Full options
python scripts/find_pairs.py \
  --sector Financials \
  --min-correlation 0.70 \
  --min-market-cap 2000000000 \
  --lookback-days 730 \
  --output pairs_analysis.json
```

**Parameters:**
- `--sector`: Sector name (Technology, Financials, etc.)
- `--symbols`: Comma-separated list of tickers (alternative to sector)
- `--min-correlation`: Minimum correlation threshold (default: 0.70)
- `--min-market-cap`: Minimum market cap filter (default: $2B)
- `--lookback-days`: Historical data period (default: 730 days)
- `--output`: Output JSON file (default: stdout)
- `--api-key`: FMP API key (or set FMP_API_KEY env var)

**Output:**
```json
[
  {
    "pair": "AAPL/MSFT",
    "stock_a": "AAPL",
    "stock_b": "MSFT",
    "correlation": 0.87,
    "beta": 1.15,
    "cointegration_pvalue": 0.012,
    "adf_statistic": -3.45,
    "half_life_days": 42,
    "current_zscore": -2.3,
    "signal": "LONG",
    "strength": "Strong"
  }
]
```

### scripts/analyze_spread.py

**Purpose:** Analyze a specific pair's spread behavior and generate trading signals.

**Usage:**
```bash
# Analyze specific pair
python scripts/analyze_spread.py --stock-a AAPL --stock-b MSFT

# Custom lookback period
python scripts/analyze_spread.py \
  --stock-a JPM \
  --stock-b BAC \
  --lookback-days 365 \
  --entry-zscore 2.0 \
  --exit-zscore 0.5
```

**Parameters:**
- `--stock-a`: First stock ticker
- `--stock-b`: Second stock ticker
- `--lookback-days`: Analysis period (default: 365)
- `--entry-zscore`: Z-score threshold for entry (default: 2.0)
- `--exit-zscore`: Z-score threshold for exit (default: 0.0)
- `--api-key`: FMP API key

**Output:**
- Current spread analysis
- Z-score calculation
- Entry/exit recommendations
- Position sizing
- Historical z-score chart (text)

## Reference Documentation

### references/methodology.md

Comprehensive guide to statistical arbitrage and pair trading:
- **Pair Selection Criteria**: How to identify good pair candidates
- **Statistical Tests**: Correlation, cointegration, stationarity
- **Spread Construction**: Price difference vs price ratio approaches
- **Mean Reversion**: Half-life calculation and interpretation
- **Risk Management**: Position sizing, stop losses, diversification
- **Common Pitfalls**: Survivorship bias, look-ahead bias, overfitting

### references/cointegration_guide.md

Deep dive into cointegration testing:
- **What is Cointegration?**: Intuitive explanation
- **ADF Test**: Step-by-step procedure
- **P-Value Interpretation**: Statistical significance thresholds
- **Half-Life Estimation**: AR(1) model approach
- **Structural Breaks**: Testing for regime changes
- **Practical Examples**: Case studies with real pairs

## Integration with Other Skills

**Sector Analyst Integration:**
- Use Sector Analyst to identify sectors in rotation
- Screen for pairs within outperforming sectors
- Pairs in leading sectors may have stronger trends

**Technical Analyst Integration:**
- Confirm pair entry/exit with individual stock technicals
- Check support/resistance levels before entry
- Validate trend direction aligns with spread signal

**Backtest Expert Integration:**
- Feed pair candidates to Backtest Expert for validation
- Test historical z-score entry/exit rules
- Optimize threshold parameters (entry z-score, stop loss)
- Walk-forward analysis for robustness

**Market Environment Analysis Integration:**
- Avoid pair trading during extreme volatility (VIX > 30)
- Correlations break down in crisis periods
- Prefer pair trading in sideways/range-bound markets

**Portfolio Manager Integration:**
- Track multiple pair positions
- Monitor overall market-neutral exposure
- Calculate portfolio-level pair trading P/L
- Rebalance hedge ratios periodically

## Important Notes

- **All analysis and output in English**
- **Statistical foundation**: No discretionary interpretation
- **Market neutral focus**: Minimize directional beta exposure
- **Data quality critical**: Garbage in, garbage out
- **Requires FMP API key**: Free tier sufficient for basic screening
- **Python dependencies**: pandas, numpy, scipy, statsmodels

## Common Use Cases

**Use Case 1: Technology Sector Pairs**
```
User: "Find pair trading opportunities in tech stocks"

Workflow:
1. Screen Technology sector for stocks with market cap > $10B
2. Calculate all pairwise correlations
3. Filter pairs with correlation ≥ 0.75
4. Run cointegration tests
5. Identify current z-score extremes (|z| > 2.0)
6. Generate top 10 pairs report
```

**Use Case 2: Specific Pair Analysis**
```
User: "Analyze AAPL and MSFT as a pair trade"

Workflow:
1. Fetch 2-year price history for AAPL and MSFT
2. Calculate correlation and beta
3. Test for cointegration
4. Calculate current spread and z-score
5. Generate entry/exit recommendation
6. Provide position sizing guidance
```

**Use Case 3: Regional Bank Pairs**
```
User: "Screen for pairs among regional banks"

Workflow:
1. Filter Financials sector for industry = "Regional Banks"
2. Exclude banks with <$5B market cap
3. Calculate pairwise statistics
4. Rank by cointegration strength
5. Focus on pairs with half-life < 45 days
6. Report top 5 mean-reverting pairs
```

## Troubleshooting

**Problem: No cointegrated pairs found**

Solutions:
- Expand universe (lower market cap threshold)
- Relax cointegration p-value to 0.10
- Try different sectors (Utilities often cointegrate well)
- Increase lookback period to 3 years

**Problem: All z-scores near zero (no trade signals)**

Solutions:
- Normal market condition (pairs in equilibrium)
- Check back later or expand universe
- Lower entry threshold to ±1.5 instead of ±2.0

**Problem: Pair correlation broke down**

Solutions:
- Check for corporate events (earnings, guidance changes)
- Verify no M&A activity or restructuring
- Remove pair from watchlist if structural break confirmed
- Monitor for 30 days before re-entering

## API Requirements

- **Required**: FMP API key (free tier sufficient)
- **Rate Limits**: ~250 requests/day on free tier
- **Data Usage**: ~2 requests per symbol for 2-year history
- **Upgrade**: Professional plan ($29/mo) recommended for frequent screening

## Resources

- **FMP Historical Price API**: https://site.financialmodelingprep.com/developer/docs/historical-price-full
- **Stock Screener API**: https://site.financialmodelingprep.com/developer/docs/stock-screener-api
- **Statsmodels Documentation**: https://www.statsmodels.org/stable/index.html
- **Cointegration Paper**: Engle & Granger (1987) - "Co-Integration and Error Correction"

---

**Version**: 1.0
**Last Updated**: 2025-11-08
**Dependencies**: Python 3.8+, pandas, numpy, scipy, statsmodels, requests
