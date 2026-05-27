---
layout: default
title: "US Stock Analysis"
grand_parent: English
parent: Skill Guides
nav_order: 63
lang_peer: /ja/skills/us-stock-analysis/
permalink: /en/skills/us-stock-analysis/
---

# US Stock Analysis
{: .no_toc }

Comprehensive US stock analysis including fundamental analysis (financial metrics, business quality, valuation), technical analysis (indicators, chart patterns, support/resistance), stock comparisons, and investment report generation. Use when user requests analysis of US stock tickers (e.g., "analyze AAPL", "compare TSLA vs NVDA", "give me a report on Microsoft"), evaluation of financial metrics, technical chart analysis, or investment recommendations for American stocks.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/us-stock-analysis.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/us-stock-analysis){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Perform comprehensive analysis of US stocks covering fundamental analysis (financials, business quality, valuation), technical analysis (indicators, trends, patterns), peer comparisons, and generate detailed investment reports. Fetch real-time market data via web search tools and apply structured analytical frameworks.

---

## 2. Prerequisites

- User provides data
- Python 3.9+ recommended

---

## 3. Quick Start

### 1. Basic Stock Information

**When to Use:** User asks for quick overview or basic info

---

## 4. Workflow

### 1. Basic Stock Information

**When to Use:** User asks for quick overview or basic info

**Steps:**
1. Search for current stock data (price, volume, market cap)
2. Gather key metrics (P/E, EPS, revenue growth, margins)
3. Get 52-week range and year-to-date performance
4. Find recent news or major developments
5. Present in concise summary format

**Output Format:**
- Company description (1-2 sentences)
- Current price and trading metrics
- Key valuation metrics (table)
- Recent performance
- Notable recent news (if any)

### 2. Fundamental Analysis

**When to Use:** User wants financial analysis, valuation assessment, or business evaluation

**Steps:**
1. **Gather comprehensive financial data:**
   - Revenue, earnings, cash flow (3-5 year trends)
   - Balance sheet metrics (debt, cash, working capital)
   - Profitability metrics (margins, ROE, ROIC)

2. **Read references/fundamental-analysis.md** for analytical framework

3. **Read references/financial-metrics.md** for metric definitions and calculations

4. **Analyze business quality:**
   - Competitive advantages
   - Management track record
   - Industry position

5. **Perform valuation analysis:**
   - Calculate key ratios (P/E, PEG, P/B, EV/EBITDA)
   - Compare to historical averages
   - Compare to peer group
   - Estimate fair value range

6. **Identify risks:**
   - Company-specific risks
   - Market/macro risks
   - Red flags from financial data

7. **Generate output** following references/report-template.md structure

**Critical Analyses:**
- Profitability trends (improving/declining margins)
- Cash flow quality (FCF vs earnings)
- Balance sheet strength (debt levels, liquidity)
- Growth sustainability
- Valuation vs peers and historical average

### 3. Technical Analysis

**When to Use:** User asks for technical analysis, chart patterns, or trading signals

**Steps:**
1. **Gather technical data:**
   - Current price and recent price action
   - Volume trends
   - Moving averages (20-day, 50-day, 200-day)
   - Technical indicators (RSI, MACD, Bollinger Bands)

2. **Read references/technical-analysis.md** for indicator definitions and patterns

3. **Identify trend:**
   - Uptrend, downtrend, or sideways
   - Strength of trend

4. **Locate support and resistance levels:**
   - Recent highs and lows
   - Moving average levels
   - Round numbers

5. **Analyze indicators:**
   - RSI: Overbought (>70) or oversold (<30)
   - MACD: Crossovers and divergences
   - Volume: Confirmation or divergence
   - Bollinger Bands: Squeeze or expansion

6. **Identify chart patterns:**
   - Reversal patterns (head and shoulders, double top/bottom)
   - Continuation patterns (flags, triangles)

7. **Generate technical outlook:**
   - Current trend assessment
   - Key levels to watch
   - Risk/reward analysis
   - Short and medium-term outlook

**Interpretation Guidelines:**
- Confirm signals with multiple indicators
- Consider volume for validation
- Note divergences between price and indicators
- Always identify risk levels (stop-loss)

### 4. Comprehensive Investment Report

**When to Use:** User asks for detailed report, investment recommendation, or complete analysis

**Steps:**
1. **Perform data gathering** (as in Basic Info)

2. **Execute fundamental analysis** (follow workflow above)

3. **Execute technical analysis** (follow workflow above)

4. **Read references/report-template.md** for complete report structure

5. **Synthesize findings:**
   - Integrate fundamental and technical insights
   - Develop bull and bear cases
   - Assess risk/reward

6. **Generate recommendation:**
   - Buy/Hold/Sell rating
   - Target price with timeframe
   - Conviction level
   - Entry strategy

7. **Create formatted report** following template structure

**Report Must Include:**
- Executive summary with recommendation
- Company overview
- Investment thesis (bull and bear cases)
- Fundamental analysis section
- Technical analysis section
- Valuation analysis
- Risk assessment
- Catalysts and timeline
- Conclusion

---

## 5. Resources

**References:**

- `skills/us-stock-analysis/references/financial-metrics.md`
- `skills/us-stock-analysis/references/fundamental-analysis.md`
- `skills/us-stock-analysis/references/report-template.md`
- `skills/us-stock-analysis/references/technical-analysis.md`
