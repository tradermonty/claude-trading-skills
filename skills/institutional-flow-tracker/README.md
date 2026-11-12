# Institutional Flow Tracker

Track institutional investor ownership changes and portfolio flows using 13F filings data to identify "smart money" accumulation and distribution patterns.

## Overview

Institutional Flow Tracker analyzes SEC 13F filings to discover stocks where sophisticated investors (hedge funds, mutual funds, pension funds) are accumulating or distributing positions. By following where institutional money flows, you can:

- **Discover opportunities** before they become mainstream
- **Validate investment ideas** by checking if smart money agrees
- **Get early warnings** when quality investors exit positions
- **Follow superinvestors** like Warren Buffett, Seth Klarman, Bill Ackman

**Key Insight:** Institutional investors manage trillions of dollars and conduct extensive research. Their collective actions often precede major price movements by 1-3 quarters.

## Features

✅ **Stock Screening** - Find stocks with significant institutional ownership changes (>10-15% QoQ)
✅ **Deep Dive Analysis** - Detailed quarterly trends, top holders, position changes for individual stocks
✅ **Institution Tracking** - Follow specific hedge funds/mutual funds portfolio moves
✅ **Signal Quality Framework** - Tier-based weighting system (superinvestors > active funds > index funds)
✅ **Multi-Quarter Trends** - Identify sustained accumulation/distribution (3+ quarters)
✅ **Concentration Analysis** - Assess ownership concentration risk
✅ **FMP API Integration** - Free tier (250 calls/day) sufficient for quarterly reviews

## Prerequisites

### Required: FMP API Key

This skill uses Financial Modeling Prep (FMP) API to access 13F filing data.

**Setup:**
```bash
# Set environment variable (recommended)
export FMP_API_KEY="your_key_here"

# Or provide via command-line when running scripts
python3 scripts/track_institutional_flow.py --api-key YOUR_KEY
```

**Get API Key:**
1. Visit: https://financialmodelingprep.com/developer/docs
2. Sign up for free account (250 requests/day)
3. Copy your API key

**API Usage:**
- Free tier: 250 requests/day (sufficient for analyzing 30-50 stocks quarterly)
- Each stock analysis uses 1-2 API calls
- Quarterly review workflow: ~50-100 API calls total

## Installation

No installation required beyond Python 3 and the `requests` library:

```bash
pip install requests
```

## Usage

Run the examples below from the `skills/institutional-flow-tracker` directory.

### 1. Screen for Stocks with Institutional Changes

Find stocks with significant institutional activity:

**Quick scan (top 50 stocks):**
```bash
python3 scripts/track_institutional_flow.py \
  --top 50 \
  --min-change-percent 10
```

**Sector-focused screening:**
```bash
python3 scripts/track_institutional_flow.py \
  --sector Technology \
  --min-institutions 20
```

**Custom screening:**
```bash
python3 scripts/track_institutional_flow.py \
  --min-market-cap 2000000000 \
  --min-change-percent 15 \
  --top 100 \
  --output institutional_results.json
```

**Output:** Markdown report with top accumulators/distributors, detailed metrics, interpretation guide

### 2. Deep Dive on Specific Stock

Comprehensive analysis of institutional ownership for a single stock:

```bash
python3 scripts/analyze_single_stock.py AAPL
```

**Extended history (12 quarters):**
```bash
python3 scripts/analyze_single_stock.py MSFT --quarters 12
```

**Output:** Detailed report with quarterly trends, new/increased/decreased/closed positions, concentration analysis

### 3. Track Specific Institutional Investors

Follow portfolio changes of specific hedge funds or investment firms:

```bash
# Track Warren Buffett's Berkshire Hathaway
python3 scripts/track_institution_portfolio.py \
  --cik 0001067983 \
  --name "Berkshire Hathaway"

# Track Cathie Wood's ARK Investment Management
python3 scripts/track_institution_portfolio.py \
  --cik 0001579982 \
  --name "ARK Investment Management"
```

**Finding CIK (Central Index Key):**
- Search SEC EDGAR: https://www.sec.gov/cgi-bin/browse-edgar
- Or use FMP API institutional search

