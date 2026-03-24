---
name: market-news-analyst
description: "This skill should be used when analyzing recent market-moving news events and their impact on equity markets and commodities. Use this skill when the user requests analysis of major financial news from the past 10 days, wants to understand market reactions to monetary policy decisions (FOMC, ECB, BOJ), needs assessment of geopolitical events' impact on commodities, or requires comprehensive review of earnings announcements from mega-cap stocks. The skill automatically collects news using WebSearch/WebFetch tools and produces impact-ranked analysis reports. All analysis thinking and output are conducted in English."
---

# Market News Analyst

Analyze market-moving news from the past 10 days, score events by impact magnitude, and produce structured reports ranked by significance. Collect news via WebSearch/WebFetch, assess multi-asset reactions, and compare against historical patterns.

## Prerequisites

- **Tools:** WebSearch and WebFetch must be available
- **Output:** Conversational guidance; full report saved to `reports/` on request using template in `references/report_template.md`

## Analysis Workflow

### Step 1: Collect News (WebSearch/WebFetch)

Execute parallel WebSearch queries across six categories for the past 10 days:

| Category | Search Terms | Targets |
|----------|-------------|---------|
| Monetary Policy | "FOMC meeting", "Federal Reserve interest rate", "ECB policy decision", "Bank of Japan" | Rate decisions, forward guidance, inflation commentary |
| Economic Data | "CPI inflation report [month]", "jobs report NFP", "GDP data", "PPI producer prices" | Data releases, consensus surprises |
| Mega-Cap Earnings | "[Company] earnings [quarter]" for Apple, Microsoft, NVIDIA, Amazon, Tesla, Meta, Google | Results, guidance, market reactions |
| Geopolitical | "Middle East conflict oil prices", "Ukraine war", "US China tensions", "trade war tariffs" | Conflicts, sanctions, trade disputes |
| Commodities | "oil prices news", "gold prices", "OPEC meeting", "natural gas", "copper prices" | Supply disruptions, demand shifts |
| Corporate | "major M&A", "bank earnings", "bankruptcy", "credit rating downgrade" | Large events beyond mega-caps |

**Source priority:** Official (FederalReserve.gov, SEC.gov, BLS.gov) > Tier 1 (Bloomberg, Reuters, WSJ, FT) > Specialized (CNBC, MarketWatch, S&P Global Platts)

**For each news item, capture:** date/time, event type, source tier, headline, key details, market timing (pre-market/trading/after-hours), initial reaction.

**Filter:** Include only Tier 1 market-moving events with clear price impact. Exclude small-cap stock news, minor product updates, routine filings.

> **Validation:** Verify at least 3 sources confirm event details before proceeding. If WebSearch returns no results for a category, note the gap and continue with remaining categories.

### Step 2: Load Knowledge Base References

**Always load:**
- `references/market_event_patterns.md` -- historical reaction patterns
- `references/trusted_news_sources.md` -- source credibility tiers

**Load conditionally based on collected news:**

| News Type | Reference File | Focus Sections |
|-----------|---------------|----------------|
| Monetary policy | market_event_patterns.md | Central Bank Monetary Policy Events |
| Geopolitical events | geopolitical_commodity_correlations.md | Energy, Precious Metals, regional frameworks |
| Mega-cap earnings | corporate_news_impact.md | Company-specific sections, contagion patterns |
| Commodity news | geopolitical_commodity_correlations.md | Specific commodity sections |

Compare collected news against historical patterns to identify expected reactions, anomalies, magnitude assessment, and contagion expectations.

### Step 3: Score Impact Magnitude

Apply the scoring framework from `references/impact_scoring_framework.md` to each event:

```
Impact Score = (Price Impact Score x Breadth Multiplier) x Forward-Looking Modifier
```

