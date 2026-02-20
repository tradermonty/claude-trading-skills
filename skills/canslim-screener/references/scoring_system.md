# CANSLIM Scoring System - Phase 3 (Full CANSLIM)

## Overview

This document specifies the composite scoring system for the CANSLIM screener. Phase 3 implements all **7 of 7** components (C, A, N, S, L, I, M), representing 100% of the full CANSLIM methodology weight using O'Neil's original component weights.

---

## Component Weights

### Phase 3 Weights (Full CANSLIM - 7 Components)

| Component | Weight | Rationale |
|-----------|--------|-----------|
| **C** - Current Earnings | **15%** | Most predictive single factor (O'Neil's #1) |
| **A** - Annual Growth | **20%** | Validates sustainability of earnings growth |
| **N** - Newness | **15%** | Momentum confirmation critical |
| **S** - Supply/Demand | **15%** | Volume accumulation/distribution analysis |
| **L** - Leadership/RS Rank | **20%** | Largest weight (tied with A) - identifies sector leaders |
| **I** - Institutional Sponsorship | **10%** | Smart money confirmation |
| **M** - Market Direction | **5%** | Gating filter - affects all stocks |
| **Total** | **100%** | Original O'Neil weights |

### Legacy Phase Weights (Reference Only)

**Phase 1 MVP** (4 components - C, A, N, M): Renormalized to C 27%, A 36%, N 27%, M 10%
**Phase 2** (6 components - C, A, N, S, I, M): Renormalized to C 19%, A 25%, N 19%, S 19%, I 13%, M 6%

---

## Component Scoring Formulas (0-100 Scale)

Each component is scored on a 0-100 point scale based on O'Neil's quantitative thresholds.

### C - Current Quarterly Earnings (0-100 Points)

**Input Data Required:**
- Latest quarterly EPS (most recent quarter)
- Year-ago quarterly EPS (same quarter, prior year)
- Latest quarterly revenue
- Year-ago quarterly revenue

**Calculation:**
```python
eps_growth_pct = ((latest_qtr_eps - year_ago_qtr_eps) / abs(year_ago_qtr_eps)) * 100
revenue_growth_pct = ((latest_qtr_revenue - year_ago_qtr_revenue) / year_ago_qtr_revenue) * 100
```

**Scoring Logic:**
```python
if eps_growth_pct >= 50 and revenue_growth_pct >= 25:
    c_score = 100  # Explosive growth
elif eps_growth_pct >= 30 and revenue_growth_pct >= 15:
    c_score = 80   # Strong growth
elif eps_growth_pct >= 18 and revenue_growth_pct >= 10:
    c_score = 60   # Meets CANSLIM minimum
elif eps_growth_pct >= 10:
    c_score = 40   # Below threshold
else:
    c_score = 0    # Weak or negative growth
```

**Interpretation:**
- **100 points**: Exceptional - Top-tier earnings acceleration
- **80 points**: Strong - Well above CANSLIM threshold
- **60 points**: Acceptable - Meets minimum 18% threshold
- **40 points**: Weak - Below CANSLIM standards
- **0 points**: Fails - Insufficient growth

**Quality Checks:**
- If revenue growth < 50% of EPS growth → Investigate earnings quality (potential buyback-driven)
- If revenue is negative while EPS is positive → Red flag (cost-cutting, not growth)

---

### A - Annual EPS Growth (0-100 Points)

**Input Data Required:**
- Annual EPS for current year and previous 3 years (4 years total)
- Annual revenue for same 4 years (validation)

**Calculation:**
```python
# 3-year CAGR (Compound Annual Growth Rate)
eps_cagr_3yr = (((current_year_eps / eps_3_years_ago) ** (1/3)) - 1) * 100
revenue_cagr_3yr = (((current_year_revenue / revenue_3_years_ago) ** (1/3)) - 1) * 100

# Growth stability check
eps_values = [year1_eps, year2_eps, year3_eps, year4_eps]  # chronological order
stable = all(eps_values[i] >= eps_values[i-1] for i in range(1, 4))  # No down years
```

**Scoring Logic:**
```python
# Base score from EPS CAGR
if eps_cagr_3yr >= 40:
    base_score = 90
elif eps_cagr_3yr >= 30:
    base_score = 70
elif eps_cagr_3yr >= 25:
    base_score = 50  # Meets CANSLIM minimum
elif eps_cagr_3yr >= 15:
    base_score = 30
else:
    base_score = 0

# Revenue growth validation penalty
if revenue_cagr_3yr < (eps_cagr_3yr * 0.5):
    base_score = int(base_score * 0.8)  # 20% penalty for weak revenue growth

# Stability bonus
if stable:  # No down years
    base_score += 10

a_score = min(base_score, 100)  # Cap at 100
```

**Interpretation:**
- **90-100 points**: Exceptional - Sustainable high growth with stability
- **70-89 points**: Strong - Well above 25% threshold
- **50-69 points**: Acceptable - Meets CANSLIM minimum
- **30-49 points**: Weak - Below threshold
- **0-29 points**: Fails - Insufficient or erratic growth

**Quality Checks:**
- Stability bonus (+10) rewards consistency (no down years)
- Revenue validation prevents buyback-driven EPS growth from scoring high

---

### N - Newness / New Highs (0-100 Points)

**Input Data Required:**
- Current stock price
- 52-week high price
- 52-week low price
- Recent daily volume data (30 days)
- Average volume (30-day average)
- Recent news headlines (optional, for new product detection)

**Calculation:**
```python
# Distance from 52-week high
distance_from_high_pct = ((current_price / week_52_high) - 1) * 100

# Breakout detection (new high on volume)
breakout_detected = (
    current_price >= week_52_high * 0.995 and  # Within 0.5% of high
    recent_volume > avg_volume * 1.4           # Volume 40%+ above average
)

# New product signal detection (keyword search in news)
new_product_signals = search_news_keywords([
    "FDA approval", "patent granted", "breakthrough", "game-changer",
    "new product", "product launch", "expansion", "acquisition"
])
```

**Scoring Logic:**
```python
# Base score from price position
if distance_from_high_pct >= -5 and breakout_detected and new_product_signals:
    base_score = 100  # Perfect setup
elif distance_from_high_pct >= -10 and breakout_detected:
    base_score = 80   # Strong momentum
elif distance_from_high_pct >= -15 or breakout_detected:
    base_score = 60   # Acceptable
elif distance_from_high_pct >= -25:
    base_score = 40   # Weak momentum
else:
    base_score = 20   # Too far from highs

# Bonus for new product/catalyst signals (optional data)
if new_product_signals:
    if "FDA approval" in signals or "breakthrough" in signals:
        base_score += 20  # High-impact catalyst
    elif "new product" in signals or "acquisition" in signals:
        base_score += 10  # Moderate catalyst

n_score = min(base_score, 100)  # Cap at 100
```

**Interpretation:**
- **90-100 points**: Exceptional - At new highs with catalysts
- **70-89 points**: Strong - Near highs with volume confirmation
- **50-69 points**: Acceptable - Within 15% of highs
- **30-49 points**: Weak - Lacks momentum
- **0-29 points**: Fails - Too far from highs, no sponsorship

**Note**: Price position is primary signal (80% of score). New product detection is supplementary (20% bonus).

---

### M - Market Direction (0-100 Points)

**Input Data Required:**
- S&P 500 current price
- S&P 500 50-day Exponential Moving Average (EMA)
- VIX current level
- Follow-through day detection (optional advanced feature)

**Calculation:**
```python
# Distance from 50-day EMA
distance_from_ema_pct = ((sp500_price / sp500_ema_50) - 1) * 100

# Trend determination
if distance_from_ema_pct >= 2.0:
    trend = "strong_uptrend"
elif distance_from_ema_pct >= 0:
    trend = "uptrend"
elif distance_from_ema_pct >= -2.0:
    trend = "choppy"
elif distance_from_ema_pct >= -5.0:
    trend = "downtrend"
else:
    trend = "bear_market"
```

**Scoring Logic:**
```python
# Base score from trend
if trend == "strong_uptrend" and vix < 15:
    base_score = 100  # Ideal conditions
elif trend == "strong_uptrend" or (trend == "uptrend" and vix < 20):
    base_score = 80   # Favorable
elif trend == "uptrend":
    base_score = 60   # Acceptable
elif trend == "choppy":
    base_score = 40   # Neutral/caution
elif trend == "downtrend":
    base_score = 20   # Weak market
else:  # bear_market or vix > 30
    base_score = 0    # Avoid stocks entirely

# VIX adjustment (fear gauge)
if vix < 15:
    base_score += 10  # Low fear, bullish
elif vix > 30:
    base_score = 0    # Panic, override trend

# Follow-through day bonus (optional advanced feature)
if follow_through_day_detected:
    base_score += 10  # Confirmed institutional buying

m_score = min(max(base_score, 0), 100)  # Cap between 0-100
```

**Interpretation:**
- **90-100 points**: Strong bull market - Aggressive buying recommended
- **70-89 points**: Bull market - Standard position sizing
- **50-69 points**: Early uptrend - Small initial positions
- **30-49 points**: Choppy/neutral - Reduce exposure, be selective
- **10-29 points**: Downtrend - Defensive posture, minimal positions
- **0 points**: Bear market - Raise 80-100% cash, do not buy

**Critical Rule**: If M score = 0, **do not buy any stocks** regardless of other component scores. Market direction trumps stock selection.

---

### L - Leadership / Relative Strength (0-100 Points)

**Input Data Required:**
- Stock 52-week historical prices
- S&P 500 52-week historical prices (benchmark)

**Calculation:**
```python
# 52-week stock performance
stock_perf = ((current_price / price_52w_ago) - 1) * 100

# 52-week S&P 500 performance
sp500_perf = ((sp500_current / sp500_52w_ago) - 1) * 100

# Relative performance
relative_perf = stock_perf - sp500_perf

# RS Rank estimate (1-99 scale)
rs_rank = calculate_rs_rank(relative_perf)
```

**Scoring Logic:**
```python
if rs_rank >= 90:
    base_score = 100  # Top decile leader
elif rs_rank >= 80:
    base_score = 80   # Strong leader
elif rs_rank >= 70:
    base_score = 60   # Above average
elif rs_rank >= 60:
    base_score = 40   # Average
else:
    base_score = 20   # Laggard
```

**Interpretation:**
- **90-100 points**: Top RS leader - stock significantly outperforming market
- **70-89 points**: Strong relative strength - outperforming market
- **50-69 points**: Average relative strength
- **30-49 points**: Below average - underperforming market
- **0-29 points**: Laggard - significantly underperforming, avoid per CANSLIM

**O'Neil's Rule**: "Buy stocks with an RS rating of 80 or higher. Avoid laggards below 70."

---

## Composite Score Calculation

### Formula (Phase 3 - Full CANSLIM)

```python
composite_score = (
    c_score * 0.15 +  # Current Earnings: 15% weight
    a_score * 0.20 +  # Annual Growth: 20% weight
    n_score * 0.15 +  # Newness: 15% weight
    s_score * 0.15 +  # Supply/Demand: 15% weight
    l_score * 0.20 +  # Leadership/RS Rank: 20% weight
    i_score * 0.10 +  # Institutional: 10% weight
    m_score * 0.05    # Market Direction: 5% weight
)

# Result: 0-100 composite score
```

### Interpretation Bands (Phase 3)

| Score Range | Rating | Percentile | Meaning | Action |
|-------------|--------|------------|---------|--------|
| **90-100** | **Exceptional+** | Top 1-2% | Rare multi-bagger setup with full institutional backing | Immediate buy, aggressive sizing (15-20% position) |
| **80-89** | **Exceptional** | Top 5-10% | Outstanding fundamentals + accumulation | Strong buy, standard sizing (10-15% position) |
| **70-79** | **Strong** | Top 15-20% | High-quality CANSLIM stock | Buy on pullback, standard sizing (10-15%) |
| **60-69** | **Above Average** | Top 30% | Solid candidate, minor weaknesses | Watchlist, smaller sizing (5-10%) on pullback |
| **50-59** | **Average** | Top 50% | Meets minimums, lacks conviction | Watchlist, wait for improvement |
| **40-49** | **Below Average** | Bottom 50% | One or more components weak | Monitor only, do not buy |
| **<40** | **Weak** | Bottom 30% | Fails CANSLIM criteria | Avoid |

### Weakest Component Identification

For each stock, identify the component with the **lowest individual score** to guide further analysis:

```python
components = {
    'C': c_score,
    'A': a_score,
    'N': n_score,
    'S': s_score,
    'L': l_score,
    'I': i_score,
    'M': m_score
}

weakest_component = min(components, key=components.get)
weakest_score = components[weakest_component]
```

**Use Case**: Helps user understand risks
- Weakest = C → Earnings deceleration risk
- Weakest = A → Lack of sustained growth history
- Weakest = N → Lacks momentum, far from highs
- Weakest = S → Distribution pattern, institutions selling
- Weakest = L → Lagging market, not a sector leader
- Weakest = I → Underowned or overcrowded, investigate further
- Weakest = M → Poor market timing, consider waiting

### Formula (Phase 2 - 6 Components)

```python
composite_score = (
    c_score * 0.19 +  # Current Earnings: 19% weight
    a_score * 0.25 +  # Annual Growth: 25% weight
    n_score * 0.19 +  # Newness: 19% weight
    s_score * 0.19 +  # Supply/Demand: 19% weight (NEW)
    i_score * 0.13 +  # Institutional: 13% weight (NEW)
    m_score * 0.06    # Market Direction: 6% weight
)

# Result: 0-100 composite score (Phase 2)
```

### Interpretation Bands (Phase 2)

| Score Range | Rating | Percentile | Meaning | Action |
|-------------|--------|------------|---------|--------|
| **90-100** | **Exceptional+** | Top 1-2% | Rare multi-bagger setup with full institutional backing | Immediate buy, aggressive sizing (15-20% position) |
| **80-89** | **Exceptional** | Top 5-10% | Outstanding fundamentals + accumulation | Strong buy, standard sizing (10-15% position) |
| **70-79** | **Strong** | Top 15-20% | High-quality CANSLIM stock | Buy on pullback, standard sizing (10-15%) |
| **60-69** | **Above Average** | Top 30% | Solid candidate, minor weaknesses | Watchlist, smaller sizing (5-10%) on pullback |
| **<60** | **Below Standard** | Bottom 70% | Fails one or more thresholds | Monitor only, do not buy |

**Key Improvement**: Phase 2 scores include institutional validation (S, I components), making them more predictive than Phase 1.

### Minimum Thresholds (Phase 2)

All 6 components must meet baseline criteria to qualify as a CANSLIM candidate:

```python
thresholds = {
    "C": 60,  # 18%+ quarterly EPS growth
    "A": 50,  # 25%+ annual CAGR
    "N": 40,  # Within 15% of 52-week high
    "S": 40,  # Accumulation pattern (ratio ≥ 1.0)
    "I": 40,  # 30+ holders OR 20%+ ownership
    "M": 40   # Market in uptrend
}

# Stock passes if ALL components >= thresholds
passes_threshold = all(score >= thresholds[comp] for comp, score in scores.items())
```

**Failure Interpretation**:
- Fails C threshold → Earnings deceleration, avoid
- Fails A threshold → Lacks sustained growth, not a growth stock
- Fails N threshold → Too far from highs, wait for strength
- Fails S threshold → Distribution pattern, institutions selling
- Fails I threshold → Neglected by institutions, lacks backing
- Fails M threshold → Bear market, wait for market recovery

### Weakest Component Identification (Phase 2)

```python
components = {
    'C': c_score,
    'A': a_score,
    'N': n_score,
    'S': s_score,  # NEW
    'I': i_score,  # NEW
    'M': m_score
}

weakest_component = min(components, key=components.get)
weakest_score = components[weakest_component]
```

**Additional Interpretations**:
- Weakest = S → Distribution pattern, institutions selling - caution
- Weakest = I → Underowned or overcrowded, investigate further

---

## Example Calculations

### Example 1: NVDA (2023 Q2) - Exceptional Setup

**Component Scores:**
- **C Score**: 100 points (EPS +429% YoY, Revenue +101% YoY)
- **A Score**: 95 points (3yr CAGR 89%, stable, revenue strong)
- **N Score**: 98 points (New all-time high, AI catalyst, breakout volume)
- **M Score**: 100 points (S&P 500 in strong uptrend, VIX <15)

**Composite Calculation:**
```python
composite = (100 * 0.27) + (95 * 0.36) + (98 * 0.27) + (100 * 0.10)
          = 27.0 + 34.2 + 26.46 + 10.0
          = 97.66 points
```

**Rating**: Exceptional (97.66/100)
**Interpretation**: Textbook CANSLIM setup - all components aligned, rare multi-bagger candidate
**Weakest Component**: A (95) - even this is exceptional
**Action**: Strong buy, aggressive position sizing (15-20% of portfolio)

---

### Example 2: META (2023 Q3) - Strong Setup

**Component Scores:**
- **C Score**: 85 points (EPS +164% YoY, Revenue +23% YoY)
- **A Score**: 78 points (3yr CAGR 28%, recovery from 2022 trough, stable recent)
- **N Score**: 88 points (5% from 52-week high, breakout pattern)
- **M Score**: 80 points (S&P 500 above EMA, VIX 18)

**Composite Calculation:**
```python
composite = (85 * 0.27) + (78 * 0.36) + (88 * 0.27) + (80 * 0.10)
          = 22.95 + 28.08 + 23.76 + 8.0
          = 82.79 points
```

**Rating**: Exceptional (82.79/100)
**Interpretation**: Strong CANSLIM candidate, slight weakness in historical growth
**Weakest Component**: A (78) - recovering from prior downturn
**Action**: Buy, standard position sizing (10-15% of portfolio)

---

### Example 3: Hypothetical "Average" Stock

**Component Scores:**
- **C Score**: 60 points (EPS +20% YoY - meets minimum)
- **A Score**: 55 points (3yr CAGR 26%, one down year)
- **N Score**: 65 points (12% from high, no catalyst)
- **M Score**: 60 points (S&P 500 just above EMA, early uptrend)

**Composite Calculation:**
```python
composite = (60 * 0.27) + (55 * 0.36) + (65 * 0.27) + (60 * 0.10)
          = 16.2 + 19.8 + 17.55 + 6.0
          = 59.55 points
```

**Rating**: Average (59.55/100)
**Interpretation**: Meets minimum thresholds but lacks conviction
**Weakest Component**: A (55) - inconsistent growth history
**Action**: Watchlist only, wait for A or N component to strengthen

---

### Example 4: Bear Market Scenario (M Score = 0)

**Component Scores:**
- **C Score**: 100 points (Excellent earnings)
- **A Score**: 90 points (Excellent growth)
- **N Score**: 95 points (New highs)
- **M Score**: 0 points (S&P 500 in bear market, VIX > 30)

**Composite Calculation:**
```python
composite = (100 * 0.27) + (90 * 0.36) + (95 * 0.27) + (0 * 0.10)
          = 27.0 + 32.4 + 25.65 + 0
          = 85.05 points
```

**Rating**: Exceptional fundamentals (85.05) BUT bear market
**Interpretation**: **DO NOT BUY** despite high score - market direction overrides stock quality
**Weakest Component**: M (0) - bear market environment
**Action**: Raise cash, wait for M score > 40 (market recovery signal)

**Critical Lesson**: This example illustrates O'Neil's principle: "You can be right about a stock but wrong about the market, and still lose money."

---

## Scoring Evolution History

Phase 3 (current) uses the original O'Neil weights across all 7 components. Previous phases used renormalized weights to compensate for missing components:

- **Phase 1 MVP** (4 components): C 27%, A 36%, N 27%, M 10%
- **Phase 2** (6 components): C 19%, A 25%, N 19%, S 19%, I 13%, M 6%
- **Phase 3** (7 components): C 15%, A 20%, N 15%, S 15%, L 20%, I 10%, M 5% (original O'Neil weights)

---

## Usage Notes

### For Screener Implementation

1. **Calculate all 7 component scores** (C, A, N, S, L, I, M) for each stock
2. **Apply composite formula** with Phase 3 weights
3. **Identify weakest component** for each stock
4. **Rank stocks** by composite score (highest to lowest)
5. **Apply market filter** FIRST: If M score < 40, warn user to reduce exposure

### For User Reports

**Include in output**:
- Composite score (0-100)
- Rating (Exceptional / Strong / Above Average / Average / Below Average / Weak)
- Individual component scores (C, A, N, S, L, I, M)
- Weakest component identification
- Interpretation guidance
- Recommended action (buy / watchlist / avoid)

**Format Example**:
```
NVDA - NVIDIA Corporation
Composite Score: 95.2 / 100 (Exceptional+)

Component Breakdown:
C (Current Earnings): 100 / 100 - Explosive growth (EPS +429% YoY)
A (Annual Growth): 95 / 100 - Exceptional 3yr CAGR (89%)
N (Newness): 98 / 100 - At new highs with AI catalyst
S (Supply/Demand): 85 / 100 - Strong accumulation pattern
L (Leadership): 92 / 100 - RS Rank 95, sector leader
I (Institutional): 90 / 100 - 6199 holders, 68% ownership
M (Market Direction): 100 / 100 - Strong bull market

Weakest Component: S (85) - Strong accumulation
Recommendation: Strong buy - Rare multi-bagger setup
```

---

## Validation and Testing

### Test Cases

Validate scoring system with known CANSLIM winners:

**Expected Results (Phase 1 MVP)**:
- NVDA (2023 Q2): 95-100 points (Exceptional)
- META (2023 Q3): 80-90 points (Exceptional/Strong)
- AAPL (2009 Q3): 85-95 points (Exceptional)
- TSLA (2020 Q3): 80-90 points (Exceptional)

**Expected Results for Non-CANSLIM Stocks**:
- Declining earnings stocks: C < 40 → Composite < 50
- Stocks far from highs: N < 40 → Composite < 60
- In bear markets: M = 0 → Warning generated regardless of other scores

### Scoring System Integrity Checks

1. **Range Validation**: All component scores must be 0-100
2. **Weight Validation**: Sum of weights = 100% (0.27 + 0.36 + 0.27 + 0.10 = 1.00)
3. **Monotonicity**: Higher inputs → Higher scores (linear or step-function increases)
4. **Boundary Conditions**: Test edge cases (zero EPS, negative growth, etc.)
5. **Historical Validation**: Backtest on known winners 2019-2024

---

This scoring system provides a quantitative, objective framework for implementing O'Neil's complete CANSLIM methodology. Phase 3 implements all 7 components with original O'Neil weights, providing comprehensive growth stock screening.
