# Report Section Templates

Output templates for the portfolio report sections, moved verbatim from `SKILL.md`.

## Asset Allocation output template

```markdown
## Asset Allocation

### Current Allocation vs Target
| Asset Class | Current | Target | Variance |
|-------------|---------|--------|----------|
| US Equities | 70.0% | 60.0% | +10.0 pp |

### Sector Breakdown
[Pie chart description or table with sector percentages]

### Top 10 Holdings
| Rank | Symbol | % of Portfolio | Sector |
|------|--------|----------------|--------|
| 1 | AAPL | 8.5% | Technology |
```

## Diversification Assessment output template

```markdown
## Diversification Assessment

**Concentration Risk:** [Low / Medium / High]
- Top 5 holdings represent 42% of portfolio
- Largest single position: AAPL at 12%

**Sector Diversification:** [Excellent / Good / Fair / Poor]
- Dominant sector: Technology at 31%
- [Assessment of balance across sectors]

**Position Count:** [Optimal / Under-diversified / Over-diversified]
- Total positions: 18 stocks
- [Recommendation]

**Correlation Concerns:**
- [List any highly correlated position pairs]
- [Diversification improvement suggestions]
```

## Risk Assessment output template

```markdown
## Risk Assessment

**Overall Risk Profile:** [Conservative / Moderate / Aggressive]

**Portfolio Beta:** 1.12 (vs market at 1.00)
- Interpretation: Portfolio is [more/less] volatile than market

**Maximum Drawdown:** -14.2% (from $125,000 to $107,250)
- Current drawdown from peak: -6.3%

**High-Risk Positions:**
| Symbol | % of Portfolio | Beta | Risk Factor |
|--------|----------------|------|-------------|
| NVDA | 11% | 1.65 | High volatility |

**Risk Concentrations:**
- 31% in a single sector (Technology)
- 18% in stocks with beta above 1.5
- [Other concentration risks]

**Risk Score:** 68/100 (Medium risk)
```

## Performance Review output template

```markdown
## Performance Review

**Total Portfolio Value:** $100,000
**Total Unrealized P&L:** $8,500 (+9.3%)
**Cash Balance:** $5,000 (5% of portfolio)

**Best Performers:**
| Symbol | Gain | Position Value |
|--------|------|----------------|
| AAPL | +22.4% | $12,240 |

**Worst Performers:**
| Symbol | Loss | Position Value |
|--------|------|----------------|
| INTC | -12.0% | $6,600 |

**Performance vs Benchmark (illustrative values):**
- Portfolio return: +9.3%
- S&P 500 return: +7.8%
- Alpha: +1.5 percentage points
```

## Per-position output template

```markdown
### AAPL - Apple Inc. (8.5% of portfolio)

**Position Details:**
- Shares: 50
- Avg Cost: $150.00
- Current Price: $170.00
- Market Value: $8,500
- Unrealized P/L: $1,000 (+13.3%)

**Fundamental Snapshot:**
- Sector: [Sector]
- Market Cap: $3.2T
- P/E: 31.4 | Dividend Yield: 0.5%
- Recent developments: [Key news or earnings]

**Technical Status:**
- Trend: [Uptrend / Downtrend / Sideways]
- Price vs 50-day MA: Above by 4.2%
- Support: $162.00 | Resistance: $176.00

**Position Assessment:**
- **Thesis Status:** [Intact / Weakening / Broken / Strengthening]
- **Valuation:** [Undervalued / Fair / Overvalued]
- **Position Sizing:** [Optimal / Overweight / Underweight]

**Recommendation:** [HOLD / ADD / TRIM / SELL]
**Rationale:** [1-2 sentence explanation]
```

## Rebalancing Recommendations output template

```markdown
## Rebalancing Recommendations

### Summary
- **Rebalancing Needed:** [Yes / No / Optional]
- **Primary Reason:** [Concentration risk / Sector drift / Cash deployment / etc]
- **Estimated Trades:** 2 sell orders, 3 buy orders

### Recommended Actions

#### HIGH PRIORITY: Risk Reduction
**TRIM NVDA** from 18% to 12% of portfolio
- **Shares to Sell:** 25 shares (about $3,000)
- **Rationale:** [Overweight / Valuation extended / etc]
- **Tax Impact:** $600 capital gain (estimate)

#### MEDIUM PRIORITY: Asset Allocation
**ADD investment-grade bond exposure**
- **Target:** Increase from 10% to 20%
- **Suggested Securities:** [Select liquid securities that fit the user's mandate]
- **Amount to Invest:** About $10,000

#### CASH DEPLOYMENT
**Current Cash:** $5,000 (5% of portfolio)
- **Recommendation:** [Deploy / Keep for opportunities / Reduce to target]
- **Suggested Allocation:** [Distribution across sectors/stocks]

### Implementation Plan
1. [First action - highest priority]
2. [Second action]
3. [Third action]
...

**Timing Considerations:**
- [Tax year-end planning / Earnings season / Market conditions]
- [Suggested phasing if applicable]
```

## Step 6: Portfolio Analysis Report structure

```markdown
# Portfolio Analysis Report

**Account:** [Account type if available]
**Report Date:** 2026-07-25
**Portfolio Value:** $100,000
**Total P&L:** $8,500 (+9.3%)

---

## Executive Summary

[3-5 bullet points summarizing key findings]
- Overall portfolio health assessment
- Major strengths
- Key risks or concerns
- Primary recommendations

---

## Holdings Overview

[Summary table of all positions]

---

## Asset Allocation
[Section from Step 3.1]

---

## Diversification Analysis
[Section from Step 3.2]

---

## Risk Assessment
[Section from Step 3.3]

---

## Performance Review
[Section from Step 3.4]

---

## Position Analysis
[Detailed analysis of top 10-15 positions from Step 4]

---

## Rebalancing Recommendations
[Section from Step 5]

---

## Action Items

**Immediate Actions:**
- [ ] [Action 1]
- [ ] [Action 2]

**Medium-Term Actions:**
- [ ] [Action 3]
- [ ] [Action 4]

**Monitoring Priorities:**
- [ ] [Watch list item 1]
- [ ] [Watch list item 2]

---

## Appendix: Full Holdings

[Complete table with all positions and metrics]
```
