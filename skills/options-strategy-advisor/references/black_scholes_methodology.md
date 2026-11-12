# Black-Scholes Methodology Reference

## Overview

The Black-Scholes model is the foundation for theoretical options pricing in this skill. This document provides the mathematical framework and interpretation guidance.

## Black-Scholes Formula

### Call Option Price
```
C = S × e^(-qT) × N(d₁) - K × e^(-rT) × N(d₂)
```

### Put Option Price
```
P = K × e^(-rT) × N(-d₂) - S × e^(-qT) × N(-d₁)
```

### Parameters
| Symbol | Description | Typical Range |
|--------|-------------|---------------|
| S | Current stock price | Market price |
| K | Strike price | User selected |
| T | Time to expiration (years) | 0.01 - 2.0 |
| r | Risk-free rate | 0.03 - 0.06 |
| σ | Volatility | 0.10 - 1.00 |
| q | Dividend yield | 0.00 - 0.05 |

### d₁ and d₂ Calculations
```
d₁ = [ln(S/K) + (r - q + σ²/2) × T] / (σ × √T)
d₂ = d₁ - σ × √T
```

## The Greeks

### Delta (Δ)
- **Definition**: Price change per $1 move in underlying
- **Call**: 0 to +1 (positive, bullish)
- **Put**: -1 to 0 (negative, bearish)
- **ATM options**: ~0.50 (call) or ~-0.50 (put)

### Gamma (Γ)
- **Definition**: Rate of change of delta
- **Always positive** for long options
- **Highest at ATM**, decreases as option moves ITM/OTM
- **Increases** as expiration approaches

### Theta (Θ)
- **Definition**: Daily time decay ($/day)
- **Negative** for long options (lose value daily)
- **Positive** for short options (collect decay)
- **Accelerates** in final 30 days

### Vega (ν)
- **Definition**: Price change per 1% IV move
- **Always positive** for long options
- **Highest at ATM**
- **Critical** for earnings plays

### Rho (ρ)
- **Definition**: Price change per 1% rate change
- **Positive** for calls, **negative** for puts
- **Small impact** in short-dated options

## Historical vs Implied Volatility

| Metric | Description | Source |
|--------|-------------|--------|
| HV (Historical) | Past price movement | Calculated from prices |
| IV (Implied) | Market expectation | Derived from option prices |

### IV-HV Relationship
- **IV > HV**: Options expensive → consider selling premium
- **IV < HV**: Options cheap → consider buying
- **IV ≈ HV**: Fairly priced

### IV Percentile Interpretation
| Percentile | Interpretation | Strategy Bias |
|------------|----------------|---------------|
| >80% | Very high IV | Sell premium |
| 50-80% | Elevated IV | Neutral/sell |
| 20-50% | Normal IV | Direction-based |
| <20% | Low IV | Buy premium |

## Model Limitations

### Assumptions (Not Always True)
1. **Constant volatility** - IV changes constantly
2. **European exercise** - American options can exercise early
3. **No transaction costs** - Commissions and slippage exist
4. **Continuous trading** - Gaps and halts occur
5. **Log-normal distribution** - Fat tails exist in practice

### When Model Underperforms
- Deep ITM American puts (early exercise value)
- Near expiration with high gamma
- Earnings/events (IV regime change)
- Low liquidity options (wide bid-ask)

## Practical Adjustments

### American Options
- Calls: Black-Scholes accurate if no dividends
- Puts: May undervalue ITM puts near expiration
- Solution: Note "European pricing approximation"

### Dividend Handling
- Include dividend yield (q) in calculations
- For discrete dividends: subtract PV from stock price
- Ex-dividend dates affect early exercise decisions

## Strategy Selection Framework

### By Market Outlook
| Outlook | Delta Target | Strategies |
|---------|--------------|------------|
| Bullish | +0.3 to +0.7 | Long call, bull spread, covered call |
| Bearish | -0.3 to -0.7 | Long put, bear spread, protective put |
| Neutral | -0.1 to +0.1 | Iron condor, straddle, butterfly |

### By Volatility View
| IV View | Vega Target | Strategies |
|---------|-------------|------------|
| IV rising | Positive | Long straddle, long strangle |
| IV falling | Negative | Iron condor, short straddle |
| IV neutral | Near zero | Spreads, collars |

## Position Sizing Guidelines

### Risk-Based Sizing
```
Max Contracts = (Account Risk $) / (Max Loss per Contract)
```