**Output:** Current portfolio holdings, new positions, exits, largest changes

## Signal Interpretation Framework

### Strong Buy Signal (95th percentile)

**Criteria:**
- Institutional ownership increasing >15% QoQ
- 3+ consecutive quarters of accumulation
- Multiple Tier 1/2 investors buying (clustering score >60)
- Quality long-term investors adding positions

**Action:** BUY with conviction (2-5% portfolio position)

### Moderate Buy Signal (75th percentile)

**Criteria:**
- Institutional ownership increasing 7-15% QoQ
- 2 consecutive quarters of accumulation
- Mix of quality buyers

**Action:** BUY with moderate conviction (1-3% position)

### Neutral Signal

**Criteria:**
- Institutional ownership change <5% QoQ
- No clear trend
- Mixed buyer/seller activity

**Action:** HOLD or decide based on other factors

### Moderate/Strong Sell Signal

**Criteria:**
- Institutional ownership decreasing 7-15% QoQ (moderate) or >15% (strong)
- 2-3+ consecutive quarters of distribution
- Quality investors exiting

**Action:** TRIM/SELL positions, avoid new entries

## Institutional Investor Quality Tiers

**Tier 1 - Superinvestors (Weight: 3.0-3.5x):**
- Warren Buffett (Berkshire Hathaway)
- Seth Klarman (Baupost Group)
- Bill Ackman (Pershing Square)
- David Tepper (Appaloosa Management)
- Patient capital, long-term oriented, concentrated portfolios

**Tier 2 - Quality Active Managers (Weight: 2.0-2.5x):**
- Fidelity Management & Research
- T. Rowe Price Associates
- Dodge & Cox
- Wellington Management
- Research-driven, solid track records

**Tier 3 - Average Institutional (Weight: 1.0-1.5x):**
- Regional mutual funds
- Most pension funds
- Benchmark-aware, committee-driven

**Tier 4 - Passive/Mechanical (Weight: 0.0-0.5x):**
- Index funds (Vanguard, BlackRock, State Street)
- Momentum/quant funds
- No fundamental views, follow index/price action

## Workflow Examples

### Quarterly Portfolio Review

**Objective:** Monitor institutional support for your holdings

1. Run institutional analysis on each holding after 13F filing deadlines
2. Flag positions with deteriorating institutional support
3. Re-evaluate thesis for positions showing Strong Sell signals
4. Consider trimming/exiting if quality investors are distributing

**13F Filing Deadlines:**
- Q1 (Jan-Mar): Mid-May
- Q2 (Apr-Jun): Mid-August
- Q3 (Jul-Sep): Mid-November
- Q4 (Oct-Dec): Mid-February

### New Position Validation

**Objective:** Validate stock ideas with institutional data

1. Run fundamental analysis on stock candidate
2. Check institutional flow signal (accumulation or distribution?)
3. If Strong Buy signal: Gain confidence, initiate position
4. If Strong Sell signal: Reconsider or avoid
5. If Neutral: Decide based on fundamentals and technicals

### Smart Money Replication

**Objective:** Follow superinvestor portfolio moves

1. Track Berkshire Hathaway, Baupost, other Tier 1 investors quarterly
2. Identify new positions or significant increases
3. Research the stock to understand their thesis
4. Initiate positions in highest-conviction ideas

### Sector Rotation Detection

**Objective:** Identify early sector rotation trends

1. Calculate aggregate institutional flow by sector
2. Rank sectors by net institutional inflow/outflow
3. Compare to expected patterns based on economic cycle
4. Overweight sectors with institutional accumulation
5. Underweight/avoid sectors with distribution

## Integration with Other Skills

**Value Dividend Screener + Institutional Flow:**
```
1. Run Value Dividend Screener to find candidates
2. For each candidate, check institutional flow
3. Prioritize stocks with Strong Buy institutional signal
```

**US Stock Analysis + Institutional Flow:**
```
1. Run comprehensive fundamental analysis
2. Validate with institutional ownership trends
3. If institutions selling despite strong fundamentals: investigate discrepancy
```

