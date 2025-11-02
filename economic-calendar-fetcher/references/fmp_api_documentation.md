# FMP Economic Calendar API Documentation

## Overview

The Financial Modeling Prep (FMP) Economic Calendar API provides access to upcoming and historical economic data releases, central bank decisions, and other market-moving events. This API enables traders and investors to stay informed about scheduled economic events that may impact financial markets.

## API Endpoint

```
https://financialmodelingprep.com/api/v3/economic_calendar
```

## Authentication

API access requires a valid FMP API key, which must be included as a query parameter in all requests.

**Parameter:** `apikey`
**Format:** String
**Required:** Yes

### Obtaining an API Key

1. Visit https://financialmodelingprep.com
2. Sign up for an account (free and paid tiers available)
3. Navigate to the API dashboard to view your API key
4. Free tier allows limited requests per day (~250-300 requests)
5. Paid tiers offer higher rate limits and additional features

## Request Parameters

### Required Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `from` | date | Start date for calendar period | `2025-01-01` |
| `to` | date | End date for calendar period | `2025-01-31` |
| `apikey` | string | Your FMP API key | `YOUR_API_KEY` |

### Date Format

- **Format:** `YYYY-MM-DD` (ISO 8601 date format)
- **Example:** `2025-07-20`
- **Maximum Range:** 90 days between `from` and `to` dates
- **Timezone:** All dates are in UTC

### Date Range Limitations

- Minimum range: 1 day
- Maximum range: 90 days
- Past dates: API returns historical events with actual values
- Future dates: API returns scheduled events with estimates (actual values will be null)

## Response Format

The API returns a JSON array of economic event objects.

### Response Structure

```json
[
    {
        "date": "2024-03-01 03:35:00",
        "country": "JP",
        "event": "3-Month Bill Auction",
        "currency": "JPY",
        "previous": -0.112,
        "estimate": null,
        "actual": -0.096,
        "change": 0.016,
        "impact": "Low",
        "changePercentage": 14.286
    }
]
```

### Response Fields

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `date` | string | Event date and time in UTC (format: `YYYY-MM-DD HH:MM:SS`) | No |
| `country` | string | ISO 2-letter country code (e.g., `US`, `JP`, `GB`, `EU`) | No |
| `event` | string | Name/description of the economic event | No |
| `currency` | string | ISO 3-letter currency code (e.g., `USD`, `EUR`, `JPY`) | No |
| `previous` | number | Previous reading/value for this indicator | Yes |
| `estimate` | number | Market consensus estimate/forecast | Yes |
| `actual` | number | Actual released value (null for future events) | Yes |
| `change` | number | Absolute change from previous reading | Yes |
| `impact` | string | Market impact level: `"High"`, `"Medium"`, `"Low"` | No |
| `changePercentage` | number | Percentage change from previous reading | Yes |

### Field Details

**`date`:**
- Format: `YYYY-MM-DD HH:MM:SS` in UTC timezone
- Represents the scheduled release time for the economic data
- For future events, this is the expected release time
- Times may be adjusted if releases are delayed

**`country`:**
- ISO 3166-1 alpha-2 country codes
- Special codes:
  - `EU`: European Union (ECB-related events)
  - `G7`: G7 summit/collaborative events
  - International organizations may use special codes

**`event`:**
- Descriptive name of the economic indicator or event
- Examples:
  - `"Non-Farm Payrolls"`
  - `"Consumer Price Index (CPI)"`
  - `"Federal Funds Rate Decision"`
  - `"GDP Growth Rate QoQ"`
  - `"Unemployment Rate"`

**`currency`:**
- ISO 4217 currency codes
- Indicates which currency's economy the event affects
- May differ from country (e.g., EU events affect EUR across multiple countries)

**`previous`:**
- The last reported value for this indicator
- Used as baseline for comparing current release
- May be revised from originally reported value
- `null` if no prior data available (new indicator)

**`estimate`:**
- Market consensus forecast compiled from analyst surveys
- Typically from Bloomberg, Reuters, or other consensus services
- `null` if no consensus exists or for less-watched indicators
- Comparing `actual` to `estimate` shows "surprise" factor

**`actual`:**
- The officially released value when data is published
- `null` for future events (not yet released)
- This is the critical field that moves markets when released
- May be revised in subsequent releases (preliminary → final revisions)

**`change`:**
- Calculated as: `actual - previous` (for past events)
- `null` if either `actual` or `previous` is null
- Sign indicates direction: positive = increase, negative = decrease
- Absolute value, not percentage

**`impact`:**
- Qualitative assessment of market-moving potential
- Three levels:
  - `"High"`: Major market-moving events (NFP, FOMC, CPI)
  - `"Medium"`: Significant but less volatile (Retail Sales, PMI)
  - `"Low"`: Minor indicators, routine data releases
- Determined by FMP based on historical volatility impact

**`changePercentage`:**
- Calculated as: `((actual - previous) / previous) * 100`
- `null` if either value is null or if `previous` is zero
- Percentage representation of the change
- Useful for comparing relative magnitude across different indicators

## Example Requests

### Fetch Events for Next 7 Days

