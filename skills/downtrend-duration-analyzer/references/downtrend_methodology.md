# Downtrend Duration Analysis Methodology

## Overview

This document describes the technical methodology for identifying downtrend periods in historical price data and computing duration statistics. The approach is designed to be robust against noise while capturing meaningful corrections.

## Peak and Trough Detection

### Rolling Window Algorithm

The primary algorithm uses a rolling window approach to identify local peaks and troughs:

1. **Peak Detection**: A price point is a local peak if it is the highest close within a `window` trading days on both sides.
   ```
   peak[i] = close[i] == max(close[i-window:i+window+1])
   ```

2. **Trough Detection**: A price point is a local trough if it is the lowest close within a `window` trading days on both sides.
   ```
   trough[i] = close[i] == min(close[i-window:i+window+1])
   ```

### Default Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `peak_window` | 20 | Trading days on each side for peak detection |
| `trough_window` | 20 | Trading days on each side for trough detection |
| `min_depth_pct` | 5.0 | Minimum decline percentage to qualify as a downtrend |

### Noise Filtering

To avoid counting minor fluctuations:
- **Minimum Depth Filter**: Only downtrends with depth >= `min_depth_pct` are included
- **Minimum Duration Filter**: Downtrends shorter than 3 days are excluded
- **Overlap Handling**: When peaks/troughs overlap (multiple detected within window), keep the most extreme value

## Downtrend Definition

A **downtrend period** is defined as:
1. Starts at a detected local peak
2. Ends at the subsequent local trough
3. No higher high occurs between peak and trough
4. Depth (%) = (trough_price - peak_price) / peak_price * 100

### Duration Calculation

Duration is measured in **trading days** (not calendar days):
- Count business days between peak date and trough date (inclusive)
- Excludes weekends and market holidays
- Use market calendar for accurate counting

## Market Cap Tier Definitions

Stocks are segmented into tiers based on market capitalization:

| Tier | Market Cap Range | Typical Characteristics |
|------|------------------|------------------------|
| **Mega** | >= $200B | Index heavyweights, high liquidity, institutional ownership |
| **Large** | $10B - $200B | Established companies, moderate volatility |
| **Mid** | $2B - $10B | Growth phase companies, higher volatility |
| **Small** | < $2B | Emerging companies, less liquidity, higher risk |

### Why Segmentation Matters

Research shows significant differences in correction behavior:
- **Mega caps** typically have shorter, shallower corrections due to:
  - Index fund rebalancing provides buying support
  - Higher analyst coverage means faster price discovery
  - Institutional investors provide liquidity

- **Small caps** experience longer, deeper corrections due to:
  - Lower liquidity amplifies price moves
  - Less analyst coverage delays information incorporation
  - Higher retail participation increases volatility

## Sector-Specific Patterns

Different sectors exhibit characteristic correction patterns:

### Defensive Sectors
- **Utilities, Consumer Staples, Healthcare**: Shorter median corrections (12-18 days)
- Lower depth, faster recovery during risk-off periods

### Cyclical Sectors
- **Technology, Consumer Discretionary, Industrials**: Longer median corrections (20-30 days)
- Deeper drawdowns, correlated with economic cycles

### Commodity-Linked Sectors
- **Energy, Materials**: Highly variable (15-45 days)
- Driven by commodity price cycles, geopolitical events

## Statistical Measures

### Percentile Interpretation

| Percentile | Meaning | Trading Application |
|------------|---------|---------------------|
| P25 | 25% of corrections end by this duration | Aggressive entry timing |
| P50 (Median) | Half of corrections end by this duration | Standard expectation |
| P75 | 75% of corrections end by this duration | Conservative planning |
| P90 | 90% of corrections end by this duration | Extended timeline, consider re-evaluation |

### Why Use Median Over Mean

- Correction durations are **right-skewed** (long tail of extended corrections)
- Mean is inflated by outliers (bear markets, sector crashes)
- Median provides more realistic "typical" expectation
- Always report both, plus percentiles, for complete picture

## Historical Benchmarks

Based on S&P 500 components, 2019-2024:

| Category | P25 | P50 | P75 | P90 |
|----------|-----|-----|-----|-----|
| All Stocks | 8 | 18 | 35 | 62 |
| Mega Cap | 6 | 12 | 25 | 45 |
| Large Cap | 8 | 16 | 32 | 55 |
| Mid Cap | 10 | 22 | 42 | 70 |
| Small Cap | 12 | 28 | 52 | 85 |

*Note: These are illustrative benchmarks; actual values vary by market conditions.*

## Application Guidelines

### Mean Reversion Strategies

1. **Entry Timing**: Use sector-specific P25-P50 range as target entry window
2. **Position Sizing**: Scale in gradually as correction extends beyond median
3. **Stop-Loss Timing**: If correction exceeds P90, reassess thesis

### Pullback Buying

1. **Wait Period**: Allow at least sector median duration before aggressive entry
2. **Depth Confirmation**: Verify decline meets minimum depth threshold
3. **Volume Pattern**: Look for volume spike at trough formation

### Risk Management

1. **Time Stops**: Set maximum holding period based on P90 duration
2. **Recovery Expectations**: Plan for median recovery time, budget for P75
3. **Sector Rotation**: Use relative correction durations to time sector moves

## Limitations

1. **Past Performance**: Historical distributions may not predict future corrections
2. **Regime Changes**: Market structure changes (ETFs, algo trading) affect patterns
3. **Black Swan Events**: Extreme events (2020 COVID, 2008 GFC) are outliers
4. **Survivorship Bias**: Analysis of current constituents excludes delisted stocks

## References

- Fama, E. & French, K. (1993). Common risk factors in the returns on stocks and bonds.
- Jegadeesh, N. (1990). Evidence of predictable behavior of security returns.
- Lo, A. & MacKinlay, A. (1988). Stock market prices do not follow random walks.
