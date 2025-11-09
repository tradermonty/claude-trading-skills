---
name: options-strategy-advisor
description: Options trading strategy analysis and simulation tool. Provides theoretical pricing using Black-Scholes model, Greeks calculation, strategy P/L simulation, and risk management guidance. Use when user requests options strategy analysis, covered calls, protective puts, spreads, iron condors, earnings plays, or options risk management. Includes volatility analysis, position sizing, and earnings-based strategy recommendations. Educational focus with practical trade simulation.
---

# Options Strategy Advisor

## Overview

This skill provides comprehensive options strategy analysis and education using theoretical pricing models. It helps traders understand, analyze, and simulate options strategies without requiring real-time market data subscriptions.

**Core Capabilities:**
- **Black-Scholes Pricing**: Theoretical option prices and Greeks calculation
- **Strategy Simulation**: P/L analysis for major options strategies
- **Earnings Strategies**: Pre-earnings volatility plays integrated with Earnings Calendar
- **Risk Management**: Position sizing, Greeks exposure, max loss/profit analysis
- **Educational Focus**: Detailed explanations of strategies and risk metrics

**Data Sources:**
- FMP API: Stock prices, historical volatility, dividends, earnings dates
- User Input: Implied volatility (IV), risk-free rate
- Theoretical Models: Black-Scholes for pricing and Greeks

## When to Use This Skill

Use this skill when:
- User asks about options strategies ("What's a covered call?", "How does an iron condor work?")
- User wants to simulate strategy P/L ("What's my max profit on a bull call spread?")
- User needs Greeks analysis ("What's my delta exposure?")
- User asks about earnings strategies ("Should I buy a straddle before earnings?")
- User wants to compare strategies ("Covered call vs protective put?")
- User needs position sizing guidance ("How many contracts should I trade?")
- User asks about volatility ("Is IV high right now?")

Example requests:
- "Analyze a covered call on AAPL"
- "What's the P/L on a $100/$105 bull call spread on MSFT?"
- "Should I trade a straddle before NVDA earnings?"
- "Calculate Greeks for my iron condor position"
- "Compare protective put vs covered call for downside protection"

## Supported Strategies

### Income Strategies
1. **Covered Call** - Own stock, sell call (generate income, cap upside)
2. **Cash-Secured Put** - Sell put with cash backing (collect premium, willing to buy stock)
3. **Poor Man's Covered Call** - LEAPS call + short near-term call (capital efficient)

### Protection Strategies
4. **Protective Put** - Own stock, buy put (insurance, limited downside)
5. **Collar** - Own stock, sell call + buy put (limited upside/downside)

### Directional Strategies
6. **Bull Call Spread** - Buy lower strike call, sell higher strike call (limited risk/reward bullish)
7. **Bull Put Spread** - Sell higher strike put, buy lower strike put (credit spread, bullish)
8. **Bear Call Spread** - Sell lower strike call, buy higher strike call (credit spread, bearish)
9. **Bear Put Spread** - Buy higher strike put, sell lower strike put (limited risk/reward bearish)

### Volatility Strategies
10. **Long Straddle** - Buy ATM call + ATM put (profit from big move either direction)
11. **Long Strangle** - Buy OTM call + OTM put (cheaper than straddle, bigger move needed)
12. **Short Straddle** - Sell ATM call + ATM put (profit from no movement, unlimited risk)
13. **Short Strangle** - Sell OTM call + OTM put (profit from no movement, wider range)

### Range-Bound Strategies
14. **Iron Condor** - Bull put spread + bear call spread (profit from range-bound movement)
15. **Iron Butterfly** - Sell ATM straddle, buy OTM strangle (profit from tight range)

### Advanced Strategies
16. **Calendar Spread** - Sell near-term option, buy longer-term option (profit from time decay)
17. **Diagonal Spread** - Calendar spread with different strikes (directional + time decay)
18. **Ratio Spread** - Unbalanced spread (more contracts on one leg)

## Analysis Workflow

### Step 1: Gather Input Data

**Required from User:**
- Ticker symbol
- Strategy type
- Strike prices
- Expiration date(s)
- Position size (number of contracts)

**Optional from User:**
- Implied Volatility (IV) - if not provided, use Historical Volatility (HV)
- Risk-free rate - default to current 3-month T-bill rate (~5.3% as of 2025)

