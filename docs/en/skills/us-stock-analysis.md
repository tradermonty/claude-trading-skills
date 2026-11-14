---
layout: default
title: US Stock Analysis
grand_parent: English
parent: Skill Guides
nav_order: 8
lang_peer: /ja/skills/us-stock-analysis/
permalink: /en/skills/us-stock-analysis/
---

# US Stock Analysis
{: .no_toc }

Perform comprehensive US stock analysis covering fundamental financials, technical indicators, valuation, peer comparisons, and structured investment reports with Buy/Hold/Sell recommendations.
{: .fs-6 .fw-300 }

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

US Stock Analysis provides a complete analytical framework for evaluating individual US equities. Rather than relying on a single script or API, the skill uses Claude's web search capabilities to gather real-time market data and applies structured analytical frameworks stored in its reference knowledge base.

<span class="badge badge-free">No API</span>

**What it solves:**
- Consolidates fundamental, technical, and valuation analysis into a single workflow
- Generates structured investment reports following a 10-section template
- Supports side-by-side stock comparisons (e.g., AAPL vs MSFT)
- Provides bull and bear case reasoning for balanced decision-making
- Fetches current data via WebSearch -- no manual data entry required

**Four analysis types:**

| Type | Depth | Best For |
|------|-------|----------|
| **Basic** | Quick overview | Price check, key metrics, recent news |
| **Fundamental** | Deep financial dive | Business quality, margins, debt, valuation |
| **Technical** | Chart and indicator analysis | Trend, support/resistance, RSI, MACD |
| **Comprehensive** | Full investment report | Buy/Hold/Sell recommendation with target price |

---

## 2. Prerequisites

- **API Key:** None required
- **WebSearch (required):** WebSearch must be available in Claude Code or the web app
- **Data source:** Claude uses WebSearch and WebFetch to gather real-time stock data from Yahoo Finance, MarketWatch, Seeking Alpha, SEC filings, and other public sources
- **No Python dependencies** -- this is a purely conversational skill with no CLI script

> US Stock Analysis works entirely through natural language prompts. Simply describe what you want to analyze and Claude handles data collection, analysis, and report generation.
{: .tip }

---

## 3. Quick Start

Tell Claude:

```
Analyze AAPL -- give me a comprehensive report with Buy/Hold/Sell recommendation
```

Claude searches for current financial data, applies the fundamental and technical analysis frameworks from its reference knowledge base, and generates a structured report with an investment recommendation. That is all you need to get started.

For a quicker check:

```
Quick overview of NVDA -- price, market cap, P/E, recent news
```

---

## 4. How It Works

1. **Determine analysis type** -- Claude identifies which of the four analysis types (Basic, Fundamental, Technical, Comprehensive) best matches your request.
2. **Collect market data** -- WebSearch queries gather current price, financials, analyst ratings, technical indicators, and recent news from trusted sources.
3. **Load reference frameworks** -- Relevant knowledge bases load on demand: `fundamental-analysis.md` for business quality assessment, `technical-analysis.md` for indicator interpretation, `financial-metrics.md` for ratio definitions, and `report-template.md` for output structure.
4. **Apply analytical framework** -- Data is evaluated against structured criteria: profitability trends, cash flow quality, balance sheet strength, competitive advantages, valuation vs peers, and technical signals.
5. **Generate structured output** -- The report follows the 10-section template: Executive Summary, Company Overview, Investment Thesis (bull/bear), Fundamental Analysis, Valuation Analysis, Technical Analysis, Risk Assessment, Catalysts, Recommendation, and Conclusion.

---

## 5. Usage Examples

### Example 1: Quick Overview

**Prompt:**
```
What's the current price and key metrics for MSFT?
```

**What you get:** A concise summary with current price, market cap, P/E, EPS, revenue growth, 52-week range, YTD performance, and any notable recent news.

**Why useful:** Fast check before market open or during research to get a snapshot without a full report.

---

### Example 2: Fundamental Analysis

**Prompt:**
```
Analyze NVDA's financials -- revenue trends, margins, debt, and business quality
```

**What you get:** A deep dive into 3-5 year revenue and earnings trends, profitability metrics (gross/operating/net margins), balance sheet analysis (debt-to-equity, current ratio, cash position), competitive advantages, and growth sustainability assessment.

