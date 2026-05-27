---
name: us-stock-analysis
description: Comprehensive US stock analysis including fundamental analysis (financial metrics, business quality, valuation), technical analysis (indicators, chart patterns, support/resistance), stock comparisons, and investment report generation. Use when user requests analysis of US stock tickers (e.g., "analyze AAPL", "compare TSLA vs NVDA", "give me a report on Microsoft"), evaluation of financial metrics, technical chart analysis, or investment recommendations for American stocks.
---

# US Stock Analysis

## Overview

Perform comprehensive analysis of US stocks covering fundamental analysis (financials, business quality, valuation), technical analysis (indicators, trends, patterns), peer comparisons, and generate detailed investment reports. Fetch real-time market data via web search tools and apply structured analytical frameworks.

## Data Sources

Always use web search tools to gather current market data:

**Primary Data to Fetch:**
1. **Current stock price and trading data** (price, volume, 52-week range)
2. **Financial statements** (income statement, balance sheet, cash flow)
3. **Key metrics** (P/E, EPS, revenue, margins, debt ratios)
4. **Analyst ratings and price targets**
5. **Recent news and developments**
6. **Peer/competitor data** (for comparisons)
7. **Technical data** (moving averages, RSI, MACD when available)

**Search Strategy:**
- Use ticker symbol + specific data needed (e.g., "AAPL financial metrics 2024")
- For comprehensive data: Search for earnings reports, investor presentations, or SEC filings
- For technical data: Search for "AAPL technical analysis" or use financial data sites
- Always verify data recency (prefer data from last quarter)

**Quality Sources:**
- Yahoo Finance, Google Finance, MarketWatch, Seeking Alpha, Bloomberg, CNBC
- Company investor relations pages
- SEC filings (10-K, 10-Q) for detailed financials
- TradingView, StockCharts for technical data

## Analysis Types

This skill supports four types of analysis. Determine which type(s) the user needs:

1. **Basic Stock Info** - Quick overview with key metrics
2. **Fundamental Analysis** - Deep dive into business, financials, valuation
3. **Technical Analysis** - Chart patterns, indicators, trend analysis
4. **Comprehensive Report** - Complete analysis combining all approaches

## Analysis Workflows

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

## Stock Comparison Analysis

**When to Use:** User asks to compare two or more stocks (e.g., "compare AAPL vs MSFT")

**Steps:**
1. **Gather data for all stocks:**
   - Follow data gathering steps for each ticker
   - Ensure comparable timeframes

2. **Read references/fundamental-analysis.md** and references/financial-metrics.md

3. **Create side-by-side comparison:**
   - Business models comparison
   - Financial metrics table (all key ratios)
   - Valuation metrics table
   - Growth rates comparison
   - Profitability comparison
   - Balance sheet strength

4. **Identify relative strengths:**
   - Where each company excels
   - Quantified advantages

5. **Technical comparison:**
   - Relative strength
   - Momentum comparison
   - Which is in better technical position

6. **Generate recommendation:**
   - Which stock is more attractive and why
   - Consider both fundamental and technical factors
   - Portfolio allocation suggestion
   - Risk-adjusted return assessment

**Output Format:** Follow "Comparison Report Structure" in references/report-template.md

## Output Guidelines

**General Principles:**
- Use tables for financial data and comparisons (easy to scan)
- Bold key metrics and findings
- Include data sources and dates
- Quantify whenever possible
- Present both bull and bear perspectives
- Be clear about assumptions and uncertainties

**Formatting:**
- **Headers** for clear section separation
- **Tables** for metrics, comparisons, historical data
- **Bullet points** for lists, factors, risks
- **Bold text** for key findings, important metrics
- **Percentages** for growth rates, returns, margins
- **Currency** formatted consistently ($B for billions, $M for millions)

**Tone:**
- Objective and balanced
- Acknowledge uncertainty
- Support claims with data
- Avoid hyperbole
- Present risks clearly

## Reference Files

Load these references as needed during analysis:

**references/technical-analysis.md**
- When: Performing technical analysis or interpreting indicators
- Contains: Indicator definitions, chart patterns, support/resistance concepts, analysis workflow

**references/fundamental-analysis.md**
- When: Performing fundamental analysis or business evaluation
- Contains: Business quality assessment, financial health analysis, valuation frameworks, risk assessment, red flags

**references/financial-metrics.md**
- When: Need definitions or calculation methods for financial ratios
- Contains: All key metrics with formulas (profitability, valuation, growth, liquidity, leverage, efficiency, cash flow)

**references/report-template.md**
- When: Creating comprehensive report or comparison
- Contains: Complete report structure, formatting guidelines, section templates, comparison format

## Example Queries

**Basic Info:**
- "What's the current price of AAPL?"
- "Give me key metrics for Tesla"
- "Quick overview of Microsoft stock"

**Fundamental:**
- "Analyze NVDA's financials"
- "Is Amazon overvalued?"
- "Evaluate Apple's business quality"
- "What's Google's debt situation?"

**Technical:**
- "Technical analysis of TSLA"
- "Is Netflix oversold?"
- "Show me support levels for AAPL"
- "What's the trend for AMD?"

**Comprehensive:**
- "Complete analysis of Microsoft"
- "Give me a full report on AAPL"
- "Should I invest in Tesla? Give me detailed analysis"

**Comparison:**
- "Compare AAPL vs MSFT"
- "Tesla vs Nvidia - which is better?"
- "Analyze Meta vs Google"

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `technical_validation` | `TechnicalValidation` | Chart-based setup quality assessment with pattern details |
| `scenario_analysis` | `ScenarioAnalysis` | Probability-weighted scenario set with trigger levels |

Schema: `schemas/json/technical_validation.json` (and sibling files for additional types above)
