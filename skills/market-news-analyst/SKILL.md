---
name: market-news-analyst
description: This skill should be used when analyzing recent market-moving news events and their impact on equity markets and commodities. Use this skill when the user requests analysis of major financial news from the past 10 days, wants to understand market reactions to monetary policy decisions (FOMC, ECB, BOJ), needs assessment of geopolitical events' impact on commodities, or requires comprehensive review of earnings announcements from mega-cap stocks. The skill automatically collects news using WebSearch/WebFetch tools and produces impact-ranked analysis reports. All analysis thinking and output are conducted in English.
---

# Market News Analyst

## Overview

This skill enables comprehensive analysis of market-moving news events from the past 10 days, focusing on their impact on US equity markets and commodities. The skill automatically collects news from trusted sources using WebSearch and WebFetch tools, evaluates market impact magnitude, analyzes actual market reactions, and produces structured English reports ranked by market impact significance.

## Prerequisites

- **Tools:** WebSearch and WebFetch tools must be available for news collection
- **API Keys:** None required (uses built-in web search capabilities)
- **Knowledge:** Familiarity with financial markets terminology is helpful but not required

## Output

This skill produces **conversational guidance** during the analysis session. When the full workflow is executed, Claude generates a comprehensive Markdown report (see Step 6 for format) that can be saved to the `reports/` directory upon user request. No files are generated automatically; output is presented in the conversation.

## When to Use This Skill

Use this skill when:
- User requests analysis of recent major market news (past 10 days)
- User wants to understand market reactions to specific events (FOMC decisions, earnings, geopolitical)
- User needs comprehensive market news summary with impact assessment
- User asks about correlations between news events and commodity price movements
- User requests analysis of how central bank policy announcements affected markets

Example user requests:
- "Analyze the major market news from the past 10 days"
- "How did the latest FOMC decision impact the market?"
- "What were the most important market-moving events this week?"
- "Analyze recent geopolitical news and commodity price reactions"
- "Review mega-cap tech earnings and their market impact"

## Analysis Workflow

Follow this structured 6-step workflow when analyzing market news:

### Step 1: News Collection via WebSearch/WebFetch

**Objective:** Gather comprehensive news from the past 10 days covering major market-moving events.

**Search Strategy:**

Execute parallel WebSearch queries covering different news categories:

**Monetary Policy:**
- Search: "FOMC meeting past 10 days", "Federal Reserve interest rate", "ECB policy decision", "Bank of Japan"
- Target: Central bank decisions, forward guidance changes, inflation commentary

**Inflation/Economic Data:**
- Search: "CPI inflation report [current month]", "jobs report NFP", "GDP data", "PPI producer prices"
- Target: Major economic data releases and surprises

**Mega-Cap Earnings:**
- Search: "Apple earnings [current quarter]", "Microsoft earnings", "NVIDIA earnings", "Amazon earnings", "Tesla earnings", "Meta earnings", "Google earnings"
- Target: Results, guidance, market reactions for largest companies

**Geopolitical Events:**
- Search: "Middle East conflict oil prices", "Ukraine war", "US China tensions", "trade war tariffs"
- Target: Conflicts, sanctions, trade disputes affecting markets

**Commodity Markets:**
- Search: "oil prices news past week", "gold prices", "OPEC meeting", "natural gas prices", "copper prices"
- Target: Supply disruptions, demand shifts, price movements

**Corporate News:**
- Search: "major M&A announcement", "bank earnings", "tech sector news", "bankruptcy", "credit rating downgrade"
- Target: Large corporate events beyond mega-caps

**Recommended News Sources (Priority Order):**
1. Official sources: FederalReserve.gov, SEC.gov (EDGAR), Treasury.gov, BLS.gov
2. Tier 1 financial news: Bloomberg, Reuters, Wall Street Journal, Financial Times
3. Specialized: CNBC (real-time), MarketWatch (summaries), S&P Global Platts (commodities)

**Search Execution:**
- Use WebSearch for broad topic searches
- Use WebFetch for specific URLs from official sources or major news outlets
- Collect publication dates to ensure news is within 10-day window
- Capture: Event date, source, headline, key details, market context (pre-market, trading hours, after-hours)

