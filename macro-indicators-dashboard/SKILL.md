---
name: macro-indicators-dashboard
description: Generate comprehensive macroeconomic indicators dashboard with GDP, inflation, unemployment, interest rates, and other key economic metrics. Use when the user wants to assess overall economic conditions, monitor macro trends, or get a holistic view of the economy.
---

# Macro Indicators Dashboard

Generate a comprehensive dashboard of key macroeconomic indicators to assess overall economic health and identify trends. Aggregate data from multiple economic metrics including GDP, inflation, unemployment, interest rates, retail sales, and industrial production into a single unified view.

## When to Use This Skill

Use this skill when the user wants to:
- Get a holistic overview of current economic conditions
- Monitor key macroeconomic trends across multiple indicators
- Assess the economic backdrop for investment decisions
- Compare current economic data with historical trends
- Identify emerging economic inflection points
- Prepare for macroeconomic analysis or reports
- Understand the broader economic environment before making portfolio decisions

## Workflow

### Step 1: Gather Dashboard Parameters

Collect the following information from the user (use sensible defaults if not specified):

**Geographic Focus:**
- Primary country (default: United States)
- Additional countries for comparison (optional)

**Time Horizon:**
- Historical lookback period (default: 5 years for trend analysis)
- Most recent data point emphasis

**Indicators to Include:**
- Core indicators (always include): GDP, CPI, Unemployment, Interest Rates
- Optional indicators: Retail Sales, Industrial Production, Consumer Confidence, Housing Starts, Trade Balance
- User-specified priorities (flag 2-3 indicators as "key focus")

**Output Preferences:**
- Detail level: Summary (key metrics only) or Comprehensive (all available data points)
- Trend analysis: Yes/No (show YoY, QoQ, MoM changes)
- Market implications: Yes/No (interpret what the data means for markets)

### Step 2: Fetch Economic Indicators Data

Execute the data fetching script to retrieve current and historical data for all requested indicators:

```bash
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --country US \
  --indicators GDP,CPI,unemployment,retailSales,industrialProduction \
  --lookback-years 5 \
  --output macro_data.json
```

**Script Behavior:**
- Fetches latest available data for each indicator from FMP API
- Retrieves historical time series for trend analysis
- Calculates growth rates (YoY, QoQ, MoM where applicable)
- Handles missing data gracefully (reports gaps, uses most recent available)
- Saves raw data to JSON file for further analysis

