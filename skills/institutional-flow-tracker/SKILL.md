---
name: institutional-flow-tracker
description: Use this skill to track institutional investor ownership changes and portfolio flows using 13F filings data. Analyzes hedge funds, mutual funds, and other institutional holders to identify stocks with significant smart money accumulation or distribution. Helps discover stocks before major moves by following where sophisticated investors are deploying capital.
---

# Institutional Flow Tracker

## Overview

This skill tracks institutional investor activity through 13F SEC filings to identify "smart money" flows into and out of stocks. By analyzing quarterly changes in institutional ownership, you can discover stocks that sophisticated investors are accumulating before major price moves, or identify potential risks when institutions are reducing positions.

**Key Insight:** Institutional investors (hedge funds, pension funds, mutual funds) manage trillions of dollars and conduct extensive research. Their collective buying/selling patterns often precede significant price movements by 1-3 quarters.

## Prerequisites

- **FMP API Key:** Set `FMP_API_KEY` environment variable or pass `--api-key` to scripts
- **Python 3.8+:** Required for running analysis scripts
- **Dependencies:** `pip install requests` (scripts handle missing dependencies gracefully)

## When to Use This Skill

Use this skill when:
- Validating investment ideas (checking if smart money agrees with your thesis)
- Discovering new opportunities (finding stocks institutions are accumulating)
- Risk assessment (identifying stocks institutions are exiting)
- Portfolio monitoring (tracking institutional support for your holdings)
- Following specific investors (tracking Warren Buffett, Cathie Wood, etc.)
- Sector rotation analysis (identifying where institutions are rotating capital)

**Do NOT use when:**
- Seeking real-time intraday signals (13F data has 45-day reporting lag)
- Analyzing micro-cap stocks (<$100M market cap with limited institutional interest)
- Looking for short-term trading signals (<3 months horizon)

## Data Sources & Requirements

### Required: FMP API Key

This skill uses Financial Modeling Prep (FMP) API to access 13F filing data:

**Setup:**
```bash
# Set environment variable (preferred)
export FMP_API_KEY=your_key_here

# Or provide when running scripts
python3 skills/institutional-flow-tracker/scripts/track_institutional_flow.py --api-key YOUR_KEY
```

**API Tier Requirements:**
- **Free Tier:** 250 requests/day (sufficient for analyzing 20-30 stocks quarterly)
- **Paid Tiers:** Higher limits for extensive screening

**13F Filing Schedule:**
- Filed quarterly within 45 days after quarter end
- Q1 (Jan-Mar): Filed by mid-May
- Q2 (Apr-Jun): Filed by mid-August
- Q3 (Jul-Sep): Filed by mid-November
- Q4 (Oct-Dec): Filed by mid-February

## Analysis Workflow

### Step 1: Identify Stocks with Significant Institutional Changes

Execute the main screening script to find stocks with notable institutional activity:

**Quick scan (top 50 stocks by institutional change):**
```bash
python3 skills/institutional-flow-tracker/scripts/track_institutional_flow.py \
  --top 50 \
  --min-change-percent 10
```

**Sector-focused scan:**
```bash
python3 skills/institutional-flow-tracker/scripts/track_institutional_flow.py \
  --sector Technology \
  --min-institutions 20
```

**Custom screening:**
```bash
python3 skills/institutional-flow-tracker/scripts/track_institutional_flow.py \
  --min-market-cap 2000000000 \
  --min-change-percent 15 \
  --top 100 \
  --output institutional_flow_results.json
```

**Output includes:**
- Stock ticker and company name
- Current institutional ownership % (of shares outstanding)
- Quarter-over-quarter change in shares held
- Number of institutions holding
- Change in number of institutions (new buyers vs sellers)
- Top institutional holders

### Step 2: Deep Dive on Specific Stocks

For detailed analysis of a specific stock's institutional ownership:

```bash
python3 skills/institutional-flow-tracker/scripts/analyze_single_stock.py AAPL
```

