# Options Strategy Advisor

Educational options trading tool providing theoretical pricing, strategy analysis, and risk management guidance using Black-Scholes model.

## Overview

Options Strategy Advisor helps traders understand and analyze options strategies without requiring expensive real-time options data. It uses theoretical pricing models (Black-Scholes) combined with free stock market data (FMP API) to simulate strategies and calculate Greeks.

**Key Features:**
- ✅ Black-Scholes pricing engine
- ✅ All Greeks calculation (Delta, Gamma, Theta, Vega, Rho)
- ✅ 17+ options strategies supported
- ✅ P/L simulation and visualization
- ✅ Earnings strategy integration
- ✅ Historical volatility calculation
- ✅ Risk management guidance

## Why This Approach?

**No expensive data subscriptions needed:**
- Real-time options data: $99-$500/month (Polygon.io, Intrinio)
- FMP API Free tier: $0/month (250 requests/day)

**Educational focus:**
- Learn how strategies work
- Understand Greeks and risk metrics
- Compare strategies side-by-side

**Practical application:**
- Theoretical prices ≈ market mid-prices
- User can input actual IV from broker
- Good for strategy planning and education

## Supported Strategies

### Income Strategies
1. **Covered Call** - Generate income from stock holdings
2. **Cash-Secured Put** - Get paid to buy stock
3. **Poor Man's Covered Call** - Capital-efficient covered call

### Protection Strategies
4. **Protective Put** - Insurance for stock positions
5. **Collar** - Limited risk/reward protection

### Directional Strategies
6. **Bull Call Spread** - Limited risk bullish play
7. **Bull Put Spread** - Credit spread for bullish view
8. **Bear Call Spread** - Credit spread for bearish view
9. **Bear Put Spread** - Limited risk bearish play

### Volatility Strategies
10. **Long Straddle** - Profit from big moves
11. **Long Strangle** - Cheaper straddle, bigger move needed
12. **Short Straddle** - Profit from no movement (high risk)
13. **Short Strangle** - Wider range straddle

### Range-Bound Strategies
14. **Iron Condor** - Profit from range-bound trading
15. **Iron Butterfly** - Tight range profit

### Advanced Strategies
16. **Calendar Spread** - Time decay play
17. **Diagonal Spread** - Directional + time decay

## Installation

### Prerequisites
- Python 3.8+
- FMP API key (free tier sufficient)

### Install Dependencies
```bash
pip install numpy scipy requests pandas
```

### Get FMP API Key
1. Visit https://financialmodelingprep.com/developer/docs
2. Sign up for free account
3. Copy API key
4. Set environment variable:
```bash
export FMP_API_KEY="your_key_here"
```

## Quick Start

### Test Black-Scholes Pricer

```bash
python scripts/black_scholes.py
```

**Example Output:**
```
BLACK-SCHOLES OPTIONS PRICER - EXAMPLE
======================================================================

Input Parameters:
  Stock Price: $180.00
  Strike Price: $185.00
  Days to Expiration: 30
  Volatility: 25.0%
  Risk-Free Rate: 5.30%
  Dividend Yield: 1.0%

======================================================================
CALL OPTION
======================================================================
Price: $2.45
Intrinsic Value: $0.00
Time Value: $2.45

Greeks:
  Delta: 0.3654 ($36.54 per $1 move)
  Gamma: 0.0234 (delta changes by 0.0234)
  Theta: -$0.18/day (loses $0.18 per day)
  Vega: $0.25 per 1% IV (gains $0.25 if IV +1%)
  Rho: $0.12 per 1% rate (gains $0.12 if rate +1%)
```

### Use in Your Code

```python
from scripts.black_scholes import OptionPricer

# Initialize pricer
pricer = OptionPricer(
    S=180,          # Stock price
    K=185,          # Strike price
    T=30/365,       # Time to expiration (years)
    r=0.053,        # Risk-free rate (5.3%)
    sigma=0.25,     # Volatility (25%)
    q=0.01          # Dividend yield (1%)
)

# Get call option price
call_price = pricer.call_price()
print(f"Call Price: ${call_price:.2f}")

# Get all Greeks for call
call_greeks = pricer.get_all_greeks('call')
print(f"Delta: {call_greeks['delta']:.4f}")
print(f"Gamma: {call_greeks['gamma']:.4f}")
print(f"Theta: ${call_greeks['theta']:.2f}/day")
print(f"Vega: ${call_greeks['vega']:.2f} per 1%")
```

### Calculate Historical Volatility

