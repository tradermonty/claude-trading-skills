---
name: market-environment-analysis
description: "Comprehensive market environment analysis and reporting tool. Analyzes global markets including US, European, Asian markets, forex, commodities, and economic indicators. Provides risk-on/risk-off assessment, sector analysis, and technical indicator interpretation. Use when asked for market analysis, market environment, global markets, trading environment, market conditions, investment climate, market sentiment, forex analysis, stock market analysis, 相場環境, 市場分析, マーケット状況, 投資環境."
---

# Market Environment Analysis

Analyze global market conditions and generate professional market environment reports.

## When to Use

- Comprehensive overview of global market conditions
- Pre-trade or pre-investment market assessment
- Daily/weekly market briefings
- Risk-on/risk-off sentiment evaluation
- Inter-market correlation and sector rotation analysis

## Prerequisites

- **WebSearch access**: Required for fetching real-time market data
- **No API keys required**: Uses web search for all data collection
- **Optional**: Economic calendar data for event-driven analysis

## Core Workflow

### 1. Data Collection

Collect latest market data using web_search. Run these queries:

```
web_search("S&P 500 NASDAQ Dow Jones today market close")
web_search("Nikkei 225 Shanghai Composite Hang Seng index today")
web_search("USD JPY EUR USD forex rates today")
web_search("WTI crude oil gold silver price today")
web_search("US Treasury yield 2 year 10 year today")
web_search("VIX index today")
```

**Validation checkpoint**: Verify all data points have timestamps within the last trading session. If any index returns stale data (>24h old on a trading day), re-query with the specific index name and "latest price".

### 2. Market Environment Assessment

Evaluate from collected data:
- **Trend Direction**: Uptrend/Downtrend/Range-bound based on index levels vs. key moving averages
- **Risk Sentiment**: Risk-on (equities up, yields up, VIX low) or Risk-off (bonds bid, gold up, VIX elevated)
- **Volatility Regime**: VIX <15 low, 15-20 normal, 20-30 elevated, >30 high anxiety
- **Sector Rotation**: Identify where capital is flowing (cyclicals vs. defensives)

**Validation checkpoint**: Cross-check sentiment signals. If equity indices and VIX both rise, flag the divergence and investigate catalysts before proceeding.

### 3. Report Generation

Generate report using `python scripts/market_utils.py` for formatting, then structure as:

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

Save to `reports/market_environment_<date>.md`.

## Script Usage

### market_utils.py

```bash
python scripts/market_utils.py
```

Available functions:
- `format_market_report_header()` - Create formatted report header
- `get_market_session_times()` - Check trading hours for major exchanges
- `categorize_volatility(vix)` - Classify VIX into regime categories
- `format_percentage_change(value)` - Format price changes consistently

## Reference Documentation

### Key Indicators

Load `references/indicators.md` for:
- Important support/resistance levels for each index
- Technical analysis key points
- Sector-specific focus areas

### Analysis Patterns

Load `references/analysis_patterns.md` for:
- Risk-on/Risk-off classification criteria
- Economic indicator interpretation frameworks
- Inter-market correlation matrices
- Seasonality and market anomalies

## Output Examples

### Quick Summary
```
📊 Market Summary [2025/01/15 14:00]
━━━━━━━━━━━━━━━━━━━━━
【US】S&P 500: 5,123.45 (+0.45%)
【JP】Nikkei 225: 38,456.78 (-0.23%)
【FX】USD/JPY: 149.85 (↑0.15)
【VIX】16.2 (Normal range)

⚡ Key Events
- Japan GDP Flash
- US Employment Report

📈 Environment: Risk-On Continues
```

### Detailed Analysis

Structure as:
1. Current market phase (Bullish/Bearish/Neutral)
2. Short-term direction (1-5 days outlook)
3. Risk events to monitor
4. Recommended position adjustments

## Economic Calendar Priority

Categorize upcoming events by market impact:
- **Critical**: FOMC, NFP, CPI
- **Important**: GDP, Retail Sales, PMI
- **Reference**: Minor releases, regional data

## Data Source Priority

1. Official releases (Central banks, Government statistics)
2. Major financial media (Bloomberg, Reuters)
3. Broker reports
4. Analyst consensus estimates

## Customization

Adjust analysis depth based on user's investment style:
- **Day Traders**: Intraday charts, order flow focus
- **Swing Traders**: Daily/weekly technicals emphasis
- **Long-term Investors**: Fundamentals, macro economics focus
- **Forex Traders**: Currency correlations, interest rate differentials
- **Options Traders**: Volatility analysis, Greeks monitoring

## Resources

- `references/indicators.md` - Key market indicators and interpretation guides
- `references/analysis_patterns.md` - Risk-on/risk-off criteria and inter-market correlations
- `scripts/market_utils.py` - Utility functions for report formatting and market status
