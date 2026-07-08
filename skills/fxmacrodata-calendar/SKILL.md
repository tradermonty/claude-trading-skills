---
name: fxmacrodata-calendar
description: Fetch official FXMacroData macro release-calendar events for trade planning, macro regime checks, and event-risk filters. Use before CPI, NFP, GDP, PCE, retail sales, PMI, and central-bank decision windows.
---

# FXMacroData Calendar

Retrieve official-source macro release-calendar events from FXMacroData. Use
this skill when a trade plan needs event timing, confirmed release dates, or a
top-tier macro risk check.

## Workflow

1. Run the calendar script:

   ```bash
   python3 skills/fxmacrodata-calendar/scripts/fetch_calendar.py --currency usd --min-tier 1
   ```

2. Review `events[]` for top-tier releases.

3. Fold the event timing into the trade plan:
   - pause new entries around high-impact releases;
   - reduce leverage or position size;
   - schedule follow-up review after the actual value is available;
   - explain which event and timestamp drove the adjustment.

## Authentication

Set `FXMACRODATA_API_KEY` for authenticated FXMacroData endpoints. Public USD
calendar rows can be fetched without a key.