```python
from scripts.black_scholes import (
    calculate_historical_volatility,
    fetch_historical_prices_for_hv
)

# Fetch prices from FMP
api_key = "your_key"
prices = fetch_historical_prices_for_hv("AAPL", api_key, days=90)

# Calculate 30-day HV
hv = calculate_historical_volatility(prices, window=30)
print(f"30-Day HV: {hv*100:.2f}%")
```

## Understanding the Metrics

### Option Price Components

**Intrinsic Value:**
- Call: max(0, Stock Price - Strike Price)
- Put: max(0, Strike Price - Stock Price)

**Time Value:**
- Option Price - Intrinsic Value
- Decays to $0 at expiration

### The Greeks

**Delta (Δ)** - Directional Exposure
```
Range: 0 to 1 (calls), -1 to 0 (puts)
Meaning: Change in option price per $1 stock move

Example: Δ = 0.50
→ If stock +$1, option +$0.50
→ If stock -$1, option -$0.50
```

**Gamma (Γ)** - Delta Acceleration
```
Meaning: Change in delta per $1 stock move
Peak: ATM options
Low: Deep ITM or OTM

Example: Γ = 0.05, Δ currently = 0.50
→ If stock +$1, delta becomes 0.55
```

**Theta (Θ)** - Time Decay
```
Meaning: Change in option price per day
Sign: Usually negative (options lose value over time)
Peak: Last 30 days before expiration

Example: Θ = -$0.15/day
→ Tomorrow, option loses $0.15 if nothing else changes
```

**Vega (ν)** - Volatility Sensitivity
```
Meaning: Change in option price per 1% IV change
Sign: Always positive (options gain value when vol increases)

Example: ν = $0.25 per 1%
→ If IV increases from 25% to 26%, option +$0.25
```

**Rho (ρ)** - Interest Rate Sensitivity
```
Meaning: Change in option price per 1% rate change
Sign: Positive for calls, negative for puts
Impact: Usually small unless long-dated options

Example: ρ = $0.10 per 1%
→ If interest rate increases 1%, option +$0.10
```

### Volatility: HV vs IV

**Historical Volatility (HV):**
- Calculated from past price movements
- Objective, based on actual data
- Available free (from price data)

**Implied Volatility (IV):**
- Derived from option market prices
- Subjective, based on supply/demand
- Requires real-time options data (or user input)

**Comparison:**
```
IV > HV: Options expensive → Consider selling premium
IV < HV: Options cheap → Consider buying options
IV = HV: Fairly priced → Any strategy works
```

## Common Workflows

### 1. Analyze a Strategy

```python
from scripts.black_scholes import OptionPricer

# Stock: AAPL @ $180
# Strategy: Bull Call Spread $180/$185 (30 DTE)

# Price long call ($180 strike)
long_call = OptionPricer(S=180, K=180, T=30/365, r=0.053, sigma=0.25)
long_price = long_call.call_price()
long_delta = long_call.call_delta()

# Price short call ($185 strike)
short_call = OptionPricer(S=180, K=185, T=30/365, r=0.053, sigma=0.25)
short_price = short_call.call_price()
short_delta = short_call.call_delta()

# Strategy metrics
net_debit = long_price - short_price
max_profit = (185 - 180) - net_debit
max_loss = -net_debit
position_delta = long_delta - short_delta

print(f"Bull Call Spread $180/$185")
print(f"Net Debit: ${net_debit:.2f}")
print(f"Max Profit: ${max_profit:.2f} (at $185+)")
print(f"Max Loss: ${max_loss:.2f} (at $180-)")
print(f"Position Delta: {position_delta:.4f}")
```

### 2. Compare IV to HV

```python
# Get HV
prices = fetch_historical_prices_for_hv("AAPL", api_key, days=90)
hv = calculate_historical_volatility(prices, window=30)

# User provides IV (from broker platform)
iv = 0.28  # 28% from ThinkorSwim

print(f"Historical Volatility: {hv*100:.2f}%")
print(f"Implied Volatility: {iv*100:.1f}%")

if iv > hv * 1.1:
    print("→ Options expensive (IV > HV) - Consider selling premium")
elif iv < hv * 0.9:
    print("→ Options cheap (IV < HV) - Consider buying options")
else:
    print("→ Fairly priced")
```

### 3. Earnings Strategy

