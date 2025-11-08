# Statistical Arbitrage and Pair Trading Methodology

## Table of Contents

1. [Introduction to Pair Trading](#introduction-to-pair-trading)
2. [Theoretical Foundation](#theoretical-foundation)
3. [Pair Selection Process](#pair-selection-process)
4. [Statistical Tests](#statistical-tests)
5. [Spread Construction and Analysis](#spread-construction-and-analysis)
6. [Entry and Exit Rules](#entry-and-exit-rules)
7. [Risk Management](#risk-management)
8. [Common Pitfalls](#common-pitfalls)
9. [Advanced Topics](#advanced-topics)

---

## Introduction to Pair Trading

### What is Pair Trading?

Pair trading is a market-neutral trading strategy that involves simultaneously buying and selling two highly correlated securities. The strategy profits from the convergence of prices when the relationship between the two stocks temporarily diverges from its historical equilibrium.

**Key Characteristics:**
- **Market Neutral**: Long one stock, short another → net beta ≈ 0
- **Mean Reverting**: Relies on temporary deviations from equilibrium
- **Statistical Foundation**: Based on mathematical relationships, not discretion
- **Relative Value**: Profits from relative performance, not absolute direction

### Historical Context

Pair trading was pioneered by **Gerry Bamberger** and later developed by **Nunzio Tartaglia** at Morgan Stanley in the 1980s. The quantitative team identified pairs of stocks whose prices historically moved together and profited when temporary divergences occurred.

**Evolution:**
- 1980s: Manual pair selection, simple spread tracking
- 1990s: Statistical models (cointegration, Kalman filters)
- 2000s: High-frequency pair trading, algorithmic execution
- 2010s+: Machine learning, regime detection, multi-asset pairs

### Why Pair Trading Works

**Economic Rationale:**
1. **Sector/Industry Linkages**: Companies in same sector share common drivers (demand, regulation, input costs)
2. **Temporary Mispricing**: Information asymmetry, behavioral biases, technical flows create temporary price divergences
3. **Mean Reversion**: Economic forces pull prices back to equilibrium (arbitrage, fundamentals)
4. **Supply Chain Relationships**: Suppliers and customers often move together

**Statistical Rationale:**
- Cointegration ensures long-run equilibrium relationship
- Short-term deviations are statistically predictable
- Z-score framework provides objective entry/exit rules

---

## Theoretical Foundation

### Cointegration vs Correlation

**Correlation:**
- Measures short-term co-movement of returns
- Range: -1 to +1
- Can be unstable over time
- Does not imply mean reversion

**Cointegration:**
- Measures long-term equilibrium relationship between price levels
- Ensures spread is stationary (mean-reverting)
- More stable foundation for pair trading
- Implies prices won't drift apart indefinitely

**Mathematical Definition:**

Two time series `P_A(t)` and `P_B(t)` are cointegrated if:
```
Spread(t) = P_A(t) - β * P_B(t)
```
is stationary (mean-reverting), where β is the cointegration coefficient.

### Stationarity

A time series is **stationary** if:
1. Constant mean over time
2. Constant variance over time
3. Autocorrelation depends only on time lag, not time itself

**Why Stationarity Matters for Pair Trading:**
- Non-stationary spread → prices can diverge forever → no mean reversion
- Stationary spread → prices revert to mean → profitable trade opportunities
- Cointegration ensures spread stationarity

### Mean Reversion

The spread follows an **Ornstein-Uhlenbeck (OU) process**:
```
dS(t) = θ(μ - S(t))dt + σdW(t)
```

Where:
- `S(t)`: Spread at time t
- `θ`: Mean reversion speed (higher = faster reversion)
- `μ`: Long-term mean of spread
- `σ`: Volatility of spread
- `dW(t)`: Brownian motion (random noise)

**Half-Life:**

Time for spread to revert halfway to its mean:
```
Half-Life = ln(2) / θ
```

**Interpretation:**
- Half-life = 10 days: Very fast mean reversion (suitable for day trading)
- Half-life = 30 days: Standard speed (typical pair trades)
- Half-life = 60+ days: Slow reversion (requires patience, longer holding)

---

## Pair Selection Process

### Step 1: Universe Definition

**Sector-Based Approach (Recommended):**
- Focus on stocks within same sector (e.g., Technology, Financials)
- Common drivers increase likelihood of cointegration
- Examples:
  - Tech: AAPL/MSFT, GOOGL/META, NVDA/AMD
  - Financials: JPM/BAC, GS/MS, WFC/USB
  - Energy: XOM/CVX, COP/EOG

**Industry-Specific Approach:**
- Narrow to specific industry (e.g., "Software" within Tech, "Regional Banks" within Financials)
- Stronger fundamental linkages
- Fewer pairs but higher quality

**Custom Approach:**
- User-specified list of stocks
- Allows testing hypotheses (e.g., supply chain pairs, competitor pairs)

**Filtering Criteria:**
- Market cap ≥ $2B (liquidity and stability)
- Average volume ≥ 1M shares/day (execution feasibility)
- Same exchange preferred (NYSE/NYSE, NASDAQ/NASDAQ)
- Exclude recent IPOs (<2 years) and distressed stocks

### Step 2: Correlation Screening

**Calculate Pearson Correlation:**
```python
import pandas as pd
import numpy as np

# Returns-based correlation
correlation = returns_A.corr(returns_B)

# Price-based correlation (for reference)
price_correlation = prices_A.corr(prices_B)
```

**Thresholds:**
- **Excellent (ρ ≥ 0.85)**: Very strong co-movement, best candidates
- **Good (ρ 0.70-0.85)**: Strong relationship, acceptable
- **Marginal (ρ 0.50-0.70)**: Moderate, requires strong cointegration
- **Poor (ρ < 0.50)**: Weak, likely not cointegrated

**Correlation Stability:**

Test correlation over multiple periods:
```python
# 6-month rolling correlation
rolling_corr = returns_A.rolling(126).corr(returns_B)

# Stability metric: std deviation of rolling correlation
stability = rolling_corr.std()

# Prefer pairs with low stability (<0.10)
```

**Red Flags:**
- Correlation declining sharply in recent period
- High correlation volatility (correlation jumps around)
- Correlation approaching zero or turning negative

### Step 3: Beta Estimation (Hedge Ratio)

**Ordinary Least Squares (OLS) Regression:**
```python
from scipy import stats

# Regress Price_A on Price_B
slope, intercept, r_value, p_value, std_err = stats.linregress(prices_B, prices_A)

beta = slope  # Hedge ratio
```

**Interpretation:**
- Beta = 1.0: Equal dollar hedge ($1 long A, $1 short B)
- Beta = 1.5: $1 long A, $1.50 short B
- Beta = 0.8: $1 long A, $0.80 short B

**Alternative Methods:**
- **Total Least Squares (TLS)**: Accounts for error in both variables
- **Kalman Filter**: Time-varying beta (advanced)
- **Rolling OLS**: Adaptive beta over time

### Step 4: Cointegration Testing

**Augmented Dickey-Fuller (ADF) Test:**

Tests null hypothesis: "Spread has unit root (non-stationary)"

```python
from statsmodels.tsa.stattools import adfuller

# Calculate spread
spread = prices_A - (beta * prices_B)

# ADF test
result = adfuller(spread, maxlag=1, regression='c')
adf_statistic = result[0]
p_value = result[1]
critical_values = result[4]

# Interpret
is_cointegrated = p_value < 0.05
```

**Interpretation:**
- **p < 0.01**: Very strong cointegration (reject null at 99% confidence)
- **p 0.01-0.05**: Moderate cointegration (reject null at 95% confidence)
- **p > 0.05**: No cointegration (fail to reject null)

**Critical Values:**
- ADF stat < critical value (1%) → Very strong evidence
- ADF stat < critical value (5%) → Moderate evidence
- ADF stat > critical value (10%) → Weak evidence

**Alternative Cointegration Tests:**
- **Engle-Granger Two-Step**: Similar to ADF
- **Johansen Test**: Multi-variate cointegration (for >2 stocks)
- **Phillips-Ouliaris Test**: More robust to structural breaks

---

## Statistical Tests

### Stationarity Tests

**Augmented Dickey-Fuller (ADF):**
- Most common stationarity test
- Tests for unit root in time series
- Null hypothesis: Series has unit root (non-stationary)

**Kwiatkowski-Phillips-Schmidt-Shin (KPSS):**
- Complementary to ADF
- Null hypothesis: Series is stationary
- Use both tests for robustness:
  - ADF rejects + KPSS fails to reject → Stationary
  - ADF fails to reject + KPSS rejects → Non-stationary

**Phillips-Perron (PP) Test:**
- Non-parametric alternative to ADF
- More robust to heteroskedasticity and serial correlation

### Half-Life Estimation

**AR(1) Model Approach:**

Model spread as first-order autoregressive process:
```
S(t) = α + φ * S(t-1) + ε(t)
```

Where:
- φ: Autocorrelation coefficient
- Mean reversion speed: θ = -ln(φ)
- Half-life: HL = ln(2) / θ

**Python Implementation:**
```python
from statsmodels.tsa.ar_model import AutoReg

# Fit AR(1) model
model = AutoReg(spread, lags=1)
result = model.fit()
phi = result.params[1]

# Calculate half-life
theta = -np.log(phi)
half_life = np.log(2) / theta
```

**Interpretation:**
- HL < 20 days: Very fast mean reversion
- HL 20-40 days: Fast mean reversion (ideal for pair trading)
- HL 40-60 days: Moderate mean reversion
- HL > 60 days: Slow mean reversion (less attractive)

### Structural Break Detection

**Chow Test:**

Tests for structural break at known date (e.g., major corporate event):
```python
from statsmodels.stats.diagnostic import breaks_cusumolsresid

# Test for breaks
stat, pvalue = breaks_cusumolsresid(ols_residuals)

# Interpret
has_structural_break = pvalue < 0.05
```

**CUSUM Test:**
- Detects unknown breakpoints
- Plots cumulative sum of residuals
- Sharp changes indicate structural breaks

**Practical Implication:**
- If structural break detected → Re-estimate cointegration relationship
- If break persists → Abandon pair (relationship broken)

---

## Spread Construction and Analysis

### Spread Definitions

**Price Difference (Additive):**
```
Spread(t) = P_A(t) - β * P_B(t)
```

**Advantages:**
- Simpler interpretation
- Stationary under cointegration

**Disadvantages:**
- Units depend on price levels
- Not suitable for stocks with very different prices

**Price Ratio (Multiplicative):**
```
Spread(t) = P_A(t) / P_B(t)
```

**Advantages:**
- Unit-free (ratio has no units)
- Better for stocks with different price levels
- Percentage-based interpretation

**Disadvantages:**
- Log transformation often needed for stationarity
- More complex statistics

**Log Price Ratio:**
```
Spread(t) = ln(P_A(t)) - ln(P_B(t))
```

**Advantages:**
- Ensures stationarity
- Returns-like interpretation
- Symmetric around zero

### Z-Score Calculation

**Definition:**
```
Z(t) = [Spread(t) - μ] / σ
```

Where:
- μ: Mean of spread over lookback period
- σ: Standard deviation of spread over lookback period

**Lookback Period:**
- **90 days (short-term)**: Responsive to recent changes, noisier
- **180 days (medium-term)**: Balanced approach (recommended)
- **252 days (long-term)**: Stable parameters, slower to adapt

**Rolling vs Expanding Window:**

**Rolling Window:**
```python
rolling_mean = spread.rolling(90).mean()
rolling_std = spread.rolling(90).std()
zscore = (spread - rolling_mean) / rolling_std
```
- Adapts to changing spread dynamics
- Can miss long-term trends

**Expanding Window:**
```python
expanding_mean = spread.expanding().mean()
expanding_std = spread.expanding().std()
zscore = (spread - expanding_mean) / expanding_std
```
- Uses all historical data
- More stable but less adaptive

### Spread Distribution Analysis

**Normality Test:**
```python
from scipy.stats import normaltest

# Test if spread is normally distributed
stat, pvalue = normaltest(spread)
is_normal = pvalue > 0.05
```

**If spread is NOT normal:**
- Use percentile-based thresholds instead of z-scores
- Example: Enter at 95th percentile instead of z > 2.0

**Skewness and Kurtosis:**
- Skewness ≠ 0: Asymmetric distribution (adjust thresholds)
- Kurtosis > 3: Fat tails (extreme values more common)

---

## Entry and Exit Rules

### Entry Conditions

**Conservative Strategy (Z ≥ ±2.0):**

**LONG Spread (Long A, Short B):**
```
Conditions:
1. Z-score < -2.0 (spread 2+ std devs below mean)
2. Cointegration p-value < 0.05
3. Correlation > 0.70
4. Half-life < 60 days
5. No structural breaks in recent 6 months

Action:
- Buy Stock A: $5,000
- Sell Stock B: $5,000 × β
```

**SHORT Spread (Short A, Long B):**
```
Conditions:
1. Z-score > +2.0 (spread 2+ std devs above mean)
2. [Same conditions 2-5 as above]

Action:
- Sell Stock A: $5,000
- Buy Stock B: $5,000 × β
```

**Aggressive Strategy (Z ≥ ±1.5):**
- Lower threshold → More frequent trades
- Higher win rate but smaller profits per trade
- Requires more active monitoring

**Very Aggressive (Z ≥ ±1.0):**
- Very frequent trades
- Transaction costs become significant
- Only viable with low commissions/rebates

### Exit Conditions

**Primary Exit: Mean Reversion**
```
Exit when Z-score crosses zero
→ Spread has reverted to mean
→ Close both legs simultaneously
```

**Partial Profit Taking:**
```
Stage 1: Exit 50% at Z-score = ±1.0
Stage 2: Exit remaining 50% at Z-score = 0
```

**Stop Loss:**
```
Hard Stop: Z-score > ±3.0
- Spread has diverged to extreme levels
- Possible structural break
→ Exit immediately to limit losses

Drawdown Stop: Total P/L < -5%
- Trade not working as expected
→ Exit to preserve capital
```

**Time-Based Exit:**
```
Maximum Holding Period: 90 days (or 3× half-life)
- If no mean reversion after expected timeframe
→ Exit to free up capital for better opportunities
```

### Signal Confirmation

**Additional Filters (Optional):**

**Volume Confirmation:**
- Require above-average volume on spread widening
- Confirms divergence is meaningful, not noise

**Trend Filter:**
- Avoid entry if overall market (SPY) trending strongly
- Correlations break down during market crashes/rallies

**Volatility Filter:**
- Skip entry if VIX > 30 (high volatility environment)
- Pair relationships less stable during volatility spikes

---

## Risk Management

### Position Sizing

**Equal Dollar Allocation:**
```
For $10,000 total allocation to one pair:
- Long Leg: $5,000
- Short Leg: $5,000 × β

If β = 1.2:
- Long Stock A: $5,000
- Short Stock B: $6,000
```

**Volatility-Adjusted Sizing:**

Scale position size by inverse of spread volatility:
```
Position Size = Base Size / (Spread Volatility / Avg Spread Volatility)
```
- High volatility pair → Smaller position
- Low volatility pair → Larger position

### Portfolio-Level Risk

**Diversification:**
- **Minimum**: 5 pairs (reduce idiosyncratic risk)
- **Optimal**: 8-10 pairs (balance diversification and management)
- **Maximum**: 15 pairs (diminishing returns, management complexity)

**Correlation Across Pairs:**
- Avoid multiple pairs with overlapping stocks (e.g., AAPL/MSFT and AAPL/GOOGL)
- Limit exposure to single sector (<50% of pairs)
- Monitor portfolio beta (should be near zero)

**Maximum Risk Allocation:**
- Single pair: 10-15% of total portfolio
- All pairs combined: 60-80% of total portfolio (rest in cash/T-bills)

### Transaction Costs

**Components:**
- **Commissions**: $0 (most brokers) but check per-share fees
- **Spread**: Bid-ask spread cost (0.01-0.05% per leg)
- **Slippage**: Market impact (0.02-0.10% per leg)
- **Short Interest**: Borrow costs for short leg (0-50% annual)
- **Hard-to-Borrow Fees**: Additional fees for difficult shorts

**Total Round-Trip Cost Estimate:**
```
Conservative: 0.4% (0.1% per leg × 4 legs)
With Short Interest: 0.4% + (0.5% × days held / 365)
```

**Breakeven Z-Score:**

Minimum z-score to exceed transaction costs:
```
Z_min = Total Transaction Cost / Expected Profit per Std Dev
```

Example:
- Transaction cost: 0.4%
- Expected profit per std dev: 0.8%
- Z_min = 0.4% / 0.8% = 0.5

→ Only enter if |Z| > 2.0 (provides 2σ × 0.8% = 1.6% profit, well above 0.4% cost)

### Margin and Leverage

**Regulation T Requirements:**
- Long stock: 50% initial margin
- Short stock: 50% initial margin + 100% collateral
- Pair trade: Effectively 100% margin requirement

**Example:**
```
Long $10,000 Stock A:
- Margin required: $5,000

Short $10,000 Stock B:
- Margin required: $5,000
- Collateral required: $10,000
- Total tied up: $15,000

Total capital required: $20,000 for $20,000 exposure
→ No leverage in market-neutral pair trading
```

**Portfolio Margin (Advanced):**
- Recognizes offsetting risk of pair
- May reduce margin requirement to 50-70% of Reg T
- Requires $125K account minimum

---

## Common Pitfalls

### 1. Survivorship Bias

**Problem:**
- Screening only currently listed stocks
- Excludes delisted stocks (bankruptcies, acquisitions)
- Overstates historical performance

**Solution:**
- Use survivorship-bias-free databases
- Acknowledge backtest limitations
- Focus on forward testing

### 2. Look-Ahead Bias

**Problem:**
- Using future information in historical analysis
- Example: Calculating z-score with full-period mean/std dev

**Incorrect:**
```python
# Using entire dataset mean (look-ahead bias)
mean = spread.mean()
std = spread.std()
zscore = (spread - mean) / std
```

**Correct:**
```python
# Using rolling window (no look-ahead)
zscore = (spread - spread.rolling(90).mean()) / spread.rolling(90).std()
```

### 3. Overfitting

**Problem:**
- Optimizing parameters on same dataset used for testing
- Finding spurious relationships

**Solutions:**
- **Out-of-Sample Testing**: Train on 70%, test on 30%
- **Walk-Forward Analysis**: Roll optimization window forward
- **Simplicity**: Prefer simple rules (z=2.0) over complex optimization
- **Economic Rationale**: Require fundamental reason for pair relationship

### 4. Ignoring Structural Breaks

**Problem:**
- Corporate actions (mergers, spin-offs, restructuring)
- Business model changes
- Regulatory changes

**Examples:**
- Tech company pivots to cloud (changes growth profile)
- Bank undergoes merger (risk profile changes)
- Regulatory change affects one stock but not the other

**Detection:**
```python
# Check for sharp correlation drop
recent_corr = returns_A[-60:].corr(returns_B[-60:])
historical_corr = returns_A[:-60].corr(returns_B[:-60])

if recent_corr < historical_corr - 0.20:
    print("WARNING: Correlation breakdown detected")
```

### 5. Insufficient Liquidity

**Problem:**
- Small cap stocks with low volume
- Wide bid-ask spreads
- Market impact on entry/exit

**Solutions:**
- Require minimum avg volume (1M shares/day)
- Check spread as % of mid-price (<0.1% acceptable)
- Size positions relative to daily volume (<5% of avg daily volume)

### 6. Correlation ≠ Causation

**Problem:**
- Pairs with high correlation but no economic linkage
- Correlation may be spurious or temporary

**Example:**
- Stock A and Bitcoin have 0.80 correlation over 6 months
- No fundamental reason for relationship
- Likely to break down

**Solution:**
- Prefer pairs with clear economic linkage
- Same sector, supply chain, competitor dynamics

### 7. Regime Changes

**Problem:**
- Market regimes affect pair relationships
- Crisis periods: Correlations → 1 (all stocks down)
- Low volatility: Mean reversion fast
- High volatility: Mean reversion slow or absent

**VIX-Based Regime Filter:**
```
If VIX < 15: Normal regime → Trade all pairs
If VIX 15-25: Elevated volatility → Trade only high-quality pairs
If VIX > 25: Crisis mode → Exit all pairs, wait for stabilization
```

---

## Advanced Topics

### Time-Varying Hedge Ratios

**Problem with Static Beta:**
- Relationship between stocks changes over time
- Fixed beta may become outdated

**Kalman Filter Approach:**

Dynamically update beta based on new observations:
```python
from pykalman import KalmanFilter

# Set up Kalman filter
kf = KalmanFilter(
    transition_matrices=[1],
    observation_matrices=[prices_B],
    initial_state_mean=initial_beta,
    initial_state_covariance=1,
    observation_covariance=1,
    transition_covariance=0.01
)

# Estimate time-varying beta
state_means, state_covs = kf.filter(prices_A)
dynamic_beta = state_means.flatten()
```

**Advantages:**
- Adapts to changing relationship
- Reduces spread variance

**Disadvantages:**
- More complex implementation
- Risk of overfitting

### Multi-Pair Portfolios

**Basket Pair Trading:**

Instead of pairwise trades, construct baskets:
```
Long Basket: Equal-weight portfolio of Stock A, C, E
Short Basket: Equal-weight portfolio of Stock B, D, F
```

**Advantages:**
- Reduced idiosyncratic risk
- More stable spread
- Lower impact from single stock events

**Statistical Arbitrage Portfolios:**
- Screen entire universe for mispriced stocks
- Long top decile (undervalued)
- Short bottom decile (overvalued)
- Continuously rebalance

### Machine Learning Enhancements

**Cointegration Regime Classification:**

Use ML to predict when pairs are likely to mean-revert:
```python
from sklearn.ensemble import RandomForestClassifier

# Features: VIX, correlation stability, spread volatility, etc.
# Label: Did spread mean-revert within 30 days?

model = RandomForestClassifier()
model.fit(features, labels)

# Predict for current pair
will_revert = model.predict(current_features)
```

**Signal Enhancement:**
- Combine z-score with ML probability
- Only enter if z < -2.0 AND ML_prob > 0.70

**Caution:**
- Risk of overfitting
- Requires substantial out-of-sample testing

### Intraday Pair Trading

**High-Frequency Approach:**
- Use minute or tick data
- Faster mean reversion (half-life in hours/minutes)
- Requires low-latency execution

**Challenges:**
- Transaction costs dominate at high frequency
- Need for co-location, direct market access
- Market microstructure noise

**Recommendation:**
- Retail traders: Stick to daily/weekly pair trading
- Institutional: Intraday feasible with infrastructure

---

## Conclusion

Pair trading is a powerful market-neutral strategy with strong statistical and economic foundations. Success requires:

1. **Rigorous pair selection** (cointegration, not just correlation)
2. **Robust statistical testing** (ADF, half-life, structural breaks)
3. **Disciplined risk management** (position sizing, stop losses)
4. **Realistic cost modeling** (transaction costs, short interest)
5. **Continuous monitoring** (regime changes, correlation breakdowns)

**Key Takeaways:**
- Cointegration > Correlation
- Z-score provides objective framework
- Mean reversion is not guaranteed (use stop losses)
- Economic linkage strengthens statistical relationship
- Simplicity and robustness > complexity and optimization

**Further Reading:**
- Engle & Granger (1987): "Co-Integration and Error Correction: Representation, Estimation, and Testing"
- Gatev, Goetzmann, Rouwenhorst (2006): "Pairs Trading: Performance of a Relative-Value Arbitrage Rule"
- Vidyamurthy (2004): "Pairs Trading: Quantitative Methods and Analysis"
- Chan (2013): "Algorithmic Trading: Winning Strategies and Their Rationale" (Chapter 7)

---

**Document Version**: 1.0
**Last Updated**: 2025-11-08
**Author**: Claude Trading Skills - Pair Trade Screener
