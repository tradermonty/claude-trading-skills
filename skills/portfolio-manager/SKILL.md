---
name: portfolio-manager
description: Comprehensive portfolio analysis using Alpaca MCP Server integration to fetch holdings and positions, then analyze asset allocation, risk metrics, individual stock positions, diversification, and generate rebalancing recommendations. Use when user requests portfolio review, position analysis, risk assessment, performance evaluation, or rebalancing suggestions for their brokerage account.
---

# Portfolio Manager

## Overview

Analyze and manage investment portfolios by integrating with Alpaca MCP Server to fetch real-time holdings data, then performing comprehensive analysis covering asset allocation, diversification, risk metrics, individual position evaluation, and rebalancing recommendations. Generate detailed portfolio reports with actionable insights.

The full brokerage analysis uses Alpaca's API through MCP for live portfolio data. The `portfolio-holdings-review` workflow provides a limited offline allocation review from CSV or saved Alpaca positions JSON. It reports gross holdings weights and per-position unrealized P&L; account-wide risk analysis uses the full brokerage workflow.

## When to Use

Invoke this skill when the user requests:
- "Analyze my portfolio"
- "Review my current positions"
- "What's my asset allocation?"
- "Check my portfolio risk"
- "Should I rebalance my portfolio?"
- "Evaluate my holdings"
- "Portfolio performance review"
- "What stocks should I buy or sell?"
- Any request involving portfolio-level analysis or management

## Prerequisites

### Limited Offline CSV Review

For a local USD equity holdings snapshot without credentials, read
`references/csv-holdings-review.md` and run `scripts/review_csv.py` with an explicit
source timestamp. Use the bundled fictional CSV to verify offline execution.
This produces gross allocation and per-position unrealized P&L only; it cannot
measure account exposure, leverage or historical performance. Keep personal
holdings and reports local. Do not fetch brokerage data or continue the full
workflow for this limited mode. Ask Navigator for "review my portfolio from CSV"
to select `portfolio-holdings-review`. The recommendation does not read the file:
provide the real input path and source timestamp to the CLI before review.
Saved Alpaca positions JSON can use `--input-format alpaca-json` for the same
limited calculations; it does not fetch broker data. Both formats follow the
shared output schema in `assets/holdings-review.schema.json`.

### Alpaca MCP Server Setup (Full Brokerage Analysis)

The full brokerage analysis requires Alpaca MCP Server to be configured and connected. The MCP server provides access to:
- Current portfolio positions
- Account equity and buying power
- Historical positions and transactions
- Market data for held securities

**MCP Server Tools Used:**
- `get_account_info` - Fetch account equity, buying power, cash balance
- `get_positions` - Retrieve all current positions with quantities, cost basis, market value
- `get_portfolio_history` - Historical portfolio performance data
- Market data tools for price quotes and fundamentals

If Alpaca MCP Server is not connected, inform the user and provide setup instructions from `references/alpaca-mcp-setup.md`.

### REST Fallback Connection Check

Run the connection check from the repository root. Use paper credentials first;
never paste credentials into a report or commit them to the repository.

```bash
export ALPACA_API_KEY="<alpaca-key-id>"
export ALPACA_SECRET_KEY="<alpaca-secret-key>"
export ALPACA_PAPER="true"
uv run python skills/portfolio-manager/scripts/check_alpaca_connection.py
```

The command writes a redacted diagnostic summary to stdout and returns zero only
when the account and positions endpoints succeed. It does not create a report
file or place orders.

## Workflow

### Step 1: Fetch Portfolio Data via Alpaca MCP or REST fallback

