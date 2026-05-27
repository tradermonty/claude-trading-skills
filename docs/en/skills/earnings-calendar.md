---
layout: default
title: "Earnings Calendar"
grand_parent: English
parent: Skill Guides
nav_order: 19
lang_peer: /ja/skills/earnings-calendar/
permalink: /en/skills/earnings-calendar/
---

# Earnings Calendar
{: .no_toc }

This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API. Use this when the user requests earnings calendar data, wants to know which companies are reporting earnings in the upcoming week, or needs a weekly earnings review. The skill focuses on mid-cap and above companies (over $2B market cap) that have significant market impact, organizing the data by date and timing in a clean markdown table format. Supports multiple environments (CLI, Desktop, Web) with flexible API key management.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/earnings-calendar.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/earnings-calendar){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API. It focuses on companies with significant market capitalization (mid-cap and above, over $2B) that are likely to impact market movements. The skill generates organized markdown reports showing which companies are reporting earnings over the next week, grouped by date and timing (before market open, after market close, or time not announced).

**Key Features**:
- Uses FMP API for reliable, structured earnings data
- Filters by market cap (>$2B) to focus on market-moving companies
- Includes EPS and revenue estimates
- Multi-environment support (CLI, Desktop, Web)
- Flexible API key management
- Organized by date, timing, and market cap

---

## 2. Prerequisites

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

---

## 3. Quick Start

```bash
# Default: next 7 days, market cap > $2B
python3 earnings-calendar/scripts/fetch_earnings_fmp.py --api-key YOUR_KEY

# Custom date range
python3 earnings-calendar/scripts/fetch_earnings_fmp.py \
  --from 2025-11-01 --to 2025-11-07 \
  --api-key YOUR_KEY
```

---

## 4. Workflow

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

---

## 5. Resources

**References:**

- `skills/earnings-calendar/references/fmp_api_guide.md`

**Scripts:**

- `skills/earnings-calendar/scripts/fetch_earnings_fmp.py`
- `skills/earnings-calendar/scripts/generate_report.py`
