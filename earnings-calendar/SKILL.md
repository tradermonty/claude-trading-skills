---
name: earnings-calendar
description: This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API. Use this when the user requests earnings calendar data, wants to know which companies are reporting earnings in the upcoming week, or needs a weekly earnings review. The skill focuses on mid-cap and above companies (over $2B market cap) that have significant market impact, organizing the data by date and timing in a clean markdown table format. Supports multiple environments (CLI, Desktop, Web) with flexible API key management.
---

# Earnings Calendar

## Overview

This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API. It focuses on companies with significant market capitalization (mid-cap and above, over $2B) that are likely to impact market movements. The skill generates organized markdown reports showing which companies are reporting earnings over the next week, grouped by date and timing (before market open, after market close, or time not announced).

**Key Features**:
- Uses FMP API for reliable, structured earnings data
- Filters by market cap (>$2B) to focus on market-moving companies
- Includes EPS and revenue estimates
- Multi-environment support (CLI, Desktop, Web)
- Flexible API key management
- Organized by date, timing, and market cap

## Prerequisites

### FMP API Key

This skill requires a Financial Modeling Prep API key.

**Get Free API Key**:
1. Visit: https://site.financialmodelingprep.com/developer/docs
2. Sign up for free account
3. Receive API key immediately
4. Free tier: 250 API calls/day (sufficient for weekly earnings calendar)

**API Key Setup by Environment**:

**Claude Code (CLI)**:
```bash
export FMP_API_KEY="your-api-key-here"
```

**Claude Desktop**:
Set environment variable in system or configure MCP server.

**Claude Web**:
API key will be requested during skill execution (stored only for current session).

## Core Workflow

### Step 1: Get Current Date and Calculate Target Week

**CRITICAL**: Always start by obtaining the accurate current date.

Retrieve the current date and time:
- Use system date/time to get today's date
- Note: "Today's date" is provided in the environment (<env> tag)
- Calculate the target week: Next 7 days from current date

**Date Range Calculation**:
```
Current Date: [e.g., November 2, 2025]
Target Week Start: [Current Date + 1 day, e.g., November 3, 2025]
Target Week End: [Current Date + 7 days, e.g., November 9, 2025]
```

**Why This Matters**:
- Earnings calendars are time-sensitive
- "Next week" must be calculated from the actual current date
- Provides accurate date range for API request

**Format dates in YYYY-MM-DD** for API compatibility.

### Step 2: Load FMP API Guide

Before retrieving data, load the comprehensive FMP API guide:

```
Read: references/fmp_api_guide.md
```

This guide contains:
- FMP API endpoint structure and parameters
- Authentication requirements
- Market cap filtering strategy (via Company Profile API)
- Earnings timing conventions (BMO, AMC, TAS)
- Response format and field descriptions
- Error handling strategies
- Best practices and optimization tips

### Step 3: API Key Detection and Configuration

Detect API key availability based on environment.

**Multi-Environment API Key Detection**:

#### 3.1 Check Environment Variable (CLI/Desktop)

```bash
if [ ! -z "$FMP_API_KEY" ]; then
  echo "✓ API key found in environment"
  API_KEY=$FMP_API_KEY
fi
```

If environment variable is set, proceed to Step 4.

#### 3.2 Prompt User for API Key (Desktop/Web)

If environment variable not found, use AskUserQuestion tool:

**Question Configuration**:
```
Question: "This skill requires an FMP API key to retrieve earnings data. Do you have an FMP API key?"
Header: "API Key"
Options:
  1. "Yes, I'll provide it now" → Proceed to 3.3
  2. "No, get free key" → Show instructions (3.2.1)
  3. "Skip API, use manual entry" → Jump to Step 8 (fallback mode)
```

**3.2.1 If user chooses "No, get free key"**:

Provide instructions:
```
To get a free FMP API key:

1. Visit: https://site.financialmodelingprep.com/developer/docs
2. Click "Get Free API Key" or "Sign Up"
3. Create account (email + password)
4. Receive API key immediately
5. Free tier includes 250 API calls/day (sufficient for daily use)

Once you have your API key, please select "Yes, I'll provide it now" to continue.
```

#### 3.3 Request API Key Input

If user has API key, request input:

**Prompt**:
```
Please paste your FMP API key below:

(Your API key will only be stored for this conversation session and will be forgotten when the session ends. For regular use, consider setting the FMP_API_KEY environment variable.)
```

**Store API key in session variable**:
```
API_KEY = [user_input]
```