**Fetched from FMP API:**
- Current stock price
- Historical prices (for HV calculation)
- Dividend yield
- Upcoming earnings date (for earnings strategies)

**Example User Input:**
```
Ticker: AAPL
Strategy: Bull Call Spread
Long Strike: $180
Short Strike: $185
Expiration: 30 days
Contracts: 10
IV: 25% (or use HV if not provided)
```

### Step 2: Calculate Historical Volatility (if IV not provided)

**Objective:** Estimate volatility from historical price movements.

**Method:**
```python
# Fetch 90 days of price data
prices = get_historical_prices("AAPL", days=90)

# Calculate daily returns
returns = np.log(prices / prices.shift(1))

# Annualized volatility
HV = returns.std() * np.sqrt(252)  # 252 trading days
```

**Output:**
- Historical Volatility (annualized percentage)
- Note to user: "HV = 24.5%, consider using current market IV for more accuracy"

**User Can Override:**
- Provide IV from broker platform (ThinkorSwim, TastyTrade, etc.)
- Script accepts `--iv 28.0` parameter

### Step 3: Price Options Using Black-Scholes

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

### Step 4: Calculate Greeks

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

### Step 5: Simulate Strategy P/L

**Objective:** Calculate profit/loss at various stock prices at expiration.

**Method:**

Generate stock price range (e.g., ±30% from current price):
```python
current_price = 180
price_range = np.linspace(current_price * 0.7, current_price * 1.3, 100)
```

For each price point, calculate P/L:
```python
def calculate_pnl(strategy, stock_price_at_expiration):
    pnl = 0

    for leg in strategy.legs:
        if leg.type == 'call':
            intrinsic_value = max(0, stock_price_at_expiration - leg.strike)
        else:  # put
            intrinsic_value = max(0, leg.strike - stock_price_at_expiration)

        if leg.position == 'long':
            pnl += (intrinsic_value - leg.premium_paid) * 100  # Per contract
        else:  # short
            pnl += (leg.premium_received - intrinsic_value) * 100

    return pnl * num_contracts
```

**Key Metrics:**
- **Max Profit**: Highest possible P/L
- **Max Loss**: Worst possible P/L
- **Breakeven Point(s)**: Stock price(s) where P/L = 0
- **Profit Probability**: Percentage of price range that's profitable (simplified)

**Example Output:**
```
Bull Call Spread: $180/$185 on AAPL (30 DTE, 10 contracts)

Current Price: $180.00
Net Debit: $2.50 per spread ($2,500 total)

Max Profit: $2,500 (at $185+)
Max Loss: -$2,500 (at $180-)
Breakeven: $182.50
Risk/Reward: 1:1

Probability Profit: ~55% (if stock stays above $182.50)
```

### Step 6: Generate P/L Diagram (ASCII Art)

**Visual representation of P/L across stock prices:**

```python
def generate_pnl_diagram(price_range, pnl_values, current_price, width=60, height=15):
    """Generate ASCII P/L diagram"""

    # Normalize to chart dimensions
    max_pnl = max(pnl_values)
    min_pnl = min(pnl_values)

    lines = []
    lines.append(f"\nP/L Diagram: {strategy_name}")
    lines.append("-" * width)

    # Y-axis levels
    levels = np.linspace(max_pnl, min_pnl, height)

    for level in levels:
        if abs(level) < (max_pnl - min_pnl) * 0.05:
            label = f"    0 |"  # Zero line
        else:
            label = f"{level:6.0f} |"

        row = label
        for i in range(width - len(label)):
            idx = int(i / (width - len(label)) * len(price_range))
            pnl = pnl_values[idx]
            price = price_range[idx]

            # Determine character
            if abs(pnl - level) < (max_pnl - min_pnl) / height:
                if pnl > 0:
                    char = '█'  # Profit
                elif pnl < 0:
                    char = '░'  # Loss
                else:
                    char = '─'  # Breakeven
            elif abs(level) < (max_pnl - min_pnl) * 0.05:
                char = '─'  # Zero line
            elif abs(price - current_price) < (price_range[-1] - price_range[0]) * 0.02:
                char = '│'  # Current price line
            else:
                char = ' '

            row += char

        lines.append(row)

    lines.append(" " * 6 + "|" + "-" * (width - 6))
    lines.append(" " * 6 + f"${price_range[0]:.0f}" + " " * (width - 20) + f"${price_range[-1]:.0f}")
    lines.append(" " * (width // 2 - 5) + "Stock Price")

    return "\n".join(lines)
```

