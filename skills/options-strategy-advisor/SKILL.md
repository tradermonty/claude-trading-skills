---
name: options-strategy-advisor
description: "Options trading strategy analysis and simulation tool. Provides theoretical pricing using Black-Scholes model, Greeks calculation, strategy P/L simulation, risk management guidance, volatility analysis, position sizing, and earnings-based strategy recommendations. Use when user requests options strategy analysis, covered calls, protective puts, spreads, iron condors, earnings plays, or options risk management. Includes volatility analysis, position sizing, and earnings-based strategy recommendations. Educational focus with practical trade simulation."
---

# Options Strategy Advisor

## Overview

Analyze and simulate options strategies using Black-Scholes pricing. Generate P/L profiles, Greeks exposure, position sizing, and trade management plans.

**Core Capabilities:**
- Black-Scholes pricing and Greeks calculation
- Strategy P/L simulation with ASCII diagrams
- Earnings-specific strategy analysis (IV crush awareness)
- Position sizing and portfolio Greeks management
- Risk assessment with exit rules and adjustment triggers

**Data Sources:**
- FMP API (optional): stock prices, historical volatility, dividends, earnings dates
- User input: IV, risk-free rate, strike selection
- Theoretical models: Black-Scholes (see `references/black_scholes_methodology.md`)

## Prerequisites

- Python 3.8+ with `numpy`, `scipy`, `requests`
- FMP API key optional (set `FMP_API_KEY` env var or use `--api-key`; without it, use manual inputs)

```bash
pip install numpy scipy requests
```

## Supported Strategies

| Category | Strategies |
|----------|-----------|
| **Income** | Covered call, cash-secured put, poor man's covered call |
| **Protection** | Protective put, collar |
| **Directional** | Bull/bear call spread, bull/bear put spread |
| **Volatility** | Long/short straddle, long/short strangle |
| **Range-bound** | Iron condor, iron butterfly |
| **Advanced** | Calendar spread, diagonal spread, ratio spread |

## Analysis Workflow

### Step 1: Gather Input Data

Collect from user:
- Ticker symbol, strategy type, strike prices, expiration, position size
- Optional: IV (default to HV), risk-free rate (default ~5.3%)

Fetch from FMP API (if available):
- Current stock price, historical prices (for HV), dividend yield, earnings date

**Validation:** Confirm all required inputs present before proceeding. If IV not provided, calculate HV from 90-day price history and note: "Using HV as proxy; provide current IV from broker for more accuracy."

### Step 2: Price Options

Run Black-Scholes pricing via `scripts/black_scholes.py`:

```bash
# With API key
python3 scripts/black_scholes.py --ticker AAPL --api-key $FMP_API_KEY

# Manual inputs
python3 scripts/black_scholes.py --stock-price 180 --strike 185 --days 30 --volatility 0.25

# Put option
python3 scripts/black_scholes.py --stock-price 180 --strike 175 --days 30 --option-type put
```

For formulas and implementation details, load `references/black_scholes_methodology.md`.

**Validation:** Verify calculated option price is positive and within expected range (0 < price < stock price for calls, 0 < price < strike for puts) before proceeding.

### Step 3: Calculate Greeks

Compute position Greeks by summing across all strategy legs:

| Greek | Measures | Key Insight |
|-------|----------|-------------|
| Delta | $/move in stock | Directional exposure |
| Gamma | Delta acceleration | Risk near expiration |
| Theta | Daily time decay | Positive = seller advantage |
| Vega | $/1% IV change | Earnings and event risk |
| Rho | $/1% rate change | Usually minor for short-dated |

For multi-leg strategies, sum each Greek across legs (long = +1 multiplier, short = -1).

**Validation:** Confirm net position delta is consistent with stated market outlook (e.g., bull spread should have positive delta). Flag any inconsistency to user.

### Step 4: Simulate Strategy P/L

Calculate P/L at expiration across a price range (current +/- 30%):

For each price point, compute intrinsic value per leg, subtract premiums, multiply by contracts.

**Key metrics to report:**
- Max profit and the stock price(s) where it occurs
- Max loss and the stock price(s) where it occurs
- Breakeven point(s)
- Risk/reward ratio

