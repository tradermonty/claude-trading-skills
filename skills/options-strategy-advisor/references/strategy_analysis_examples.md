# Strategy Analysis Examples

Worked examples for Steps 6 to 9 of the options strategy workflow, moved verbatim from `SKILL.md`.

## Step 6 detail: Generate P/L Diagram (ASCII Art)

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

## Step 7 detail: Strategy-Specific Analysis

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

## Step 8 detail: Earnings Strategy Analysis

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

## Step 9 detail: Risk Management Guidance

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