**Example Output:**
```
P/L Diagram: Bull Call Spread $180/$185
------------------------------------------------------------
 +2500 |                               ████████████████████
       |                         ██████
       |                   ██████
       |             ██████
     0 |       ──────
       | ░░░░░░
       |░░░░░░
 -2500 |░░░░░
      |____________________________________________________________
       $126                  $180                   $234
                          Stock Price

Legend: █ Profit  ░ Loss  ── Breakeven  │ Current Price
```

### Step 7: Strategy-Specific Analysis

Provide tailored guidance based on strategy type:

**Covered Call:**
```
Income Strategy: Generate premium while capping upside

Setup:
- Own 100 shares of AAPL @ $180
- Sell 1x $185 call (30 DTE) for $3.50

Max Profit: $850 (Stock at $185+ = $5 stock gain + $3.50 premium)
Max Loss: Unlimited downside (stock ownership)
Breakeven: $176.50 (Cost basis - premium received)

Greeks:
- Delta: -0.30 (reduces stock delta from 1.00 to 0.70)
- Theta: +$8/day (time decay benefit)

Assignment Risk: If AAPL > $185 at expiration, shares called away

When to Use:
- Neutral to slightly bullish
- Want income in sideways market
- Willing to sell stock at $185

Exit Plan:
- Buy back call if stock rallies strongly (preserve upside)
- Let expire if stock stays below $185
- Roll to next month if want to keep shares
```

**Protective Put:**
```
Insurance Strategy: Limit downside while keeping upside

Setup:
- Own 100 shares of AAPL @ $180
- Buy 1x $175 put (30 DTE) for $2.00

Max Profit: Unlimited (stock can rise infinitely)
Max Loss: -$7 per share = ($5 stock loss + $2 premium)
Breakeven: $182 (Cost basis + premium paid)

Greeks:
- Delta: +0.80 (stock delta 1.00 - put delta 0.20)
- Theta: -$6/day (time decay cost)

Protection: Guaranteed to sell at $175, no matter how far stock falls

When to Use:
- Own stock, worried about short-term drop
- Earnings coming up, want protection
- Alternative to stop-loss (can't be stopped out)

Cost: "Insurance premium" - typically 1-3% of stock value

Exit Plan:
- Let expire worthless if stock rises (cost of insurance)
- Exercise put if stock falls below $175
- Sell put if stock drops but want to keep shares
```

**Iron Condor:**
```
Range-Bound Strategy: Profit from low volatility

Setup (example on AAPL @ $180):
- Sell $175 put for $1.50
- Buy $170 put for $0.50
- Sell $185 call for $1.50
- Buy $190 call for $0.50

Net Credit: $2.00 ($200 per iron condor)

Max Profit: $200 (if stock stays between $175-$185)
Max Loss: $300 (if stock moves outside $170-$190)
Breakevens: $173 and $187
Profit Range: $175 to $185 (58% probability)

Greeks:
- Delta: ~0 (market neutral)
- Theta: +$15/day (time decay benefit)
- Vega: -$25 (short volatility)

When to Use:
- Expect low volatility, range-bound movement
- After big move, think consolidation
- High IV environment (sell expensive options)

Risk: Unlimited if one side tested
- Use stop loss at 2x credit received (exit at -$400)

Adjustments:
- If tested on one side, roll that side out in time
- Close early at 50% max profit to reduce tail risk
```

### Step 8: Earnings Strategy Analysis

**Integration with Earnings Calendar:**

When user asks about earnings strategies, fetch earnings date:
```python
from earnings_calendar import get_next_earnings_date

earnings_date = get_next_earnings_date("AAPL")
days_to_earnings = (earnings_date - today).days
```

**Pre-Earnings Strategies:**

