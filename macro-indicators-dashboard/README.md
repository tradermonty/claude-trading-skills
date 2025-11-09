# Macro Indicators Dashboard

Generate comprehensive macroeconomic indicators dashboard with GDP, inflation, unemployment, interest rates, and other key economic metrics to assess overall economic health and identify market trends.

## Overview

The Macro Indicators Dashboard skill aggregates multiple economic indicators into a single unified view, providing investors and traders with a holistic assessment of current economic conditions. By analyzing GDP, CPI, unemployment, interest rates, retail sales, and industrial production together, this skill helps identify the current phase of the economic cycle and provides actionable market implications.

## Key Features

### 📊 Multi-Indicator Analysis
- Fetches and analyzes 5+ core economic indicators simultaneously
- Provides historical context (5-year lookback by default)
- Calculates trends (YoY, QoQ, MoM changes)
- Identifies inflection points and accelerating/decelerating trends

### 🔄 Cross-Indicator Synthesis
- Evaluates consistency across growth, inflation, and labor indicators
- Identifies leading vs. lagging indicators
- Detects contradictions (e.g., strong GDP but rising unemployment)
- Compares current configuration to historical economic cycles

### 📈 Market Implications Assessment
- Translates economic data into equity market outlook
- Provides fixed income positioning guidance
- Forecasts monetary policy expectations
- Assesses recession probability and tail risks

### 🎯 Economic Cycle Identification
- Determines current phase: Early Expansion, Mid-Expansion, Late Expansion, or Recession
- Provides sector rotation recommendations
- Suggests asset allocation adjustments
- Highlights key risks for each phase

## Supported Economic Indicators

| Indicator | Description | Frequency | Importance |
|-----------|-------------|-----------|------------|
| **GDP** | Gross Domestic Product growth rate | Quarterly | ⭐⭐⭐⭐⭐ Core |
| **CPI** | Consumer Price Index (inflation) | Monthly | ⭐⭐⭐⭐⭐ Core |
| **Unemployment** | Unemployment rate | Monthly | ⭐⭐⭐⭐⭐ Core |
| **Retail Sales** | Consumer spending on goods | Monthly | ⭐⭐⭐⭐ Leading |
| **Industrial Production** | Manufacturing, mining, utilities output | Monthly | ⭐⭐⭐⭐ Coincident |
| **Consumer Confidence** | Consumer sentiment survey | Monthly | ⭐⭐⭐ Leading |
| **Interest Rates** | Federal Funds Rate (derived from calendar) | Daily | ⭐⭐⭐⭐⭐ Core |

## Installation

### Prerequisites
- Python 3.7 or higher
- FMP API key (free tier sufficient)

### API Key Setup

```bash
# Set environment variable (recommended)
export FMP_API_KEY=your_fmp_api_key_here

# Or provide via command-line argument
python3 scripts/fetch_macro_data.py --api-key YOUR_KEY
```

### FMP API Free Tier
- **Requests per day:** 250
- **Cost:** Free
- **Sufficient for:** Daily or weekly dashboard updates
- **Sign up:** https://site.financialmodelingprep.com/developer/docs

## Usage

### Basic Usage

Fetch default indicators (GDP, CPI, unemployment, retail sales, industrial production):

```bash
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py
```

Output saved to: `macro_data.json`

### Custom Indicators

Specify which indicators to fetch:

```bash
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --indicators GDP,CPI,unemployment
```

### Custom Output File

```bash
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --output my_macro_dashboard.json
```

### Country Selection

```bash
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --country US
```

### Complete Example

```bash
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --indicators GDP,CPI,unemployment,retailSales,industrialProduction \
  --country US \
  --lookback-years 5 \
  --output macro_data_2025-11-09.json
```

## Output Format

The script generates a JSON file with the following structure:

