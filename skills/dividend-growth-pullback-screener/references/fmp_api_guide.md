# Financial Modeling Prep (FMP) API Guide

## Overview

Financial Modeling Prep provides comprehensive financial data APIs for stocks, forex, cryptocurrencies, and more. This guide focuses on endpoints used for dividend growth stock screening with RSI technical indicators.

### Two-Stage Screening Approach

This screener supports two screening modes:

**1. Two-Stage (FINVIZ + FMP) - RECOMMENDED**
- **Stage 1**: FINVIZ Elite API pre-screens with RSI filter (1 API call → 10-50 candidates)
- **Stage 2**: FMP API performs detailed fundamental analysis on pre-screened candidates
- **Advantage**: Dramatically reduces FMP API calls by leveraging FINVIZ's technical filters
- **Cost**: FINVIZ Elite $40/month + FMP free tier

**2. FMP-Only (Original Method)**
- **Single Stage**: FMP stock-screener + detailed analysis
- **Limitation**: FMP free tier (250 requests/day) limits to ~40 stocks
- **Cost**: FMP free tier (upgrades available)

**Recommended**: Two-stage approach for regular screening (daily/weekly) to maximize coverage while minimizing costs.

## API Key Setup

### Obtaining an API Key

1. Visit https://financialmodelingprep.com/developer/docs
2. Sign up for a free account
3. Navigate to Dashboard → API Keys
4. Copy your API key

### Free Tier Limits

- **250 requests per day**
- **Rate limit**: ~5 requests per second
- **No credit card required**
- Sufficient for daily/weekly screening runs

### Paid Plans (Optional)

Prices and limits change; see `site.financialmodelingprep.com/pricing-plans` in a browser for current plans.

## Setting API Key

### Method 1: Environment Variable (Recommended)

**Linux/macOS:**
```bash
export FMP_API_KEY=your_api_key_here
```

**Windows (Command Prompt):**
```cmd
set FMP_API_KEY=your_api_key_here
```

**Windows (PowerShell):**
```powershell
$env:FMP_API_KEY="your_api_key_here"
```

**Persistent (add to shell profile):**
```bash
# Add to ~/.bashrc or ~/.zshrc
echo 'export FMP_API_KEY=your_api_key_here' >> ~/.bashrc
source ~/.bashrc
```

### Method 2: Command-Line Argument

```bash
python3 scripts/screen_dividend_growth_rsi.py --fmp-api-key your_api_key_here
```

## FINVIZ API Setup (Optional - For Two-Stage Screening)

### Obtaining FINVIZ Elite API Key

1. Visit https://elite.finviz.com
2. Subscribe to FINVIZ Elite ($40/month or $400/year)
3. Navigate to Settings → API
4. Copy your API key

### Setting FINVIZ API Key

**Environment Variable (Recommended):**
```bash
export FINVIZ_API_KEY=your_finviz_key_here
```

**Command-Line Argument:**
```bash
python3 screen_dividend_growth_rsi.py --use-finviz --finviz-api-key YOUR_KEY
```

### FINVIZ Pre-Screening Filters

When using `--use-finviz`, the screener applies these filters via FINVIZ Elite API:

- **Market Cap**: Mid-cap or higher (≥$2B)
- **Dividend Yield**: 0.5-3% (captures dividend growers, excludes high-yield REITs/utilities)
- **Dividend Growth (3Y)**: 10%+ (FMP verifies 12%+)
- **EPS Growth (3Y)**: 5%+ (positive earnings momentum)
- **Sales Growth (3Y)**: 5%+ (positive revenue momentum)
- **RSI (14-period)**: Under 40 (oversold/pullback)
- **Geography**: USA

**Output**: Set of stock symbols (typically 30-50 stocks) passed to FMP for detailed analysis.

**Rationale for balanced filters:**
- 10%+ dividend growth ensures high-quality dividend compounders
- 5%+ EPS/sales growth captures growing businesses (not just mature dividend payers)
- 0.5-3% yield range excludes mature high-yielders (>4%) and focuses on growth stocks
- Reduces FINVIZ candidates from ~90 to ~30-50 stocks
- Stays within FMP free tier limits with efficient analysis (250 requests/day)