**Long Straddle/Strangle:**
```
Setup (AAPL @ $180, earnings in 7 days):
- Buy $180 call for $5.00
- Buy $180 put for $4.50
- Total Cost: $9.50

Thesis: Expect big move (>5%) but unsure of direction

Breakevens: $170.50 and $189.50
Profit if: Stock moves >$9.50 in either direction

Greeks:
- Delta: ~0 (neutral)
- Vega: +$50 (long volatility)
- Theta: -$25/day (time decay hurts)

IV Crush Risk: ⚠️ CRITICAL
- Pre-earnings IV: 40% (elevated)
- Post-earnings IV: 25% (typical)
- IV drop: -15 points = -$750 loss even if stock doesn't move!

Analysis:
- Implied Move: √(DTE/365) × IV × Stock Price
  = √(7/365) × 0.40 × 180 = ±$10.50
- Breakeven Move Needed: ±$9.50
- Probability Profit: ~30-40% (implied move > breakeven move)

Recommendation:
✅ Consider if you expect >10% move (larger than implied)
❌ Avoid if expect normal ~5% earnings move (IV crush will hurt)

Alternative: Buy further OTM strikes to reduce cost
- $175/$185 strangle cost $4.00 (need >$8 move, but cheaper)
```

**Short Iron Condor:**
```
Setup (AAPL @ $180, earnings in 7 days):
- Sell $170/$175 put spread for $2.00
- Sell $185/$190 call spread for $2.00
- Net Credit: $4.00

Thesis: Expect stock to stay range-bound ($175-$185)

Profit Zone: $175 to $185
Max Profit: $400
Max Loss: $100

IV Crush Benefit: ✅
- Short high IV before earnings
- IV drops after earnings → profit on vega
- Even if stock moves slightly, IV drop helps

Greeks:
- Delta: ~0 (market neutral)
- Vega: -$40 (short volatility - good here!)
- Theta: +$20/day

Recommendation:
✅ Good if expect normal earnings reaction (<8% move)
✅ Benefit from IV crush regardless of direction
⚠️ Risk if stock gaps outside range (>10% move)

Exit Plan:
- Close next day if IV crushed (capture profit early)
- Use stop loss if one side tested (-2x credit)
```

### Step 9: Risk Management Guidance

**Position Sizing:**

```
Account Size: $50,000
Risk Tolerance: 2% per trade = $1,000 max risk

Iron Condor Example:
- Max loss per spread: $300
- Max contracts: $1,000 / $300 = 3 contracts
- Actual position: 3 iron condors

Bull Call Spread Example:
- Debit paid: $2.50 per spread
- Max contracts: $1,000 / $250 = 4 contracts
- Actual position: 4 spreads
```

**Portfolio Greeks Management:**

```
Portfolio Guidelines:
- Delta: -10 to +10 (mostly neutral)
- Theta: Positive preferred (seller advantage)
- Vega: Monitor if >$500 (IV risk)

Current Portfolio:
- Delta: +5 (slightly bullish)
- Theta: +$150/day (collecting $150 daily)
- Vega: -$300 (short volatility)

Interpretation:
✅ Neutral delta (safe)
✅ Positive theta (time working for you)
⚠️ Short vega: If IV spikes, lose $300 per 1% IV increase
→ Reduce short premium positions if VIX rising
```

**Adjustments and Exits:**

```
Exit Rules by Strategy:

Covered Call:
- Profit: 50-75% of max profit
- Loss: Stock drops >5%, buy back call to preserve upside
- Time: 7-10 DTE, roll to avoid assignment

Spreads:
- Profit: 50% of max profit (close early, reduce tail risk)
- Loss: 2x debit paid (cut losses early)
- Time: 21 DTE, close or roll (avoid gamma risk)

Iron Condor:
- Profit: 50% of credit (close early common)
- Loss: One side tested, 2x credit lost
- Adjustment: Roll tested side out in time

Straddle/Strangle:
- Profit: Stock moved >breakeven, close immediately
- Loss: Theta eating position, stock not moving
- Time: Day after earnings (if earnings play)
```

## Output Format

**Strategy Analysis Report Template:**

