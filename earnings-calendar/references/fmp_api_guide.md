# FMP Earnings Calendar API Guide

This reference provides guidance on using the Financial Modeling Prep (FMP) Earnings Calendar API to retrieve upcoming earnings announcements for US stocks.

## FMP API Overview

Financial Modeling Prep (FMP) provides a comprehensive financial data API with earnings calendar endpoints that return structured JSON data including announcement dates, EPS estimates, revenue estimates, and actual results for publicly traded companies.

**Official Documentation**: https://site.financialmodelingprep.com/developer/docs/earnings-calendar-api

## API Endpoint

**Earnings Calendar Endpoint**:
```
https://financialmodelingprep.com/api/v3/earning_calendar
```

### Authentication

FMP API requires an API key for authentication:
```
https://financialmodelingprep.com/api/v3/earning_calendar?apikey=YOUR_API_KEY&from=2025-11-03&to=2025-11-09
```

**Getting an API Key**:
- Free tier: https://site.financialmodelingprep.com/developer/docs
- Sign up for free account
- Receive API key immediately
- Free tier: 250 API calls/day

## Request Parameters

### Required Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `apikey` | string | Your FMP API key | `YOUR_API_KEY` |
| `from` | date | Start date (YYYY-MM-DD) | `2025-11-03` |
| `to` | date | End date (YYYY-MM-DD) | `2025-11-09` |

### Constraints

- **Maximum Records**: 4000 records per request
- **Maximum Date Range**: 90 days
- **Rate Limiting**: Free tier = 250 calls/day, Premium = 750-2500 calls/day
- **Date Format**: YYYY-MM-DD (ISO 8601)

### Example Request

```bash
curl "https://financialmodelingprep.com/api/v3/earning_calendar?apikey=YOUR_KEY&from=2025-11-03&to=2025-11-09"
```

## Response Format

### JSON Structure

```json
[
    {
        "symbol": "AAPL",
        "date": "2025-11-04",
        "eps": null,
        "epsEstimated": 1.54,
        "time": "amc",
        "revenue": null,
        "revenueEstimated": 123400000000,
        "fiscalDateEnding": "2025-09-30",
        "updatedFromDate": "2025-11-01"
    },
    {
        "symbol": "MSFT",
        "date": "2025-11-05",
        "eps": null,
        "epsEstimated": 2.75,
        "time": "amc",
        "revenue": null,
        "revenueEstimated": 56200000000,
        "fiscalDateEnding": "2025-09-30",
        "updatedFromDate": "2025-11-02"
    }
]
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | string | Stock ticker symbol |
| `date` | string | Earnings announcement date (YYYY-MM-DD) |
| `eps` | number/null | Actual EPS (null if not yet announced) |
| `epsEstimated` | number | Estimated EPS by analysts |
| `time` | string | Timing: "bmo" (before market open), "amc" (after market close), "tba" (to be announced) |
| `revenue` | number/null | Actual revenue (null if not yet announced) |
| `revenueEstimated` | number | Estimated revenue by analysts |
| `fiscalDateEnding` | string | Fiscal period ending date |
| `updatedFromDate` | string | Last update date for this entry |

## Timing Conventions

### BMO (Before Market Open)
- API value: `"bmo"` or `"pre-market"`
- Announced before US market opens at 9:30 AM ET
- Typically around 6:00-8:00 AM ET
- **Impact**: Provides time for market to digest before trading begins

### AMC (After Market Close)
- API value: `"amc"` or `"after-market"`
- Announced after US market closes at 4:00 PM ET
- Typically around 4:00-5:00 PM ET
- **Impact**: Overnight reaction, gap up/down at next day's open

### TBA (To Be Announced)
- API value: `"tba"` or `null`
- Specific time not yet announced
- Could be BMO or AMC
- Monitor company investor relations for updates

## Filtering by Market Cap

FMP API doesn't provide market cap in the earnings calendar endpoint. To filter by market cap:

### Option 1: Use Company Profile API (Recommended)

**Step 1**: Get earnings calendar data
```
GET /api/v3/earning_calendar?apikey=KEY&from=2025-11-03&to=2025-11-09
```

**Step 2**: For each symbol, fetch market cap from profile endpoint
```
GET /api/v3/profile/{symbol}?apikey=KEY
```

Response includes:
```json
{
    "symbol": "AAPL",
    "companyName": "Apple Inc.",
    "mktCap": 3000000000000,
    "sector": "Technology",
    "industry": "Consumer Electronics"
}
```

**Step 3**: Filter companies with `mktCap > 2000000000` ($2B+)

### Option 2: Use Batch Profile API (More Efficient)

Request profiles for multiple symbols in one call:
```
GET /api/v3/profile/AAPL,MSFT,GOOGL,AMZN?apikey=KEY
```

This reduces API calls significantly.

## Python Implementation Strategy

### Basic Request

```python
import requests
from datetime import datetime, timedelta

