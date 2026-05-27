---
layout: default
title: "Economic Calendar Fetcher"
grand_parent: English
parent: Skill Guides
nav_order: 21
lang_peer: /ja/skills/economic-calendar-fetcher/
permalink: /en/skills/economic-calendar-fetcher/
---

# Economic Calendar Fetcher
{: .no_toc }

Fetch upcoming economic events and data releases using FMP API. Retrieve scheduled central bank decisions, employment reports, inflation data, GDP releases, and other market-moving economic indicators for specified date ranges (default: next 7 days). The script outputs raw JSON or text; the assistant filters, assesses impact, and generates the Markdown report.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/economic-calendar-fetcher.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/economic-calendar-fetcher){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Retrieve upcoming economic events and data releases from the Financial Modeling Prep (FMP) Economic Calendar API. This skill fetches scheduled economic indicators including central bank monetary policy decisions, employment reports, inflation data (CPI/PPI), GDP releases, retail sales, manufacturing data, and other market-moving events that impact financial markets.

The skill uses a Python script to query the FMP API and returns raw JSON or text output. The assistant then filters events, assesses market impact, and generates a chronological Markdown report for each scheduled event. No files are generated automatically.

**Key Capabilities:**
- Fetch economic events for specified date ranges (max 90 days)
- Support flexible API key provision (environment variable or CLI argument)
- Filter by impact level, country, or event type (filtering performed by the assistant)
- Present filtered results as structured Markdown reports with impact analysis (assistant-generated, not script-generated)
- Default to next 7 days for quick market outlook

**Data Source:**
- FMP Economic Calendar API: `https://financialmodelingprep.com/api/v3/economic_calendar`
- Covers major economies: US, EU, UK, Japan, China, Canada, Australia
- Event types: Central bank decisions, employment, inflation, GDP, trade, housing, surveys

---

## 2. When to Use

Use this skill when the user requests:

1. **Economic Calendar Queries:**
   - "What economic events are coming up this week?"
   - "Show me the economic calendar for the next two weeks"
   - "When is the next FOMC meeting?"
   - "What major economic data is being released next month?"

2. **Market Event Planning:**
   - "What should I watch for in the markets this week?"
   - "Are there any high-impact economic releases coming?"
   - "When is the next jobs report / CPI release / GDP report?"

3. **Specific Date Range Requests:**
   - "Get economic events from January 1 to January 31"
   - "What's on the economic calendar for Q1 2025?"

4. **Country-Specific Queries:**
   - "Show me US economic data releases next week"
   - "What ECB events are scheduled?"
   - "When is Japan releasing their inflation data?"

**DO NOT use this skill for:**
- Past economic events (use market-news-analyst for historical analysis)
- Corporate earnings calendars (this skill excludes earnings)
- Real-time market data or live quotes
- Technical analysis or chart interpretation

---

## 3. Prerequisites

- **FMP API Key** (required): Sign up at https://financialmodelingprep.com for a free key (250 requests/day). Set via `FMP_API_KEY` environment variable or pass `--api-key` to the script.
- **Python 3.10+**: Required to run `skills/economic-calendar-fetcher/scripts/get_economic_calendar.py`.
- **No third-party packages**: The script uses only the Python standard library.

---

## 4. Quick Start

```bash
# Default: next 7 days
python3 economic-calendar-fetcher/scripts/get_economic_calendar.py --api-key YOUR_KEY

# Specific date range (max 90 days)
python3 economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-11-01 --to 2025-11-30 \
  --api-key YOUR_KEY \
  --format json
```

---

## 5. Workflow

Follow these steps to fetch and analyze the economic calendar:

### Step 1: Obtain FMP API Key

**Check for API key availability (in priority order):**

1. **Recommended:** Check if `FMP_API_KEY` environment variable is set — this keeps the key out of session logs
2. **Acceptable:** Use `--api-key` CLI argument for one-off runs
3. **Not recommended:** Asking the user to paste the key into chat — session logs may retain it
4. If user doesn't have an API key, provide instructions:
   - Visit https://financialmodelingprep.com
   - Sign up for free account (250 requests/day limit)
   - Navigate to API dashboard to obtain key

**Example user interaction:**
```
User: "Show me economic events for next week"
Assistant: "I'll fetch the economic calendar. I'll use the FMP_API_KEY environment variable if it's set. Otherwise, please pass the key via --api-key when running the script."
```

### Step 2: Determine Date Range

**Set appropriate date range based on user request:**

**Default (no specific dates):** Today + 7 days
**User specifies period:** Use exact dates (validate format: YYYY-MM-DD)
**Maximum range:** 90 days (FMP API limitation)

**Examples:**
- "Next week" → Today to +7 days
- "Next two weeks" → Today to +14 days
- "January 2025" → 2025-01-01 to 2025-01-31
- "Q1 2025" → 2025-01-01 to 2025-03-31

**Validate date range:**
- Ensure start date ≤ end date
- Ensure range ≤ 90 days
- Warn if querying past dates

### Step 3: Execute API Fetch Script

**Run the get_economic_calendar.py script with appropriate parameters:**

**Basic usage (default 7 days):**
```bash
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py --api-key YOUR_KEY
```

**With specific date range:**
```bash
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-01-01 \
  --to 2025-01-31 \
  --api-key YOUR_KEY \
  --format json
```

**Using environment variable (no --api-key needed):**
```bash
export FMP_API_KEY=your_key_here
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-01-01 \
  --to 2025-01-07
```

**Script parameters:**
- `--from`: Start date (YYYY-MM-DD) - default: today
- `--to`: End date (YYYY-MM-DD) - default: today + 7 days
- `--api-key`: FMP API key (optional if FMP_API_KEY env var set)
- `--format`: Output format (json or text) - default: json
- `--output`: Output file path (optional, default: stdout)

**Handle errors:**
- Invalid API key → Ask user to verify key
- Rate limit exceeded (429) → Suggest waiting or upgrading FMP tier
- Network errors → Check your connection and re-run the script
- Invalid date format → Provide correct format example

### Step 4: Parse and Filter Events

**Process the JSON response from the script:**

1. **Parse event data:** Extract all events from API response
2. **Apply user filters if specified:**
   - Impact level: "High", "Medium", "Low"
   - Country: "US", "EU", "JP", "CN", etc.
   - Event type: FOMC, CPI, Employment, GDP, etc.
   - Currency: USD, EUR, JPY, etc.

**Filter examples:**
- "Show only high-impact events" → Filter impact == "High"
- "US events only" → Filter country == "US"
- "Central bank decisions" → Search event name for "Rate", "Policy", "FOMC", "ECB", "BOJ"

**Event data structure:**
```json
{
  "date": "2025-01-15 14:30:00",
  "country": "US",
  "event": "Consumer Price Index (CPI) YoY",
  "currency": "USD",
  "previous": 2.6,
  "estimate": 2.7,
  "actual": null,
  "change": null,
  "impact": "High",
  "changePercentage": null
}
```

### Step 5: Assess Market Impact

**Evaluate the market significance of each event:**

**Impact Level Classification (from FMP):**
- **High Impact:** Major market-moving events
  - FOMC rate decisions, ECB/BOJ policy meetings
  - Non-Farm Payrolls (NFP), CPI, GDP
  - Market typically shows 0.5-2%+ intraday volatility

- **Medium Impact:** Significant but less volatile
  - Retail Sales, Industrial Production
  - PMI surveys, Consumer Confidence
  - Housing data, Durable Goods Orders

- **Low Impact:** Minor indicators
  - Weekly jobless claims (unless extreme)
  - Regional manufacturing surveys
  - Minor auction results

**Additional Context Factors:**

1. **Current Market Sensitivity:**
   - High inflation environment → CPI/PPI elevated importance
   - Recession fears → Employment data more critical
   - Rate cut speculation → Central bank meetings crucial

2. **Surprise Potential:**
   - Compare estimate vs. previous reading
   - Large expected changes = higher attention
   - Consensus uncertainty = higher impact potential

3. **Event Clustering:**
   - Multiple related events same day = amplified impact
   - Example: CPI + Retail Sales + Fed speech = Very High impact day

4. **Forward Significance:**
   - Does this event influence upcoming central bank decisions?
   - Is this a preliminary or final reading?
   - Will this data be revised?

### Step 6: Generate Output Report

> **Responsibility:** The script outputs raw JSON or text. This step is performed by the assistant using the script's output. No Markdown files are generated automatically; results are displayed in chat and can be saved to `reports/` on request.

**Create structured markdown report with the following sections:**

**Report Header:**
```markdown
# Economic Calendar
**Period:** [Start Date] to [End Date]
**Report Generated:** [Timestamp]
**Total Events:** [Count]
**High Impact Events:** [Count]
```

**Event Listing (Chronological):**

For each event, provide:

```markdown

---

## 6. Resources

**References:**

- `skills/economic-calendar-fetcher/references/fmp_api_documentation.md`

**Scripts:**

- `skills/economic-calendar-fetcher/scripts/get_economic_calendar.py`
