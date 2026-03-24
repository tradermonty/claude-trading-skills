---
name: earnings-calendar
description: "This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API. Use this when the user requests earnings calendar data, wants to know which companies are reporting earnings in the upcoming week, or needs a weekly earnings review. The skill focuses on mid-cap and above companies (over $2B market cap) that have significant market impact, organizing the data by date and timing in a clean markdown table format. Supports multiple environments (CLI, Desktop, Web) with flexible API key management."
---

# Earnings Calendar

Retrieve upcoming US stock earnings announcements via FMP API, filtered to mid-cap+ (>$2B market cap), organized by date and timing (BMO/AMC/TAS) in markdown tables with EPS and revenue estimates.

## Prerequisites

- **FMP API Key** — Free tier (250 calls/day) is sufficient
  - Sign up: https://site.financialmodelingprep.com/developer/docs
  - Set via `export FMP_API_KEY="your-key"` (CLI) or provide at runtime (Desktop/Web)

## Workflow

### Step 1: Calculate Date Range

1. Get current date from the environment (`<env>` tag or system date).
2. Set target range: **next 7 days** from today, formatted as `YYYY-MM-DD`.

### Step 2: Load API Reference

Read `references/fmp_api_guide.md` for endpoint details, authentication, market cap filtering strategy, and earnings timing conventions.

### Step 3: Obtain API Key

1. Check `$FMP_API_KEY` environment variable.
2. If unset, prompt the user via AskUserQuestion with options: provide key, get free key instructions, or skip to fallback (Step 6).
3. Store key in session variable only — never persist to disk.

> **On auth failure (401):** Re-prompt for API key. On rate limit (429): inform user of 250/day limit, suggest waiting or upgrading.

### Step 4: Fetch and Process Earnings Data

Run the fetch script with calculated date range:

```bash
python scripts/fetch_earnings_fmp.py <START_DATE> <END_DATE> "${API_KEY}" > earnings_data.json
```

The script automatically:
- Calls FMP Earnings Calendar API
- Fetches company profiles (market cap, sector, industry)
- Filters to market cap >$2B
- Normalizes timing to BMO/AMC/TAS
- Sorts by date, then timing, then market cap descending
- Outputs JSON array with fields: `symbol`, `companyName`, `date`, `timing`, `marketCap`, `marketCapFormatted`, `sector`, `industry`, `epsEstimated`, `revenueEstimated`, `fiscalDateEnding`, `exchange`

> **On empty results:** Widen date range to 14 days and retry. If still empty, note that no earnings are scheduled and proceed to delivery.
> **On connection error:** Retry once, then fall back to Step 6.

### Step 5: Generate Report

```bash
python scripts/generate_report.py earnings_data.json earnings_calendar_<TODAY>.md
```

The script produces a markdown report with:
- **Header**: date range, data source, total company count
- **Executive summary**: total companies, mega/large-cap vs mid-cap counts, peak day
- **Daily sections**: grouped by date, sub-grouped by timing (BMO → AMC → TAS), sorted by market cap descending within each group
- **Tables**: Ticker | Company | Market Cap | Sector | EPS Est. | Revenue Est.
- **Key observations**: top 5 by market cap, sector distribution, trading considerations (heavy volume days, pre-market/after-hours movers)
- **Timing reference**: BMO (6-8 AM ET), AMC (4-5 PM ET), TAS (undisclosed)
- **Data notes**: market cap tiers (Mega >$200B, Large $10B-$200B, Mid $2B-$10B), filter criteria, freshness disclaimer

See `assets/earnings_report_template.md` for the full template structure.

### Quality Checks (before delivery)

Verify:
- All dates fall within target week
- Every company has timing (BMO/AMC/TAS) and market cap
- Companies sorted by market cap within each section
- Summary statistics match the data
- No placeholder text remains
- Markdown tables render correctly

### Step 6: Deliver Report

Save as `earnings_calendar_<YYYY-MM-DD>.md` (date = report generation date) and present a brief summary highlighting total count, peak day, and top companies.

## Fallback Mode (No API)

If API is unavailable, direct user to gather data manually from:
- Finviz: `https://finviz.com/screener.ashx?v=111&f=cap_midover%2Cearningsdate_nextweek`
- Yahoo Finance: `https://finance.yahoo.com/calendar/earnings`

Accept user-provided data, process it using the same grouping/sorting logic, and generate the report with "Data Source: Manual Entry" noted.

## Resources

- **API guide**: `references/fmp_api_guide.md`
- **Fetch script**: `scripts/fetch_earnings_fmp.py`
- **Report generator**: `scripts/generate_report.py`
- **Report template**: `assets/earnings_report_template.md`
- **FMP Earnings API docs**: https://site.financialmodelingprep.com/developer/docs/earnings-calendar-api
