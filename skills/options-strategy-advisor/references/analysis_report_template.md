# Analysis Report Template

Output format for options strategy analysis reports, moved verbatim from `SKILL.md`.

## Strategy Analysis Report Template and File Naming

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