```markdown
# Options Strategy Analysis: [Strategy Name]

**Symbol:** [TICKER]
**Strategy:** [Strategy Type]
**Expiration:** [Date] ([DTE] days)
**Contracts:** [Number]

---

## Strategy Setup

### Leg Details
| Leg | Type | Strike | Price | Position | Quantity |
|-----|------|--------|-------|----------|----------|
| 1 | Call | $180 | $5.00 | Long | 1 |
| 2 | Call | $185 | $2.50 | Short | 1 |

**Net Debit/Credit:** $2.50 debit ($250 total for 1 spread)

---

## Profit/Loss Analysis

**Max Profit:** $250 (at $185+)
**Max Loss:** -$250 (at $180-)
**Breakeven:** $182.50
**Risk/Reward Ratio:** 1:1

**Probability Analysis:**
- Probability of Profit: ~55% (stock above $182.50)
- Expected Value: $25 (simplified)

---

## P/L Diagram

[ASCII art diagram here]

---

## Greeks Analysis

### Position Greeks (1 spread)
- **Delta:** +0.20 (gains $20 if stock +$1)
- **Gamma:** +0.03 (delta increases by 0.03 if stock +$1)
- **Theta:** -$5/day (loses $5 per day from time decay)
- **Vega:** +$8 (gains $8 if IV increases 1%)

### Interpretation
- **Directional Bias:** Slightly bullish (positive delta)
- **Time Decay:** Working against you (negative theta)
- **Volatility:** Benefits from IV increase (positive vega)

---

## Risk Assessment

### Maximum Risk
**Scenario:** Stock falls below $180
**Max Loss:** -$250 (100% of premium paid)
**% of Account:** 0.5% (if $50k account)

### Assignment Risk
**Early Assignment:** Low (calls have time value)
**At Expiration:** Manage positions if in-the-money

---

## Trade Management

### Entry
✅ Enter if: [Conditions]
- Stock price $178-$182
- IV below 30%
- >21 DTE

### Profit Taking
- **Target 1:** 50% profit ($125) - Close half
- **Target 2:** 75% profit ($187.50) - Close all

### Stop Loss
- **Trigger:** Stock falls below $177 (-$150 loss)
- **Action:** Close position immediately

### Adjustments
- If stock rallies to $184, consider rolling short call higher
- If stock drops to $179, add second spread at $175/$180

---

## Suitability

### When to Use This Strategy
✅ Moderately bullish on AAPL
✅ Expect upside to $185-$190
✅ Want defined risk
✅ 21-45 DTE timeframe

### When to Avoid
❌ Very bullish (buy stock or long call instead)
❌ High IV environment (wait for IV to drop)
❌ Earnings in <7 days (IV crush risk)

---

## Alternatives Comparison

| Strategy | Max Profit | Max Loss | Complexity | When Better |
|----------|-----------|----------|------------|-------------|
| Bull Call Spread | $250 | -$250 | Medium | Moderately bullish |
| Long Call | Unlimited | -$500 | Low | Very bullish |
| Covered Call | $850 | Unlimited | Medium | Own stock already |
| Bull Put Spread | $300 | -$200 | Medium | Want credit spread |

**Recommendation:** Bull call spread is good balance of risk/reward for moderate bullish thesis.

---

*Disclaimer: This is theoretical analysis using Black-Scholes pricing. Actual market prices may differ. Trade at your own risk. Options are complex instruments with significant loss potential.*
```

**File Naming Convention:**
```
options_analysis_[TICKER]_[STRATEGY]_[DATE].md
```

Example: `options_analysis_AAPL_BullCallSpread_2025-11-08.md`

## Key Principles

### Theoretical Pricing Limitations

