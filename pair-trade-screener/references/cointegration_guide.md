# Cointegration Testing Guide

## Table of Contents

1. [What is Cointegration?](#what-is-cointegration)
2. [Cointegration vs Correlation](#cointegration-vs-correlation)
3. [Augmented Dickey-Fuller (ADF) Test](#augmented-dickey-fuller-adf-test)
4. [Practical Implementation](#practical-implementation)
5. [Interpreting Results](#interpreting-results)
6. [Half-Life Estimation](#half-life-estimation)
7. [Testing for Structural Breaks](#testing-for-structural-breaks)
8. [Case Studies](#case-studies)

---

## What is Cointegration?

### Intuitive Explanation

Imagine two drunk people walking home from a bar. They're both stumbling randomly, but one person has a dog on a leash. The person and the dog may wander in different directions temporarily, but the leash keeps them together in the long run. They are "cointegrated."

**In finance:**
- Person A = Stock A price
- Person B (with dog) = Stock B price
- Leash = Economic relationship (sector, supply chain, competition)

While both stock prices are non-stationary (random walks), their **difference** (or spread) is stationary because the economic "leash" pulls them back together.

### Mathematical Definition

Two non-stationary time series **X(t)** and **Y(t)** are cointegrated if there exists a coefficient **β** such that:

```
Spread(t) = X(t) - β * Y(t)
```

is stationary (mean-reverting).

**Key Components:**
- **X(t), Y(t)**: Non-stationary price series (random walks)
- **β**: Cointegration coefficient (hedge ratio)
- **Spread(t)**: Stationary series (mean-reverting)

### Why Cointegration Matters for Pair Trading

**Without Cointegration:**
- Prices can drift apart indefinitely
- No guarantee of mean reversion
- High risk of permanent losses

**With Cointegration:**
- Prices have long-term equilibrium
- Temporary deviations are predictable
- Mean reversion is statistically ensured

**Example:**

**Non-Cointegrated Pair:**
```
Stock A: Oil producer
Stock B: Tech company
Correlation: 0.75 (recent coincidence)

Result: No economic linkage → correlation breaks down → prices diverge forever
```

**Cointegrated Pair:**
```
Stock A: Exxon (XOM)
Stock B: Chevron (CVX)
Correlation: 0.92
Cointegration p-value: 0.008 (strong)

Result: Same sector, similar business → prices stay together → mean reversion reliable
```

---

## Cointegration vs Correlation

### Key Differences

| Aspect | Correlation | Cointegration |
|--------|-------------|---------------|
| **Measures** | Short-term returns co-movement | Long-term price level relationship |
| **Data** | First differences (returns) | Price levels |
| **Range** | -1 to +1 | p-value (0 to 1) |
| **Stationarity** | Assumes both series stationary | Allows non-stationary series |
| **Mean Reversion** | Does not imply | Guarantees (for spread) |
| **Stability** | Can be unstable | More stable |

### Why Correlation Alone is Insufficient

**Problem with Correlation:**

Two random walks can have high correlation **by chance** without any fundamental relationship.

**Example:**
```python
import numpy as np

# Generate two independent random walks
np.random.seed(42)
walk_A = np.cumsum(np.random.randn(252))
walk_B = np.cumsum(np.random.randn(252))

# Calculate correlation
correlation = np.corrcoef(walk_A, walk_B)[0, 1]
# Result: Might be 0.60-0.80 purely by chance!
```

**Key Point:**
- High correlation ≠ Mean reversion
- Need cointegration to ensure spread is stationary

### Combining Correlation and Cointegration

**Best Practice:**

Use both as filters:
1. **Correlation** (≥ 0.70): Quick screen for co-movement
2. **Cointegration** (p < 0.05): Rigorous test for mean reversion

**Decision Matrix:**

| Correlation | Cointegration | Trade? |
|-------------|---------------|--------|
| High (≥0.70) | Yes (p<0.05) | ✅ **YES** |
| High (≥0.70) | No (p>0.05) | ❌ **NO** |
| Low (<0.70) | Yes (p<0.05) | 🟡 **MAYBE** (unusual) |
| Low (<0.70) | No (p>0.05) | ❌ **NO** |

---

## Augmented Dickey-Fuller (ADF) Test

### Purpose

The ADF test determines whether a time series has a **unit root** (non-stationary) or is stationary.

**Hypotheses:**
- **Null (H0)**: Series has unit root (non-stationary)
- **Alternative (H1)**: Series is stationary

**For pair trading:**
- Test the **spread** (not individual prices)
- Reject H0 → Spread is stationary → Pair is cointegrated

### Test Procedure

**Step 1: Calculate Spread**
```python
spread = price_A - (beta * price_B)
```

**Step 2: Run ADF Test**
```python
from statsmodels.tsa.stattools import adfuller

result = adfuller(spread, maxlag=1, regression='c')
adf_statistic = result[0]
p_value = result[1]
critical_values = result[4]
```

**Parameters:**
- `maxlag=1`: Number of lags (typically 1 for daily data)
- `regression='c'`: Include constant term (drift)
- Alternatives: `'ct'` (constant + trend), `'n'` (no constant)

**Step 3: Interpret Results**
```python
if p_value < 0.05:
    print("Reject null → Spread is stationary → Cointegrated")
else:
    print("Fail to reject null → Not cointegrated")
```

### ADF Test Equation

The ADF test estimates:
```
ΔSpread(t) = α + β*Spread(t-1) + Σ(γ_i * ΔSpread(t-i)) + ε(t)
```

Where:
- ΔSpread(t) = Spread(t) - Spread(t-1) (first difference)
- β: Coefficient of interest (tests for unit root)
- α: Drift term
- Σ(γ_i * ΔSpread(t-i)): Lagged differences (capture serial correlation)

**Test Statistic:**
```
ADF = β / SE(β)
```

**Decision Rule:**
- If ADF < Critical Value → Reject null (stationary)
- If p-value < 0.05 → Reject null (stationary)

### Critical Values

**Standard Critical Values (constant, no trend):**

| Significance Level | Critical Value |
|--------------------|----------------|
| 1% | -3.43 |
| 5% | -2.86 |
| 10% | -2.57 |

**Example:**
```
ADF Statistic: -3.75
Critical Value (5%): -2.86

Since -3.75 < -2.86 → Reject null → Stationary
```

---

## Practical Implementation

### Complete Python Example

```python
import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import adfuller
from scipy import stats

# Step 1: Load price data
prices_A = pd.Series([100, 102, 104, 103, 105, ...])  # Stock A
prices_B = pd.Series([50, 51, 52, 51.5, 52.5, ...])    # Stock B

# Step 2: Calculate beta (hedge ratio)
slope, intercept, r_value, p_value, std_err = stats.linregress(prices_B, prices_A)
beta = slope

print(f"Beta (hedge ratio): {beta:.4f}")
print(f"Correlation: {r_value:.4f}")

# Step 3: Calculate spread
spread = prices_A - (beta * prices_B)

# Step 4: Run ADF test
adf_result = adfuller(spread, maxlag=1, regression='c')

adf_statistic = adf_result[0]
p_value = adf_result[1]
critical_values = adf_result[4]
n_lags = adf_result[2]

# Step 5: Display results
print("\n=== Cointegration Test Results ===")
print(f"ADF Statistic: {adf_statistic:.4f}")
print(f"P-value: {p_value:.4f}")
print(f"Number of Lags: {n_lags}")
print(f"\nCritical Values:")
for key, value in critical_values.items():
    print(f"  {key}: {value:.4f}")

# Step 6: Interpret
if p_value < 0.01:
    print("\n✅ STRONG Cointegration (p < 0.01)")
    strength = "★★★"
elif p_value < 0.05:
    print("\n✅ MODERATE Cointegration (p < 0.05)")
    strength = "★★"
else:
    print("\n❌ NOT Cointegrated (p > 0.05)")
    strength = "☆"

# Step 7: Calculate half-life (if cointegrated)
if p_value < 0.05:
    from statsmodels.tsa.ar_model import AutoReg

    model = AutoReg(spread, lags=1)
    result = model.fit()
    phi = result.params[1]

    half_life = -np.log(2) / np.log(phi)
    print(f"\nHalf-Life: {half_life:.1f} days")

    if half_life < 30:
        print("  → Fast mean reversion (excellent)")
    elif half_life < 60:
        print("  → Moderate mean reversion (good)")
    else:
        print("  → Slow mean reversion (acceptable)")
```

### FMP API Integration

```python
import requests
import pandas as pd

def get_price_history(symbol, api_key, days=730):
    """Fetch historical prices from FMP API"""
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}?apikey={api_key}"
    response = requests.get(url)
    data = response.json()

    # Extract historical prices
    hist = data['historical'][:days]
    hist = hist[::-1]  # Reverse to chronological order

    df = pd.DataFrame(hist)
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')

    return df['adjClose']

# Example usage
api_key = "YOUR_API_KEY"
prices_AAPL = get_price_history("AAPL", api_key)
prices_MSFT = get_price_history("MSFT", api_key)

# Align dates
common_dates = prices_AAPL.index.intersection(prices_MSFT.index)
prices_AAPL = prices_AAPL.loc[common_dates]
prices_MSFT = prices_MSFT.loc[common_dates]

# Test for cointegration
slope, intercept, r_value, p_value, std_err = stats.linregress(prices_MSFT, prices_AAPL)
beta = slope
spread = prices_AAPL - (beta * prices_MSFT)

adf_result = adfuller(spread, maxlag=1)
print(f"AAPL/MSFT Cointegration p-value: {adf_result[1]:.4f}")
```

---

## Interpreting Results

### P-Value Interpretation

**What p-value means:**
- Probability of observing test statistic if null hypothesis (unit root) is true
- Lower p-value = stronger evidence against null = stronger cointegration

**Guidelines:**

| P-Value Range | Interpretation | Confidence | Trade? |
|---------------|----------------|------------|--------|
| p < 0.01 | Very strong cointegration | 99% | ✅ **YES** (★★★) |
| p 0.01-0.03 | Strong cointegration | 97-99% | ✅ **YES** (★★★) |
| p 0.03-0.05 | Moderate cointegration | 95-97% | ✅ **YES** (★★) |
| p 0.05-0.10 | Weak evidence | 90-95% | 🟡 **MARGINAL** (★) |
| p > 0.10 | No cointegration | <90% | ❌ **NO** (☆) |

### ADF Statistic Interpretation

**More negative = stronger cointegration:**

```
ADF < -4.0: Very strong (★★★★)
ADF -3.5 to -4.0: Strong (★★★)
ADF -3.0 to -3.5: Moderate (★★)
ADF -2.5 to -3.0: Weak (★)
ADF > -2.5: Not cointegrated (☆)
```

**Example Rankings:**

```python
Pair A: ADF = -4.25, p = 0.002 → ★★★★ (Best)
Pair B: ADF = -3.65, p = 0.018 → ★★★ (Excellent)
Pair C: ADF = -2.95, p = 0.042 → ★★ (Good)
Pair D: ADF = -2.45, p = 0.125 → ☆ (Reject)
```

### Common Mistakes

**Mistake 1: Testing Individual Prices**
```python
# WRONG: Testing if stock price is stationary
adf_result = adfuller(prices_A)  # ❌ Will always fail (prices are random walks)
```

**Correct:**
```python
# RIGHT: Test if SPREAD is stationary
spread = prices_A - (beta * prices_B)
adf_result = adfuller(spread)  # ✅ Tests for cointegration
```

**Mistake 2: Ignoring Lag Selection**
```python
# WRONG: Using too many lags (overfitting)
adf_result = adfuller(spread, maxlag=20)  # ❌ Too complex

# RIGHT: Use simple lag structure
adf_result = adfuller(spread, maxlag=1)  # ✅ Appropriate for daily data
```

**Mistake 3: Confusing Correlation with Cointegration**
```python
# WRONG: Assuming high correlation = cointegration
if correlation > 0.80:
    trade_pair()  # ❌ Not sufficient

# RIGHT: Test for cointegration explicitly
if correlation > 0.70 and cointegration_pvalue < 0.05:
    trade_pair()  # ✅ Both conditions required
```

---

## Half-Life Estimation

### What is Half-Life?

Half-life measures how quickly the spread mean-reverts. Specifically, it's the expected time for the spread to move halfway back to its mean.

**Example:**
```
Current spread: +2.0 (2 std devs above mean)
Half-life: 20 days

Expected spread after 20 days: +1.0 (halfway to mean)
Expected spread after 40 days: +0.5 (halfway from +1.0 to 0)
```

### AR(1) Model Approach

Model spread as autoregressive process:
```
S(t) = α + φ * S(t-1) + ε(t)
```

Where:
- φ: Autocorrelation coefficient (persistence)
- φ close to 1.0 → Slow mean reversion (long half-life)
- φ close to 0.0 → Fast mean reversion (short half-life)

**Half-Life Formula:**
```
Half-Life = -ln(2) / ln(φ)
```

### Python Implementation

```python
from statsmodels.tsa.ar_model import AutoReg

# Fit AR(1) model to spread
model = AutoReg(spread, lags=1)
result = model.fit()

# Extract autocorrelation coefficient
phi = result.params[1]

# Calculate half-life
half_life = -np.log(2) / np.log(phi)

print(f"Autocorrelation (φ): {phi:.4f}")
print(f"Half-Life: {half_life:.1f} days")
```

### Interpreting Half-Life

| Half-Life | Speed | Suitability | Holding Period |
|-----------|-------|-------------|----------------|
| < 10 days | Very fast | Day/swing trading | < 2 weeks |
| 10-30 days | Fast | Short-term pairs | 2-6 weeks |
| 30-60 days | Moderate | Standard pairs | 1-3 months |
| 60-90 days | Slow | Long-term pairs | 2-6 months |
| > 90 days | Very slow | Poor for trading | Avoid |

**Trading Implications:**

**Fast Half-Life (< 30 days):**
- ✅ Quick profits
- ✅ Lower holding risk
- ✅ Frequent opportunities
- ❌ Transaction costs matter more

**Slow Half-Life (> 60 days):**
- ✅ More stable relationships
- ❌ Capital tied up longer
- ❌ Fewer trading opportunities
- ❌ Higher holding risk (regime changes)

### Half-Life Stability

**Test half-life over multiple periods:**
```python
# Calculate rolling half-life
rolling_half_life = []

for i in range(252, len(spread)):
    window = spread[i-252:i]
    model = AutoReg(window, lags=1)
    result = model.fit()
    phi = result.params[1]
    hl = -np.log(2) / np.log(phi)
    rolling_half_life.append(hl)

# Check stability
std_hl = np.std(rolling_half_life)
mean_hl = np.mean(rolling_half_life)
cv = std_hl / mean_hl  # Coefficient of variation

if cv < 0.30:
    print("Half-life is STABLE (good)")
else:
    print("Half-life is UNSTABLE (warning)")
```

---

## Testing for Structural Breaks

### Why Structural Breaks Matter

**Definition:**
- A structural break is a sudden, permanent change in the cointegration relationship
- Examples: Merger, spin-off, business model pivot, regulatory change

**Impact on Pair Trading:**
- Break in cointegration → Spread no longer mean-reverts
- Holding pair through break → Large losses
- Must detect breaks early and exit

### Chow Test

Tests for known breakpoint (e.g., specific corporate event date):

```python
from statsmodels.stats.diagnostic import breaks_cusumolsresid

# Fit OLS regression
from scipy import stats
slope, intercept = stats.linregress(prices_B, prices_A)[:2]
residuals = prices_A - (slope * prices_B + intercept)

# Test for structural breaks
stat, pvalue = breaks_cusumolsresid(residuals)

if pvalue < 0.05:
    print("⚠️ STRUCTURAL BREAK DETECTED")
else:
    print("✅ No structural break")
```

### Rolling Cointegration

**Monitor cointegration over time:**
```python
rolling_pvalues = []

for i in range(252, len(prices_A)):
    window_A = prices_A[i-252:i]
    window_B = prices_B[i-252:i]

    slope, intercept = stats.linregress(window_B, window_A)[:2]
    spread_window = window_A - (slope * window_B)

    adf_result = adfuller(spread_window, maxlag=1)
    pvalue = adf_result[1]
    rolling_pvalues.append(pvalue)

# Plot rolling p-values
import matplotlib.pyplot as plt
plt.plot(rolling_pvalues)
plt.axhline(y=0.05, color='r', linestyle='--', label='Significance threshold')
plt.ylabel('P-Value')
plt.xlabel('Time')
plt.title('Rolling Cointegration P-Value')
plt.legend()
plt.show()
```

**Interpretation:**
- P-value stays below 0.05 → Cointegration stable ✅
- P-value crosses above 0.05 → Cointegration breaking down ⚠️
- P-value remains above 0.10 → Relationship broken ❌

### Early Warning System

**Exit conditions based on cointegration degradation:**
```python
# Calculate 90-day rolling cointegration p-value
recent_pvalue = calculate_rolling_cointegration(prices_A[-90:], prices_B[-90:])

if recent_pvalue > 0.10:
    print("🚨 EXIT SIGNAL: Cointegration broken")
    exit_pair()
elif recent_pvalue > 0.05:
    print("⚠️ WARNING: Cointegration weakening")
    reduce_position()
else:
    print("✅ Cointegration healthy")
```

---

## Case Studies

### Case Study 1: XOM/CVX (Strong Cointegration)

**Background:**
- Exxon Mobil (XOM) and Chevron (CVX)
- Both: Large oil & gas companies
- Same sector, similar business models

**Analysis:**
```python
# 2-year data (2023-2025)
correlation: 0.94
beta: 1.08
adf_statistic: -4.25
p_value: 0.0008
half_life: 28 days
```

**Interpretation:**
- ✅ Very strong cointegration (p < 0.01)
- ✅ High correlation (0.94)
- ✅ Fast mean reversion (28 days)
- ✅ Economic linkage (same sector)

**Rating:** ★★★★ (Excellent pair)

**Trade Signal (Example):**
```
Current Z-Score: +2.3 (XOM expensive relative to CVX)
→ SHORT XOM, LONG CVX
Entry: Z > +2.0
Exit: Z < 0.0
Stop: Z > +3.0
```

### Case Study 2: JPM/BAC (Moderate Cointegration)

**Background:**
- JPMorgan Chase (JPM) and Bank of America (BAC)
- Both: Large banks
- Different focus areas (JPM more investment banking, BAC more retail)

**Analysis:**
```python
correlation: 0.85
beta: 1.35
adf_statistic: -3.12
p_value: 0.031
half_life: 42 days
```

**Interpretation:**
- ✅ Moderate cointegration (p = 0.031)
- ✅ Good correlation (0.85)
- ✅ Acceptable mean reversion (42 days)
- ⚠️ Different business mix (less perfect linkage)

**Rating:** ★★★ (Good pair)

### Case Study 3: AAPL/TSLA (No Cointegration)

**Background:**
- Apple (AAPL) and Tesla (TSLA)
- Both: High-growth tech stocks
- Different businesses (consumer electronics vs EVs)

**Analysis:**
```python
correlation: 0.72
beta: 0.88
adf_statistic: -2.15
p_value: 0.182
half_life: N/A (not stationary)
```

**Interpretation:**
- ❌ No cointegration (p = 0.182)
- ✅ Moderate correlation (0.72)
- ❌ No mean reversion
- ❌ Weak economic linkage

**Rating:** ☆ (Reject pair)

**Why correlation failed:**
- Both had high returns in 2023-2024 (growth stock rally)
- Correlation driven by macro factors (interest rates), not fundamental linkage
- Likely to diverge when market conditions change

### Case Study 4: Structural Break Example (GE)

**Background:**
- General Electric (GE) underwent major restructuring 2018-2021
- Spun off healthcare (GEHC) and energy divisions

**Analysis:**
```python
# Pre-spinoff (2018-2020): GE/UTX pair
correlation: 0.81
p_value: 0.025 (cointegrated)

# Post-spinoff (2021-2023): GE/UTX pair
correlation: 0.52
p_value: 0.235 (NOT cointegrated)
```

**Lesson:**
- Corporate actions can break cointegration
- Must monitor for structural breaks
- Exit pairs when cointegration deteriorates

---

## Summary Checklist

Before trading a pair, verify:

### Statistical Checklist
- [ ] Correlation ≥ 0.70 (preferably ≥ 0.80)
- [ ] Cointegration p-value < 0.05 (preferably < 0.03)
- [ ] ADF statistic < -3.0
- [ ] Half-life 20-60 days
- [ ] No structural breaks in recent 6 months

### Economic Checklist
- [ ] Same sector or supply chain relationship
- [ ] Similar business models
- [ ] No pending M&A or restructuring
- [ ] Similar market cap and liquidity
- [ ] Both stocks shortable (for short leg)

### Risk Checklist
- [ ] Transaction costs < expected profit
- [ ] Adequate liquidity (>1M avg volume)
- [ ] Position sized appropriately (10-15% max)
- [ ] Stop loss defined (Z > ±3.0)
- [ ] Maximum holding period set (90 days)

---

**Document Version**: 1.0
**Last Updated**: 2025-11-08
**References**:
- Engle & Granger (1987): "Co-Integration and Error Correction"
- Hamilton (1994): "Time Series Analysis" (Chapter 19)
- Tsay (2010): "Analysis of Financial Time Series" (Chapter 8)