**Confirm with user**:
```
✓ API key received and stored for this session.

Security Note:
- API key is stored only in current conversation context
- Not saved to disk or persistent storage
- Will be forgotten when session ends
- Do not share this conversation if it contains your API key

Proceeding with earnings data retrieval...
```

### Step 4: Retrieve Earnings Data via FMP API

Use the Python script to fetch earnings data from FMP API.

**Script Location**:
```
scripts/fetch_earnings_fmp.py
```

**Execution**:

**Option A: With Environment Variable (CLI)**:
```bash
python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09
```

**Option B: With Session API Key (Desktop/Web)**:
```bash
python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09 "${API_KEY}"
```

**Script Workflow** (automatic):
1. Validates API key and date parameters
2. Calls FMP Earnings Calendar API for date range
3. Fetches company profiles (market cap, sector, industry)
4. Filters companies with market cap >$2B
5. Normalizes timing (BMO/AMC/TAS)
6. Sorts by date → timing → market cap (descending)
7. Outputs JSON to stdout

**Expected Output Format** (JSON):
```json
[
  {
    "symbol": "AAPL",
    "companyName": "Apple Inc.",
    "date": "2025-11-04",
    "timing": "AMC",
    "marketCap": 3000000000000,
    "marketCapFormatted": "$3.0T",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "epsEstimated": 1.54,
    "revenueEstimated": 123400000000,
    "fiscalDateEnding": "2025-09-30",
    "exchange": "NASDAQ"
  },
  ...
]
```

**Save to file** (recommended for use with report generator):
```bash
python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09 "${API_KEY}" > earnings_data.json
```

Or capture to variable:
```bash
earnings_data=$(python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09 "${API_KEY}")
```

**Error Handling**:

If script returns errors:
- **401 Unauthorized**: Invalid API key → Verify key or re-enter
- **429 Rate Limit**: Exceeded 250 calls/day → Wait or upgrade plan
- **Empty Result**: No earnings in date range → Expand date range or note in report
- **Connection Error**: Network issue → Retry or use cached data if available

### Step 5: Process and Organize Data

Once earnings data is retrieved (JSON format), process and organize it:

#### 5.1 Parse JSON Data

Load JSON data from script output:
```python
import json
earnings_data = json.loads(earnings_json_string)
```

Or if saved to file:
```python
with open('earnings_data.json', 'r') as f:
    earnings_data = json.load(f)
```

#### 5.2 Verify Data Structure

Confirm data includes required fields:
- ✓ symbol
- ✓ companyName
- ✓ date
- ✓ timing (BMO/AMC/TAS)
- ✓ marketCap
- ✓ sector

#### 5.3 Group by Date

Group all earnings announcements by date:
- Sunday, [Full Date] (if applicable)
- Monday, [Full Date]
- Tuesday, [Full Date]
- Wednesday, [Full Date]
- Thursday, [Full Date]
- Friday, [Full Date]
- Saturday, [Full Date] (if applicable)

#### 5.4 Sub-Group by Timing

Within each date, create three sub-sections:
1. **Before Market Open (BMO)**
2. **After Market Close (AMC)**
3. **Time Not Announced (TAS)**

Data is already sorted by timing from the script, so maintain this order.

#### 5.5 Within Each Timing Group

Companies are already sorted by market cap descending (script output):
- Mega-cap (>$200B) first
- Large-cap ($10B-$200B) second
- Mid-cap ($2B-$10B) third

This prioritization ensures the most market-moving companies are listed first.

#### 5.6 Calculate Summary Statistics

Compute:
- **Total Companies**: Count of all companies in dataset
- **Mega/Large Cap Count**: Count where marketCap >= $10B
- **Mid Cap Count**: Count where marketCap between $2B and $10B
- **Peak Day**: Day of week with most earnings announcements
- **Sector Distribution**: Count by sector (Technology, Healthcare, Financial, etc.)
- **Highest Market Cap Companies**: Top 5 companies by market cap

### Step 6: Generate Markdown Report

Use the report generation script to create a formatted markdown report from the JSON data.

**Script Location**:
```
scripts/generate_report.py
```

**Execution**:

**Option A: Output to stdout**:
```bash
python scripts/generate_report.py earnings_data.json
```

**Option B: Save to file**:
```bash
python scripts/generate_report.py earnings_data.json earnings_calendar_2025-11-02.md
```

**What the script does**:
1. Loads earnings data from JSON file
2. Groups by date and timing (BMO/AMC/TAS)
3. Sorts by market cap within each group
4. Calculates summary statistics
5. Generates formatted markdown report
6. Outputs to stdout or saves to file