def fetch_earnings_calendar(api_key, start_date, end_date):
    """
    Fetch earnings calendar from FMP API

    Args:
        api_key: FMP API key
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        List of earnings announcements
    """
    url = "https://financialmodelingprep.com/api/v3/earning_calendar"
    params = {
        "apikey": api_key,
        "from": start_date,
        "to": end_date
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    return response.json()

# Usage
api_key = "YOUR_API_KEY"
earnings = fetch_earnings_calendar(api_key, "2025-11-03", "2025-11-09")
```

### With Market Cap Filtering

```python
def fetch_company_profiles(api_key, symbols):
    """
    Fetch company profiles for multiple symbols (batch)

    Args:
        api_key: FMP API key
        symbols: List of ticker symbols

    Returns:
        Dictionary mapping symbol to profile data
    """
    # Batch symbols (max 100 per request)
    batch_size = 100
    profiles = {}

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        symbols_str = ",".join(batch)

        url = f"https://financialmodelingprep.com/api/v3/profile/{symbols_str}"
        params = {"apikey": api_key}

        response = requests.get(url, params=params)
        response.raise_for_status()

        for profile in response.json():
            profiles[profile["symbol"]] = profile

    return profiles

def filter_by_market_cap(earnings, profiles, min_market_cap=2000000000):
    """
    Filter earnings by minimum market cap ($2B default)

    Args:
        earnings: List of earnings announcements
        profiles: Dictionary of company profiles
        min_market_cap: Minimum market cap in dollars

    Returns:
        Filtered list of earnings for mid-cap+ companies
    """
    filtered = []

    for earning in earnings:
        symbol = earning["symbol"]
        profile = profiles.get(symbol)

        if profile and profile.get("mktCap", 0) >= min_market_cap:
            # Merge earnings data with profile data
            earning["marketCap"] = profile["mktCap"]
            earning["companyName"] = profile.get("companyName", symbol)
            earning["sector"] = profile.get("sector", "N/A")
            earning["industry"] = profile.get("industry", "N/A")
            filtered.append(earning)

    return filtered

# Complete workflow
api_key = "YOUR_API_KEY"

# Step 1: Get earnings calendar
earnings = fetch_earnings_calendar(api_key, "2025-11-03", "2025-11-09")

# Step 2: Get company profiles
symbols = [e["symbol"] for e in earnings]
profiles = fetch_company_profiles(api_key, symbols)

# Step 3: Filter by market cap (>$2B)
filtered_earnings = filter_by_market_cap(earnings, profiles)
```

## API Key Management - Multi-Environment Support

### Environment 1: Claude Code (CLI)

Set environment variable:
```bash
export FMP_API_KEY="your-api-key-here"
```

Access in Python:
```python
import os
api_key = os.environ.get('FMP_API_KEY')
```

### Environment 2: Claude Desktop

Configure MCP server settings or use environment variable in system.

### Environment 3: Claude Web

API key cannot be stored persistently. Request from user during execution:

**Workflow**:
1. Check for environment variable
2. If not found, prompt user: "Please provide your FMP API key"
3. Store in session variable for current conversation
4. Use for all API calls in this session

**Security Note**:
- Key stored only in conversation context
- Forgotten when session ends
- User should use free tier or limited-scope keys

## Error Handling

### Common Errors

**401 Unauthorized**:
```json
{
    "Error Message": "Invalid API KEY. Please retry or visit our documentation to create one FREE https://site.financialmodelingprep.com/developer/docs"
}
```
Solution: Verify API key is correct

**429 Rate Limit Exceeded**:
```json
{
    "Error Message": "Limit Reach. Please upgrade your plan or visit our documentation for more details at https://site.financialmodelingprep.com/developer/docs"
}
```
Solution: Reduce API calls or upgrade plan

**400 Bad Request**:
- Invalid date format
- Date range exceeds 90 days
- Missing required parameters

### Error Handling Code

```python
def fetch_earnings_with_error_handling(api_key, start_date, end_date):
    """Fetch earnings with proper error handling"""
    try:
        url = "https://financialmodelingprep.com/api/v3/earning_calendar"
        params = {
            "apikey": api_key,
            "from": start_date,
            "to": end_date
        }

        response = requests.get(url, params=params, timeout=30)

        # Check for API errors
        if response.status_code == 401:
            print("ERROR: Invalid API key")
            print("Get free API key: https://site.financialmodelingprep.com/developer/docs")
            return None

        if response.status_code == 429:
            print("ERROR: Rate limit exceeded")
            print("Free tier: 250 calls/day. Consider upgrading.")
            return None

        response.raise_for_status()
        data = response.json()

        # Check if response is error message
        if isinstance(data, dict) and "Error Message" in data:
            print(f"API Error: {data['Error Message']}")
            return None

        return data

    except requests.exceptions.Timeout:
        print("ERROR: Request timeout. Please try again.")
        return None

    except requests.exceptions.ConnectionError:
        print("ERROR: Connection error. Check your internet connection.")
        return None

    except Exception as e:
        print(f"ERROR: Unexpected error: {str(e)}")
        return None
```

## Data Quality Considerations

### Accuracy
- FMP data is generally reliable for earnings dates
- EPS and revenue estimates updated regularly from analyst consensus
- Companies can change dates last-minute; verify critical dates

### Completeness
- Covers most US publicly traded companies
- Some smaller companies may have limited data
- Pre-IPO companies won't appear until trading begins

### Timeliness
- API updated regularly throughout the day
- Earnings dates typically known 2-4 weeks in advance
- Some companies announce dates very close to earnings (1-2 days prior)

### Data Freshness
- Check `updatedFromDate` field for last update timestamp
- Estimates may change as earnings date approaches
- Time field (`bmo`/`amc`/`tba`) may update closer to date

## Best Practices

### 1. Calculate Date Range Accurately
Always get current date first:
```python
from datetime import datetime, timedelta

today = datetime.now()
start_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
end_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
```

### 2. Batch API Calls
Use batch endpoints to reduce API calls:
- Earnings calendar: One call for entire week
- Company profiles: Batch up to 100 symbols per call

### 3. Cache Results
For repeated analyses within same day:
```python
import json
from pathlib import Path

def cache_earnings_data(data, cache_file="earnings_cache.json"):
    """Save earnings data to cache file"""
    cache_path = Path(cache_file)
    cache_path.write_text(json.dumps(data, indent=2))

def load_cached_data(cache_file="earnings_cache.json", max_age_hours=6):
    """Load cached data if recent enough"""
    cache_path = Path(cache_file)
    if not cache_path.exists():
        return None

    # Check cache age
    cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
    if cache_age.total_seconds() > max_age_hours * 3600:
        return None

    return json.loads(cache_path.read_text())
```

### 4. Handle Missing Data Gracefully
```python
def safe_get(data, key, default="N/A"):
    """Safely get value from dict with default"""
    value = data.get(key)
    return value if value is not None else default
```

### 5. Sort and Prioritize by Market Cap
```python
def sort_by_market_cap(earnings):
    """Sort earnings by market cap descending"""
    return sorted(
        earnings,
        key=lambda x: x.get("marketCap", 0),
        reverse=True
    )
```

## API Call Optimization

### Minimize API Calls

For a typical weekly earnings calendar:
1. **Earnings Calendar API**: 1 call (all week)
2. **Company Profiles API**: N/100 calls (where N = number of symbols)

**Example**:
- 200 companies reporting
- Profile API calls: 200/100 = 2 calls
- **Total**: 3 API calls (well within 250/day free limit)

### Rate Limit Management

```python
import time

def rate_limited_request(url, params, delay=0.1):
    """Make request with rate limiting"""
    time.sleep(delay)
    return requests.get(url, params=params)
```

For free tier (250 calls/day):
- Per hour limit: ~10 calls/hour safe
- Add 0.5-1 second delay between calls if making many requests

## Alternative Endpoints

### For Real-Time Market Cap Data

**Market Capitalization Endpoint**:
```
GET /api/v3/market-capitalization/{symbol}?apikey=KEY
```

Returns current market cap only (faster, but requires per-symbol calls).

### For Historical Earnings Results

**Historical Earnings Endpoint**:
```
GET /api/v3/historical/earning_calendar/{symbol}?apikey=KEY
```

Returns past earnings results with actual vs. estimated comparisons.

## Comparison: FMP vs Other Data Sources

| Feature | FMP API | Finviz | Yahoo Finance |
|---------|---------|--------|---------------|
| **Access Method** | REST API | Web Scraping | Web Scraping |
| **Authentication** | API Key | None | None |
| **Data Format** | JSON | HTML | HTML |
| **Rate Limit** | 250/day (free) | IP-based | IP-based |
| **Reliability** | High | Medium | Medium |
| **Market Cap Filter** | Via Profile API | Built-in | Manual |
| **EPS Estimates** | ✓ | ✗ | ✓ |
| **Revenue Estimates** | ✓ | ✗ | ✓ |
| **Timing Info** | ✓ | ✓ | ✓ |
| **Historical Data** | ✓ | ✗ | Limited |
| **Free Tier** | ✓ | ✓ | ✓ |

**Recommendation**: FMP API is the most reliable and structured option for programmatic access.

## Troubleshooting

### Problem: API returns empty array

**Solutions**:
- Verify date range is valid (future dates)
- Check date format is YYYY-MM-DD
- Verify API key is active
- Try wider date range (e.g., +14 days instead of +7)

### Problem: Some major companies missing

**Solutions**:
- Company may not have announced earnings date yet
- Some companies announce dates very late (1-2 days before)
- Cross-reference with company investor relations website
- Check if company is on earnings date hold

### Problem: Market cap data missing

**Solutions**:
- Company profile may not be available
- Use alternative market cap endpoint
- Fall back to manual market cap lookup
- Some thinly traded stocks may lack profile data

### Problem: Rate limit hit unexpectedly

**Solutions**:
- Check other scripts/tools using same API key
- Implement caching to reduce repeated calls
- Add delays between requests
- Consider upgrading to paid tier

## Example Output Structure

After fetching and processing FMP data:

```python
{
    "symbol": "AAPL",
    "companyName": "Apple Inc.",
    "date": "2025-11-04",
    "time": "amc",
    "marketCap": 3000000000000,
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "epsEstimated": 1.54,
    "revenueEstimated": 123400000000
}
```

This enriched data can then be organized by date, timing, and market cap for the final earnings calendar report.

## Resources

- **FMP Documentation**: https://site.financialmodelingprep.com/developer/docs
- **API Key Signup**: https://site.financialmodelingprep.com/developer/docs
- **Earnings Calendar API**: https://site.financialmodelingprep.com/developer/docs/earnings-calendar-api
- **Company Profile API**: https://site.financialmodelingprep.com/developer/docs/companies-key-metrics-api
- **Rate Limits**: https://site.financialmodelingprep.com/developer/docs/pricing

---

*This guide is optimized for the earnings-calendar skill and FMP API integration.*