Three dimensions:
1. **Price Impact** (Severe=10, Major=7, Moderate=4, Minor=2, Negligible=1) -- based on actual asset price movements across equities, commodities, bonds, currencies
2. **Breadth** (Systemic=3x, Cross-Asset=2x, Sector-Wide=1.5x, Stock-Specific=1x) -- how many markets/sectors affected
3. **Forward Significance** (Regime Change=x1.50, Trend Confirmation=x1.25, Isolated=x1.00, Contrary Signal=x0.75) -- future implications

Rank all events by score, highest first. See `references/impact_scoring_framework.md` for thresholds, examples, and detailed calculation guidance.

> **Validation:** Cross-check scores against at least 2 data sources for price movements. Flag any event where sources report conflicting magnitudes.

### Step 4: Analyze Market Reactions

For each event with Impact Score >5, analyze:

**Immediate reaction (intraday):** Direction, magnitude, timing, VIX movement.

**Multi-asset response:**
- Equities: Index performance, sector rotation, growth/value divergence
- Fixed income: Treasury yields (2Y/10Y/30Y), curve shape, credit spreads, TIPS breakevens
- Commodities: Energy, precious metals, base metals, agricultural (as relevant)
- Currencies: DXY, major pairs, safe havens (JPY, CHF), EM currencies
- Derivatives: VIX level, options activity, futures positioning

**Pattern comparison** against knowledge base -- classify each reaction as:
- **Consistent:** Matched historical pattern
- **Amplified:** Exceeded typical magnitude (investigate: positioning, sentiment, cumulative factors)
- **Dampened:** Less than expected (investigate: priced in, offsetting factors)
- **Inverse:** Opposite of expected (investigate: "good news is bad news" dynamics)

Flag anomalies: market shrugged off major news, overreacted to minor news, contagion failed, safe-haven correlations broke.

> **Validation:** If reaction data is unavailable or conflicting for an event, note the uncertainty explicitly rather than estimating.

### Step 5: Assess Correlation and Causation

When multiple events overlap in the 10-day window, classify their interaction:

- **Reinforcing:** Same direction, often non-linear combined impact (e.g., hawkish FOMC + hot CPI)
- **Offsetting:** Opposite impacts, muted net reaction -- identify dominant factor
- **Sequential:** One event primed reaction to next (path dependence)
- **Coincidental:** Unrelated timing -- note attribution uncertainty

For geopolitical events, trace commodity correlations using `references/geopolitical_commodity_correlations.md`: map conflict to supply risk, assess actual vs feared impact, determine duration (temporary spike vs sustained).

Trace transmission mechanisms: direct (news to price), indirect (news to economy to price), sentiment (risk appetite shift), feedback loops (selloff to margin calls to deeper selloff).

> **Validation:** Explicitly distinguish correlation from causation. Acknowledge when attribution is uncertain due to simultaneous factors.

### Step 6: Generate Report

Produce the structured Markdown report using the template in `references/report_template.md`.

Key sections: Executive Summary, Impact Rankings table, Detailed Event Analysis (per event), Thematic Synthesis, Commodity Deep Dive, Forward-Looking Implications, Data Sources.

**File naming:** `market_news_analysis_[START_DATE]_to_[END_DATE].md`

Save to `reports/` directory on user request.

> **Validation:** Before finalizing, verify all price movements cite specific percentages/basis points, all claims reference sources, and the report maintains consistent English throughout.

## Resources

| Reference File | Content |
|---------------|---------|
| `references/market_event_patterns.md` | Historical patterns: central banks, inflation, employment, GDP, geopolitics, earnings, credit events, case studies |
| `references/geopolitical_commodity_correlations.md` | Commodity correlations: energy, precious/base metals, agriculture, rare earths, regional frameworks |
| `references/corporate_news_impact.md` | Mega-cap frameworks: Magnificent 7, financials, healthcare, energy, consumer, industrials, contagion patterns |
| `references/trusted_news_sources.md` | Source tiers: official, financial news, specialized, research; credibility criteria, red flags |
| `references/impact_scoring_framework.md` | Scoring formula, price impact thresholds, breadth multipliers, forward-looking modifiers, examples |
| `references/report_template.md` | Full Markdown report template with all sections and quality standards |
