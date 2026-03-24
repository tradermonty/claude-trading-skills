---
name: pair-trade-screener
description: "Statistical arbitrage tool for identifying and analyzing pair trading opportunities. Detects cointegrated stock pairs within sectors, analyzes spread behavior, calculates z-scores, and provides entry/exit recommendations for market-neutral strategies. Use when user requests pair trading opportunities, statistical arbitrage screening, mean-reversion strategies, or market-neutral portfolio construction. Supports correlation analysis, cointegration testing, and spread backtesting."
---

# Pair Trade Screener

Identify and analyze statistical arbitrage opportunities through pair trading — a market-neutral strategy profiting from relative price movements of two correlated securities.

## Analysis Workflow

### Step 1: Define Pair Universe

Determine the stock pool via one of:

- **Sector-based** (recommended): Screen all stocks in a sector (Technology, Financials, Healthcare, etc.)
- **Custom list**: User-provided tickers (e.g., `["AAPL", "MSFT", "GOOGL", "META", "NVDA"]`)
- **Industry-specific**: Narrow to an industry within a sector (e.g., "Regional Banks" in Financials)

**Filtering criteria:** Market cap >= $2B, avg volume >= 1M shares/day, actively traded, same exchange preferred.

### Step 2: Retrieve Historical Price Data

Fetch 2 years of daily adjusted closing prices via FMP API:

```bash
python scripts/fetch_price_data.py --sector Technology --lookback 730
```

**Validation checkpoint:** Verify consistent date ranges across symbols. Remove stocks with >10% missing data. Forward-fill minor gaps.

### Step 3: Correlation and Beta Analysis

```bash
python scripts/find_pairs.py --sector Technology --min-correlation 0.70
```

For each pair (i, j):
1. Calculate Pearson correlation (rho). Filter pairs with rho >= 0.70.
2. Calculate rolling 90-day correlation to verify stability.
3. Calculate hedge ratio: `Beta = Cov(A, B) / Var(B)`

**Validation checkpoint:** Reject pairs where recent correlation dropped >0.15 below historical correlation. Require rho stable across 6mo, 1yr, and 2yr windows.

### Step 4: Cointegration Testing

For each correlated pair, run the Augmented Dickey-Fuller test:

```python
from statsmodels.tsa.stattools import adfuller

spread = price_a - (beta * price_b)
result = adfuller(spread)
is_cointegrated = result[1] < 0.05  # p-value threshold
```

**Validation checkpoint:** Reject if p-value >= 0.05. Rank by strength:
- p < 0.01: Strong cointegration
- p 0.01-0.05: Moderate cointegration

Calculate half-life: `half_life = -log(2) / log(mean_reversion_coefficient)`

**Validation checkpoint:** Reject if half-life > 90 days. Prefer < 30 days for short-term trading.

### Step 5: Spread Analysis and Z-Score

Calculate z-score using 90-day rolling window:

```
Z-Score = (Current_Spread - Mean_Spread) / Std_Dev_Spread
```

**Z-score signal thresholds:**

| Z-Score | Signal | Action |
|---------|--------|--------|
| > +2.0 | SHORT | Short A, Long B (hedge ratio = beta) |
| +1.5 to +2.0 | WATCH | Monitor for entry |
| -1.5 to +1.5 | NEUTRAL | No trade |
| -2.0 to -1.5 | WATCH | Monitor for entry |
| < -2.0 | LONG | Buy A, Short B (hedge ratio = beta) |

For detailed spread analysis of a specific pair:

```bash
python scripts/analyze_spread.py --stock-a AAPL --stock-b MSFT --entry-zscore 2.0 --exit-zscore 0.5
```

### Step 6: Generate Entry/Exit Recommendations

**Entry conditions** (all must be met):
- |Z-score| >= 2.0 (conservative) or >= 1.5 (aggressive)
- Cointegration p-value < 0.05
- Half-life < 60 days

