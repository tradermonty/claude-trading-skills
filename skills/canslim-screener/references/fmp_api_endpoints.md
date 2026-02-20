# FMP API Endpoints - CANSLIM Screener Phase 3 (Full CANSLIM)

## Overview

This document specifies the Financial Modeling Prep (FMP) API endpoints required for the CANSLIM screener Phase 3 implementation (all 7 components: C, A, N, S, L, I, M).

**Base URL**: `https://financialmodelingprep.com/api/v3`

**Authentication**: All requests require `apikey` parameter

**Rate Limiting**:
- Free tier: 250 requests/day
- Recommended delay: 0.3 seconds between requests (200 requests/minute max)

---

## C Component - Current Quarterly Earnings

### Endpoint: Income Statement (Quarterly)

**URL**: `/income-statement/{symbol}?period=quarter&limit=8`

**Method**: GET

**Parameters**:
- `symbol`: Stock ticker (e.g., "AAPL")
- `period`: "quarter" (quarterly data)
- `limit`: 8 (fetch last 8 quarters = 2 years)
- `apikey`: Your FMP API key

**Example Request**:
```bash
curl "https://financialmodelingprep.com/api/v3/income-statement/AAPL?period=quarter&limit=8&apikey=YOUR_KEY"
```

**Response Fields Used**:
```json
[
  {
    "date": "2023-09-30",  # Quarter end date
    "symbol": "AAPL",
    "reportedCurrency": "USD",
    "fillingDate": "2023-11-02",
    "eps": 1.46,           # Diluted EPS ← KEY
    "epsdiلuted": 1.46,     # Alternative field
    "revenue": 89498000000, # Total revenue ← KEY
    "grossProfit": 41104000000,
    "operatingIncome": 26982000000,
    "netIncome": 22956000000
  },
  # ... 7 more quarters
]
```

**Usage**:
- Compare `eps` from most recent quarter to quarter 4 positions back (YoY comparison)
- Compare `revenue` same way
- Calculate YoY growth percentage

**API Calls**: 1 per stock

---

## A Component - Annual EPS Growth

### Endpoint: Income Statement (Annual)

**URL**: `/income-statement/{symbol}?period=annual&limit=5`

**Method**: GET

**Parameters**:
- `symbol`: Stock ticker
- `period`: "annual" (annual data)
- `limit`: 5 (fetch last 5 years for 4-year CAGR calculation)
- `apikey`: Your FMP API key

**Example Request**:
```bash
curl "https://financialmodelingprep.com/api/v3/income-statement/AAPL?period=annual&limit=5&apikey=YOUR_KEY"
```

**Response Fields Used**:
```json
[
  {
    "date": "2023-09-30",   # Fiscal year end
    "symbol": "AAPL",
    "eps": 6.13,            # Annual diluted EPS ← KEY
    "revenue": 383285000000, # Annual revenue ← KEY
    "netIncome": 96995000000
  },
  # ... 4 more years
]
```

**Usage**:
- Use 4 most recent years to calculate 3-year CAGR
- CAGR = ((EPS_current / EPS_3years_ago) ^ (1/3)) - 1
- Check for stability (no down years)
- Validate with revenue CAGR

**API Calls**: 1 per stock

---

## N Component - Newness / New Highs

### Endpoint 1: Historical Prices (Daily)

**URL**: `/historical-price-full/{symbol}?timeseries=365`

**Method**: GET

**Parameters**:
- `symbol`: Stock ticker
- `timeseries`: 365 (fetch last 365 days)
- `apikey`: Your FMP API key

**Example Request**:
```bash
curl "https://financialmodelingprep.com/api/v3/historical-price-full/AAPL?timeseries=365&apikey=YOUR_KEY"
```

**Response Fields Used**:
```json
{
  "symbol": "AAPL",
  "historical": [
    {
      "date": "2024-01-10",
      "open": 185.16,
      "high": 186.40,     # Daily high ← KEY
      "low": 184.00,      # Daily low ← KEY
      "close": 185.92,    # Close price ← KEY
      "volume": 50123456  # Daily volume ← KEY
    },
    # ... 364 more days
  ]
}
```

**Usage**:
- Calculate 52-week high: `max(historical[0:252].high)`
- Calculate 52-week low: `min(historical[0:252].low)`
- Current price: `historical[0].close`
- Distance from high: `(current / 52wk_high - 1) * 100`
- Detect breakout: Check if recent high >= 52wk_high with elevated volume

**API Calls**: 1 per stock

### Endpoint 2: Quote (Real-Time Price)

**URL**: `/quote/{symbol}`