Check if earnings coming up (use Earnings Calendar skill):
```python
# If earnings in 7 days:
# - IV typically elevated (30-50% higher)
# - Consider straddle/strangle (profit from big move)
# - Or sell iron condor (profit from IV crush)

# Example: Long Straddle
straddle_cost = call_price + put_price
breakeven_up = stock_price + straddle_cost
breakeven_down = stock_price - straddle_cost

print(f"Straddle Cost: ${straddle_cost:.2f}")
print(f"Breakevens: ${breakeven_down:.2f} / ${breakeven_up:.2f}")
print(f"Need {abs(breakeven_up - stock_price)/stock_price*100:.1f}% move to profit")
```

## Limitations & Best Practices

### Theoretical vs Market Prices

**Black-Scholes Assumptions:**
- European options (can't exercise early)
- Constant volatility (changes in reality)
- No transaction costs
- Continuous trading

**Real World Differences:**
- American options (most stocks) can exercise early
- Bid-ask spread: Actual cost higher than theoretical mid
- Commissions and slippage
- Liquidity: Wide markets on illiquid options

### Best Practices

**1. Use for Education & Planning:**
- Learn how strategies work
- Compare different approaches
- Understand risk/reward before trading

**2. Verify Before Trading:**
- Get real quotes from your broker
- Check bid-ask spread
- Confirm option liquidity (open interest, volume)

**3. Input Actual IV:**
- Theoretical price assumes constant volatility
- Use current market IV for accuracy
- Check IV percentile (high/low relative to history)

**4. Account for Dividends:**
- Ex-dividend dates affect option prices
- Calls lose value, puts gain value on ex-div date
- Script supports dividend yield input

**5. Monitor Greeks:**
- Delta: Overall directional exposure
- Theta: Daily time decay (seller advantage)
- Vega: Volatility risk (watch during earnings)
- Gamma: Risk of delta changing (avoid near expiration)

## Integration with Other Skills

**Earnings Calendar:**
- Fetch earnings dates
- Identify IV crush opportunities
- Time earnings strategies

**Technical Analyst:**
- Use support/resistance for strike selection
- Trend analysis for directional strategies
- Breakout potential for straddle timing

**US Stock Analysis:**
- Fundamental analysis for LEAPS
- Dividend yield for covered call/put
- Earnings quality for earnings plays

**Bubble Detector:**
- High risk → protective puts
- Low risk → bullish strategies
- Critical risk → avoid long premium

**Portfolio Manager:**
- Track options with stock positions
- Aggregate Greeks across portfolio
- Options as hedging tool

## API Usage & Costs

**Free Tier Sufficient:**
- Stock prices: 1 request per symbol
- Historical prices (HV): 1 request per symbol
- Dividend data: 1 request per symbol

**Example Analysis Cost:**
```
Covered Call on AAPL:
- Current price: 1 request
- HV calculation: 1 request (90 days data)
- Dividend yield: 1 request
Total: 3 requests

Daily budget: 250 requests / day
→ Can analyze ~80 strategies per day
```

## Troubleshooting

### Negative Option Price
**Cause:** Invalid inputs (strike vs stock price)
**Solution:** Check that inputs make sense

### Greeks Seem Wrong
**Cause:** Using wrong units (annual vs daily)
**Solution:** Verify T is in years, theta is per day

### HV Very Different from IV
**Normal:** IV reflects future expectations, HV is past
**Action:** Use IV from broker for more accuracy

### Option Price Too High/Low
**Cause:** Volatility input incorrect
**Solution:** Verify sigma is annual (e.g., 0.25 for 25%)

## Resources

### Documentation
- `SKILL.md` - Complete workflow and strategies
- `references/strategies_guide.md` - All strategies explained (TBD)
- `references/greeks_explained.md` - Greeks deep dive (TBD)

### External Resources
- Options Playbook: https://www.optionsplaybook.com/
- CBOE Education: https://www.cboe.com/education/
- Black-Scholes Calculator: https://www.option-price.com/

### Get Real IV
- ThinkorSwim (TD Ameritrade): Free
- TastyTrade: Free
- Barchart: https://www.barchart.com/options
- CBOE: http://www.cboe.com/delayedquote/

## Future Enhancements

**Planned:**
- Strategy simulation script (complete P/L analysis)
- P/L diagram generator (ASCII art)
- Earnings strategy advisor (integrated with Earnings Calendar)
- Complete strategy reference guides

**Contributions Welcome:**
- Additional strategies
- Improved volatility models
- Better visualization tools

## License

Educational use. Trade at your own risk. Options involve significant risk and are not suitable for all investors.

---

**Version:** 1.0
**Last Updated:** 2025-11-08
**Dependencies:** Python 3.8+, numpy, scipy, requests
**API:** FMP API (Free tier sufficient)
**Model:** Black-Scholes (European options pricing)