**Error Handling:**
- If API rate limit reached, report which indicators were successfully fetched
- If specific indicator unavailable, continue with available data
- Alert user to any data staleness (e.g., GDP data that's >3 months old)

### Step 3: Analyze Indicator Trends

For each indicator, perform trend analysis:

**Calculate Changes:**
- Year-over-Year (YoY) change
- Quarter-over-Quarter (QoQ) change for quarterly data
- Month-over-Month (MoM) change for monthly data
- 5-year average for context

**Identify Trend Direction:**
- Accelerating (rate of change increasing)
- Decelerating (rate of change decreasing)
- Stable (minimal change)
- Inflection point (direction reversal)

**Assess Historical Context:**
- Compare current level to 5-year range (percentile)
- Identify if current reading is extreme (>90th or <10th percentile)
- Note proximity to key thresholds (e.g., unemployment near natural rate, inflation near Fed target)

### Step 4: Synthesize Economic Narrative

Integrate findings across all indicators to form coherent economic assessment:

**Growth Indicators (GDP, Retail Sales, Industrial Production):**
- Is the economy expanding, contracting, or stable?
- Which sectors are driving growth or weakness?
- Are there leading indicators of change (e.g., retail sales weakening before GDP)?

**Inflation Indicators (CPI, PPI if available):**
- Is inflation accelerating, decelerating, or stable?
- How does current inflation compare to central bank targets?
- Are there supply-side or demand-side pressures?

**Labor Market Indicators (Unemployment, Job Openings if available):**
- Is the labor market tight, balanced, or weak?
- Are unemployment trends consistent with GDP trends?
- Any signs of labor market inflection?

**Monetary Policy Indicators (Interest Rates, Fed Funds Rate):**
- What is the current policy stance (accommodative, neutral, restrictive)?
- How have rates changed recently?
- Are current rates consistent with inflation and growth trends?

**Cross-Indicator Consistency:**
- Are all indicators pointing in the same direction?
- Any contradictions (e.g., strong GDP but rising unemployment)?
- Which indicators are leading vs. lagging?

### Step 5: Assess Market Implications

Translate economic findings into market impact assessment:

**Equity Market Implications:**
- Growth trajectory support for equities (expanding = positive, contracting = negative)
- Inflation impact on valuations (high inflation = multiple compression)
- Sector rotation implications (e.g., cyclicals vs. defensives)
- Earnings outlook based on economic backdrop

**Fixed Income Implications:**
- Interest rate direction (inflation + growth → higher rates)
- Yield curve implications
- Credit spread outlook (recession risk → wider spreads)
- Duration positioning (rising rates = shorter duration)

**Monetary Policy Expectations:**
- Likely Fed/central bank response
- Rate hike/cut probability in next 6-12 months
- QE/QT implications

**Risk Assessment:**
- Recession probability (based on indicator configuration)
- Stagflation risk (high inflation + weak growth)
- Economic stability vs. volatility
- Tail risk indicators (extreme readings)

### Step 6: Generate Dashboard Report

Create comprehensive markdown report with the following structure:

#### Report Header:
```markdown
# Macroeconomic Indicators Dashboard
**Generated:** [Date/Time]
**Geographic Focus:** [Country]
**Analysis Period:** [Start Date] to [End Date]
**Key Focus:** [2-3 priority indicators]

---

## Executive Summary

[2-3 paragraph synthesis of economic conditions]

**Economic Growth:** [Expanding/Stable/Contracting + brief explanation]
**Inflation:** [Accelerating/Stable/Decelerating + brief explanation]
**Labor Market:** [Tight/Balanced/Weak + brief explanation]
**Monetary Policy:** [Accommodative/Neutral/Restrictive + brief explanation]

**Overall Assessment:** [Coherent 1-2 sentence economic narrative]

**Market Implications:** [Bull/Bear/Mixed + key drivers]

---
```

#### Core Indicators Section:

For each core indicator (GDP, CPI, Unemployment, Interest Rates), create detailed subsection:

```markdown
## [Indicator Name]

**Latest Reading:** [Value] ([Date])
**Previous:** [Value] ([Date])
**Change:** [+/- X.X%] ([Period])

**Trend Analysis:**
- YoY Change: [+/- X.X%]
- 5-Year Average: [Value]
- Current Percentile (5yr): [XXth percentile]
- Trend: [Accelerating/Decelerating/Stable/Inflection]

**Historical Context:**
[ASCII chart or table showing 5-year trend]

| Period | Value | YoY Change |
|--------|-------|------------|
| Latest | X.X% | +X.X% |
| -1Q | X.X% | +X.X% |
| -2Q | X.X% | +X.X% |
| -3Q | X.X% | +X.X% |
| -4Q | X.X% | +X.X% |

**Interpretation:**
[2-3 sentences explaining what this indicator reveals about the economy]

**Market Impact:** [Brief assessment of market implications]

---
```

#### Optional Indicators Section:

For optional indicators (Retail Sales, Industrial Production, etc.), use abbreviated format:

```markdown
## Additional Indicators

### Retail Sales
- **Latest:** $XXX.X billion (Month-over-Month: +X.X%)
- **Trend:** [Accelerating/Stable/Decelerating]
- **Implication:** [1 sentence]

### Industrial Production
- **Latest:** XXX.X index (Month-over-Month: +X.X%)
- **Trend:** [Accelerating/Stable/Decelerating]
- **Implication:** [1 sentence]

[Repeat for other optional indicators]

---
```

#### Cross-Indicator Analysis:

```markdown
## Cross-Indicator Analysis

**Indicator Alignment:**
- Growth indicators (GDP, Retail, Industrial): [Aligned/Mixed + direction]
- Inflation indicators: [Aligned/Mixed + direction]
- Labor indicators: [Aligned/Mixed + direction]
- Policy indicators: [Aligned/Mixed + direction]

**Leading Indicators:**
[Identify which indicators are changing ahead of others]

**Contradictions/Divergences:**
[Note any indicators moving in opposite directions + potential explanations]

**Historical Patterns:**
[Compare current configuration to past cycles, e.g., "Similar to 2018 late-cycle expansion"]

---
```

#### Market Implications Section:

```markdown
## Market Implications

### Equity Markets
**Outlook:** [Positive/Neutral/Negative]
- Growth trajectory: [Impact]
- Valuation pressure from inflation: [Impact]
- Sector rotation: [Recommendations]
- Earnings outlook: [Assessment]

### Fixed Income Markets
**Outlook:** [Positive/Neutral/Negative]
- Rate direction: [Up/Stable/Down + magnitude]
- Yield curve: [Steepening/Flattening/Inverting]
- Credit spreads: [Widening/Stable/Tightening]
- Duration positioning: [Longer/Neutral/Shorter]

### Monetary Policy Expectations
**Next 6 Months:** [Rate hike/hold/cut + probability]
**Next 12 Months:** [Cumulative rate change estimate]
**QE/QT:** [Expansion/Stable/Contraction]

### Risk Assessment
**Recession Probability (12mo):** [XX%]
**Key Risks:**
- [Risk 1]
- [Risk 2]
- [Risk 3]

**Tail Risks:** [Extreme scenarios to monitor]

---
```

#### Reference Data Section:

```markdown
## Reference Data

**Data Sources:**
- Financial Modeling Prep (FMP) API
- Latest data as of: [Date]

**Indicator Definitions:**
- **GDP:** Gross Domestic Product, annualized real growth rate
- **CPI:** Consumer Price Index, year-over-year change
- **Unemployment:** Unemployment rate as % of labor force
- **Interest Rates:** [Specify rate type, e.g., Federal Funds Rate]
- [Define other indicators included]

**Methodology:**
- Historical lookback: [X years]
- Trend calculations: [YoY/QoQ/MoM as applicable]
- Percentile calculations: Based on [X-year] rolling window

**Limitations:**
- Data subject to revisions (especially GDP)
- Indicator availability varies by country
- Some indicators released with lag (GDP ~1 month lag)

---
```

#### Save Output:

Save report as: `macro_indicators_dashboard_[COUNTRY]_[DATE].md`

Example: `macro_indicators_dashboard_US_2025-11-09.md`

### Step 7: Provide Actionable Insights

After generating the dashboard, provide user with:

**Immediate Takeaways:**
- 3 most important observations from the data
- Biggest change since last report
- Key metrics to watch in coming weeks

**Suggested Actions:**
- Portfolio positioning recommendations based on macro outlook
- Sectors or asset classes to overweight/underweight
- Risk management considerations
- Timing for next dashboard update (suggest monthly or quarterly)

**Follow-up Analysis:**
- Suggest complementary skills to use (e.g., "Run Sector Analyst on cyclical sectors given strong GDP growth")
- Identify specific companies/sectors most exposed to macro trends
- Recommend deeper dives into specific indicators showing unusual patterns

## Integration with Other Skills

**Complementary Skills:**
- **Economic Calendar Fetcher**: Check upcoming data releases that will update this dashboard
- **Market News Analyst**: Understand recent events driving economic changes
- **Sector Analyst**: Identify sectors best positioned for current macro environment
- **US Market Bubble Detector**: Cross-reference macro conditions with bubble indicators
- **Technical Analyst**: Confirm macro view with market price action

**Workflow Combinations:**

**Monthly Macro Review:**
1. Run Macro Indicators Dashboard
2. Run Economic Calendar Fetcher for next 30 days
3. Run Sector Analyst to identify rotation opportunities
4. Update portfolio allocations

**Pre-FOMC Analysis:**
1. Run Macro Indicators Dashboard
2. Review inflation and employment indicators
3. Formulate Fed policy expectations
4. Position portfolio ahead of meeting

**Recession Watch:**
1. Run Macro Indicators Dashboard monthly
2. Track leading indicators (Retail Sales, Industrial Production)
3. Monitor yield curve via dashboard
4. Run US Market Bubble Detector for confirmation
5. Adjust portfolio defensively if recession signals converge

## Key Indicators Explained

### Core Indicators

**GDP (Gross Domestic Product):**
- Measures total economic output
- Released quarterly with ~1 month lag
- Real GDP (inflation-adjusted) most relevant
- Growth >3% = strong, 2-3% = moderate, <2% = weak, <0% = recession

**CPI (Consumer Price Index):**
- Measures inflation at consumer level
- Released monthly
- Fed targets 2% annual inflation
- >3% = above target (hawkish), <2% = below target (dovish)

**Unemployment Rate:**
- % of labor force actively seeking work
- Released monthly
- Natural rate ~4-5%
- <4% = very tight labor market, >6% = weak labor market

**Interest Rates (Federal Funds Rate):**
- Short-term rate controlled by Fed
- Changed at FOMC meetings (8 per year)
- Current rate vs. neutral rate (~2.5%) indicates policy stance
- Higher rates = restrictive, lower rates = accommodative

### Optional Indicators

**Retail Sales:**
- Consumer spending, ~70% of GDP
- Released monthly
- Leading indicator for GDP
- Strong retail sales often precede strong GDP

**Industrial Production:**
- Manufacturing, mining, utilities output
- Released monthly
- Coincident indicator for economic activity
- Sensitive to global trade and investment cycles

**Consumer Confidence:**
- Survey-based measure of sentiment
- Released monthly
- Leading indicator for consumer spending
- High confidence → future spending increase

**Housing Starts:**
- New residential construction
- Released monthly
- Leading indicator for economic activity
- Sensitive to interest rates and credit conditions

## Important Notes

### Data Availability

- **FMP API Tier:** Free tier (250 requests/day) sufficient for most use cases
- **Update Frequency:**
  - Monthly indicators (CPI, Unemployment, Retail Sales): Update monthly
  - Quarterly indicators (GDP): Update quarterly
  - Daily indicators (Interest Rates, Treasury Yields): Update daily
- **Data Lag:** Most indicators released 2-4 weeks after period end; GDP released ~1 month after quarter end

### Limitations

- Economic data subject to revisions (GDP often revised 2-3 times)
- Different indicators on different release schedules (dashboard shows point-in-time snapshot)
- FMP API may not have all indicators for all countries
- Some indicators (e.g., Consumer Confidence) may require premium API tier

### Best Practices

- **Update Frequency:** Run dashboard monthly for most users, weekly for active macro traders
- **Focus Indicators:** Prioritize 2-3 indicators most relevant to user's investment strategy
- **Context Matters:** Always interpret indicators in context of economic cycle and recent events
- **Combine with News:** Use Market News Analyst skill to understand drivers of economic changes
- **Verify Data:** Cross-reference unusual readings with multiple sources
- **Revisions:** Note when historical data changes due to revisions

### Interpretation Guidelines

**Expansion Phase Indicators:**
- Rising GDP, low unemployment, moderate inflation, rising interest rates
- Equity bullish, duration bearish, credit spreads tight

**Late-Cycle Indicators:**
- Slowing GDP, very low unemployment, rising inflation, high interest rates
- Equity neutral, inflation assets bullish, prepare for rotation

**Recession Indicators:**
- Negative GDP, rising unemployment, falling inflation, falling interest rates
- Equity bearish, duration bullish, credit spreads wide, defensives outperform

**Early Recovery Indicators:**
- Rising GDP from low base, high unemployment (lagging), low inflation, low interest rates
- Equity bullish (especially cyclicals), duration neutral, credit spreads tightening

## Resources

**Reference Materials:**
- `references/indicators_guide.md`: Detailed explanation of each economic indicator
- `references/interpretation_framework.md`: How to interpret indicator combinations
- `references/market_impacts.md`: Historical relationship between indicators and asset class returns
- `references/economic_cycles.md`: Economic cycle patterns and indicator behavior

**Helper Scripts:**
- `scripts/fetch_macro_data.py`: Fetch economic indicators from FMP API
- `scripts/calculate_trends.py`: Calculate growth rates and trends (optional, can be integrated into main script)
- `scripts/generate_dashboard.py`: Generate formatted dashboard report (optional, can be done in main workflow)

**Assets:**
- `assets/dashboard_template.md`: Markdown template for dashboard output

## Example Usage

**Basic Usage:**
```
User: "Give me a macro indicators dashboard for the US"

Claude: [Runs fetch_macro_data.py with default parameters, generates comprehensive dashboard with GDP, CPI, Unemployment, Interest Rates, Retail Sales, and Industrial Production]
```

**Focused Analysis:**
```
User: "I want to see inflation and labor market indicators to assess Fed policy"

Claude: [Generates dashboard focused on CPI, PPI, Unemployment, Job Openings, and Interest Rates with detailed Fed policy implications]
```

**Comparative Analysis:**
```
User: "Compare US and EU macro conditions"

Claude: [Generates side-by-side dashboard for US and Eurozone, highlighting divergences]
```

**Historical Context:**
```
User: "Show me macro dashboard with 10-year historical context"

Claude: [Generates dashboard with extended lookback, identifies current position in economic cycle]
```
