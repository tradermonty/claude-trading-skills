---
name: us-stock-analysis
description: Comprehensive US stock analysis including fundamental analysis (financial metrics, business quality, valuation), technical analysis (indicators, chart patterns, support/resistance), stock comparisons, and investment report generation. Use when user requests analysis of US stock tickers (e.g., "analyze AAPL", "compare TSLA vs NVDA", "give me a report on Microsoft"), evaluation of financial metrics, technical chart analysis, or investment recommendations for American stocks.
---

# US Stock Analysis

## Overview

Perform comprehensive analysis of US stocks covering fundamental analysis (financials, business quality, valuation), technical analysis (indicators, trends, patterns), peer comparisons, and generate detailed investment reports. Fetch real-time market data via web search tools and apply structured analytical frameworks.

## Data Gathering

Use web search tools to fetch current market data. Required data points per analysis type:

| Data Category | Basic | Fundamental | Technical | Full Report |
|---------------|:-----:|:-----------:|:---------:|:-----------:|
| Price, volume, market cap | x | x | x | x |
| Financial statements (3-5yr) | | x | | x |
| Key ratios (P/E, EPS, margins) | x | x | | x |
| Analyst ratings & targets | | x | | x |
| Recent news & catalysts | x | x | | x |
| Peer/competitor data | | x | | x |
| Moving averages, RSI, MACD | | | x | x |

**Search Query Examples:**
- Price data: `"AAPL stock price today market cap 2024"`
- Financials: `"NVDA 10-Q Q3 2024 revenue earnings cash flow"`
- Valuation: `"MSFT P/E ratio PEG EV/EBITDA vs sector average"`
- Technical: `"TSLA 50-day 200-day moving average RSI MACD"`
- Peers: `"AAPL vs MSFT vs GOOGL revenue growth comparison 2024"`

**Data Validation Checkpoints:**
- Verify financial data is from the most recent reported quarter before proceeding
- Cross-check key metrics (revenue, EPS) across at least two sources
- Confirm price data is from the current trading session
- Flag any data older than 90 days as potentially stale

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

**Sample Output Format:**

```markdown
## AAPL — Apple Inc.
Consumer electronics and services company. Market leader in smartphones, PCs, and wearables.

| Metric | Value |
|--------|-------|
| Price | $178.52 |
| Market Cap | $2.78T |
| P/E (TTM) | 28.4 |
| EPS (TTM) | $6.29 |
| Revenue Growth (YoY) | +4.8% |
| Net Margin | 25.3% |
| 52-Week Range | $142.00 – $199.62 |
| YTD Return | +12.1% |

**Recent:** [1-2 sentence summary of key catalyst or news]
```

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

**Validation Before Output:**
- Confirm all financials are from the same reporting period
- Verify FCF and earnings are directionally consistent; flag divergences
- Check that peer comparisons use the same fiscal period

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

**Signal Validation Checklist:**
- [ ] At least 2 indicators confirm the signal direction
- [ ] Volume supports the move (rising on breakouts, declining on pullbacks)
- [ ] No price-indicator divergence present (or divergence is flagged)
- [ ] Key risk level (stop-loss) identified with specific price

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

- Use **tables** for all financial data and comparisons
- **Bold** key metrics and actionable findings
- Include data source and date for every metric cited
- Format currency consistently: $B (billions), $M (millions)
- Present both bull and bear perspectives with supporting data
- State assumptions and confidence level explicitly

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

| Type | Example |
|------|---------|
| Basic | "Quick overview of Microsoft stock", "Key metrics for Tesla" |
| Fundamental | "Is Amazon overvalued?", "Analyze NVDA's financials" |
| Technical | "Technical analysis of TSLA", "Support levels for AAPL" |
| Full Report | "Should I invest in Tesla? Detailed analysis" |
| Comparison | "Compare AAPL vs MSFT", "Tesla vs Nvidia — which is better?" |
