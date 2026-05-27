---
layout: default
title: "Market Environment Analysis"
grand_parent: English
parent: Skill Guides
nav_order: 39
lang_peer: /ja/skills/market-environment-analysis/
permalink: /en/skills/market-environment-analysis/
---

# Market Environment Analysis
{: .no_toc }

Comprehensive market environment analysis and reporting tool. Analyzes global markets including US, European, Asian markets, forex, commodities, and economic indicators. Provides risk-on/risk-off assessment, sector analysis, and technical indicator interpretation. Triggers on keywords like market analysis, market environment, global markets, trading environment, market conditions, investment climate, market sentiment, forex analysis, stock market analysis, 相場環境, 市場分析, マーケット状況, 投資環境.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/market-environment-analysis.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/market-environment-analysis){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Market Environment Analysis

---

## 2. When to Use

- When you need a comprehensive overview of global market conditions
- Before making trading or investment decisions
- For daily/weekly market briefings
- When assessing risk-on/risk-off sentiment
- For understanding inter-market correlations and sector rotation
- When preparing market reports for clients or personal records

---

## 3. Prerequisites

- **WebSearch access**: Required for fetching real-time market data
- **No API keys required**: This skill uses web search for data collection
- **Optional**: Economic calendar data for event-driven analysis

---

## 4. Quick Start

```bash
1. Executive Summary (3-5 key points)
2. Global Market Overview
   - US Markets
   - Asian Markets
   - European Markets
3. Forex & Commodities Trends
4. Key Events & Economic Indicators
5. Risk Factor Analysis
6. Investment Strategy Implications
```

---

## 5. Workflow

### 1. Initial Data Collection
Collect latest market data using web_search tool:
1. Major stock indices (S&P 500, NASDAQ, Dow, Nikkei 225, Shanghai Composite, Hang Seng)
2. Forex rates (USD/JPY, EUR/USD, major currency pairs)
3. Commodity prices (WTI crude, Gold, Silver)
4. US Treasury yields (2-year, 10-year, 30-year)
5. VIX index (Fear gauge)
6. Market trading status (open/close/current values)

### 2. Market Environment Assessment
Evaluate the following from collected data:
- **Trend Direction**: Uptrend/Downtrend/Range-bound
- **Risk Sentiment**: Risk-on/Risk-off
- **Volatility Status**: Market anxiety level from VIX
- **Sector Rotation**: Where capital is flowing

### 3. Report Structure

#### Standard Report Format:
```
1. Executive Summary (3-5 key points)
2. Global Market Overview
   - US Markets
   - Asian Markets
   - European Markets
3. Forex & Commodities Trends
4. Key Events & Economic Indicators
5. Risk Factor Analysis
6. Investment Strategy Implications
```

---

## 6. Resources

**References:**

- `skills/market-environment-analysis/references/analysis_patterns.md`
- `skills/market-environment-analysis/references/indicators.md`

**Scripts:**

- `skills/market-environment-analysis/scripts/market_utils.py`