**Method**: GET

**Parameters**:
- `symbol`: Stock ticker (can be comma-separated for batch)
- `apikey`: Your FMP API key

**Example Request**:
```bash
curl "https://financialmodelingprep.com/api/v3/quote/AAPL?apikey=YOUR_KEY"
```

**Response Fields Used**:
```json
[
  {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "price": 185.92,               # Current price ← KEY
    "changesPercentage": 1.23,
    "change": 2.25,
    "dayLow": 184.00,
    "dayHigh": 186.40,
    "yearHigh": 198.23,            # 52-week high ← KEY
    "yearLow": 164.08,             # 52-week low ← KEY
    "marketCap": 2913000000000,
    "volume": 50123456,
    "avgVolume": 48000000,         # Average volume ← KEY
    "exchange": "NASDAQ",
    "sector": "Technology"
  }
]
```

**Usage**:
- Alternative to historical prices for 52-week high/low
- Faster (1 call vs historical prices) but less granular
- Use for quick screening; historical prices for detailed analysis

**API Calls**: 1 per stock (or batch multiple)

### Endpoint 3: Stock News (Optional - New Product Detection)

**URL**: `/stock_news?tickers={symbol}&limit=50`

**Method**: GET

**Parameters**:
- `tickers`: Stock ticker (comma-separated for multiple)
- `limit`: 50 (recent news articles)
- `apikey`: Your FMP API key

**Example Request**:
```bash
curl "https://financialmodelingprep.com/api/v3/stock_news?tickers=AAPL&limit=50&apikey=YOUR_KEY"
```

**Response Fields Used**:
```json
[
  {
    "symbol": "AAPL",
    "publishedDate": "2024-01-10T14:30:00.000Z",
    "title": "Apple Launches Revolutionary AI Chip",  # ← KEY (keyword search)
    "image": "https://...",
    "site": "Reuters",
    "text": "Apple Inc announced today...",
    "url": "https://..."
  },
  # ... 49 more articles
]
```

**Usage**:
- Search `title` field for keywords:
  - High impact: "FDA approval", "patent granted", "breakthrough"
  - Moderate: "new product", "product launch", "acquisition"
- Bonus points for N component if catalyst detected
- **Optional**: Can skip to reduce API calls (N component primarily uses price action)

**API Calls**: 1 per stock (optional, can be skipped to save quota)

---

## M Component - Market Direction

### Endpoint 1: Quote (Major Indices)

**URL**: `/quote/^GSPC,^IXIC,^DJI`

**Method**: GET

**Parameters**:
- Symbol: `^GSPC` (S&P 500), `^IXIC` (Nasdaq), `^DJI` (Dow Jones)
- Can batch multiple indices in single call
- `apikey`: Your FMP API key

**Example Request**:
```bash
curl "https://financialmodelingprep.com/api/v3/quote/%5EGSPC,%5EIXIC,%5EDJI?apikey=YOUR_KEY"
```

**Response Fields Used**:
```json
[
  {
    "symbol": "^GSPC",
    "name": "S&P 500",
    "price": 4783.45,         # Current level ← KEY
    "changesPercentage": 0.85,
    "change": 40.25,
    "dayLow": 4750.20,
    "dayHigh": 4790.10,
    "yearHigh": 4818.62,
    "yearLow": 4103.78,
    "marketCap": null,
    "volume": null,
    "avgVolume": null
  },
  # IXIC, DJI...
]
```

**Usage**:
- Get current S&P 500 price for trend analysis
- Compare to 50-day EMA (from separate call or calculated locally)

**API Calls**: 1 (batch call for all indices)

### Endpoint 2: Historical Prices (S&P 500 for EMA Calculation)

**URL**: `/historical-price-full/^GSPC?timeseries=60`

**Method**: GET

**Parameters**:
- Symbol: `^GSPC` (S&P 500)
- `timeseries`: 60 (fetch 60 days for 50-day EMA calculation)
- `apikey`: Your FMP API key

**Example Request**:
```bash
curl "https://financialmodelingprep.com/api/v3/historical-price-full/%5EGSPC?timeseries=60&apikey=YOUR_KEY"
```

**Response Fields Used**:
```json
{
  "symbol": "^GSPC",
  "historical": [
    {
      "date": "2024-01-10",
      "close": 4783.45  # ← KEY (for EMA calculation)
    },
    # ... 59 more days
  ]
}
```

**Usage**:
- Calculate 50-day EMA from closing prices
- EMA formula: `EMA_today = (Price_today * k) + (EMA_yesterday * (1 - k))` where `k = 2/(50+1)`
- Alternative: Use simple moving average (SMA) for simplicity