The script automatically handles all formatting including:
- Proper markdown table structure
- Date grouping and day names
- Market cap sorting
- EPS and revenue formatting
- Summary statistics calculation

**Report Structure**:

```markdown
# Upcoming Earnings Calendar - Week of [START_DATE] to [END_DATE]

**Report Generated**: [Current Date]
**Data Source**: FMP API (Mid-cap and above, >$2B market cap)
**Coverage Period**: Next 7 days
**Total Companies**: [COUNT]

---

## Executive Summary

- **Total Companies Reporting**: [TOTAL_COUNT]
- **Mega/Large Cap (>$10B)**: [LARGE_CAP_COUNT]
- **Mid Cap ($2B-$10B)**: [MID_CAP_COUNT]
- **Peak Day**: [DAY_WITH_MOST_EARNINGS]

---

## [Day Name], [Full Date]

### Before Market Open (BMO)

| Ticker | Company | Market Cap | Sector | EPS Est. | Revenue Est. |
|--------|---------|------------|--------|----------|--------------|
| [TICKER] | [COMPANY] | [MCAP] | [SECTOR] | [EPS] | [REV] |

### After Market Close (AMC)

| Ticker | Company | Market Cap | Sector | EPS Est. | Revenue Est. |
|--------|---------|------------|--------|----------|--------------|
| [TICKER] | [COMPANY] | [MCAP] | [SECTOR] | [EPS] | [REV] |

### Time Not Announced (TAS)

| Ticker | Company | Market Cap | Sector | EPS Est. | Revenue Est. |
|--------|---------|------------|--------|----------|--------------|
| [TICKER] | [COMPANY] | [MCAP] | [SECTOR] | [EPS] | [REV] |

---

[Repeat for each day of week]

---

## Key Observations

### Highest Market Cap Companies This Week
1. [COMPANY] ([TICKER]) - [MCAP] - [DATE] [TIME]
2. [COMPANY] ([TICKER]) - [MCAP] - [DATE] [TIME]
3. [COMPANY] ([TICKER]) - [MCAP] - [DATE] [TIME]

### Sector Distribution
- **Technology**: [COUNT] companies
- **Healthcare**: [COUNT] companies
- **Financial**: [COUNT] companies
- **Consumer**: [COUNT] companies
- **Other**: [COUNT] companies

### Trading Considerations
- **Days with Heavy Volume**: [DATES with multiple large-cap earnings]
- **Pre-Market Focus**: [BMO companies that may move markets]
- **After-Hours Focus**: [AMC companies that may move markets]

---

## Timing Reference

- **BMO (Before Market Open)**: Announcements typically around 6:00-8:00 AM ET before market opens at 9:30 AM ET
- **AMC (After Market Close)**: Announcements typically around 4:00-5:00 PM ET after market closes at 4:00 PM ET
- **TAS (Time Not Announced)**: Specific time not yet disclosed - monitor company investor relations

---

## Data Notes

- **Market Cap Categories**:
  - Mega Cap: >$200B
  - Large Cap: $10B-$200B
  - Mid Cap: $2B-$10B

- **Filter Criteria**: This report includes companies with market cap $2B and above (mid-cap+) with earnings scheduled for the next week.

- **Data Source**: Financial Modeling Prep (FMP) API

- **Data Freshness**: Earnings dates and times can change. Verify critical dates through company investor relations websites for the most current information.

- **EPS and Revenue Estimates**: Analyst consensus estimates from FMP API. Actual results will be reported on earnings date.

---

## Additional Resources

- **FMP API Documentation**: https://site.financialmodelingprep.com/developer/docs
- **Seeking Alpha Calendar**: https://seekingalpha.com/earnings/earnings-calendar
- **Yahoo Finance Calendar**: https://finance.yahoo.com/calendar/earnings

---

*Report generated using FMP Earnings Calendar API with mid-cap+ filter (>$2B market cap). Data current as of report generation time. Always verify earnings dates through official company sources.*
```

**Formatting Best Practices**:
- Use markdown tables for clean presentation
- Bold important company names (mega-cap) if desired
- Include market cap in human-readable format ($3.0T, $150B, $5.2B) - already formatted by script
- Group logically by date then timing
- Include summary section at top for quick overview
- Add EPS and revenue estimates if available

### Step 7: Quality Assurance

Before finalizing the report, verify:

**Data Quality Checks**:
1. ✓ All dates fall within the target week (next 7 days)
2. ✓ Market cap values are present for all companies
3. ✓ Each company has timing specified (BMO/AMC/TAS)
4. ✓ Companies are sorted by market cap within each section
5. ✓ Summary statistics are accurate
6. ✓ Report generation date is clearly stated
7. ✓ EPS and revenue estimates included where available

