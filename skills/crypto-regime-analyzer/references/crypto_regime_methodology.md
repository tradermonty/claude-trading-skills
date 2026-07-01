# Crypto Regime Methodology

Scoring rationale, thresholds, and data schemas for `crypto-regime-analyzer`.

## Design Principles

1. **BTC-anchored.** Bitcoin trend structure carries the largest weight (25%) because alt regimes rarely stay risk-on while BTC's primary trend is broken. Alt breadth and dominance are interpreted *conditionally* on BTC trend.
2. **Contrarian at extremes, trend-following in the middle.** Funding, drawdown, and momentum components give small contrarian bumps at washout extremes (near-total negative momentum, >65% drawdown with vol expansion, negative funding) because those readings historically coincide with improving forward returns — while remaining trend-respecting in normal ranges.
3. **Degrade, never fail.** Every component reports `data_available`; missing components have weight proportionally redistributed, mirroring `market-breadth-analyzer`.
4. **Free and keyless.** All live data comes from CoinGecko public + Binance public futures endpoints. Thresholds are heuristics chosen for interpretability, not backtest-optimized parameters — treat them as documented defaults to be revisited, not edge claims.

## Component Details

### 1. BTC Trend Structure (25%)

Inputs: >= 210 daily BTC closes.

| Structure | Base |
|---|---|
| price > 50DMA > 200DMA (bull stack) | 90 |
| price between 200DMA and 50DMA, stack intact (pullback) | 65 |
| price below both, 50DMA still > 200DMA | 55 |
| price > 50DMA but 50DMA <= 200DMA (recovery attempt) | 45 |
| price < 50DMA < 200DMA (bear stack) | 15 |

Modifier: 200DMA slope over a 20-day lookback, +10 rising / -10 falling. Signal notes when the 50/200DMA gap is within 1.5% (imminent cross watch). Score clamped to [0, 100].

### 2. Alt Breadth Participation (20%)

Inputs: daily closes for the top-N universe excluding BTC; coins with < 200 observations are skipped and listed. Requires >= 5 usable alts.

Base from % above 200DMA: >=80% → 95, >=65% → 80, >=50% → 65, >=35% → 45, >=20% → 25, else 10. Modifier: 50DMA breadth leading 200DMA breadth by >= 15pts → +5 (fresh thrust); lagging by >= 15pts → -5 (rolling over).

### 3. BTC Dominance Regime (15%)

Inputs: >= 31 daily dominance observations + BTC-trend-constructive flag (Component 1 score >= 60). Direction = 30d change, ±0.5pt flat band.

| BTC trend | Dominance | Score | Reading |
|---|---|---|---|
| up | falling | 90 | Alt rotation (risk-on down the risk curve) |
| up | flat | 75 | — |
| up | rising | 65 | BTC-led, alts lagging |
| down | rising | 30 | Defensive rotation inside crypto |
| down | flat | 25 | — |
| down | falling | 10 | Indiscriminate de-risking |

Extremes: dominance >= 62% in a BTC downtrend → +5 (washout watch); <= 40% in an uptrend → -5 (froth caution).

### 4. Perpetual Funding Regime (15%)

Inputs: latest 8h funding rate per tracked USDT perp (>= 2 symbols). Average across symbols, banded:

| Avg 8h funding | Score | Reading |
|---|---|---|
| <= -0.010% | 80 | Washed out (shorts pay) |
| -0.010% .. 0% | 65 | Skeptical |
| 0% .. +0.010% | 75 | Neutral (Binance baseline is +0.010%) |
| +0.010% .. +0.030% | 55 | Long leverage building |
| +0.030% .. +0.060% | 30 | Crowded longs |
| > +0.060% | 10 | Euphoric; liquidation-cascade risk |

### 5. Drawdown & Volatility Position (15%)

Inputs: >= 365 daily BTC closes. Base from drawdown vs trailing 1y high: <=10% → 90, <=20% → 75, <=35% → 55, <=50% → 35, <=65% → 20, else 10. Modifier: 30d realized vol (annualized, log returns) vs its trailing-1y distribution sampled at weekly stride — bottom third → +10, top third → -10. Contrarian floor: drawdown > 65% AND vol in top third → score floors at 15 (capitulation zone).

### 6. Momentum Thrust / Washout (10%)

Inputs: 31+ daily closes per coin, >= 5 usable coins, BTC included. % of universe with positive 30d return: >=85% → 90, >=65% → 75, >=45% → 55, >=25% → 35, >=10% → 20, <10% → 35 (washout: contrarian bump over the plain mapping).

## Composite & Zones

Weighted average over available components with proportional weight redistribution. Zones: 80-100 RISK_ON, 60-79 CONSTRUCTIVE, 40-59 NEUTRAL, 20-39 DEFENSIVE, 0-19 RISK_OFF, each mapped to a posture string (see SKILL.md).

## Offline Snapshot Schema (`--input-json`)

```json
{
  "as_of": "2026-07-01T00:00:00Z",
  "series": {
    "BTC": [45000.0, 45210.5, "... daily closes oldest -> newest ..."],
    "ETH": [2400.0, 2415.2],
    "SOL": [140.0, 141.8]
  },
  "dominance_series": [56.1, 56.0, 55.8],
  "funding": {
    "BTCUSDT": 0.0001,
    "ETHUSDT": 0.00008
  }
}
```

Rules:

- `series` **must** include a `"BTC"` key; all other keys are treated as alts.
- Closes are floats, oldest -> newest, ideally 400+ observations (210 minimum for BTC trend, 365 for drawdown/vol, 200 for alt breadth membership).
- `dominance_series` is daily BTC dominance percentages oldest -> newest; empty list is allowed (component degrades).
- `funding` values are decimal 8h rates (`0.0001` = +0.010%); empty object is allowed (component degrades).

## Data Sources (live mode)

| Endpoint | Used for | Auth |
|---|---|---|
| `GET api.coingecko.com/api/v3/coins/markets` | Top-N universe | none |
| `GET api.coingecko.com/api/v3/coins/{id}/market_chart` | Daily close history | none |
| `GET api.coingecko.com/api/v3/global` | Current BTC dominance | none |
| `GET fapi.binance.com/fapi/v1/premiumIndex` | Latest funding per perp | none |

Fetches are throttled at ~6.5s between history calls to respect CoinGecko's free-tier limits and cached per UTC day under `--cache-dir`.