### Portfolio Greeks Limits
| Greek | Conservative | Moderate | Aggressive |
|-------|--------------|----------|------------|
| Delta | ±10 | ±25 | ±50 |
| Theta | +$50/day | +$150/day | +$300/day |
| Vega | ±$200 | ±$500 | ±$1000 |

## Step 3 detail: Price Options Using Black-Scholes

Note: the formulas below are the plain textbook form. The implementation in `scripts/black_scholes.py` and the Black-Scholes Formula section above use a continuous dividend yield `q`, which replaces the "subtract present value of dividends from S" adjustment.

**Black-Scholes Model:**

For European-style options:
```
Call Price = S * N(d1) - K * e^(-r*T) * N(d2)
Put Price = K * e^(-r*T) * N(-d2) - S * N(-d1)

Where:
d1 = [ln(S/K) + (r + σ²/2) * T] / (σ * √T)
d2 = d1 - σ * √T

S = Current stock price
K = Strike price
r = Risk-free rate
T = Time to expiration (years)
σ = Volatility (IV or HV)
N() = Cumulative standard normal distribution
```

**Adjustments:**
- Subtract present value of dividends from S for calls
- American options: Use approximation or note "European pricing, may undervalue American options"

**Python Implementation:**
```python
from scipy.stats import norm
import numpy as np

def black_scholes_call(S, K, T, r, sigma, q=0):
    """
    S: Stock price
    K: Strike price
    T: Time to expiration (years)
    r: Risk-free rate
    sigma: Volatility
    q: Dividend yield
    """
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)

    call_price = S*np.exp(-q*T)*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    return call_price

def black_scholes_put(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)

    put_price = K*np.exp(-r*T)*norm.cdf(-d2) - S*np.exp(-q*T)*norm.cdf(-d1)
    return put_price
```

**Output for Each Option Leg:**
- Theoretical price
- Note: "Market price may differ due to bid-ask spread and American vs European pricing"

## Step 4 detail: Calculate Greeks

**The Greeks** measure option price sensitivity to various factors:

**Delta (Δ):** Change in option price per $1 change in stock price
```python
def delta_call(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * norm.cdf(d1)

def delta_put(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * (norm.cdf(d1) - 1)
```

**Gamma (Γ):** Change in delta per $1 change in stock price
```python
def gamma(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
```

**Theta (Θ):** Change in option price per day (time decay)
```python
def theta_call(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)

    theta = (-S*norm.pdf(d1)*sigma*np.exp(-q*T)/(2*np.sqrt(T))
             - r*K*np.exp(-r*T)*norm.cdf(d2)
             + q*S*norm.cdf(d1)*np.exp(-q*T))

    return theta / 365  # Per day
```

**Vega (ν):** Change in option price per 1% change in volatility
```python
def vega(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return S * np.exp(-q*T) * norm.pdf(d1) * np.sqrt(T) / 100  # Per 1%
```

**Rho (ρ):** Change in option price per 1% change in interest rate
```python
def rho_call(S, K, T, r, sigma, q=0):
    d2 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T)) - sigma*np.sqrt(T)
    return K * T * np.exp(-r*T) * norm.cdf(d2) / 100  # Per 1%
```

**Position Greeks:**

For a strategy with multiple legs, sum Greeks across all legs:
```python
# Example: Bull Call Spread
# Long 1x $180 call
# Short 1x $185 call

delta_position = (1 * delta_long) + (-1 * delta_short)
gamma_position = (1 * gamma_long) + (-1 * gamma_short)
theta_position = (1 * theta_long) + (-1 * theta_short)
vega_position = (1 * vega_long) + (-1 * vega_short)
```

**Greeks Interpretation:**

| Greek | Meaning | Example |
|-------|---------|---------|
| **Delta** | Directional exposure | Δ = 0.50 → $50 profit if stock +$1 |
| **Gamma** | Delta acceleration | Γ = 0.05 → Delta increases by 0.05 if stock +$1 |
| **Theta** | Daily time decay | Θ = -$5 → Lose $5/day from time passing |
| **Vega** | Volatility sensitivity | ν = $10 → Gain $10 if IV increases 1% |
| **Rho** | Interest rate sensitivity | ρ = $2 → Gain $2 if rates increase 1% |

## References

- Black, F. & Scholes, M. (1973). "The Pricing of Options and Corporate Liabilities"
- Hull, J.C. "Options, Futures, and Other Derivatives"
- CBOE Education: https://www.cboe.com/education/
