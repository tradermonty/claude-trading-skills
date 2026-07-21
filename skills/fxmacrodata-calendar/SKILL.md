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

   Treat a nonzero exit as an unverified event-risk state, never as an empty
   calendar. Only a successful response containing `events: []` establishes
   that no matching events were returned. The client accepts results only when
   the response currency matches the request and `data_quality` confirms an
   official, current, non-proxy, non-fallback, timestamp-complete,
   point-in-time-safe source. Each event must include an announcement timestamp
   and a non-empty release identifier.

3. Fold the event timing into the trade plan:
   - pause new entries around high-impact releases;
   - reduce leverage or position size;
   - schedule follow-up review after the actual value is available;
   - explain which event and timestamp drove the adjustment.

## Authentication

Set `FXMACRODATA_API_KEY` for authenticated FXMacroData endpoints. Public USD
calendar rows can be fetched without a key. The client uses the canonical
`https://api.fxmacrodata.com/v1` endpoint and accepts `--min-tier` values 1,
2, or 3 only. Live calendar responses currently include `market_tier`; the
skill treats it as an extension field and requires integer values 1 through 3
for filtering, although the current `CalendarReleaseRow` OpenAPI schema does
not declare that field.