```json
{
  "metadata": {
    "generated_at": "2025-11-09T14:30:00",
    "country": "US",
    "indicators_requested": ["GDP", "CPI", "unemployment"],
    "indicators_fetched": ["GDP", "CPI", "unemployment"]
  },
  "indicators": {
    "GDP": {
      "metadata": {
        "name": "GDP",
        "display_name": "Gross Domestic Product",
        "unit": "%",
        "frequency": "quarterly",
        "description": "Real GDP growth rate (annualized)"
      },
      "analysis": {
        "available": true,
        "latest": {
          "value": 2.8,
          "date": "2025-09-30"
        },
        "previous": {
          "value": 3.0,
          "date": "2025-06-30"
        },
        "changes": {
          "yoy": 2.5,
          "qoq": -6.7,
          "mom": null
        },
        "context": {
          "avg_5yr": 2.4,
          "percentile_5yr": 58
        },
        "trend": {
          "direction": "stable",
          "inflection_point": false
        },
        "historical": [
          {"date": "2025-09-30", "value": 2.8},
          {"date": "2025-06-30", "value": 3.0},
          ...
        ]
      }
    },
    "CPI": { ... },
    "unemployment": { ... }
  }
}
```

## Dashboard Report Generation

The skill workflow (SKILL.md) uses the fetched data to generate a comprehensive markdown report with:

1. **Executive Summary**: 2-3 paragraph synthesis of economic conditions
2. **Core Indicators Section**: Detailed analysis of each indicator with:
   - Latest reading and historical context
   - Trend analysis (YoY, QoQ, MoM changes)
   - Interpretation and market impact
3. **Cross-Indicator Analysis**: Alignment, leading indicators, contradictions
4. **Market Implications**: Equity, fixed income, monetary policy outlook
5. **Risk Assessment**: Recession probability, key risks, tail risks

Example report: `macro_indicators_dashboard_US_2025-11-09.md`

## Common Workflows

### Weekly Macro Check
```bash
# Every Monday morning
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --output weekly_macro.json

# Claude generates dashboard report
# Review for major changes since last week
```

### Pre-FOMC Analysis
```bash
# Before Federal Reserve meetings
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --indicators CPI,unemployment,retailSales \
  --output fomc_prep.json

# Focus on inflation and employment indicators
# Formulate Fed policy expectations
```

### Monthly Portfolio Review
```bash
# First of each month
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --indicators GDP,CPI,unemployment,retailSales,industrialProduction,consumerConfidence \
  --lookback-years 10 \
  --output monthly_macro_$(date +%Y-%m).json

# Full dashboard with extended historical context
# Identify sector rotation opportunities
```

### Recession Watch Mode
```bash
# Monitor leading indicators closely
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --indicators GDP,unemployment,retailSales,industrialProduction,consumerConfidence \
  --output recession_watch.json

# Watch for: declining retail sales, falling industrial production,
# rising unemployment, negative GDP
```

## Interpreting the Dashboard

### Economic Cycle Phases

**Early Expansion (Recovery):**
- GDP accelerating, unemployment high but falling, low inflation, low rates
- **Action:** Overweight equities (especially cyclicals), underweight bonds

**Mid-Expansion:**
- GDP moderate growth, unemployment near natural rate, inflation near target
- **Action:** Stay invested in equities, neutral bonds

**Late Expansion:**
- GDP slowing, unemployment very low, inflation rising, rates high
- **Action:** Reduce risk, rotate to defensives, shorten bond duration

**Recession:**
- GDP negative, unemployment rising, inflation falling, rates falling
- **Action:** Overweight bonds and defensives, underweight cyclicals

### Key Indicator Combinations

**Goldilocks Scenario (Ideal):**
- Moderate GDP growth + Low unemployment + Low inflation + Stable rates
- Very bullish for equities

**Stagflation (Dangerous):**
- Weak GDP + High unemployment + High inflation
- Very difficult for all asset classes (real assets outperform)

**Overheating (Late Cycle Warning):**
- Slowing GDP + Very low unemployment + Rising inflation + Fed hiking aggressively
- Recession risk high, reduce equity exposure

### Leading vs. Lagging Indicators

