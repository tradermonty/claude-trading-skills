---
layout: default
title: "Portfolio Manager"
grand_parent: English
parent: Skill Guides
nav_order: 46
lang_peer: /ja/skills/portfolio-manager/
permalink: /en/skills/portfolio-manager/
---

# Portfolio Manager
{: .no_toc }

Comprehensive portfolio analysis using Alpaca MCP Server integration to fetch holdings and positions, then analyze asset allocation, risk metrics, individual stock positions, diversification, and generate rebalancing recommendations. Use when user requests portfolio review, position analysis, risk assessment, performance evaluation, or rebalancing suggestions for their brokerage account.
{: .fs-6 .fw-300 }

<span class="badge badge-api">Alpaca Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/portfolio-manager.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/portfolio-manager){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Analyze and manage investment portfolios by integrating with Alpaca MCP Server to fetch real-time holdings data, then performing comprehensive analysis covering asset allocation, diversification, risk metrics, individual position evaluation, and rebalancing recommendations. Generate detailed portfolio reports with actionable insights.

This skill leverages Alpaca's brokerage API through MCP (Model Context Protocol) to access live portfolio data, ensuring analysis is based on actual current positions rather than manually entered data.

---

## 2. When to Use

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

---

## 3. Prerequisites

### Alpaca MCP Server Setup

This skill requires Alpaca MCP Server to be configured and connected. The MCP server provides access to:
- Current portfolio positions
- Account equity and buying power
- Historical positions and transactions
- Market data for held securities

**MCP Server Tools Used:**
- `get_account_info` - Fetch account equity, buying power, cash balance
- `get_positions` - Retrieve all current positions with quantities, cost basis, market value
- `get_portfolio_history` - Historical portfolio performance data
- Market data tools for price quotes and fundamentals

If Alpaca MCP Server is not connected, inform the user and provide setup instructions from `references/alpaca_mcp_setup.md`.

---

## 4. Quick Start

```bash
# Test Alpaca connection
python3 skills/portfolio-manager/scripts/check_alpaca_connection.py

# Portfolio analysis is done via Claude with Alpaca MCP tools
# See portfolio-manager/references/alpaca-mcp-setup.md for setup
```

---

## 5. Workflow

### Step 1: Fetch Portfolio Data via Alpaca MCP

Use Alpaca MCP Server tools to gather current portfolio information:

**1.1 Get Account Information:**
```
Use mcp__alpaca__get_account_info to fetch:
- Account equity (total portfolio value)
- Cash balance
- Buying power
- Account status
```

**1.2 Get Current Positions:**
```
Use mcp__alpaca__get_positions to fetch all holdings:
- Symbol ticker
- Quantity held
- Average entry price (cost basis)
- Current market price
- Current market value
- Unrealized P&L ($ and %)
- Position size as % of portfolio
```

**1.3 Get Portfolio History (Optional):**
```
Use mcp__alpaca__get_portfolio_history for performance analysis:
- Historical equity values
- Time-weighted return calculation
- Drawdown analysis
```

**Data Validation:**
- Verify all positions have valid ticker symbols
- Confirm market values sum to approximate account equity
- Check for any stale or inactive positions
- Handle edge cases (fractional shares, options, crypto if supported)

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

**Output Format:**
```markdown

---

## 6. Resources

**References:**

- `skills/portfolio-manager/references/alpaca-mcp-setup.md`
- `skills/portfolio-manager/references/asset-allocation.md`
- `skills/portfolio-manager/references/diversification-principles.md`
- `skills/portfolio-manager/references/portfolio-risk-metrics.md`
- `skills/portfolio-manager/references/position-evaluation.md`
- `skills/portfolio-manager/references/rebalancing-strategies.md`
- `skills/portfolio-manager/references/risk-profile-questionnaire.md`
- `skills/portfolio-manager/references/target-allocations.md`

**Scripts:**

- `skills/portfolio-manager/scripts/check_alpaca_connection.py`
