# Impact Scoring Framework

Score each news event across three dimensions, then rank by total score.

## Formula

```
Impact Score = (Price Impact Score x Breadth Multiplier) x Forward-Looking Modifier
```

## 1. Price Impact Score (Primary Factor)

| Rating | Points | Equity Index | Sector ETF | Mega-Cap Stock | Oil (WTI/Brent) | Gold | Base Metals | 10Y Yield | DXY |
|--------|--------|-------------|------------|----------------|-----------------|------|-------------|-----------|-----|
| Severe | 10 | +/-2%+ | +/-5%+ | +/-10%+ | +/-5%+ | +/-3%+ | +/-4%+ | +/-20bps+ | +/-1.5%+ |
| Major | 7 | +/-1-2% | +/-3-5% | +/-5-10% | +/-3-5% | +/-1.5-3% | +/-2-4% | +/-10-20bps | +/-0.75-1.5% |
| Moderate | 4 | +/-0.5-1% | +/-1-3% | +/-2-5% | +/-1-3% | +/-0.5-1.5% | +/-1-2% | +/-5-10bps | +/-0.3-0.75% |
| Minor | 2 | +/-0.2-0.5% | <1% | — | — | — | — | — | — |
| Negligible | 1 | <0.2% | — | — | — | — | — | — | — |

## 2. Breadth Multiplier

| Breadth | Multiplier | Criteria | Examples |
|---------|-----------|----------|----------|
| Systemic | 3x | Multiple asset classes, global markets | FOMC surprise, banking crisis, major war |
| Cross-Asset | 2x | Equities + commodities, or equities + bonds | Inflation surprise, geopolitical supply shock |
| Sector-Wide | 1.5x | Entire sector or related sectors | Tech earnings cluster, energy policy |
| Stock-Specific | 1x | Single company (unless mega-cap with index impact) | Individual earnings, M&A |

## 3. Forward-Looking Modifier

| Significance | Modifier | Criteria | Examples |
|-------------|----------|----------|----------|
| Regime Change | x1.50 | Fundamental market structure shift | Fed pivot, major geopolitical realignment |
| Trend Confirmation | x1.25 | Reinforces existing trajectory | Consecutive hot CPI, sustained earnings beats |
| Isolated Event | x1.00 | One-off, limited forward signal | Single data point in range, company-specific |
| Contrary Signal | x0.75 | Contradicts prevailing narrative | Good news ignored, bad news rallied |

## Example Calculations

**FOMC 75bps Hike (hawkish):** S&P -2.5% (Severe=10) x Systemic(3x) x Trend Confirmation(1.25) = **37.5**

**NVIDIA Earnings Beat:** NVDA +15%, Nasdaq +1.5% (Severe=10) x Sector-Wide(1.5x) x Trend Confirmation(1.25) = **18.75**

**Middle East Flare-up:** Oil +8%, S&P -1.2% (Severe=10) x Cross-Asset(2x) x Isolated(1.0) = **20**

**Non-Mega-Cap Earnings:** Stock +12%, no index impact (Major=7) x Stock-Specific(1x) x Isolated(1.0) = **7**

## Ranking

After scoring all events, rank highest to lowest. This determines report ordering. Events with Impact Score >5 receive detailed reaction analysis.