**Exit rules:**
- **Primary:** Z-score crosses 0 (mean reversion complete) — close both legs
- **Partial:** Exit 50% at |z| = 1.0, remainder at z = 0
- **Stop loss:** Exit if |z| > 3.0 (possible structural break)
- **Time stop:** Exit after 90 days if no mean reversion

### Step 7: Position Sizing

For market-neutral exposure with portfolio allocation P and hedge ratio beta:
- Long leg: P/2 of Stock A
- Short leg: (P/2) x beta of Stock B

**Risk constraints:**
- Max allocation per pair: 10-20% of portfolio
- Max active pairs: 5-8
- Max loss per pair: 2-3% of total portfolio
- Portfolio-level pair risk: <= 10%

**Practical considerations:**
- Transaction costs: ~0.4% round-trip (both legs, entry + exit)
- Verify short availability and factor borrow fees
- Enter/exit both legs simultaneously to avoid leg risk

### Step 8: Generate Report

Produce a structured markdown report saved as `pair_trade_analysis_[SECTOR]_[YYYY-MM-DD].md` containing:

1. **Executive summary**: Pairs analyzed, cointegrated pairs found, top 5 by statistical strength
2. **Pairs table**: Pair name, correlation, cointegration p-value, z-score, signal, half-life
3. **Detailed analysis** (top 10): Metrics, spread position, entry/exit recs, position sizing, risk
4. **Risk warnings**: Deteriorating correlations, structural breaks, low liquidity

## Minimum Requirements for Valid Pair

- Correlation >= 0.70 over 2 years
- Cointegration p-value < 0.05 (ADF test)
- Half-life < 90 days
- No structural breaks in recent 6 months
- Avg volume >= 500K shares/day

**Red flags (exclude):** Correlation dropped >0.20 in 6 months, half-life increasing, significant corporate events (M&A, spin-off, bankruptcy risk).

## Scripts Reference

### scripts/find_pairs.py

Screen for cointegrated pairs within a sector or custom list.

```bash
# Sector screening
python scripts/find_pairs.py --sector Technology --min-correlation 0.70

# Custom tickers
python scripts/find_pairs.py --symbols AAPL,MSFT,GOOGL,META --min-correlation 0.75

# Full options
python scripts/find_pairs.py \
  --sector Financials \
  --min-correlation 0.70 \
  --min-market-cap 2000000000 \
  --lookback-days 730 \
  --output pairs_analysis.json
```

Output JSON per pair: `pair`, `stock_a`, `stock_b`, `correlation`, `beta`, `cointegration_pvalue`, `adf_statistic`, `half_life_days`, `current_zscore`, `signal`, `strength`.

### scripts/analyze_spread.py

Analyze a specific pair's spread behavior and generate trading signals.

```bash
python scripts/analyze_spread.py \
  --stock-a JPM --stock-b BAC \
  --lookback-days 365 \
  --entry-zscore 2.0 --exit-zscore 0.5
```

Output: Current spread analysis, z-score, entry/exit recommendations, position sizing, historical z-score chart.

## Reference Documentation

- `references/methodology.md` — Pair selection criteria, statistical tests, spread construction, mean reversion, risk management, common pitfalls
- `references/cointegration_guide.md` — ADF test procedure, p-value interpretation, half-life estimation, structural breaks, practical examples

## Integration with Other Skills

- **Sector Analyst**: Identify sectors in rotation, then screen for pairs within them
- **Technical Analyst**: Confirm pair entry/exit with individual stock technicals
- **Backtest Expert**: Walk-forward validation of z-score entry/exit rules
- **Portfolio Manager**: Track multiple pair positions and monitor market-neutral exposure

## Requirements

- **FMP API key** (free tier sufficient): Set `FMP_API_KEY` env var or pass `--api-key`
- **Python**: 3.8+, pandas, numpy, scipy, statsmodels, requests
- **Rate limits**: ~250 requests/day on free tier; ~2 requests per symbol for 2-year history