**Leading (Predictive):**
- Retail Sales (leads GDP by 1-2 quarters)
- Consumer Confidence (leads spending by 3-6 months)
- Industrial Production (coincident but more volatile than GDP)

**Lagging (Confirmatory):**
- GDP (tells you where economy was)
- Unemployment (peaks after recession ends)

**Use leading indicators to get ahead of economic turns!**

## Integration with Other Skills

### Complementary Skills

**Economic Calendar Fetcher:**
```bash
# Check upcoming data releases
# Plan for dashboard updates around major releases (GDP, CPI, jobs report)
```

**Market News Analyst:**
```bash
# Understand recent events driving economic changes
# Example: "Why did retail sales spike last month?" (stimulus check, tax refund, etc.)
```

**Sector Analyst:**
```bash
# After identifying economic phase in macro dashboard:
# - Early cycle → analyze financials, consumer discretionary, industrials
# - Late cycle → analyze utilities, consumer staples, healthcare
```

**US Market Bubble Detector:**
```bash
# Cross-reference macro conditions with bubble indicators
# Example: Strong GDP + low unemployment + high valuations = late cycle risk
```

**Technical Analyst:**
```bash
# Confirm macro view with price action
# Example: Dashboard shows recession risk → check if market is breaking support
```

### Multi-Skill Workflow Example

**Monthly Macro Review Process:**

1. **Run Macro Indicators Dashboard** (this skill)
   - Get comprehensive economic overview
   - Identify current cycle phase
   - Note key trends and risks

2. **Run Economic Calendar Fetcher**
   - Check upcoming data releases for next 30 days
   - Plan for potential market-moving events

3. **Run Sector Analyst**
   - Based on cycle phase, identify sector opportunities
   - Example: Late cycle → analyze defensive sectors

4. **Run Technical Analyst**
   - Confirm macro view with market price action
   - Identify entry/exit points for sector rotation

5. **Update Portfolio**
   - Adjust allocations based on macro outlook
   - Implement sector rotation
   - Adjust risk exposure

## Limitations and Considerations

### Data Availability
- FMP API may not have all indicators for all countries
- Some indicators (Consumer Confidence) may require premium tier
- Data availability varies by country (US has most complete data)

### Data Lag
- GDP released ~1 month after quarter end
- Monthly indicators released 2-4 weeks after month end
- Dashboard shows point-in-time snapshot, not real-time conditions

### Revisions
- GDP revised 2-3 times after initial release
- Employment data subject to revisions
- Initial readings can be misleading, wait for confirmation

### FMP API Limitations
- Free tier: 250 requests/day (sufficient for daily updates)
- Rate limiting: Spread requests if fetching many indicators
- Some advanced indicators may require paid tier

### Interpretation Challenges
- Economic data is noisy (single data point can be misleading)
- Look for 3-month trends, not one-month moves
- Context matters (same reading means different things in different cycles)
- Contradictions between indicators require judgment

## Best Practices

### Update Frequency
- **Active traders:** Weekly updates (especially before FOMC)
- **Long-term investors:** Monthly updates (first week of month)
- **After major releases:** Update when key data drops (GDP, jobs report, CPI)

### Focus Indicators
- **Always include:** GDP, CPI, unemployment (core trinity)
- **Add based on focus:**
  - Consumer-focused: Retail Sales, Consumer Confidence
  - Manufacturing-focused: Industrial Production
  - Fed-focused: CPI, Unemployment (dual mandate)

### Verification
- Cross-reference unusual readings with multiple sources
- Check news for explanations of outliers (strikes, weather, policy changes)
- Don't overreact to single data point (wait for trend confirmation)

### Historical Context
- Always compare to 5-year average (percentile ranking)
- Note extremes (>90th or <10th percentile)
- Compare to previous economic cycles (2000, 2008, 2020)

### Combine with Other Analysis
- Macro indicators are top-down, combine with bottom-up fundamental analysis
- Use technical analysis for timing (macro for direction, technicals for entry/exit)
- Monitor market expectations (consensus forecasts) for surprise potential

## Troubleshooting