**What Users Should Know:**
1. **Black-Scholes Assumptions:**
   - European-style options (can't exercise early)
   - Constant volatility (IV changes in reality)
   - No transaction costs
   - Continuous trading

2. **Real vs Theoretical:**
   - Bid-ask spread: Actual cost higher than theoretical
   - American options: Can be exercised early (especially ITM puts)
   - Liquidity: Wide markets on illiquid options
   - Dividends: Ex-dividend dates affect pricing

3. **Best Practices:**
   - Use as educational tool and comparative analysis
   - Get real quotes from broker before trading
   - Understand theoretical price ≈ mid-market price
   - Account for commissions and slippage

### Volatility Guidance

**Historical vs Implied Volatility:**

```
Historical Volatility (HV): What happened
- Calculated from past price movements
- Objective, based on data
- Available for free (FMP API)

Implied Volatility (IV): What market expects
- Derived from option prices
- Subjective, based on supply/demand
- Requires live options data (user provides)

Comparison:
- IV > HV: Options expensive (consider selling)
- IV < HV: Options cheap (consider buying)
- IV = HV: Fairly priced
```

**IV Percentile:**

User provides current IV, we calculate percentile:
```python
# Fetch 1-year HV data
historical_hvs = calculate_hv_series(prices_1yr, window=30)

# Calculate IV percentile
iv_percentile = percentileofscore(historical_hvs, current_iv)

if iv_percentile > 75:
    guidance = "High IV - consider selling premium (credit spreads, iron condors)"
elif iv_percentile < 25:
    guidance = "Low IV - consider buying options (long calls/puts, debit spreads)"
else:
    guidance = "Normal IV - any strategy appropriate"
```

## Integration with Other Skills

**Earnings Calendar:**
- Fetch earnings dates automatically
- Suggest earnings-specific strategies
- Calculate days to earnings (DTE critical for IV)
- Warn about IV crush risk

**Technical Analyst:**
- Use support/resistance for strike selection
- Trend analysis for directional strategies
- Breakout potential for straddle/strangle timing

**US Stock Analysis:**
- Fundamental analysis for longer-term strategies (LEAPS)
- Dividend yield for covered call/put analysis
- Earnings quality for earnings plays

**Bubble Detector:**
- High bubble risk → focus on protective puts
- Low risk → bullish strategies
- Critical risk → avoid long premium (theta hurts)

**Portfolio Manager:**
- Track options positions alongside stock positions
- Aggregate Greeks across portfolio
- Options as hedging tool for stock positions

## Important Notes

- **All analysis in English**
- **Educational focus**: Strategies explained clearly
- **Theoretical pricing**: Black-Scholes approximation
- **User IV input**: Optional, defaults to HV
- **No real-time data required**: FMP Free tier sufficient
- **Dependencies**: Python 3.8+, numpy, scipy, pandas

## Common Use Cases

**Use Case 1: Learn Strategy**
```
User: "Explain a covered call"

Workflow:
1. Load strategy reference (references/strategies_guide.md)
2. Explain concept, risk/reward, when to use
3. Simulate example on AAPL
4. Show P/L diagram
5. Compare to alternatives
```

**Use Case 2: Analyze Specific Trade**
```
User: "Analyze $180/$185 bull call spread on AAPL, 30 days"

Workflow:
1. Fetch AAPL price from FMP
2. Calculate HV or ask user for IV
3. Price both options (Black-Scholes)
4. Calculate Greeks
5. Simulate P/L
6. Generate analysis report
```

**Use Case 3: Earnings Strategy**
```
User: "Should I trade options before NVDA earnings?"

Workflow:
1. Fetch NVDA earnings date (Earnings Calendar)
2. Calculate days to earnings
3. Estimate IV percentile (if user provides IV)
4. Suggest straddle/strangle vs iron condor
5. Warn about IV crush
6. Simulate both strategies
```

**Use Case 4: Portfolio Greeks Check**
```
User: "What are my total portfolio Greeks?"

Workflow:
1. User provides current positions
2. Calculate Greeks for each position
3. Sum Greeks across portfolio
4. Assess overall exposure
5. Suggest adjustments if needed
```

## Troubleshooting

**Problem: IV not available**
- Solution: Use HV as proxy, note to user
- Ask user to provide IV from broker platform

**Problem: Negative option price**
- Solution: Check inputs (strike vs stock price)
- Deep ITM options may have numerical issues

**Problem: Greeks seem wrong**
- Solution: Verify inputs (T, sigma, r)
- Check if using annual vs daily values

**Problem: Strategy too complex**
- Solution: Break into legs, analyze separately
- Refer to references for strategy details

## Resources

**References:**
- `references/strategies_guide.md` - All 17+ strategies explained
- `references/greeks_explained.md` - Greeks deep dive
- `references/volatility_guide.md` - HV vs IV, when to trade

**Scripts:**
- `scripts/black_scholes.py` - Pricing engine and Greeks
- `scripts/strategy_analyzer.py` - Strategy simulation
- `scripts/earnings_strategy.py` - Earnings-specific analysis

**External Resources:**
- Options Playbook: https://www.optionsplaybook.com/
- CBOE Education: https://www.cboe.com/education/
- Black-Scholes Calculator: Various online tools for verification

---

**Version**: 1.0
**Last Updated**: 2025-11-08
**Dependencies**: Python 3.8+, numpy, scipy, pandas, requests
**API**: FMP API (Free tier sufficient)
