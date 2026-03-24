---
name: portfolio-manager
description: "Comprehensive portfolio analysis using Alpaca MCP Server integration to fetch holdings and positions, then analyze asset allocation, risk metrics, individual stock positions, diversification, and generate rebalancing recommendations. Use when user requests portfolio review, position analysis, risk assessment, performance evaluation, or rebalancing suggestions for their brokerage account."
---

# Portfolio Manager

Analyze investment portfolios via Alpaca MCP Server. Fetch real-time holdings, perform allocation/risk/diversification analysis, evaluate individual positions, and generate rebalancing recommendations with actionable reports.

## Prerequisites

Alpaca MCP Server must be configured and connected. If unavailable, inform the user and load `references/alpaca-mcp-setup.md` for setup instructions. Fallback: accept manual CSV of positions.

## Workflow

### Step 1: Fetch Portfolio Data

**1.1 Account info:**
```
mcp__alpaca__get_account_info()
```
Extract: equity, cash balance, buying power, account status.

**1.2 Current positions:**
```
mcp__alpaca__get_positions()
```
Extract per position: symbol, quantity, avg entry price, current price, market value, unrealized P&L ($ and %), portfolio weight %.

**1.3 Portfolio history (if performance analysis requested):**
```
mcp__alpaca__get_portfolio_history()
```
Extract: historical equity values, time-weighted returns, drawdown data.

**1.4 Validate data before proceeding:**
- Confirm position market values sum to ~account equity. If >5% discrepancy, flag and note in report.
- Check for stale/inactive positions. If found, warn user and exclude from analysis.
- Handle edge cases (fractional shares, options, crypto) by noting unsupported types.

### Step 2: Enrich Position Data

For each position, use WebSearch or available market data APIs to gather:
- Sector/industry classification, market cap
- Valuation metrics (P/E, P/B, dividend yield)
- Price trend vs 20/50/200-day moving averages
- Recent news and material developments

If enrichment fails for a position, proceed with available data and note gaps.

### Step 3: Portfolio-Level Analysis

Run all four sub-analyses. Load the indicated reference file for each framework.

**3.1 Asset Allocation** -- load `references/asset-allocation.md`
- Classify holdings by: asset class, sector, market cap, geography
- Compare current vs target allocation (use `references/target-allocations.md` if user has no stated target)
- Flag any dimension with >10% drift from target

**3.2 Diversification** -- load `references/diversification-principles.md`
- Calculate position concentration (HHI index)
- Flag: single position >15%, single sector >35%, total positions <10 or >50
- Identify highly correlated pairs (correlation >0.8) as redundancy risk

**3.3 Risk Assessment** -- load `references/portfolio-risk-metrics.md`
- Weighted portfolio beta
- Maximum drawdown (from history) and current drawdown from peak
- Classify overall risk profile: Conservative / Moderate / Aggressive
- Flag high-risk positions (beta >1.5, large unrealized losses)

**3.4 Performance Review**
- Total unrealized P&L ($ and %)
- Top 5 winners and bottom 5 losers by % return
- If history available: YTD and benchmark comparison (S&P 500)

If user's risk profile is unknown, load `references/risk-profile-questionnaire.md` and infer from current allocation and position types.

### Step 4: Individual Position Analysis

For top 10-15 positions by weight, load `references/position-evaluation.md` and evaluate each:

| Field | Detail |
|-------|--------|
| Position details | Shares, avg cost, current price, market value, unrealized P&L |
| Fundamental snapshot | Sector, market cap, P/E, dividend yield, recent developments |
| Technical status | Trend direction, price vs 50-day MA, support/resistance |
| Thesis status | Intact / Weakening / Broken / Strengthening |
| Valuation | Undervalued / Fair / Overvalued |
| Sizing | Optimal / Overweight / Underweight |
| **Recommendation** | **HOLD / ADD / TRIM / SELL** with 1-2 sentence rationale |

### Step 5: Rebalancing Recommendations

Load `references/rebalancing-strategies.md`. Generate prioritized actions:

1. **Immediate** -- risk reduction (trim concentrated positions, broken theses)
2. **High priority** -- major allocation drift (>10% from target)
3. **Medium priority** -- moderate drift (5-10%), cash deployment if cash >10%
4. **Low priority** -- fine-tuning, opportunistic adjustments

For each action specify: symbol, direction (TRIM/ADD/SELL), share count or dollar amount, rationale, estimated tax impact.

### Step 6: Generate Report

Save comprehensive markdown report to `portfolio_analysis_YYYY-MM-DD.md` with sections:

1. **Executive Summary** -- 3-5 bullet key findings
2. **Holdings Overview** -- summary table of all positions
3. **Asset Allocation** -- from Step 3.1
4. **Diversification** -- from Step 3.2
5. **Risk Assessment** -- from Step 3.3
6. **Performance Review** -- from Step 3.4
7. **Position Analysis** -- from Step 4
8. **Rebalancing Recommendations** -- from Step 5 with implementation plan
9. **Action Items** -- checklist of immediate, medium-term, and monitoring items

### Step 7: Interactive Follow-up

Handle common follow-ups: "Why sell X?", "What should I buy instead?", "What's my biggest risk?", "Should I rebalance now or wait?", "Compare to benchmark". For deep-dive on a specific position, invoke `us-stock-analysis` skill if available.

## Advanced Analysis (on request)

- **Tax-loss harvesting**: Identify positions with >5% unrealized loss, check wash sale eligibility, suggest replacement securities
- **Dividend income**: Estimate annual yield, dividend growth trajectory, yield on cost
- **Correlation matrix**: For 5-20 position portfolios, flag redundant pairs (>0.8 correlation)
- **Scenario analysis**: Model portfolio under bull (+20%), bear (-20%), sector rotation, and rising rate scenarios

## Output Guidelines

- Use explicit action verbs: TRIM, ADD, HOLD, SELL
- Specify quantities (share counts, dollar amounts)
- Assign priority levels to every recommendation
- Use tables for comparisons; percentages for allocations; dollar amounts for absolutes
- Directional indicators: up-arrow, down-arrow, right-arrow for trends

## Error Handling

| Condition | Action |
|-----------|--------|
| Alpaca MCP not connected | Load `references/alpaca-mcp-setup.md`, offer manual CSV fallback |
| API returns incomplete data | Proceed with available data, note limitations in report |
| Stale position data | Flag issue, recommend refreshing connection, caveat findings |
| Empty portfolio (no positions) | Offer portfolio construction guidance; suggest `value-dividend-screener` or `us-stock-analysis` for ideas |

## Disclaimer

Include in all reports: *This analysis is for informational purposes only and does not constitute financial advice. Past performance does not guarantee future results. Consult a qualified financial advisor before making investment decisions. Data accuracy depends on Alpaca API and third-party sources; verify critical information independently.*
