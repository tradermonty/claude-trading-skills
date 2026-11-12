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

**Multi-Environment API Key Detection**: Read `references/api_key_setup_flow.md` when no `FMP_API_KEY` environment variable is found. It holds the environment check, the AskUserQuestion prompt, the free-key instructions and the session-only key handling.

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

Once earnings data is retrieved (JSON format), process and organize it: Read `references/data_processing_steps.md` when parsing and organizing the fetched earnings JSON (steps 5.1 to 5.6).

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

**Report Structure**: Read `references/report_template.md` for the full markdown report structure.

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

Read `references/use_cases.md` for four worked use cases: weekly review, a specific day, mega-cap focus, sector focus.

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
- Install the skill's dependencies: `pip install -r skills/earnings-calendar/requirements.txt` (a missing `requests` makes the script print "ERROR: requests library not found" to stderr and exit with status 2, with the full `requirements.txt` path in the message)
- Check script has execute permissions: `chmod +x fetch_earnings_fmp.py`
- Run with python3 explicitly: `python3 fetch_earnings_fmp.py ...`

## Best Practices

Read `references/best_practices_and_security.md` (section "Best Practices") for the Do's and Don'ts list.

## Security Notes

Read `references/best_practices_and_security.md` (section "Security Notes: API Key Security") for API key handling guidance per environment.

## Resources

Read `references/resource_links.md` for FMP documentation links, supplementary sources and the skill resource list.

---

## Summary

This skill provides a reliable, API-driven approach to generating weekly earnings calendars for US stocks. By using FMP API, it ensures structured, accurate data with additional insights like EPS/revenue estimates. The multi-environment support makes it flexible for CLI, Desktop, and Web usage, while the fallback mode ensures functionality even without API access.

**Key Workflow**: Date Calculation → API Key Setup → API Data Retrieval → Processing → Report Generation → QA → Delivery

**Output**: Clean, organized markdown report with earnings grouped by date/timing/market cap, including summary statistics and trading considerations.