**Filtering Criteria:**
- Focus on Tier 1 market-moving events (see references/market_event_patterns.md)
- Prioritize news with clear market impact (price moves, volume spikes)
- Exclude: Stock-specific small-cap news, minor product updates, routine filings

Think in English throughout collection process. Document each significant news item with:
- Date and time
- Event type (monetary policy, earnings, geopolitical, etc.)
- Source reliability tier
- Initial market reaction (if observable)

### Step 2: Load Knowledge Base References

**Objective:** Access domain expertise to inform impact assessment.

Load relevant reference files based on collected news types:

**Always Load:**
- `references/market_event_patterns.md` - Comprehensive patterns for all major event types
- `references/trusted_news_sources.md` - Source credibility assessment

**Conditionally Load (Based on News Collected):**

If **monetary policy news** found:
- Focus on: market_event_patterns.md → Central Bank Monetary Policy Events section
- Key frameworks: Interest rate hike/cut reactions, QE/QT impacts, hawkish/dovish tone

If **geopolitical events** found:
- Load: `references/geopolitical_commodity_correlations.md`
- Focus on: Energy Commodities, Precious Metals, regional frameworks matching event

If **mega-cap earnings** found:
- Load: `references/corporate_news_impact.md`
- Focus on: Specific company sections, sector contagion patterns

If **commodity news** found:
- Load: `references/geopolitical_commodity_correlations.md`
- Focus on: Specific commodity sections (Oil, Gold, Copper, etc.)

**Knowledge Integration:**
Compare collected news against historical patterns to:
- Predict expected market reactions
- Identify anomalies (market reacted differently than historical pattern)
- Assess whether reaction was typical magnitude or outsized
- Determine if contagion occurred as expected

### Step 3: Impact Magnitude Assessment

**Objective:** Rank each news event by market impact significance.

**Impact Assessment Framework:**

For each news item, evaluate across three dimensions: Read `references/impact_assessment_framework.md` (section "Step 3 detail: Impact Assessment Framework") when scoring events. It holds the three dimensions (asset price impact, breadth, forward-looking significance) with their thresholds.

**Impact Score Calculation:**

```
Impact Score = (Price Impact Score × Breadth Multiplier) + Forward-Looking Modifier

Price Impact Score:
- Severe: 10 points
- Major: 7 points
- Moderate: 4 points
- Minor: 2 points
- Negligible: 1 point
```

Read `references/impact_assessment_framework.md` (section "Step 3 detail: Example Calculations") for worked impact score examples (FOMC, NVIDIA earnings, geopolitical flare-up, single stock).

**Ranking:**
After scoring all news items, rank from highest to lowest impact score. This determines report ordering.

### Step 4: Market Reaction Analysis

**Objective:** Analyze how markets actually responded to each event.

For each significant news item (Impact Score >5), conduct detailed reaction analysis:

**Immediate Reaction (Intraday):**
- Direction: Positive, negative, mixed
- Magnitude: Align with price impact categories
- Timing: Pre-market, during trading, after-hours
- Volatility: VIX movement, bid-ask spreads

**Multi-Asset Response:**

**Equities:**
- Index performance (S&P 500, Nasdaq, Dow, Russell 2000)
- Sector rotation (which sectors outperformed/underperformed)
- Individual stock moves (mega-caps, relevant companies)
- Growth vs Value, Large vs Small Cap divergences

**Fixed Income:**
- Treasury yields (2Y, 10Y, 30Y)
- Yield curve shape (steepening, flattening, inversion)
- Credit spreads (IG, HY)
- TIPS breakevens (inflation expectations)

**Commodities:**
- Energy: Oil (WTI, Brent), Natural Gas
- Precious Metals: Gold, Silver
- Base Metals: Copper, Aluminum (if relevant)
- Agricultural: Wheat, Corn, Soybeans (if relevant)

**Currencies:**
- USD Index (DXY)
- EUR/USD, USD/JPY, GBP/USD
- Emerging market currencies
- Safe havens (JPY, CHF)

**Derivatives:**
- VIX (volatility index)
- Options activity (put/call ratio, unusual volume)
- Futures positioning

**Pattern Comparison:**

Compare observed reaction against expected pattern from knowledge base:

- **Consistent:** Reaction matched historical pattern
  - Example: Fed hike → Tech stocks down, USD up (as expected)