**API Calls**: 1 (reused for all stocks)

### Endpoint 3: VIX (Fear Gauge)

**URL**: `/quote/^VIX`

**Method**: GET

**Parameters**:
- Symbol: `^VIX` (CBOE Volatility Index)
- `apikey`: Your FMP API key

**Example Request**:
```bash
curl "https://financialmodelingprep.com/api/v3/quote/%5EVIX?apikey=YOUR_KEY"
```

**Response Fields Used**:
```json
[
  {
    "symbol": "^VIX",
    "name": "CBOE Volatility Index",
    "price": 13.24,  # Current VIX level ← KEY
    "changesPercentage": -2.15,
    "change": -0.29
  }
]
```

**Usage**:
- VIX < 15: Low fear (bullish environment)
- VIX 15-20: Normal (healthy market)
- VIX 20-30: Elevated (caution)
- VIX > 30: Panic (bear market signal)

**API Calls**: 1 (reused for all stocks)

---

## L Component - Leadership / Relative Strength (Phase 3)

### Endpoint: Historical Prices (52-Week)

**URL**: `/v3/historical-price-full/{symbol}?timeseries=365`

**Purpose**: Calculate 52-week stock performance vs S&P 500 benchmark for RS Rank estimation

**Request**:
```bash
curl "https://financialmodelingprep.com/api/v3/historical-price-full/NVDA?timeseries=365&apikey=YOUR_KEY"
```

**Response Structure**:
```json
{
  "symbol": "NVDA",
  "historical": [
    {
      "date": "2025-01-10",
      "close": 148.50,
      "open": 146.20,
      "high": 149.80,
      "low": 145.90,
      "volume": 250000000
    }
    // ... 364 more days
  ]
}
```

**Usage**:
```python
# Stock 52-week performance
current_price = historical[0]['close']
price_52w_ago = historical[-1]['close']  # ~252 trading days
stock_perf = ((current_price / price_52w_ago) - 1) * 100

# Compare vs S&P 500 (^GSPC) for RS calculation
relative_perf = stock_perf - sp500_perf
```

**S&P 500 Benchmark Data**: S&P 500 52-week historical prices are fetched once using `^GSPC` (same endpoint, shared for both M component EMA and L component RS calculation). Both quote and historical use `^GSPC` to ensure price scale consistency.

**API Calls**: 1 per stock (52-week data) + 1 shared S&P 500 call

---

## S Component - Supply and Demand

### Endpoint: Historical Prices (Already Fetched for N Component)

**URL**: `/v3/historical-price-full/{symbol}?timeseries=90`

**Purpose**: Volume-based accumulation/distribution analysis

**Data Reuse**: S component uses the same historical_prices data already fetched for N component (52-week high calculation). **No additional API calls required.**

**Algorithm**:
```python
# Classify last 60 days into up-days and down-days
for day in last_60_days:
    if close > previous_close:
        up_days.append(volume)
    elif close < previous_close:
        down_days.append(volume)

# Calculate accumulation/distribution ratio
avg_up_volume = sum(up_days) / len(up_days)
avg_down_volume = sum(down_days) / len(down_days)
ratio = avg_up_volume / avg_down_volume
```

**Scoring**:
- Ratio ≥ 2.0: 100 points (Strong Accumulation)
- Ratio 1.5-2.0: 80 points (Accumulation)
- Ratio 1.0-1.5: 60 points (Neutral/Weak Accumulation)
- Ratio 0.7-1.0: 40 points (Neutral/Weak Distribution)
- Ratio 0.5-0.7: 20 points (Distribution)
- Ratio < 0.5: 0 points (Strong Distribution)

**API Calls**: 0 (data already fetched)

---

## I Component - Institutional Sponsorship (Phase 2)

### Endpoint: Institutional Holders

**URL**: `/v3/institutional-holder/{symbol}`

**Purpose**: Analyze institutional holder count and ownership percentage

**Authentication**: Requires FMP API key (available on free tier)

**Request**:
```bash
curl "https://financialmodelingprep.com/api/v3/institutional-holder/AAPL?apikey=YOUR_KEY"
```

**Response Structure**:
```json
[
  {
    "holder": "Vanguard Group Inc",
    "shares": 1295611697,
    "dateReported": "2024-09-30",
    "change": 12500000,
    "changePercent": 0.0097
  },
  {
    "holder": "Blackrock Inc.",
    "shares": 1042156037,
    "dateReported": "2024-09-30",
    "change": -5234567,
    "changePercent": -0.0050
  },
  {
    "holder": "Berkshire Hathaway Inc",
    "shares": 915560382,
    "dateReported": "2024-09-30",
    "change": 0,
    "changePercent": 0.0000
  }
  // ... hundreds more holders ...
]
```