## Key Endpoints Used

### 1. Stock Screener

**Endpoint:** `/v3/stock-screener`

**Purpose:** Initial filtering by market cap and exchange

**Parameters:**
- `marketCapMoreThan`: Minimum market cap (e.g., 2000000000 = $2B)
- `exchange`: Exchanges to include (e.g., "NASDAQ,NYSE")
- `limit`: Max results (default: 1000)

**Note:** This screener does NOT pre-filter by dividend yield (unlike value-dividend-screener). We retrieve a broader universe and calculate actual yields from dividend history to ensure accuracy.

**Example Request:**
```
https://financialmodelingprep.com/api/v3/stock-screener?
  marketCapMoreThan=2000000000&
  exchange=NASDAQ,NYSE&
  limit=1000&
  apikey=YOUR_API_KEY
```

**Response Format:**
```json
[
  {
    "symbol": "AAPL",
    "companyName": "Apple Inc.",
    "marketCap": 2800000000000,
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "price": 185.50,
    "exchange": "NASDAQ",
    "isActivelyTrading": true
  }
]
```

### 2. Historical Dividend

**Endpoint:** `/v3/historical-price-full/stock_dividend/{symbol}`

**Purpose:** Dividend history for growth rate calculation and yield verification

**Example Request:**
```
https://financialmodelingprep.com/api/v3/historical-price-full/stock_dividend/AAPL?
  apikey=YOUR_API_KEY
```

**Response Format:**
```json
{
  "symbol": "AAPL",
  "historical": [
    {
      "date": "2024-11-08",
      "label": "November 08, 24",
      "adjDividend": 0.25,
      "dividend": 0.25,
      "recordDate": "2024-11-11",
      "paymentDate": "2024-11-14",
      "declarationDate": "2024-10-31"
    }
  ]
}
```

**Usage in Script:**
- Aggregate dividends by calendar year (sum all payments in each year)
- Calculate 3-year dividend CAGR: `((Div_Year3 / Div_Year0) ^ (1/3) - 1) × 100`
- Extract latest annual dividend for yield calculation
- Verify consistency (no significant cuts year-over-year)

### 3. Historical Prices (NEW for RSI)

**Endpoint:** `/v3/historical-price-full/{symbol}`

**Purpose:** Daily price data for RSI calculation

**Parameters:**
- `symbol`: Stock ticker
- `timeseries`: Number of days to retrieve (e.g., 30)

**Example Request:**
```
https://financialmodelingprep.com/api/v3/historical-price-full/AAPL?
  timeseries=30&
  apikey=YOUR_API_KEY
```

**Response Format:**
```json
{
  "symbol": "AAPL",
  "historical": [
    {
      "date": "2024-11-01",
      "open": 184.50,
      "high": 186.20,
      "low": 183.80,
      "close": 185.50,
      "adjClose": 185.50,
      "volume": 45000000,
      "unadjustedVolume": 45000000,
      "change": 1.00,
      "changePercent": 0.54,
      "vwap": 185.10,
      "label": "November 01, 24",
      "changeOverTime": 0.0054
    }
  ]
}
```

**Usage in Script:**
- Extract `close` prices from last 30 days
- Sort chronologically (oldest first)
- Calculate 14-period RSI:
  1. Compute price changes (close[i] - close[i-1])
  2. Separate gains and losses
  3. Calculate average gain and average loss over 14 periods
  4. RS = Average Gain / Average Loss
  5. RSI = 100 - (100 / (1 + RS))

**RSI Filter:** Stocks with RSI > 40 are excluded (not oversold/pullback)

### 4. Income Statement

**Endpoint:** `/v3/income-statement/{symbol}`

**Purpose:** Revenue, EPS, net income analysis

**Parameters:**
- `symbol`: Stock ticker (e.g., "AAPL")
- `limit`: Number of periods (e.g., 5 for 5 years)
- `period`: "annual" (default)

**Example Request:**
```
https://financialmodelingprep.com/api/v3/income-statement/AAPL?
  limit=5&
  apikey=YOUR_API_KEY
```

