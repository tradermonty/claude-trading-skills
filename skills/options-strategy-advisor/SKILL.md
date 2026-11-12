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

## Prerequisites

**Required:**
- Python 3.9+ with `numpy`, `scipy`, `requests`

**Optional:**
- FMP API key (for real-time stock prices and historical volatility)
  - Supply the key to the optional Python data-fetching helpers; no pricing CLI flags are supported
  - Without API key: Use manual inputs for stock price and volatility

**Installation:**
```bash
pip install numpy scipy requests
```

**Quick Start Examples:**
Run from the installed skill directory after installing `requirements.txt`.
Use the library for custom inputs; the module's fixed research demonstration does
not parse ticker, pricing or strategy flags. This fictional European option uses
`T` in years and annual decimal rates/volatility/dividend yield. The model assumes
constant volatility/rates and continuous dividends; it is not a trading recommendation.

<!-- options-library-example -->
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
from black_scholes import OptionPricer

# Fictional European option; T is years, r/sigma/q are annual decimals.
pricer = OptionPricer(S=100.0, K=100.0, T=1.0, r=0.0, sigma=0.2, q=0.0)
greeks = pricer.get_all_greeks("call")
print(greeks)
```

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
- Pass broker IV of 28% as `sigma=0.28` to `OptionPricer`

### Step 3: Price Options Using Black-Scholes

Read `references/black_scholes_methodology.md` (section "Step 3 detail: Price Options Using Black-Scholes") when pricing each option leg. It holds the Black-Scholes formulas, dividend and American-option adjustments, the Python implementation and the per-leg output notes.

### Step 4: Calculate Greeks

Read `references/black_scholes_methodology.md` (section "Step 4 detail: Calculate Greeks") when calculating Greeks. It holds the per-Greek Python functions, the position-Greeks aggregation example and the Greeks interpretation table.

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

Read `references/strategy_analysis_examples.md` (section "Step 6 detail: Generate P/L Diagram (ASCII Art)") when drawing the P/L diagram. It holds the `generate_pnl_diagram` function and an example diagram.

### Step 7: Strategy-Specific Analysis

Provide tailored guidance based on strategy type:

Read `references/strategy_analysis_examples.md` (section "Step 7 detail: Strategy-Specific Analysis") when writing strategy-specific guidance. It holds the worked Covered Call, Protective Put and Iron Condor examples.

### Step 8: Earnings Strategy Analysis

Read `references/strategy_analysis_examples.md` (section "Step 8 detail: Earnings Strategy Analysis") when the user asks about an earnings play. It holds the Earnings Calendar integration snippet and the Long Straddle/Strangle and Short Iron Condor examples with IV crush analysis.

### Step 9: Risk Management Guidance

Read `references/strategy_analysis_examples.md` (section "Step 9 detail: Risk Management Guidance") when sizing a position or setting exit rules. It holds the position-sizing examples, portfolio Greeks guidelines and exit rules by strategy.

## Output Format

Read `references/analysis_report_template.md` (section "Strategy Analysis Report Template and File Naming") when writing the final report. It holds the full Markdown report template and the file naming convention.

## Key Principles

Read `references/pricing_and_volatility_guidance.md` when explaining pricing limitations or volatility (HV vs IV, IV percentile). It holds the Black-Scholes assumption caveats and the volatility guidance.

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
- **Dependencies**: Python 3.9+, numpy, scipy, requests

## Common Use Cases

Read `references/common_use_cases.md` when planning the workflow for a typical request. It holds four worked use cases: learn a strategy, analyze a trade, earnings strategy, portfolio Greeks check.

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
- `references/black_scholes_methodology.md` - Black-Scholes formulas, Greeks, and interpretation

**Scripts:**
- `scripts/black_scholes.py` - Pricing engine and Greeks

**External Resources:**
- Options Playbook: https://www.optionsplaybook.com/
- CBOE Education: https://www.cboe.com/education/
- Black-Scholes Calculator: Various online tools for verification

---

**Version**: 1.0
**Last Updated**: 2025-11-08
**Dependencies**: Python 3.9+, numpy, scipy, requests
**API**: FMP API (Free tier sufficient)
