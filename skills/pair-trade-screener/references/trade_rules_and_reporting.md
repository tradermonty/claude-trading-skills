# Trade Rules and Reporting

Steps 6 to 8 detail, moved verbatim from `SKILL.md`.

## Step 6 detail: Entry and Exit Conditions

**Entry Conditions:**

**Conservative Approach (Z ≥ ±2.0):**
```
LONG Signal:
- Z-score < -2.0 (spread 2+ std devs below mean)
- Spread is mean-reverting (cointegration p < 0.05)
- Half-life < 60 days
→ Action: Buy Stock A, Short Stock B (hedge ratio = beta)

SHORT Signal:
- Z-score > +2.0 (spread 2+ std devs above mean)
- Spread is mean-reverting (cointegration p < 0.05)
- Half-life < 60 days
→ Action: Short Stock A, Buy Stock B (hedge ratio = beta)
```

**Aggressive Approach (Z ≥ ±1.5):**
- Lower threshold for more frequent trades
- Higher win rate but smaller avg profit per trade
- Requires tighter risk management

**Exit Conditions:**

**Primary Exit: Mean Reversion (Z = 0)**
```
Exit when spread returns to mean (z-score crosses 0)
→ Close both legs simultaneously
```

**Secondary Exit: Partial Profit Take**
```
Exit 50% when z-score reaches ±1.0
Exit remaining 50% at z-score = 0
```

**Stop Loss:**
```
Exit if z-score extends beyond ±3.0 (extreme divergence)
Risk: Possible structural break in relationship
```

**Time-Based Exit:**
```
Exit after 90 days if no mean-reversion
Prevents holding broken pairs indefinitely
```

## Step 7 detail: Position Sizing and Risk Management

**Market Neutral Sizing:**

**Share-Hedged Sizing (Price-Level OLS):**

For a pair (Stock A, Stock B) with price-level OLS slope β (`Spread = Price_A - β × Price_B`), each 1 share of Stock A is hedged by β shares of Stock B:

```
If gross allocation = $10,000 for this pair:
- Shares of A: n_A = $10,000 / (Price_A + β × Price_B)
- Shares of B: n_B = β × n_A
- Dollar notional A: n_A × Price_A
- Dollar notional B: n_B × Price_B  (= notional_A × β × Price_B / Price_A)

Example (Price_A = $120, Price_B = $100, β = 1.2):
- n_A = $10,000 / ($120 + 1.2 × $100) = 41.67 shares → Long $5,000 Stock A
- n_B = 1.2 × 41.67 = 50.00 shares → Short $5,000 Stock B
→ Spread-neutral (ΔSpread = 0 ⇒ P&L = 0), gross notional = $10,000
```

**Position Sizing Considerations:**
- Total pair allocation: 10-20% of portfolio per pair
- Maximum pairs: 5-8 active pairs for diversification
- Correlation across pairs: Avoid highly correlated pairs

**Risk Metrics:**
- Maximum loss per pair: 2-3% of total portfolio
- Stop loss trigger: Z-score > ±3.0 or -5% loss on spread
- Portfolio-level risk: Sum of all pair risks ≤ 10%

## Step 8 detail: Pair Analysis Report

**Report Sections:**

1. **Executive Summary**
   - Total pairs analyzed
   - Number of cointegrated pairs found
   - Top 5 opportunities ranked by statistical strength

2. **Cointegrated Pairs Table**
   - Pair name (Stock A / Stock B)
   - Correlation coefficient
   - Cointegration p-value
   - Current z-score
   - Trade signal (Long/Short/None)
   - Half-life

3. **Detailed Analysis (Top 10 Pairs)**
   - Pair description
   - Statistical metrics
   - Current spread position
   - Entry/exit recommendations
   - Position sizing
   - Risk assessment

4. **Spread Charts (Text-Based)**
   - Historical z-score plot (ASCII art)
   - Entry/exit levels marked
   - Current position indicator

5. **Risk Warnings**
   - Pairs with deteriorating correlation
   - Structural breaks detected
   - Low liquidity warnings

**File Naming Convention:**
```
pair_trade_analysis_[SECTOR]_[YYYY-MM-DD].md
```

Example: `pair_trade_analysis_Technology_2025-11-08.md`