**Completeness Checks**:
1. ✓ All days of the target week are included (even if no earnings)
2. ✓ Major known companies are not missing (verify against external sources if needed)
3. ✓ Sector information is included where available
4. ✓ Timing reference section is present
5. ✓ Data sources are credited (FMP API)

**Format Checks**:
1. ✓ Markdown tables are properly formatted
2. ✓ Dates are consistently formatted
3. ✓ Market caps use consistent units (B for billions, T for trillions)
4. ✓ All sections follow template structure
5. ✓ No placeholder text ([PLACEHOLDER]) remains
6. ✓ EPS and revenue estimates properly formatted

### Step 8: Save and Deliver Report

Save the generated report with an appropriate filename:

**Filename Convention**:
```
earnings_calendar_[YYYY-MM-DD].md
```

Example: `earnings_calendar_2025-11-02.md`

The filename date represents the report generation date, not the earnings week.

**Delivery**:
- Save the markdown file to the working directory
- Inform the user that the report has been generated
- Provide a brief summary of key findings (e.g., "45 companies reporting next week, with Apple and Microsoft on Monday")

**Example Summary**:
```
✓ Earnings calendar report generated: earnings_calendar_2025-11-02.md

Summary for week of November 3-9, 2025:
- 45 companies reporting earnings
- 28 large/mega-cap, 17 mid-cap
- Peak day: Thursday (15 companies)
- Notable: Apple (Mon AMC), Microsoft (Tue AMC), Tesla (Wed AMC)

Top 5 by market cap:
1. Apple - $3.0T (Mon AMC)
2. Microsoft - $2.8T (Tue AMC)
3. Alphabet - $1.8T (Thu AMC)
4. Amazon - $1.6T (Fri AMC)
5. Tesla - $800B (Wed AMC)
```

## Fallback Mode (Step 8 Alternative): Manual Data Entry

If API access is unavailable or user chooses to skip API:

**Provide Instructions for Manual Entry**:

```
Since FMP API is not available, you can manually gather earnings data:

1. Visit Finviz: https://finviz.com/screener.ashx?v=111&f=cap_midover%2Cearningsdate_nextweek
2. Or Yahoo Finance: https://finance.yahoo.com/calendar/earnings
3. Note down companies reporting next week

Please provide the following information for each company:
- Ticker symbol
- Company name
- Earnings date
- Timing (BMO/AMC/TAS)
- Market cap (approximate)
- Sector

I will format this into the standard earnings calendar report.
```

**Process Manual Input**:
1. Parse user-provided earnings data
2. Organize by date, timing, and market cap
3. Generate report using same template
4. Note in report: "Data Source: Manual Entry"

## Use Cases and Examples

### Use Case 1: Weekly Review (Primary Use Case)

**User Request**: "Get next week's earnings calendar"

**Workflow**:
1. Get current date (e.g., November 2, 2025)
2. Calculate target week (November 3-9, 2025)
3. Load FMP API guide
4. Detect/request API key
5. Fetch earnings data:
   ```bash
   python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09 > earnings_data.json
   ```
6. Generate markdown report:
   ```bash
   python scripts/generate_report.py earnings_data.json earnings_calendar_2025-11-02.md
   ```
7. Notify user with summary

**Complete One-Liner**:
```bash
python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09 > earnings_data.json && \
python scripts/generate_report.py earnings_data.json earnings_calendar_2025-11-02.md
```

### Use Case 2: Focused on Specific Day

**User Request**: "What earnings are coming out Monday?"

**Workflow**:
1. Get current date and identify next Monday (e.g., November 4, 2025)
2. Fetch full week data (same as Use Case 1)
3. Generate full report but highlight Monday section
4. Provide verbal summary of Monday's earnings with emphasis

### Use Case 3: Mega-Cap Focus

**User Request**: "Show me earnings for companies over $100B market cap next week"

**Workflow**:
1. Fetch full earnings data (script already filters >$2B)
2. Process and organize as normal
3. When generating report, add a "Mega-Cap Focus" section at top
4. Filter tables to show only companies >$100B
5. Note: Still include full data in appendix for reference

### Use Case 4: Sector-Specific

**User Request**: "What tech companies have earnings next week?"

**Workflow**:
1. Fetch full earnings data
2. Process and organize as normal
3. Filter results by sector = "Technology"
4. Generate report with focus on technology sector
5. Note: Template structure remains the same; content is filtered