**Why useful:** Evaluates whether the business fundamentals justify the current stock price, identifying strengths and red flags in the financial statements.

---

### Example 3: Technical Analysis

**Prompt:**
```
Technical analysis of AMZN -- trend, support/resistance, and indicators
```

**What you get:** Current trend direction and strength, key support and resistance levels, moving average positions (20/50/200-day), RSI reading, MACD status, volume trends, and any notable chart patterns forming.

**Why useful:** Identifies optimal entry and exit timing based on technical signals, complementing fundamental analysis with price action context.

---

### Example 4: Comprehensive Report

**Prompt:**
```
Give me a full investment report on META with a Buy/Hold/Sell recommendation
```

**What you get:** A complete 10-section report covering business overview, investment thesis (bull and bear cases), fundamental analysis, valuation analysis with peer comparison and fair value estimate, technical analysis, risk assessment, upcoming catalysts, and a final recommendation with target price, conviction level, and entry strategy.

**Why useful:** Provides the most thorough analysis available, suitable for making actual investment decisions or presenting to others.

---

### Example 5: Peer Comparison

**Prompt:**
```
Compare AAPL vs MSFT -- which is a better investment right now?
```

**What you get:** A side-by-side comparison table covering business models, financial metrics (revenue, margins, growth rates), valuation ratios (P/E, PEG, EV/EBITDA), balance sheet strength, technical positioning, relative strength analysis, and a recommendation on which stock is more attractive with portfolio allocation suggestions.

**Why useful:** Directly answers the "which one should I buy?" question with quantified comparisons across every dimension.

---

### Example 6: Post-Earnings Impact

**Prompt:**
```
GOOGL just reported earnings -- analyze the results and market reaction
```

**What you get:** Analysis of the earnings beat/miss versus consensus, revenue and EPS trends, guidance changes, management commentary highlights, market reaction (price move, volume), and forward implications for the stock's outlook.

**Why useful:** Rapid assessment of whether an earnings report changes the investment thesis, especially important for deciding whether to add, hold, or trim a position.

---

### Example 7: Valuation Assessment

**Prompt:**
```
Is Tesla overvalued? Look at P/E, PEG, EV/EBITDA, and compare to auto industry peers
```

**What you get:** Current valuation metrics compared to historical averages and peer group (traditional auto, EV pure-plays, tech), fair value estimate using multiple methodologies, margin of safety calculation, and assessment of whether growth expectations embedded in the price are realistic.

**Why useful:** Cuts through narrative-driven pricing to determine whether the stock offers value at current levels, using multiple valuation lenses.

---

## 6. Understanding the Output

The comprehensive report follows a structured 10-section template:

1. **Executive Summary** -- A standalone 2-3 paragraph overview with the recommendation, key thesis, and valuation summary.
2. **Company Overview** -- Business description, market position, and key statistics table.
3. **Investment Thesis** -- Bull case (3-5 positive factors with evidence) and bear case (3-5 risks with probability assessment).
4. **Fundamental Analysis** -- Business quality, financial performance tables, and growth analysis.
5. **Valuation Analysis** -- Current metrics table, peer comparison table, fair value range, and margin of safety.
6. **Technical Analysis** -- Trend, support/resistance levels, indicator readings, and chart patterns.
7. **Risk Assessment** -- Company-specific risks (prioritized), market/macro risks, and mitigation factors.
8. **Catalysts and Timeline** -- Upcoming events that could move the stock (earnings, product launches, regulatory).
9. **Recommendation** -- Buy/Hold/Sell rating, conviction level (High/Medium/Low), target price with timeframe, and entry strategy.
10. **Conclusion** -- Key points summary and monitoring triggers.

Reports are saved to the `reports/` directory with the naming convention `stock_analysis_[TICKER]_[DATE].md`.

---

## 7. Tips & Best Practices

