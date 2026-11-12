# Report Template

Step 4 report structure, moved verbatim from `SKILL.md`.

```markdown
# Value Dividend Stock Screening Report

**Generated:** [Timestamp]
**Screening Criteria:**
- Dividend Yield: >= 3.5%
- P/E Ratio: <= 20
- P/B Ratio: <= 2
- Dividend Growth (3Y CAGR): >= 5%
- Revenue Trend: Positive over 3 years
- EPS Trend: Positive over 3 years

**Total Results:** [N] stocks

---

## Top 20 Stocks Ranked by Composite Score

| Rank | Symbol | Company | Yield | P/E | Div Growth | Score |
|------|--------|---------|-------|-----|------------|-------|
| 1 | [TICKER] | [Name] | [%] | [X.X] | [%] | [XX.X] |
| ... |

---

## Detailed Analysis

### 1. [SYMBOL] - [Company Name] (Score: XX.X)

**Sector:** [Sector Name]
**Market Cap:** $[X.XX]B
**Current Price:** $[XX.XX]

**Valuation Metrics:**
- Dividend Yield: [X.X]%
- P/E Ratio: [XX.X]
- P/B Ratio: [X.X]

**Growth Profile (3-Year):**
- Dividend CAGR: [X.X]% [✓ Consistent / ⚠ One cut]
- Revenue CAGR: [X.X]%
- EPS CAGR: [X.X]%

**Dividend Sustainability:**
- Payout Ratio: [XX]%
- FCF Payout Ratio: [XX]%
- FCF Observed: [amount or unavailable] ([POSITIVE / ZERO / NEGATIVE / MISSING_DATA])
- FCF Coverage: [COVERED / AT_LIMIT / INSUFFICIENT_FCF / ZERO_FCF / NEGATIVE_FCF / MISSING_DATA / NO_DIVIDEND]
- Decision Basis: [EARNINGS_AND_FCF / FFO]
- Status: [✓ Sustainable / ⚠ Not confirmed]; Bonus: [0 / 10] points
- Explanation: [sustainability_note]

**Financial Health:**
- Debt-to-Equity: [X.XX]
- Current Ratio: [X.XX]
- Status: [✓ Healthy / ⚠ Caution]

**Quality Metrics:**
- ROE: [XX]%
- Net Profit Margin: [XX]%
- Quality Score: [XX]/100

**Investment Considerations:**
- [Key strength 1]
- [Key strength 2]
- [Risk factor or consideration]

---

[Repeat for other top stocks]

---

## Portfolio Construction Guidance

**Diversification Recommendations:**
- Sector breakdown of top 20 results
- Suggested allocation strategy
- Concentration risk warnings

**Monitoring Recommendations:**
- Key metrics to track quarterly
- Warning signs for each position
- Rebalancing triggers

**Risk Considerations:**
- Market cap concentration
- Sector biases in results
- Economic sensitivity warnings
```