## Troubleshooting

### Problem: API key not working

**Solutions**:
- Verify API key is correct (copy-paste carefully)
- Check if API key is active (login to FMP dashboard)
- Ensure no extra spaces before/after key
- Try generating new API key from FMP dashboard

### Problem: Script returns empty results

**Solutions**:
- Verify date range is in future (not past dates)
- Check date format is YYYY-MM-DD
- Try wider date range (e.g., 14 days instead of 7)
- Verify companies actually have announced earnings dates for that week

### Problem: Missing major companies

**Solutions**:
- Company may not have announced earnings date yet
- Some companies announce dates very late (1-2 days before)
- Cross-reference with company investor relations website
- Market cap may have dropped below $2B threshold

### Problem: Rate limit hit (429 error)

**Solutions**:
- Free tier: 250 calls/day
- Each weekly report uses ~3-5 API calls
- Check if other tools/scripts are using same API key
- Wait 24 hours for rate limit reset
- Consider upgrading to paid tier if needed frequently

### Problem: Script execution error

**Solutions**:
- Verify Python 3 is installed: `python3 --version`
- Install requests library: `pip install requests`
- Check script has execute permissions: `chmod +x fetch_earnings_fmp.py`
- Run with python3 explicitly: `python3 fetch_earnings_fmp.py ...`

## Best Practices

### Do's
✓ Always get current date first before any data retrieval
✓ Use FMP API as primary source for reliability
✓ Store API key in environment variable for CLI usage
✓ Sort by market cap to prioritize high-impact companies
✓ Group by date then timing for logical organization
✓ Include summary statistics for quick overview
✓ Credit data sources in report footer
✓ Use clean markdown tables for readability
✓ Provide timing reference section for clarity
✓ Note data freshness and potential for changes
✓ Include EPS and revenue estimates when available

### Don'ts
✗ Don't assume "next week" without calculating from current date
✗ Don't omit timing information (BMO/AMC/TAS)
✗ Don't mix date formats within report (stay consistent)
✗ Don't include micro/small-cap unless specifically requested
✗ Don't forget to sort by market cap within sections
✗ Don't share API key in conversations or reports
✗ Don't include earnings from current week or past dates
✗ Don't generate report without quality assurance checks
✗ Don't commit API keys to version control

## Security Notes

### API Key Security

**Important Reminders**:
1. ✓ Use free tier API keys for testing
2. ✓ Rotate keys regularly
3. ✓ Don't share conversations containing API keys
4. ✓ Set API key as environment variable for CLI
5. ✓ Keys provided in chat are session-only (forgotten after session ends)
6. ✗ Never commit API keys to Git repositories
7. ✗ Never use production API keys with sensitive data access

**Best Practice**:
For Claude Code (CLI), always use environment variable:
```bash
# Add to ~/.zshrc or ~/.bashrc
export FMP_API_KEY="your-key-here"
```

For Claude Web, understand that:
- API key entered in chat is temporary
- Stored only in conversation context
- Not saved to disk
- Forgotten when session ends

## Resources

**FMP API**:
- Main Documentation: https://site.financialmodelingprep.com/developer/docs
- Get API Key: https://site.financialmodelingprep.com/developer/docs
- Earnings Calendar API: https://site.financialmodelingprep.com/developer/docs/earnings-calendar-api
- Company Profile API: https://site.financialmodelingprep.com/developer/docs/companies-key-metrics-api
- Pricing/Rate Limits: https://site.financialmodelingprep.com/developer/docs/pricing

**Supplementary Sources** (for verification):
- Seeking Alpha: https://seekingalpha.com/earnings/earnings-calendar
- Yahoo Finance: https://finance.yahoo.com/calendar/earnings
- MarketWatch: https://www.marketwatch.com/tools/earnings-calendar

**Skill Resources**:
- FMP API Guide: `references/fmp_api_guide.md`
- Python Script: `scripts/fetch_earnings_fmp.py`
- Report Template: `assets/earnings_report_template.md`

---

## Summary

This skill provides a reliable, API-driven approach to generating weekly earnings calendars for US stocks. By using FMP API, it ensures structured, accurate data with additional insights like EPS/revenue estimates. The multi-environment support makes it flexible for CLI, Desktop, and Web usage, while the fallback mode ensures functionality even without API access.

**Key Workflow**: Date Calculation → API Key Setup → API Data Retrieval → Processing → Report Generation → QA → Delivery

**Output**: Clean, organized markdown report with earnings grouped by date/timing/market cap, including summary statistics and trading considerations.