- **Amplified:** Reaction exceeded typical pattern
  - Example: Inflation print +0.3% above consensus → Selloff 2x typical
  - Investigate: Positioning, sentiment, cumulative factors

- **Dampened:** Reaction less than historical pattern
  - Example: Geopolitical event → Oil barely moved
  - Investigate: Already priced in, other offsetting factors

- **Inverse:** Reaction opposite of historical pattern
  - Example: Good news ignored, bad news rallied
  - Investigate: "Good news is bad news" dynamics, Fed pivot hopes

**Anomaly Identification:**

Flag reactions that deviate significantly from patterns:
- Market shrugged off typically market-moving news
- Overreaction to typically minor news
- Contagion failed to spread as expected
- Safe havens didn't work (correlations broke)

**Sentiment Indicators:**

- Risk-On vs Risk-Off: Which regime dominated
- Positioning: Evidence of crowded trades unwinding
- Momentum: Follow-through in subsequent sessions or reversal

### Step 5: Correlation and Causation Assessment

**Objective:** Distinguish direct impacts from coincidental timing.

Read `references/correlation_causation_assessment.md` when separating direct impacts from coincidental timing. It holds multi-event analysis, geopolitical-commodity correlations, transmission mechanisms and feedback loops.

### Step 6: Report Generation

**Objective:** Create structured English Markdown report ranked by market impact.

**Report Structure:** Read `references/report_template.md` when writing the final report. It holds the full Markdown report structure.

**File Naming Convention:**
`market_news_analysis_[START_DATE]_to_[END_DATE].md`

Example: `market_news_analysis_2024-10-25_to_2024-11-03.md`

**Report Quality Standards:**
- Objective, fact-based analysis (no speculation beyond probability-weighted scenarios)
- Quantify price movements with specific percentages
- Cite sources for major claims
- Distinguish between correlation and causation
- Acknowledge uncertainty when attributing market moves to specific news
- Use proper financial terminology
- Maintain consistent English throughout

## Key Analysis Principles

When conducting market news analysis:

1. **Impact Over Noise:** Focus on truly market-moving news, filter out minor events
2. **Multi-Asset Perspective:** Analyze across equities, bonds, commodities, currencies to understand full impact
3. **Pattern Recognition:** Compare against historical precedents while noting unique aspects
4. **Causation Discipline:** Be rigorous about attributing market moves to specific news vs coincidental timing
5. **Forward-Looking:** Emphasize implications for future market behavior, not just backward-looking description
6. **Objectivity:** Separate market reaction (what happened) from personal market view (what should happen)
7. **Quantification:** Use specific numbers (%, bps) rather than vague terms ("significant," "large")
8. **Source Credibility:** Weight official sources and Tier 1 news over rumors and unverified reports
9. **Breadth Analysis:** Individual stock moves only significant if mega-cap or systemic signal
10. **English Consistency:** All thinking, analysis, and output in English for consistency

## Common Pitfalls to Avoid

**Over-Attribution:**
- Not every market move is news-driven (technicals, flows, month-end rebalancing exist)
- Acknowledge when attribution is uncertain

**Recency Bias:**
- Latest news isn't always most important
- Rank by actual impact, not chronological order

**Hindsight Bias:**
- Distinguish "obvious in retrospect" from "surprising at the time"
- Note consensus expectations vs actual outcomes

**Single-Factor Analysis:**
- Markets respond to multiple factors simultaneously
- Acknowledge interaction effects

**Ignoring Magnitude:**
- A "hot" CPI that's 0.1% above consensus is different from 0.5% above
- Quantify surprise factor

## Resources

Read `references/reference_index.md` for a description of what each reference file covers.

## Important Notes

- All analysis thinking must be conducted in English
- All output Markdown files must be in English
- Use WebSearch and WebFetch tools to collect news automatically
- Focus on trusted news sources as defined in references
- Rank events by impact score (price impact × breadth × forward significance)
- Target analysis period: Past 10 days from current date
- Emphasize US equity markets and commodities as primary analysis subjects
- FOMC and other central bank policy decisions receive highest priority analysis
- Distinguish between correlation and causation rigorously
- Quantify all market reactions with specific percentages
- Load appropriate reference files based on news types collected
- Generate comprehensive reports ranked by market impact (highest impact first)