### Script Returns No Data
```bash
# Check API key is set
echo $FMP_API_KEY

# Test API key with simple request
curl "https://financialmodelingprep.com/stable/economic-indicators?name=GDP&apikey=$FMP_API_KEY"

# Verify indicator name is correct (case-sensitive)
python3 scripts/fetch_macro_data.py --indicators GDP,CPI,unemployment
```

### Rate Limit Exceeded
```bash
# Reduce number of indicators
python3 scripts/fetch_macro_data.py --indicators GDP,CPI,unemployment

# Wait and retry (free tier resets every 24 hours)
```

### Missing Indicators
```bash
# Some indicators may not be available for all countries
# Try with US (most complete data)
python3 scripts/fetch_macro_data.py --country US

# Check FMP API documentation for indicator availability
```

### Data Appears Stale
```bash
# Economic data has natural lag (GDP released 1 month after quarter end)
# Check metadata "generated_at" and "latest.date" fields
# Quarterly indicators (GDP) update every 3 months (normal)
```

## Examples

### Example 1: Basic Dashboard
```bash
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py
```

**Output:**
```
Fetching macroeconomic indicators for US...
Requested indicators: GDP, CPI, unemployment, retailSales, industrialProduction

Fetching GDP...
  ✓ GDP: 2.8 (2025-09-30)
Fetching CPI...
  ✓ CPI: 3.2 (2025-10-31)
Fetching unemployment...
  ✓ unemployment: 3.9 (2025-10-31)
Fetching retailSales...
  ✓ retailSales: 710.5 (2025-10-31)
Fetching industrialProduction...
  ✓ industrialProduction: 103.2 (2025-10-31)

✓ Successfully fetched 5 of 5 indicators
✓ Output written to macro_data.json
```

### Example 2: Pre-FOMC Focus
```bash
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --indicators CPI,unemployment \
  --output fomc_prep.json
```

**Use case:** Before Federal Reserve meeting, focus on the Fed's dual mandate (price stability + full employment)

### Example 3: Recession Watch
```bash
python3 macro-indicators-dashboard/scripts/fetch_macro_data.py \
  --indicators GDP,unemployment,retailSales,industrialProduction,consumerConfidence \
  --output recession_watch_$(date +%Y-%m-%d).json
```

**Use case:** Monitor leading indicators for signs of economic slowdown

## Resources

### Reference Guides
- **`references/indicators_guide.md`**: Comprehensive guide to each economic indicator
  - Detailed explanations of GDP, CPI, unemployment, etc.
  - Interpretation frameworks
  - Historical context and examples
  - Common mistakes to avoid

### FMP API Documentation
- **Economic Indicators API**: https://site.financialmodelingprep.com/developer/docs/economic-indicator-api
- **Economic Calendar API**: https://site.financialmodelingprep.com/developer/docs/economic-calendar-api
- **Pricing**: https://site.financialmodelingprep.com/developer/docs/pricing

### Economic Data Sources
- **FRED (Federal Reserve Economic Data)**: https://fred.stlouisfed.org (free, comprehensive)
- **Bureau of Economic Analysis (BEA)**: https://www.bea.gov (GDP data)
- **Bureau of Labor Statistics (BLS)**: https://www.bls.gov (unemployment, CPI)
- **Conference Board**: https://www.conference-board.org (consumer confidence)

### Further Reading
- **NBER Business Cycle Dating**: https://www.nber.org/cycles
- **Fed Economic Projections (SEP)**: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- **IMF World Economic Outlook**: https://www.imf.org/en/Publications/WEO

## Support

For issues or questions:
- Check `SKILL.md` for detailed workflow
- Review `references/indicators_guide.md` for indicator interpretations
- Consult FMP API documentation for data availability
- Verify API key is set and has not exceeded daily limit

## License

Part of the Claude Trading Skills repository. See main repository README for license information.

---

**Last Updated:** 2025-11-09
**Version:** 1.0.0
**Skill Type:** Data Analysis, Economic Indicators, Dashboard
**API Requirements:** FMP API (Free tier sufficient)