**Portfolio Manager + Institutional Flow:**
```
1. Fetch current portfolio via Alpaca
2. Run institutional analysis on each holding quarterly
3. Flag positions with deteriorating institutional support
4. Rebalance away from Strong Sell signals
```

**Technical Analyst + Institutional Flow:**
```
1. Identify technical setup (e.g., breakout, basing pattern)
2. Check if institutional buying confirms
3. Higher conviction if both technical + institutional signals align
```

## Data Limitations

**Reporting Lag:**
- 13F filings due 45 days after quarter end
- Positions as of quarter-end snapshot
- Current positions may have changed since filing

**Coverage:**
- Only institutions managing >$100M file 13F
- Excludes individual investors and smaller funds
- Only long equity positions (no shorts, options, bonds)

**Best Practices:**
- Use as confirming indicator, not leading signal
- Look for multi-quarter trends (3+ quarters)
- Weight quality institutions heavily (Tier 1 > Tier 4)
- Combine with fundamental and technical analysis
- Update quarterly, not daily

## Reference Materials

The `references/` folder contains comprehensive guides:

- **13f_filings_guide.md** - Understanding 13F SEC filings, reporting requirements, data quality considerations, common pitfalls
- **institutional_investor_types.md** - Different investor types (hedge funds, mutual funds, etc.), their strategies, quality tiers, weighting framework
- **interpretation_framework.md** - Systematic approach to interpreting signals, decision trees, multi-factor integration

## Script Parameters Reference

### track_institutional_flow.py

**Required:**
- `--api-key` or FMP_API_KEY environment variable

**Optional:**
- `--top N` - Return top N stocks (default: 50)
- `--min-change-percent X` - Minimum % ownership change (default: 10)
- `--min-market-cap X` - Minimum market cap in dollars (default: 1B)
- `--sector NAME` - Filter by sector
- `--min-institutions N` - Minimum institutional holders (default: 10)
- `--sort-by FIELD` - Sort by ownership_change/institution_count_change/dollar_value_change
- `--output FILE` - Output JSON file

### analyze_single_stock.py

**Required:**
- Stock ticker symbol (positional argument)
- `--api-key` or FMP_API_KEY environment variable

**Optional:**
- `--quarters N` - Number of quarters to analyze (default: 8)
- `--output FILE` - Output markdown report path

### track_institution_portfolio.py

**Required:**
- `--cik CIK` - Central Index Key of institution
- `--name NAME` - Institution name for report
- `--api-key` or FMP_API_KEY environment variable

**Optional:**
- `--top N` - Show top N holdings (default: 50)
- `--output FILE` - Output markdown report path

## Notable Institutional Investors to Track

### Tier 1 Superinvestors

| Investor | CIK | Strategy | Track Because |
|----------|-----|----------|---------------|
| Berkshire Hathaway (Warren Buffett) | 0001067983 | Value/Quality | Long-term compounders, patient capital |
| Baupost Group (Seth Klarman) | 0001061768 | Deep Value | Distressed opportunities, contrarian |
| Pershing Square (Bill Ackman) | 0001336528 | Activist/Value | Catalytic events, concentrated bets |
| Appaloosa Management (David Tepper) | 0001079114 | Value | Contrarian, high conviction |
| Third Point (Dan Loeb) | 0001040273 | Event-Driven | Catalyst-driven, activism |

### Tier 2 Quality Active Managers

| Fund Family | CIK | Strategy | Track Because |
|-------------|-----|----------|---------------|
| Fidelity Management | 0000315066 | Growth & Value | Large analyst team, quality research |
| T. Rowe Price | 0001113169 | Growth | Bottom-up research, growth focus |
| Dodge & Cox | 0000922614 | Deep Value | Contrarian, value-oriented |
| ARK Investment (Cathie Wood) | 0001579982 | Disruptive Innovation | High-conviction tech/innovation bets |

## Support & Resources

- FMP API Documentation: https://financialmodelingprep.com/developer/docs
- SEC 13F Filings Database: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F
- WhaleWisdom (free tier): https://whalewisdom.com

## License

Educational and research purposes. See repository license for details.
