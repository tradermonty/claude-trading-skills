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

## Prerequisites

- Python 3.9 or newer
- An FMP API key with access to the company screener and historical-price endpoints
- `statsmodels>=0.14,<0.15` for ADF and autoregression calculations

Set the API key without placing it on the command line or in a committed file:

```bash
export FMP_API_KEY="<fmp-api-key>"
```

Run the scripts from the repository root with the statistical dependency isolated
to the command:

```bash
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/find_pairs.py \
  --symbols AAPL,MSFT \
  --output /tmp/pair-trade/pairs.json
```

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
- Adjustments: Dividend-adjusted `adjClose` from `/stable/historical-price-eod/dividend-adjusted` when available. The fallback `full` endpoint serves unadjusted `close`; the run then warns per symbol and records `price_basis: close`
- Clean data: No gaps or missing values

**FMP API Endpoint:**
```
GET /stable/historical-price-eod/dividend-adjusted?symbol={symbol}   # preferred, adjClose
GET /stable/historical-price-eod/full?symbol={symbol}                  # fallback, unadjusted close
Header: apikey: <FMP_API_KEY>
```

**Data Validation:**
- Verify consistent date ranges across all symbols
- Remove stocks with >10% missing data
- Fill minor gaps with forward-fill method
- Log data quality issues

**Script Execution:**
```bash
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/find_pairs.py \
  --sector Technology \
  --lookback-days 730 \
  --output /tmp/pair-trade/technology.json
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

Read `references/trade_rules_and_reporting.md` (section "Step 6 detail: Entry and Exit Conditions") when generating entry and exit recommendations. It holds the conservative and aggressive entry rules, mean-reversion, partial-profit, stop-loss and time-based exits.

### Step 7: Position Sizing and Risk Management

**Objective:** Determine dollar amounts for market-neutral exposure.

Read `references/trade_rules_and_reporting.md` (section "Step 7 detail: Position Sizing and Risk Management") when sizing a pair. It holds market-neutral sizing, position sizing considerations and risk metrics.

### Step 8: Generate Pair Analysis Report

**Objective:** Create structured markdown report with findings and recommendations.

Read `references/trade_rules_and_reporting.md` (section "Step 8 detail: Pair Analysis Report") when writing the report. It holds the report sections, a markdown template and the file naming convention.

## Output

`find_pairs.py` creates the requested parent directory and writes one JSON object
with `metadata` and `pairs` keys. Each pair includes the correlation, hedge ratio,
ADF result, half-life, current z-score, signal, and generation timestamp. Progress
and a ranked summary are written to stdout. File-system errors produce a concise
stderr message and a nonzero exit.

`analyze_spread.py` writes a single-pair statistical report to stdout and does not
create files. Both commands reject invalid or non-finite thresholds, insufficient
lookback windows, and duplicate symbols before making API requests. Missing
`statsmodels` produces an install command on stderr without a traceback.

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

Read `references/script_usage.md` for full CLI usage, options and output formats of `find_pairs.py` and `analyze_spread.py`.

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

Read `references/skill_integrations.md` for how to combine this skill with Sector Analyst, Technical Analyst, Backtest Expert, Market Environment Analysis and Portfolio Manager.

## Important Notes

- **All analysis and output in English**
- **Statistical foundation**: No discretionary interpretation
- **Market neutral focus**: Minimize directional beta exposure
- **Data quality critical**: Garbage in, garbage out
- **Requires FMP API key**: Access to company-screener and historical-price endpoints depends on your subscription.
- **Python dependencies**: pandas, numpy, scipy, requests, and `statsmodels>=0.14,<0.15`

## Common Use Cases

Read `references/common_use_cases.md` for three worked use cases: technology sector pairs, a specific pair, regional bank pairs.

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

- **Required**: FMP API key with access to the company screener and historical-price endpoints.
- **Transport**: Generated client; screener uses `/stable/company-screener` only. Historical prices try the dividend-adjusted stable endpoint first, then the canonical stable `full` and v3 fallback.
- **History**: Available history is fetched without a current-date bound, then the latest requested number of rows is retained. `adjClose` is used when supplied; otherwise raw `close`, which is not dividend-adjusted. Each symbol's basis is recorded as `price_basis` (`dividend_adjusted`, `adj_close` or `close`) in the `find_pairs` JSON `metadata` and printed by `analyze_spread`, and a stderr warning names every symbol on raw `close`. Mixed bases in one run warn separately.
- **Failures**: Invalid provider shapes fail with a diagnostic; an empty/failed sector request exits instead of producing a candidate list. Historical failures return no series.
- **Access and quotas**: Depend on the provider plan; this migration does not verify free-tier availability, plan access to the dividend-adjusted endpoint, current pricing or quotas (all unverified). Once the daily limit is reached, a batch stops requesting immediately.

## Resources

- **FMP Historical Price API**: https://site.financialmodelingprep.com/developer/docs/historical-price-full
- **Stock Screener API**: https://site.financialmodelingprep.com/developer/docs/stock-screener-api
- **Statsmodels Documentation**: https://www.statsmodels.org/stable/index.html
- **Cointegration Paper**: Engle & Granger (1987) - "Co-Integration and Error Correction"

---

**Version**: 1.0
**Last Updated**: 2025-11-08
**Dependencies**: Python 3.8+, pandas, numpy, scipy, statsmodels, requests