Generate ASCII P/L diagram showing profit zone, loss zone, breakevens, and current price marker.

**Validation:** Confirm max loss matches the defined risk of the strategy type (e.g., debit spread max loss = net debit paid). If mismatch, recheck inputs.

### Step 5: Strategy-Specific Guidance

Provide tailored analysis based on strategy type. For each strategy, include:

1. **Setup summary** with specific numbers from user inputs
2. **When to use** (market outlook, IV environment)
3. **Greeks interpretation** for this specific position
4. **Assignment risk** assessment
5. **Exit plan:**
   - Profit target (typically 50-75% of max profit)
   - Stop loss trigger and action
   - Time-based exit (DTE threshold for rolling)
   - Adjustment options if position is tested

### Step 6: Earnings Strategy Analysis (if applicable)

When strategy involves earnings:

1. Fetch earnings date via Earnings Calendar integration
2. Calculate days to earnings
3. Estimate IV crush impact: compare pre-earnings IV to typical post-earnings IV
4. Calculate breakeven move needed vs implied move
5. Recommend straddle/strangle (expect big move) vs iron condor (expect range-bound)

**Critical warning:** Always quantify IV crush risk. Example: "15-point IV drop = -$750 vega loss even if stock doesn't move."

### Step 7: Risk Management

**Position sizing:**
```
Max contracts = Account risk $ / Max loss per contract
Example: $1,000 risk / $300 max loss = 3 contracts
```

**Portfolio Greeks check:** Sum Greeks across all open positions. Flag if:
- Delta exceeds +/-25 (concentrated directional risk)
- Vega exceeds +/-$500 (concentrated volatility risk)
- Theta is negative and >$100/day (time decay bleeding)

**Exit rules by strategy type:**

| Strategy | Profit Target | Stop Loss | Time Exit |
|----------|--------------|-----------|-----------|
| Covered call | 50-75% max | Stock -5%, buy back call | 7-10 DTE, roll |
| Spreads | 50% max | 2x debit paid | 21 DTE, close/roll |
| Iron condor | 50% credit | 2x credit lost | Roll tested side |
| Straddle/strangle | Stock > breakeven | Theta eroding, no movement | Day after earnings |

## Output Format

Generate a structured analysis report. Save to `reports/` as `options_analysis_[TICKER]_[STRATEGY]_[DATE].md`.

**Required sections:**
1. Strategy Setup (leg table with type, strike, price, position, quantity)
2. Net debit/credit and total cost
3. P/L Analysis (max profit, max loss, breakevens, risk/reward)
4. P/L Diagram (ASCII art)
5. Greeks Analysis (position Greeks + interpretation)
6. Risk Assessment (max risk scenario, assignment risk, % of account)
7. Trade Management (entry conditions, profit targets, stop loss, adjustments)
8. Suitability (when to use, when to avoid)
9. Alternatives Comparison (table of 3-4 alternative strategies)

**Disclaimer:** Include at end: "Theoretical analysis using Black-Scholes pricing. Actual market prices may differ. Options carry significant loss potential."

## Integration Points

| Skill | Integration |
|-------|------------|
| Earnings Calendar | Fetch earnings dates, DTE for IV analysis |
| Technical Analyst | Support/resistance for strike selection |
| US Stock Analysis | Fundamentals for LEAPS, dividend yield for covered calls |
| Bubble Detector | High risk = protective puts, low risk = bullish strategies |
| Portfolio Manager | Track options + stock positions, aggregate Greeks |

## References

- `references/black_scholes_methodology.md` - Formulas, Greeks definitions, model limitations, strategy selection framework
- `scripts/black_scholes.py` - Pricing engine (Black-Scholes + Greeks calculation)

## Troubleshooting

| Problem | Solution |
|---------|---------|
| IV not available | Use HV as proxy; ask user for broker IV |
| Negative option price | Check inputs (strike vs stock price relationship) |
| Greeks seem wrong | Verify T in years, sigma annualized, r as decimal |
| Strategy too complex | Break into individual legs, analyze separately |