**Key Fields**:
- `holder`: Institution name (string)
- `shares`: Number of shares held (int)
- `dateReported`: 13F filing date (string, YYYY-MM-DD)
- `change`: Change in shares from previous quarter (int)
- `changePercent`: Percentage change (float)

**Typical Response Size**: 100-7,000 holders per stock (AAPL has ~7,111 holders)

**Free Tier Availability**: ✅ Available (tested with AAPL on 2026-01-12)

**Usage**:
```python
# Calculate total institutional ownership
total_shares_held = sum(holder['shares'] for holder in institutional_holders)
ownership_pct = (total_shares_held / shares_outstanding) * 100

# Count unique holders
num_holders = len(institutional_holders)

# Detect superinvestors
SUPERINVESTORS = [
    "BERKSHIRE HATHAWAY",
    "BAUPOST GROUP",
    "PERSHING SQUARE",
    # ...
]
superinvestor_present = any(
    superinvestor in holder['holder'].upper()
    for holder in institutional_holders
    for superinvestor in SUPERINVESTORS
)
```

**Scoring** (O'Neil's Criteria):
- 50-100 holders + 30-60% ownership: 100 points (Sweet spot)
- Superinvestor present + good holder count: 90 points
- 30-50 holders + 20-40% ownership: 80 points
- Acceptable ranges: 60 points
- Suboptimal (< 20% or > 80% ownership): 40 points
- Extreme (< 10% or > 90% ownership): 20 points

**API Calls**: 1 per stock

**Data Freshness**: Updated quarterly (13F filings due 45 days after quarter-end)

**Quality Notes**:
- Large-cap stocks (AAPL, MSFT): 5,000-10,000 holders
- Mid-cap stocks: 500-2,000 holders
- Small-cap stocks: 50-500 holders
- Micro-cap stocks: < 50 holders (may lack institutional interest)

---

## API Call Summary (Per Stock)

### Phase 3 (Full CANSLIM: C, A, N, S, L, I, M)

**Per-Stock Calls**:
1. Profile (for company info): 1 call
2. Quote (for current price): 1 call
3. Income Statement (Quarterly): 1 call
4. Income Statement (Annual): 1 call
5. Historical Prices (90 days): 1 call (reused for N and S)
6. Historical Prices (365 days): 1 call (for L component RS calculation)
7. Institutional Holders: 1 call

**Per-Stock Total**: 7 calls (profile, quote, income×2, historical_90d, historical_365d, institutional)

**Market Data Calls** (One-Time per Session):
1. S&P 500 Quote (`^GSPC`): 1 call (shared)
2. S&P 500 Historical (`^GSPC`, 365 days): 1 call (shared, used for both M component EMA and L component RS benchmark)
3. VIX Quote (`^VIX`): 1 call (shared)

**Market Data Total**: 3 calls

**Important**: Both the quote and historical data use `^GSPC` (S&P 500 index) to ensure price scale consistency for M component EMA calculation. Using SPY (ETF, ~500) for historical while ^GSPC (~5000) for quote would cause a ~10× scale mismatch.

**Total for 40 Stocks**:
- Per-stock: 40 stocks × 7 calls = 280 calls
- Market data: 3 calls
- **Grand Total: ~283 calls (exceeds 250 free tier limit)** ⚠️