- **Specify the analysis type explicitly.** Saying "fundamental analysis of AAPL" gives you a focused financial deep dive, while "analyze AAPL" defaults to a broader overview. Be specific about what you need.
- **Ask for comparisons when choosing between stocks.** The peer comparison format is the most efficient way to evaluate alternatives, producing side-by-side tables that make differences immediately visible.
- **Combine with earnings calendar timing.** Run a comprehensive analysis before earnings to establish expectations, then follow up with a post-earnings impact analysis to update your thesis.
- **Request specific metrics if you have a framework.** Asking "What's NVDA's ROIC, free cash flow yield, and revenue growth rate?" gets targeted data faster than a full report.
- **Use for position review.** Periodically run updated analysis on holdings to check whether the original investment thesis still holds.
- **Check data recency.** The skill notes data sources and dates in its output. For fast-moving situations, verify that the data reflects the most recent quarter.

---

## 8. Combining with Other Skills

| Workflow | How to Combine |
|----------|---------------|
| **Earnings-driven research** | Run Earnings Calendar to identify upcoming reports, then US Stock Analysis for pre-earnings thesis, then post-earnings impact analysis |
| **Screen-to-analysis pipeline** | Use FinViz Screener or CANSLIM Screener to find candidates, then US Stock Analysis for deep dives on the top picks |
| **Portfolio review cycle** | Use Portfolio Manager to pull current holdings, then run US Stock Analysis on each position to update buy/hold/sell ratings |
| **Technical confirmation** | After fundamental analysis identifies a candidate, use Technical Analyst (chart image skill) for detailed visual chart reading |
| **Position sizing** | After US Stock Analysis provides a buy recommendation with entry and stop levels, feed those into Position Sizer for risk-based share count calculation |

---

## 9. Troubleshooting

### Data seems outdated

**Cause:** WebSearch may return cached or older results for some metrics.

**Fix:** Ask Claude to search specifically for the most recent quarter: "Search for AAPL Q1 2026 earnings results" rather than "AAPL financials." Specifying the quarter and year improves data freshness.

### Missing technical indicators

**Cause:** Some technical data (exact RSI values, MACD histogram) may not be available from web search alone.

**Fix:** For precise technical readings, combine with the Technical Analyst skill using actual chart images, or specify "search TradingView AAPL RSI" to target technical data sources.

### Comparison misses a metric

**Cause:** Not all companies report the same metrics (e.g., subscription revenue vs product revenue).

**Fix:** Ask Claude to note which metrics are not directly comparable and provide the closest equivalent. Specifying "compare AAPL vs MSFT using P/E, PEG, EV/EBITDA, FCF yield, and revenue growth" ensures the exact metrics you want.

### Report is too long or too short

**Cause:** The skill defaults to comprehensive output for ambiguous requests.

**Fix:** Specify the analysis type explicitly. "Quick overview" produces a concise summary. "Comprehensive report" produces the full 10-section template. "Just the valuation section" gives you only what you need.

---

## 10. Reference

### Analysis Types

| Type | Trigger Phrases | Key Output |
|------|----------------|------------|
| **Basic** | "quick overview," "key metrics," "what's the price" | Price, market cap, P/E, recent news |
| **Fundamental** | "financials," "business quality," "is it overvalued" | Revenue trends, margins, debt, valuation ratios |
| **Technical** | "technical analysis," "trend," "support levels" | Moving averages, RSI, MACD, chart patterns |
| **Comprehensive** | "full report," "complete analysis," "should I invest" | 10-section report with Buy/Hold/Sell recommendation |

### Reference Knowledge Base

| File | When Loaded | Content |
|------|------------|---------|
| `references/fundamental-analysis.md` | Fundamental or comprehensive analysis | Business quality assessment, financial health analysis, valuation frameworks, risk assessment, red flags |
| `references/technical-analysis.md` | Technical or comprehensive analysis | Indicator definitions, chart patterns, support/resistance concepts, analysis workflow |
| `references/financial-metrics.md` | Any analysis requiring ratio definitions | All key metrics with formulas: profitability, valuation, growth, liquidity, leverage, efficiency, cash flow |
| `references/report-template.md` | Comprehensive report or comparison | Complete report structure, formatting guidelines, section templates, comparison format |

### Data Sources Used

| Data Type | Preferred Sources |
|-----------|------------------|
| Price and trading data | Yahoo Finance, Google Finance |
| Financial statements | SEC EDGAR (10-K, 10-Q), company IR pages |
| Analyst ratings | MarketWatch, Seeking Alpha, Bloomberg |
| Technical data | TradingView, StockCharts |
| News and developments | CNBC, Reuters, WSJ |