**Key Fields Used:**
- `revenue`: Total revenue
- `eps`: Earnings per share
- `netIncome`: Net income (for payout ratio calculation)
- `date`: Fiscal period end date

**Usage in Script:**
- Calculate 3-year revenue CAGR (must be positive for qualification)
- Calculate 3-year EPS CAGR (must be positive)
- Extract net income for payout ratio calculation

### 5. Balance Sheet Statement

**Endpoint:** `/v3/balance-sheet-statement/{symbol}`

**Purpose:** Debt, equity, liquidity analysis

**Parameters:**
- `symbol`: Stock ticker
- `limit`: Number of periods (typically 5)

**Key Fields Used:**
- `totalDebt`: Total debt (short-term + long-term)
- `totalStockholdersEquity`: Shareholders' equity
- `totalCurrentAssets`: Current assets
- `totalCurrentLiabilities`: Current liabilities

**Usage in Script:**
- Debt-to-Equity: totalDebt / totalStockholdersEquity (must be < 2.0)
- Current Ratio: totalCurrentAssets / totalCurrentLiabilities (must be > 1.0)
- Financial health check (both ratios must pass)

### 6. Cash Flow Statement

**Endpoint:** `/v3/cash-flow-statement/{symbol}`

**Purpose:** Free cash flow analysis for dividend sustainability

**Parameters:**
- `symbol`: Stock ticker
- `limit`: Number of periods

**Key Fields Used:**
- `freeCashFlow`: Free cash flow (OCF - Capex)
- `dividendsPaid`: Actual dividends paid (negative value)

**Usage in Script:**
- FCF Payout Ratio: dividendsPaid / freeCashFlow
- Validates dividend is covered by cash generation (< 100% is sustainable)

### 7. Key Metrics

**Endpoint:** `/v3/key-metrics/{symbol}`

**Purpose:** ROE, profit margins, valuation ratios

**Parameters:**
- `symbol`: Stock ticker
- `limit`: Number of periods (typically 1 for latest)

**Key Fields Used:**
- `roe`: Return on Equity (decimal, e.g., 0.15 = 15%)
- `netProfitMargin`: Net profit margin (decimal)
- `peRatio`: Price-to-Earnings ratio
- `pbRatio`: Price-to-Book ratio
- `numberOfShares`: Shares outstanding (for payout ratio calculation)

**Usage in Script:**
- ROE: Quality metric for composite scoring (higher is better)
- Profit Margin: Profitability metric for scoring
- P/E and P/B: Context only (no exclusionary limits in this screener)
- Number of Shares: Used to calculate total dividend payout

## Rate Limiting Strategy

### Built-in Protection

The screening script includes rate limiting:
- **0.3 second delay** between requests (~3 requests/second)
- **Automatic retry** on 429 (rate limit exceeded) with 60-second backoff
- **Timeout**: 30 seconds per request
- **Graceful degradation**: Stops analysis if rate limit reached, returns partial results

### Managing Request Budget

For free tier (250 requests/day):

**Requests per stock analyzed:**
- Stock Screener: 1 request (returns 100-1000 stocks)
- Dividend History: 1 request per symbol
- Historical Prices (RSI): 1 request per symbol
- Income Statement: 1 request per symbol
- Balance Sheet: 1 request per symbol
- Cash Flow: 1 request per symbol
- Key Metrics: 1 request per symbol

**Total: 6 requests per symbol + 1 screener request**

**Budget allocation:**
- Initial screener: 1 request
- Detailed analysis: 6 × N stocks = 6N requests
- **Maximum stocks per run**: (250 - 1) / 6 = ~41 stocks

**FMP-Only Mode Optimization**: Use `--max-candidates` parameter to limit analysis:
```bash
python3 screen_dividend_growth_rsi.py --max-candidates 40
```

**Two-Stage Mode (RECOMMENDED)**:

When using FINVIZ pre-screening (`--use-finviz`):

**Request breakdown:**
- FINVIZ pre-screen: 1 FINVIZ API call → 10-50 symbols
- FMP quote fetching: 1 request per symbol (to get current price)
- FMP detailed analysis: 6 requests per symbol (dividend, prices, income, balance, cashflow, metrics)