Use Alpaca MCP Server tools to gather current portfolio information when available. In scheduled Hermes jobs, MCP tools may not be exposed even when Alpaca credentials are present; in that case, use the Alpaca REST API directly with `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, and `ALPACA_PAPER`.

Read `references/alpaca-data-fetch.md` (section "Step 1 detail: account, positions and portfolio history requests") when fetching data. It holds the MCP tool and REST fallback endpoints and headers for steps 1.1 to 1.3.

**Scheduled-job fallback discipline:**
- Clearly label the source as `Alpaca REST fallback` rather than MCP.
- Use `ALPACA_PAPER=true` to choose paper endpoint; otherwise use live endpoint.
- Still validate that long market value plus cash approximately reconciles to equity, and highlight margin/leverage if `long_market_value > equity`.
- For weekly core portfolio cron jobs, compute exposure using equity as the denominator as well as gross market value: `gross_long_exposure = long_market_value / equity`, `cash_pct = cash / equity`, and explicitly flag margin-funded portfolios when gross exposure is materially above 100% or cash is negative. Do not let sector weights look benign by using only gross-long denominator when the account is levered.
- When the request emphasizes dividend holdings or forced-review triggers, build normalized monitor input from the live holdings and hand it to `kanchi-dividend-review-monitor` rather than treating dividend review as a narrative-only section. Also build tax-planning input for `kanchi-dividend-us-tax-accounting` when account-location notes are requested; label it degraded if account type or holding-period windows are unavailable.

**Data Validation:**
- Verify all positions have valid ticker symbols
- Confirm market values sum to approximate account equity
- Check for any stale or inactive positions
- Handle edge cases (fractional shares, options, crypto if supported)

### Reconcile holdings before weekly allocation review

For `core-portfolio-weekly`, follow
[`references/position-reconciliation.md`](references/position-reconciliation.md)
to compare complete broker and ACTIVE / PARTIALLY_CLOSED memory snapshots using
`scripts/reconcile_positions.py`. Generate the JSON and Markdown reconciliation
reports. Stop allocation and rebalance review if `can_continue` is false or if
snapshot completeness, account attribution or freshness cannot be established.
Keep discrepancies for manual resolution; never place orders or modify theses
through reconciliation. This is an offline, manually prepared gate; existing
weekly replay fixtures do not yet execute it.

### Step 2: Enrich Position Data

For each position in the portfolio, gather additional market data and fundamentals:

**2.1 Current Market Data:**
- Real-time or delayed price quotes
- Daily volume and liquidity metrics
- 52-week range
- Market capitalization

**2.2 Fundamental Data:**
Use WebSearch or available market data APIs to fetch:
- Sector and industry classification
- Key valuation metrics (P/E, P/B, dividend yield)
- Recent earnings and financial health indicators
- Analyst ratings and price targets
- Recent news and material developments

**2.3 Technical Analysis:**
- Price trend (20-day, 50-day, 200-day moving averages)
- Relative strength
- Support and resistance levels
- Momentum indicators (RSI, MACD if available)

### Step 3: Portfolio-Level Analysis

Perform comprehensive portfolio analysis using frameworks from reference files:

#### 3.1 Asset Allocation Analysis

**Read references/asset-allocation.md** for allocation frameworks

Analyze current allocation across multiple dimensions:

**By Asset Class:**
- Equities vs Fixed Income vs Cash vs Alternatives
- Compare to target allocation for user's risk profile
- Assess if allocation matches investment goals

**By Sector:**
- Technology, Healthcare, Financials, Consumer, etc.
- Identify sector concentration risks
- Compare to benchmark sector weights (e.g., S&P 500)

**By Market Cap:**
- Large-cap vs Mid-cap vs Small-cap distribution
- Concentration in mega-caps
- Market cap diversification score

**By Geography:**
- US vs International vs Emerging Markets
- Domestic concentration risk assessment

**Output Format (illustrative values):**
Read `references/report-section-templates.md` (section "Asset Allocation output template") for the asset allocation output template.

#### 3.2 Diversification Analysis

**Read references/diversification-principles.md** for diversification theory

Evaluate portfolio diversification quality:

**Position Concentration:**
- Identify top holdings and their aggregate weight
- Flag if any single position exceeds 10-15% of portfolio
- Calculate Herfindahl-Hirschman Index (HHI) for concentration measurement

**Sector Concentration:**
- Identify dominant sectors
- Flag if any sector exceeds 30-40% of portfolio
- Compare to benchmark sector diversity

**Correlation Analysis:**
- Estimate correlation between major positions
- Identify highly correlated holdings (potential redundancy)
- Assess true diversification benefit

**Number of Positions:**
- Optimal range: 15-30 stocks for individual portfolios
- Flag if under-diversified (<10 stocks) or over-diversified (>50 stocks)

**Output (illustrative values):**
Read `references/report-section-templates.md` (section "Diversification Assessment output template") for the diversification output template.

#### 3.3 Risk Analysis

**Read references/portfolio-risk-metrics.md** for risk measurement frameworks

Calculate and interpret key risk metrics:

**Volatility Measures:**
- Estimated portfolio beta (weighted average of position betas)
- Individual position volatilities
- Portfolio standard deviation (if historical data available)

**Downside Risk:**
- Maximum drawdown (from portfolio history)
- Current drawdown from peak
- Positions with significant unrealized losses

**Risk Concentration:**
- Percentage in high-volatility stocks (beta > 1.5)
- Percentage in speculative/unprofitable companies
- Leverage usage (if applicable)

**Tail Risk:**
- Exposure to potential black swan events
- Single-stock concentration risk
- Sector-specific event risk

**Output (illustrative values):**
Read `references/report-section-templates.md` (section "Risk Assessment output template") for the risk assessment output template.

#### 3.4 Performance Analysis

Evaluate portfolio performance using available data:

**Absolute Returns:**
- Overall portfolio unrealized P&L ($ and %)
- Best performing positions (top 5 by % gain)
- Worst performing positions (bottom 5 by % loss)

**Time-Weighted Returns (if history available):**
- YTD return
- 1-year, 3-year, 5-year annualized returns
- Compare to benchmark (S&P 500, relevant index)

**Position-Level Performance:**
- Winners vs Losers ratio
- Average gain on winning positions
- Average loss on losing positions
- Positions near 52-week highs/lows

**Output (illustrative values):**
Read `references/report-section-templates.md` (section "Performance Review output template") for the performance review output template.

### Step 4: Individual Position Analysis

For key positions (top 10-15 by portfolio weight), perform detailed analysis:

**Read references/position-evaluation.md** for position analysis framework

For each significant position:

**4.1 Current Thesis Validation:**
- Why was this position initiated? (if known from user context)
- Has the investment thesis played out or broken?
- Recent company developments and news

**4.2 Valuation Assessment:**
- Current valuation metrics (P/E, P/B, etc.)
- Compare to historical valuation range
- Compare to sector peers
- Overvalued / Fair / Undervalued assessment

**4.3 Technical Health:**
- Price trend (uptrend, downtrend, sideways)
- Position relative to moving averages
- Support and resistance levels
- Momentum status

**4.4 Position Sizing:**
- Current weight in portfolio
- Is size appropriate given conviction and risk?
- Overweight or underweight vs optimal

**4.5 Action Recommendation:**
- **HOLD** - Position is well-sized and thesis intact
- **ADD** - Underweight given opportunity, thesis strengthening
- **TRIM** - Overweight or valuation stretched
- **SELL** - Thesis broken, better opportunities elsewhere

**Output per position (illustrative values):**
Read `references/report-section-templates.md` (section "Per-position output template") for the per-position output template.

### Step 5: Rebalancing Recommendations

**Read references/rebalancing-strategies.md** for rebalancing approaches

Generate specific rebalancing recommendations:

**5.1 Identify Rebalancing Triggers:**
- Positions that have drifted significantly from target weights
- Sector/asset class allocations requiring adjustment
- Overweight positions to trim (exceeded threshold)
- Underweight areas to add (below threshold)
- Tax considerations (capital gains implications)

**5.2 Develop Rebalancing Plan:**

**Positions to TRIM:**
- Overweight positions (>threshold deviation from target)
- Stocks that have run up significantly (valuation concerns)
- Concentrated positions exceeding 15-20% of portfolio
- Positions with broken thesis

**Positions to ADD:**
- Underweight sectors or asset classes
- High-conviction positions currently underweight
- New opportunities to improve diversification

**Cash Deployment:**
- If excess cash (>10% of portfolio), suggest deployment
- Prioritize based on opportunity and allocation gaps

**5.3 Prioritization:**
Rank rebalancing actions by priority:
1. **Immediate** - Risk reduction (trim concentrated positions)
2. **High Priority** - Major allocation drift (>10% from target)
3. **Medium Priority** - Moderate drift (5-10% from target)
4. **Low Priority** - Fine-tuning and opportunistic adjustments

**Output (illustrative values):**
Read `references/report-section-templates.md` (section "Rebalancing Recommendations output template") for the rebalancing output template.

### Step 6: Generate Portfolio Report

Create comprehensive markdown report saved to repository root:

**Filename:** `portfolio_analysis_YYYY-MM-DD.md`

**Report Structure:** Read `references/report-section-templates.md` (section "Step 6: Portfolio Analysis Report structure") for the full report structure, from Executive Summary to Appendix.

### Step 7: Interactive Follow-up

Be prepared to answer follow-up questions: Read `references/follow-up-and-advanced.md` (section "Step 7 detail: Interactive Follow-up") when answering follow-up questions. It holds the common questions with answer guidance.

## Analysis Frameworks

### Target Allocation Templates

This skill includes reference allocation models for different investor profiles:

**Read references/target-allocations.md** for detailed models:

- **Conservative** (Capital preservation, income focus)
- **Moderate** (Balanced growth and income)
- **Growth** (Long-term capital appreciation)
- **Aggressive** (Maximum growth, high risk tolerance)

Each model includes:
- Asset class targets (Stocks/Bonds/Cash/Alternatives)
- Sector guidelines
- Market cap distribution
- Geographic allocation
- Position sizing rules

Use these as comparison benchmarks when user hasn't specified their allocation strategy.

### Risk Profile Assessment

If user's target allocation is unknown, assess appropriate risk profile based on:
- Age (if mentioned)
- Investment timeline (if mentioned)
- Current allocation (reveals preferences)
- Position types (conservative vs speculative stocks)

**Read references/risk-profile-questionnaire.md** for assessment framework

## Output Guidelines

**Tone and Style:**
- Objective and analytical
- Actionable recommendations with clear rationale
- Acknowledge uncertainty in market forecasts
- Balance optimism with risk awareness
- Quantify whenever possible

**Data Presentation:**
- Tables for comparisons and metrics
- Percentages for allocations and returns
- Dollar amounts for absolute values
- Consistent formatting throughout report

**Recommendation Clarity:**
- Explicit action verbs (TRIM, ADD, HOLD, SELL)
- Specific quantities derived from live position sizes and current prices
- Priority levels (Immediate, High, Medium, Low)
- Supporting rationale for each recommendation

**Visual Descriptions:**
- Describe allocation breakdowns as if creating pie charts
- Sector weights as bar chart equivalents
- Performance trends with directional indicators (↑ ↓ →)

## Resources

Read `references/resource-index.md` to decide which reference file to load. It holds the per-file When/Contains index.

## Error Handling

**If Alpaca MCP Server is not connected:**
1. For full brokerage analysis, explain the Alpaca requirement and provide
   setup instructions from references/alpaca-mcp-setup.md.
2. For a local holdings-only review, use `portfolio-holdings-review` and the
   documented CSV or saved-position contract in references/csv-holdings-review.md.
3. State its unavailable account-level analyses before interpreting results.

**If API returns incomplete data:**
- Proceed with available data
- Note limitations in report
- Suggest manual verification for missing positions

**If position data seems stale:**
- Flag the issue
- Recommend refreshing connection or checking Alpaca status
- Proceed with analysis but caveat findings

**If user has no positions:**
- Acknowledge empty portfolio
- Offer portfolio construction guidance instead of analysis
- Suggest using value-dividend-screener or us-stock-analysis for stock ideas

## Advanced Features

Read `references/follow-up-and-advanced.md` (section "Advanced Features") when the user asks for tax-loss harvesting, dividend income, correlation or scenario analysis.

## Example Queries

Read `references/follow-up-and-advanced.md` (section "Example Queries") for example queries grouped by analysis type.

## Limitations and Disclaimers

**Include in all reports:**

*This analysis is for informational purposes only and does not constitute financial advice. Investment decisions should be made based on individual circumstances, risk tolerance, and financial goals. Past performance does not guarantee future results. Consult with a qualified financial advisor before making investment decisions.*

*Data accuracy depends on Alpaca API and third-party market data sources. Verify critical information independently. Tax implications are estimates only; consult a tax professional for specific guidance.*