```bash
curl "https://financialmodelingprep.com/api/v3/economic_calendar?from=2025-01-01&to=2025-01-07&apikey=YOUR_API_KEY"
```

### Fetch High-Impact Events Only (Post-Processing)

Note: API does not have an `impact` filter parameter, so filtering must be done after retrieval.

```python
import requests

response = requests.get(
    "https://financialmodelingprep.com/api/v3/economic_calendar",
    params={
        "from": "2025-01-01",
        "to": "2025-01-31",
        "apikey": "YOUR_API_KEY"
    }
)

events = response.json()
high_impact_events = [e for e in events if e["impact"] == "High"]
```

### Fetch Events for Specific Country (Post-Processing)

```python
us_events = [e for e in events if e["country"] == "US"]
eu_events = [e for e in events if e["country"] == "EU"]
```

## Rate Limits

Rate limits depend on your FMP subscription tier:

| Tier | Requests/Day | Requests/Second |
|------|--------------|-----------------|
| Free | 250 | 5 |
| Starter | 500 | 10 |
| Professional | 1,000+ | 20+ |

If you exceed rate limits, the API returns HTTP 429 (Too Many Requests).

## Error Handling

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | Success | Request successful, data returned |
| 400 | Bad Request | Invalid parameters (malformed dates, missing required params) |
| 401 | Unauthorized | Invalid or missing API key |
| 403 | Forbidden | API key valid but lacks permission (expired subscription) |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | FMP server error (retry after delay) |

### Error Response Format

```json
{
    "Error Message": "Invalid API KEY. Please retry or visit our documentation to create one FREE https://financialmodelingprep.com/developer/docs"
}
```

### Common Errors

**Invalid API Key:**
```json
{"Error Message": "Invalid API KEY..."}
```
**Solution:** Verify API key is correct, active subscription

**Date Range Too Large:**
```json
{"Error Message": "Maximum date range is 90 days"}
```
**Solution:** Reduce date range to 90 days or less

**Rate Limit Exceeded:**
- HTTP 429 response
**Solution:** Wait before next request, upgrade subscription tier

## Best Practices

### 1. Respect Rate Limits

Implement exponential backoff for retries:
```python
import time

def fetch_with_retry(url, params, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, params=params)
        if response.status_code == 429:
            wait_time = 2 ** attempt  # Exponential backoff
            time.sleep(wait_time)
            continue
        return response
    raise Exception("Max retries exceeded")
```

### 2. Cache Results

Economic calendar data doesn't change frequently once released:
- Cache past events indefinitely (actual values don't change)
- Cache future events for 1-24 hours (estimates rarely change)
- Refresh cache after event release time passes

### 3. Efficient Date Ranges

- Query 7-30 day ranges to minimize API calls
- Don't query dates more than 3-6 months in future (sparse data)
- Use smaller ranges (1-7 days) for real-time monitoring

### 4. Handle Null Values

Many fields can be `null`, especially for future events:
```python
event_value = event.get("actual") or event.get("estimate") or event.get("previous")
if event_value is None:
    print("No value available for this event")
```

### 5. Time Zone Awareness

All API times are UTC:
```python
from datetime import datetime, timezone

utc_time = datetime.strptime(event["date"], "%Y-%m-%d %H:%M:%S")
utc_time = utc_time.replace(tzinfo=timezone.utc)

# Convert to local timezone
local_time = utc_time.astimezone()
```

## Data Accuracy and Timeliness

### Release Time Accuracy

- Most release times accurate within ±1 minute
- Delayed releases possible (technical issues, holidays)
- Times may shift due to daylight saving time changes

### Data Revisions

Economic data is often revised:
- **Preliminary:** First release (most market impact)
- **Revised:** 1-2 months later
- **Final:** 2-3 months later

The API `previous` field reflects the latest revised value, not necessarily the original preliminary release.

### Coverage

FMP Economic Calendar covers:
- **Major Economies:** US, EU, UK, Japan, China, Canada, Australia
- **Event Types:**
  - Employment data (NFP, unemployment rate)
  - Inflation (CPI, PPI, PCE)
  - Growth (GDP, retail sales, industrial production)
  - Central bank decisions (FOMC, ECB, BOJ, BOE)
  - Surveys (PMI, consumer confidence, sentiment indices)
  - Trade data (trade balance, exports/imports)
  - Housing data (starts, permits, sales)

## Comparison with Other Sources

| Feature | FMP API | Forex Factory | Investing.com |
|---------|---------|---------------|---------------|
| API Access | Yes | No (scraping only) | No (scraping only) |
| Historical Data | Yes | Limited | Yes (web only) |
| Free Tier | Yes (250/day) | N/A | N/A |
| Data Format | JSON | HTML | HTML |
| Reliability | High | Medium (changes) | Medium (changes) |

FMP is a reliable, legitimate API source compared to scraping financial calendar websites (which violates ToS and is fragile).

## Support and Documentation

- **Official Docs:** https://financialmodelingprep.com/developer/docs/economic-calendar-api
- **API Status:** https://status.financialmodelingprep.com
- **Support:** support@financialmodelingprep.com
- **Community:** Active Discord and forum for FMP users