**Total FMP requests**:
- 10 symbols: 10 + (6 × 10) = 70 requests
- 30 symbols: 30 + (6 × 30) = 210 requests
- 50 symbols: 50 + (6 × 50) = 350 requests (exceeds free tier)

**Advantage**: FINVIZ's RSI filter typically returns 10-30 stocks (not 1000), making FMP analysis feasible within free tier limits.

**Cost comparison:**
- **Paid FMP plan** (see `site.financialmodelingprep.com/pricing-plans`): see the page for current limits
- **FINVIZ Elite + FMP Free** ($40/month, 250 FMP requests): ~30 stocks/day with RSI pre-filtering
- **Result**: FINVIZ approach provides higher-quality candidates (RSI pre-filtered) despite lower volume

### Best Practices

1. **Use FINVIZ two-stage for regular screening**: Maximizes candidate quality, stays within FMP free tier
2. **Run FMP-only for one-time analysis**: Good for testing or when FINVIZ subscription not available
3. **Run during off-peak hours**: Lower chance of rate limits
4. **Space out runs**: Once daily or weekly, not multiple times per hour
5. **Cache results**: Save JSON output and analyze locally
6. **Upgrade if needed**: If screening >30 stocks daily, consider a paid FMP plan (see `site.financialmodelingprep.com/pricing-plans` in a browser)

## Error Handling

### Common Errors

**1. Invalid API Key**
```json
{
  "Error Message": "Invalid API KEY. Please retry or visit our documentation."
}
```
**Solution**: Check API key, verify it's active in FMP dashboard

**2. Rate Limit Exceeded (429)**
```json
{
  "Error Message": "You have exceeded the rate limit. Please wait."
}
```
**Solution**: Script automatically retries once after 60 seconds. If persistent, wait 24 hours for rate limit reset.

**3. Symbol Not Found**
```json
{
  "Error Message": "Invalid ticker symbol"
}
```
**Solution**: Script skips symbol and continues (expected for delisted/invalid tickers)

**4. Insufficient Price Data for RSI**
- Empty array or < 20 days of price data
**Solution**: Script skips symbol (common for newly listed stocks, low-volume stocks, or data gaps)

**5. Insufficient Dividend Data**
- Empty dividend history or < 4 years of data
**Solution**: Script skips symbol (requires 4+ years to calculate 3-year CAGR)

### Debugging

**Check request count:**
```bash
# Count API calls in script output
python3 scripts/screen_dividend_growth_rsi.py 2>&1 | grep "Analyzing" | wc -l
```

**Monitor rate limit status:**
Script outputs warning when approaching limit:
```
⚠️  API rate limit reached after analyzing 41 stocks.
Returning results collected so far: 3 qualified stocks
```

**Verbose debugging (if needed):**
Add at top of script:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Data Quality Considerations

### Data Freshness

- **Annual statements**: Updated after fiscal year end (delays possible)
- **Real-time prices**: Updated during market hours
- **Dividend history**: Updated after declaration/payment
- **RSI calculation**: Based on most recent 30 days of price data

### Data Gaps

Some stocks may have:
- **Incomplete price history**: < 30 days (newly public, suspended trading)
- **Missing dividends**: Not all dividend-paying stocks report via API
- **Inconsistent metrics**: Different accounting standards, restatements
- **Adjusted prices**: Stock splits, dividends affect historical prices

**Script behavior**: Skips stocks with insufficient data (requires 4+ years dividends, 30+ days prices)

### Data Accuracy

FMP sources data from:
- SEC EDGAR filings (US companies)
- Exchange data feeds (real-time prices)
- Company investor relations

**Note**: Always verify critical investment decisions with:
- Company filings (10-K, 10-Q) at sec.gov
- Company investor relations websites
- Multiple data sources for confirmation

### RSI Calculation Accuracy

**Inputs:**
- 30 days of closing prices (ensures 14-period RSI + buffer)
- Standard 14-period RSI formula