**This generates:**
- Historical institutional ownership trend (8 quarters)
- List of all institutional holders with position changes
- Concentration analysis (top 10 holders' % of total institutional ownership)
- New positions vs increased vs decreased positions
- Data quality assessment with reliability grade

**Key metrics to evaluate:**
- **Ownership %:** Higher institutional ownership (>70%) = more stability but limited upside
- **Ownership Trend:** Rising ownership = bullish, falling = bearish
- **Concentration:** High concentration (top 10 > 50%) = risk if they sell
- **Quality of Holders:** Presence of quality long-term investors (Berkshire, Fidelity) vs momentum funds

### Step 3: Track Specific Institutional Investors

> **Note:** `track_institution_portfolio.py` is **not yet implemented**. FMP API organizes
> institutional holder data by stock (not by institution), making full portfolio reconstruction
> impractical via this API alone.

**Alternative approach — use `analyze_single_stock.py` to check if a specific institution holds a stock:**
```bash
# Analyze a stock and look for a specific institution in the output
python3 skills/institutional-flow-tracker/scripts/analyze_single_stock.py AAPL
# Then search the report for "Berkshire" or "ARK" in the Top 20 holders table
```

**For full institution-level portfolio tracking, use these external resources:**
1. **WhaleWisdom:** https://whalewisdom.com (free tier available, 13F portfolio viewer)
2. **SEC EDGAR:** https://www.sec.gov/cgi-bin/browse-edgar (official 13F filings)
3. **DataRoma:** https://www.dataroma.com (superinvestor portfolio tracker)

### Step 4: Interpretation and Action

Read the references for interpretation guidance:
- `skills/institutional-flow-tracker/references/13f_filings_guide.md` - Understanding 13F data and limitations
- `skills/institutional-flow-tracker/references/institutional_investor_types.md` - Different investor types and their strategies
- `skills/institutional-flow-tracker/references/interpretation_framework.md` - How to interpret institutional flow signals

**Signal Strength Framework:**

**Strong Bullish (Consider buying):**
- Institutional ownership increasing >15% QoQ
- Number of institutions increasing >10%
- Quality long-term investors adding positions
- Low current ownership (<40%) with room to grow
- Accumulation happening across multiple quarters

**Moderate Bullish:**
- Institutional ownership increasing 5-15% QoQ
- Mix of new buyers and sellers, net positive
- Current ownership 40-70%

**Neutral:**
- Minimal change in ownership (<5%)
- Similar number of buyers and sellers
- Stable institutional base

**Moderate Bearish:**
- Institutional ownership decreasing 5-15% QoQ
- More sellers than buyers
- High ownership (>80%) limiting new buyers

**Strong Bearish (Consider selling/avoiding):**
- Institutional ownership decreasing >15% QoQ
- Number of institutions decreasing >10%
- Quality investors exiting positions
- Distribution happening across multiple quarters
- Concentration risk (top holder selling large position)

### Step 5: Portfolio Application

**For new positions:**
1. Run institutional analysis on your stock idea
2. Look for confirmation (institutions also accumulating)
3. If strong bearish signals, reconsider or reduce position size
4. If strong bullish signals, gain confidence in thesis

**For existing holdings:**
1. Quarterly review after 13F filing deadlines
2. Monitor for distribution (early warning system)
3. If institutions are exiting, re-evaluate your thesis
4. Consider trimming if widespread institutional selling

**Screening workflow integration:**
1. Use Value Dividend Screener or other screeners to find candidates
2. Run Institutional Flow Tracker on top candidates
3. Prioritize stocks with institutional accumulation
4. Avoid stocks with institutional distribution

## Output Format

All analysis generates structured markdown reports saved to repository root:

**Filename convention:** `institutional_flow_analysis_<TICKER/THEME>_<DATE>.md`

**Report sections:**
1. Executive Summary (key findings)
2. Institutional Ownership Trend (current vs historical)
3. Top Holders and Changes
4. New Buyers vs Sellers
5. Concentration Analysis
6. Interpretation and Recommendations
7. Data Sources and Timestamp

## Data Reliability Grades

All analysis now includes a **reliability grade** based on data quality:

- **Grade A:** Coverage ratio < 3x, match ratio >= 50%, genuine holder ratio >= 70%. Safe for investment decisions.
- **Grade B:** Genuine holder ratio >= 30%. Reference only - use with caution.
- **Grade C:** Genuine holder ratio < 30%. UNRELIABLE - excluded from screening results.

The screening script (`track_institutional_flow.py`) automatically excludes Grade C stocks.
The single stock analysis (`analyze_single_stock.py`) displays the grade with appropriate warnings.

**Why this matters:** FMP returns different numbers of holders per quarter. A stock may show
5,415 holders in Q4 but only 201 in Q3. Without filtering, aggregate metrics produce
misleading percent changes (e.g., +400%). The data quality module filters to "genuine" holders
(present in both quarters) to produce reliable metrics.

## Limitations and Caveats

**Data Lag:**
- 13F filings have 45-day reporting delay
- Positions may have changed since filing date
- Use as confirming indicator, not leading signal

**Coverage:**
- Only institutions managing >$100M are required to file
- Excludes individual investors and smaller funds
- International institutions may not file 13F

**Reporting Rules:**
- Only long equity positions reported (no shorts, options, bonds)
- Holdings as of quarter-end snapshot
- Some positions may be confidential (delayed reporting)

**Interpretation:**
- Correlation ≠ causation (stocks can fall despite institutional buying)
- Consider overall market environment and fundamentals
- Combine with technical analysis and other skills

## Advanced Use Cases

**Insider + Institutional Combo:**
- Look for stocks where both insiders AND institutions are buying
- Particularly powerful signal when aligned

**Sector Rotation Detection:**
- Track aggregate institutional flows by sector
- Identify early rotation trends before they appear in price

**Contrarian Plays:**
- Find quality stocks institutions are selling (potential value)
- Requires strong fundamental conviction

**Smart Money Validation:**
- Before major position, check if smart money agrees
- Gain confidence or find overlooked risks

## References

The `skills/institutional-flow-tracker/references/` folder contains detailed guides:

- **skills/institutional-flow-tracker/references/13f_filings_guide.md** - Comprehensive guide to 13F SEC filings, what they include, reporting requirements, and data quality considerations
- **skills/institutional-flow-tracker/references/institutional_investor_types.md** - Different types of institutional investors (hedge funds, mutual funds, pension funds, etc.), their typical strategies, and how to interpret their moves
- **skills/institutional-flow-tracker/references/interpretation_framework.md** - Detailed framework for interpreting institutional ownership changes, signal quality assessment, and integration with other analysis

## Script Parameters

### track_institutional_flow.py

Main screening script for finding stocks with significant institutional changes.

**Required:**
- `--api-key`: FMP API key (or set FMP_API_KEY environment variable)

**Optional:**
- `--top N`: Return top N stocks by institutional change (default: 50)
- `--min-change-percent X`: Minimum % change in institutional ownership (default: 10)
- `--min-market-cap X`: Minimum market cap in dollars (default: 1B)
- `--sector NAME`: Filter by specific sector
- `--min-institutions N`: Minimum number of institutional holders (default: 10)
- `--limit N`: Number of stocks to fetch from screener (default: 100). Lower values save API calls.
- `--output FILE`: Output JSON file path
- `--output-dir DIR`: Output directory for reports (default: reports/)
- `--sort-by FIELD`: Sort by 'ownership_change' or 'institution_count_change'

### analyze_single_stock.py

Deep dive analysis on a specific stock's institutional ownership.

**Required:**
- Ticker symbol (positional argument)
- `--api-key`: FMP API key (or set FMP_API_KEY environment variable)

**Optional:**
- `--quarters N`: Number of quarters to analyze (default: 8, i.e., 2 years)
- `--output FILE`: Output markdown report path
- `--output-dir DIR`: Output directory for reports (default: reports/)
- `--compare-to TICKER`: Compare institutional ownership to another stock (future feature)

### track_institution_portfolio.py

**Status: NOT YET IMPLEMENTED**

This script is a placeholder. It prints alternative resources (WhaleWisdom, SEC EDGAR, DataRoma) and exits with error code 1. FMP API organizes institutional holder data by stock (not by institution), making full portfolio reconstruction impractical.

For institution-specific portfolio tracking, use:
1. WhaleWisdom: https://whalewisdom.com (free tier available)
2. SEC EDGAR: https://www.sec.gov/cgi-bin/browse-edgar
3. DataRoma: https://www.dataroma.com

### Data Quality Module (data_quality.py)

Shared utility module used by both `track_institutional_flow.py` and `analyze_single_stock.py`:

- **classify_holder():** Classifies holders as genuine/new_full/exited/unknown
- **calculate_filtered_metrics():** Computes metrics using genuine holders only
- **reliability_grade():** Assigns A/B/C grade based on data quality
- **is_tradable_stock():** Filters out ETFs, funds, and inactive stocks
- **deduplicate_share_classes():** Removes BRK-A/B, GOOG/GOOGL duplicates

## Integration with Other Skills

**Value Dividend Screener + Institutional Flow:**
```
1. Run Value Dividend Screener to find candidates
2. For each candidate, check institutional flow
3. Prioritize stocks with rising institutional ownership
```

**US Stock Analysis + Institutional Flow:**
```
1. Run comprehensive fundamental analysis
2. Validate with institutional ownership trends
3. If institutions are selling, investigate why
```

**Portfolio Manager + Institutional Flow:**
```
1. Fetch current portfolio via Alpaca
2. Run institutional analysis on each holding
3. Flag positions with deteriorating institutional support
4. Consider rebalancing away from distribution
```

**Technical Analyst + Institutional Flow:**
```
1. Identify technical setup (e.g., breakout)
2. Check if institutional buying confirms
3. Higher conviction if both align
```

## Best Practices

1. **Quarterly Reviews:** Set calendar reminders for 13F filing deadlines
2. **Multi-Quarter Trends:** Look for sustained trends (3+ quarters), not one-time changes
3. **Quality Over Quantity:** Berkshire adding > 100 small funds adding
4. **Context Matters:** Rising ownership in a falling stock may be value investors catching a falling knife
5. **Combine Signals:** Never use institutional flow in isolation
6. **Update Your Data:** Re-run analysis each quarter as new 13Fs are filed

## Support & Resources

- FMP API Documentation: https://financialmodelingprep.com/developer/docs
- SEC 13F Filings Database: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F
- Institutional Investor Database: https://whalewisdom.com (free tier available)

---

**Note:** This skill is designed for long-term investors (3-12 month horizon). For short-term trading, combine with technical analysis and other momentum indicators.