**Key Efficiency**:
- S component: 0 extra calls (reuses historical_prices from N component's 90-day fetch)
- L component: +1 call per stock (365-day historical prices, separate cache key from 90-day)
- S&P 500 historical data: shared between M (EMA) and L (RS benchmark)

**Free Tier Workaround**: Use `--max-candidates 35` (35 × 7 + 3 = 248 calls, within 250 limit). For full 40-stock screening, upgrade to FMP Starter tier ($29.99/mo, 750 calls/day).

**Note on `mktCap` field**: FMP profile API returns `mktCap` (not `marketCap`). The screener handles both field names for compatibility.

---

## Rate Limiting Strategy

### Implementation

```python
import time

def rate_limited_get(url, params):
    """Enforce 0.3s delay between requests (200 requests/minute max)"""
    response = requests.get(url, params=params)
    time.sleep(0.3)  # 300ms delay
    return response
```

### Handling 429 Errors (Rate Limit Exceeded)

```python
def handle_rate_limit(response):
    """Retry once with 60-second wait if rate limit hit"""
    if response.status_code == 429:
        print("WARNING: Rate limit exceeded. Waiting 60 seconds...")
        time.sleep(60)
        return True  # Signal to retry
    return False  # No retry needed
```

### Free Tier Management

**Daily Quota**: 250 requests/day

**Strategies to Stay Within Limits**:
1. **Batch calls where possible**: Use comma-separated symbols in quote endpoint
2. **Cache market data**: Fetch S&P 500/VIX once, reuse for all stocks
3. **Skip optional calls**: News endpoint can be omitted to save 40 calls
4. **Limit universe**: Analyze top 35 stocks for free tier, or 40 with Starter tier
5. **Progressive filtering**: Apply cheap filters first (market cap, sector) before expensive API calls

---

## Error Handling

### Common Errors

**401 Unauthorized**:
- Cause: Invalid or missing API key
- Solution: Verify `apikey` parameter, check environment variable

**404 Not Found**:
- Cause: Invalid symbol or endpoint
- Solution: Verify ticker symbol exists, check endpoint URL

**429 Too Many Requests**:
- Cause: Exceeded daily/minute rate limit
- Solution: Wait 60 seconds (minute limit) or 24 hours (daily limit)

**500 Internal Server Error**:
- Cause: FMP server issue
- Solution: Retry after 5 seconds, skip stock if persistent

**Empty Response `[]`**:
- Cause: Symbol exists but no data available (e.g., recent IPO, delisted stock)
- Solution: Skip stock, log warning

### Retry Logic

```python
MAX_RETRIES = 1
retry_count = 0

while retry_count <= MAX_RETRIES:
    response = make_request()
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 429:
        time.sleep(60)
        retry_count += 1
    else:
        print(f"ERROR: {response.status_code}")
        return None

print("ERROR: Max retries exceeded")
return None
```

---

## Data Quality Considerations

### Freshness

- **Quarterly/Annual Data**: Updated within 1-2 days of earnings release
- **Price Data**: Real-time (15-minute delay on free tier)
- **News Data**: Updated continuously

### Completeness

- **Large-cap stocks**: Complete historical data (10+ years)
- **Mid-cap stocks**: Mostly complete (5+ years typical)
- **Small-cap/Recent IPOs**: May have gaps (<2 years data)

### Validation

Always check for:
- `null` or `0` values in critical fields (EPS, revenue)
- Negative EPS when calculating growth rates (use absolute value in denominator)
- Missing quarters (delisted stocks, special situations)

---

## Example API Call Sequence

For analyzing NVDA:

```bash
# 1. Quarterly income statement (C component)
curl "https://financialmodelingprep.com/api/v3/income-statement/NVDA?period=quarter&limit=8&apikey=YOUR_KEY"

# 2. Annual income statement (A component)
curl "https://financialmodelingprep.com/api/v3/income-statement/NVDA?period=annual&limit=5&apikey=YOUR_KEY"

# 3. Historical prices (N component)
curl "https://financialmodelingprep.com/api/v3/quote/NVDA?apikey=YOUR_KEY"

# 4. S&P 500 for market direction (M component - once per session)
curl "https://financialmodelingprep.com/api/v3/quote/%5EGSPC&apikey=YOUR_KEY"
curl "https://financialmodelingprep.com/api/v3/historical-price-full/%5EGSPC?timeseries=60&apikey=YOUR_KEY"
curl "https://financialmodelingprep.com/api/v3/quote/%5EVIX&apikey=YOUR_KEY"
```

**Total**: 7 calls per stock (profile, quote, income×2, historical_90d, historical_365d, institutional) + 3 market calls (reused for all stocks)

---

## Cost Analysis

### Free Tier (250 requests/day)

- **40 stocks × 7 calls = 280 calls**
- **Market data: 3 calls**
- **Total: ~283 calls (exceeds 250 quota)** ⚠️
- **Workaround**: Use `--max-candidates 35` (35 × 7 + 3 = 248 calls)

### Paid Tiers

- **Starter ($29.99/month)**: 750 requests/day → ~106 stocks/run ((750 - 3) / 7)
- **Professional ($79.99/month)**: 2000 requests/day → ~285 stocks/run ((2000 - 3) / 7)

**Recommendation for Phase 3**: Free tier supports up to 35 stocks (`--max-candidates 35`). For the default 40-stock universe, upgrade to Starter tier ($29.99/mo).

---

This API reference provides complete documentation for implementing Phase 3 (Full CANSLIM) screening. Free tier users should use `--max-candidates 35` to stay within the 250 calls/day limit.
