---
layout: default
title: "Pair Trade Screener"
grand_parent: English
parent: Skill Guides
nav_order: 43
lang_peer: /ja/skills/pair-trade-screener/
permalink: /en/skills/pair-trade-screener/
---

# Pair Trade Screener
{: .no_toc }

Statistical arbitrage tool for identifying and analyzing pair trading opportunities. Detects cointegrated stock pairs within sectors, analyzes spread behavior, calculates z-scores, and provides entry/exit recommendations for market-neutral strategies. Use when user requests pair trading opportunities, statistical arbitrage screening, mean-reversion strategies, or market-neutral portfolio construction. Supports correlation analysis, cointegration testing, and spread backtesting.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/pair-trade-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/pair-trade-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

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

---

## 2. When to Use

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

---

## 3. Prerequisites

- **FMP API key** required (`FMP_API_KEY` environment variable)
- Financial Modeling Prep API
- Python 3.9+ recommended

---

## 4. Quick Start

```bash
# Screen for pairs in specific sector
python3 pair-trade-screener/scripts/find_pairs.py --sector Technology

# Analyze specific pair
python3 pair-trade-screener/scripts/analyze_spread.py AAPL MSFT

# Custom cointegration parameters
python3 pair-trade-screener/scripts/find_pairs.py \
  --sector Financials \
  --min-correlation 0.7 \
  --lookback-days 365
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/pair-trade-screener/references/cointegration_guide.md`
- `skills/pair-trade-screener/references/methodology.md`

**Scripts:**

- `skills/pair-trade-screener/scripts/analyze_spread.py`
- `skills/pair-trade-screener/scripts/find_pairs.py`