**Potential issues:**
- **Data gaps**: Weekends, holidays, halted trading (script uses available data)
- **Split adjustments**: FMP provides adjusted prices (correct behavior)
- **Intraday volatility**: RSI uses only closing prices (not intraday highs/lows)

**Validation**: Compare calculated RSI with other sources (TradingView, Yahoo Finance) to verify accuracy.

## Screening Workflow

### Request Sequence

```
1. Stock Screener (1 request)
   ↓ Returns 100-1000 candidates

For each candidate (up to max-candidates limit):

2. Dividend History (1 request)
   ↓ Calculate dividend yield and CAGR
   ↓ If yield < 1.5% or CAGR < 12% → Skip

3. Historical Prices (1 request)
   ↓ Calculate RSI
   ↓ If RSI > 40 → Skip

4. Income Statement (1 request)
   ↓ Calculate revenue/EPS growth
   ↓ If negative growth → Skip

5. Balance Sheet (1 request)
   ↓ Check financial health
   ↓ If unhealthy ratios → Skip

6. Cash Flow (1 request)
   ↓ Calculate FCF payout ratio

7. Key Metrics (1 request)
   ↓ Extract ROE, margins, valuation

8. Composite Scoring
   ↓ Rank qualified stocks

9. Output JSON + Markdown Report
```

**Optimization**: Early exits reduce API calls. If a stock fails dividend or RSI checks (steps 2-3), remaining 4 API calls are skipped.

## API Documentation

**Official Docs**: https://financialmodelingprep.com/developer/docs

**Key Sections:**
- Stock Fundamentals API
- Stock Screener API
- Historical Dividend API
- Historical Price API
- Ratios API

**Support**: support@financialmodelingprep.com

## Alternative Data Sources

If FMP limits are restrictive:

1. **Alpha Vantage**: Free tier, 500 requests/day, includes RSI endpoint
2. **Yahoo Finance (yfinance)**: Free, unlimited, Python library available
3. **Quandl/Nasdaq Data Link**: Free tier available for fundamental data
4. **IEX Cloud**: Free tier, 50k messages/month

**Implementation Notes:**
- Alternative sources require script modifications for different data formats
- Yahoo Finance (yfinance) provides built-in RSI calculation
- Alpha Vantage has dedicated technical indicators endpoint

**yfinance Example (Free Alternative):**
```python
import yfinance as yf

# Get stock data
ticker = yf.Ticker("AAPL")

# Dividend history
dividends = ticker.dividends

# Historical prices
prices = ticker.history(period="1mo")

# Calculate RSI manually or use TA-Lib
```

**Trade-offs:**
- FMP: Structured, comprehensive, rate-limited
- yfinance: Free, unlimited, less reliable (Yahoo API changes frequently)
- Alpha Vantage: Good for technical indicators, limited fundamental data

## Troubleshooting

### "No Results Found"

**Possible Causes:**
1. All stocks failed RSI check (market not oversold)
2. High dividend growth (12%+) is rare
3. API rate limit reached before finding qualified stocks

**Solutions:**
- Relax RSI: `--rsi-max 45`
- Lower dividend growth: `--min-div-growth 10.0`
- Reduce candidates: `--max-candidates 30` to avoid rate limit
- Check during market corrections (more oversold opportunities)

### "Rate Limit Reached Quickly"

**Causes:**
- Used API for other purposes earlier today
- Script analyzed many stocks before finding qualified ones
- API limit reset not yet occurred (resets at UTC midnight)

**Solutions:**
- Wait 24 hours for rate limit reset
- Use `--max-candidates 30` to conserve requests
- Upgrade to a paid FMP plan (see `site.financialmodelingprep.com/pricing-plans` in a browser)
- Check current usage in FMP dashboard

### "RSI Calculation Errors"

**Causes:**
- Stock has < 20 days of trading history
- Data gaps (suspended trading, newly listed)
- API returned incomplete price data

**Solution:**
Script automatically skips these stocks with warning:
```
⚠️  Insufficient price data for RSI calculation
```

No action needed - this is expected behavior.

---

**Last Updated**: November 2025
**Script Version**: 1.0
**FMP API Version**: v3
