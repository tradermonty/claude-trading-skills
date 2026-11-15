# Financial Modeling Prep (FMP) API Guide

## Overview

Financial Modeling Prep provides comprehensive financial data APIs for stocks, forex, cryptocurrencies, and more. This guide focuses on endpoints used for dividend stock screening.

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
python3 scripts/screen_dividend_stocks.py --fmp-api-key your_api_key_here
```

## Key Endpoints Used

### 1. Stock Screener

**Endpoint:** `/v3/stock-screener`

**Purpose:** Initial filtering by dividend yield, P/E, P/B, market cap

**Parameters:**
- `dividendYieldMoreThan`: Minimum dividend yield (e.g., 3.5)
- `priceEarningRatioLowerThan`: Maximum P/E ratio (e.g., 20)
- `priceToBookRatioLowerThan`: Maximum P/B ratio (e.g., 2)
- `marketCapMoreThan`: Minimum market cap (e.g., 2000000000 = $2B)
- `exchange`: Exchanges to include (e.g., "NASDAQ,NYSE")
- `limit`: Max results (default: 1000)

**Example Request:**
```
https://financialmodelingprep.com/api/v3/stock-screener?
  dividendYieldMoreThan=3.5&
  priceEarningRatioLowerThan=20&
  priceToBookRatioLowerThan=2&
  marketCapMoreThan=2000000000&
  exchange=NASDAQ,NYSE&
  limit=1000&
  apikey=YOUR_API_KEY
```

**Response Format:**
```json
[
  {
    "symbol": "T",
    "companyName": "AT&T Inc.",
    "marketCap": 150000000000,
    "sector": "Communication Services",
    "industry": "Telecom Services",
    "beta": 0.65,
    "price": 20.50,
    "lastAnnualDividend": 1.11,
    "volume": 35000000,
    "exchange": "NYSE",
    "exchangeShortName": "NYSE",
    "country": "US",
    "isEtf": false,
    "isActivelyTrading": true,
    "dividendYield": 0.0541,
    "pe": 7.5,
    "priceToBook": 1.2
  }
]
```

### 2. Income Statement

**Endpoint:** `/v3/income-statement/{symbol}`

**Purpose:** Revenue, EPS, net income analysis

**Parameters:**
- `symbol`: Stock ticker (e.g., "AAPL")
- `limit`: Number of periods (e.g., 5 for 5 years)
- `period`: "annual" or "quarter"

**Example Request:**
```
https://financialmodelingprep.com/api/v3/income-statement/AAPL?
  limit=5&
  apikey=YOUR_API_KEY
```

**Key Fields Used:**
- `revenue`: Total revenue
- `eps`: Earnings per share
- `netIncome`: Net income
- `date`: Fiscal period end date

### 3. Balance Sheet Statement

**Endpoint:** `/v3/balance-sheet-statement/{symbol}`

**Purpose:** Debt, equity, liquidity analysis

**Parameters:**
- `symbol`: Stock ticker
- `limit`: Number of periods

**Key Fields Used:**
- `totalDebt`: Total debt (short-term + long-term)
- `totalStockholdersEquity`: Shareholders' equity
- `totalCurrentAssets`: Current assets
- `totalCurrentLiabilities`: Current liabilities

### 4. Cash Flow Statement

**Endpoint:** `/v3/cash-flow-statement/{symbol}`

**Purpose:** Free cash flow, dividends paid analysis

**Parameters:**
- `symbol`: Stock ticker
- `limit`: Number of periods

**Key Fields Used:**
- `operatingCashFlow`: Cash from operations
- `capitalExpenditure`: Capex (negative value)
- `dividendsPaid`: Dividends paid (negative value)
- `freeCashFlow`: OCF - Capex

### 5. Key Metrics

**Endpoint:** `/v3/key-metrics/{symbol}`

**Purpose:** ROE, ROA, and other quality metrics

**Parameters:**
- `symbol`: Stock ticker
- `limit`: Number of periods

**Key Fields Used:**
- `roe`: Return on Equity (decimal, e.g., 0.15 = 15%)
- `roa`: Return on Assets
- `roic`: Return on Invested Capital
- `debtToEquity`: Debt-to-equity ratio
- `currentRatio`: Current ratio

### 6. Historical Dividend

**Endpoint:** `/v3/historical-price-full/stock_dividend/{symbol}`

**Purpose:** Dividend history for growth rate calculation

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

## Rate Limiting Strategy

### Built-in Protection

The screening script includes rate limiting:
- **0.3 second delay** between requests (~3 requests/second)
- **Automatic retry** on 429 (rate limit exceeded) with 60-second backoff
- **Timeout**: 30 seconds per request

### Managing Request Budget

For free tier (250 requests/day):

**Requests per stock analyzed:**
- Stock Screener: 1 request (returns 100-1000 stocks)
- Income Statement: 1 request per symbol
- Balance Sheet: 1 request per symbol
- Cash Flow: 1 request per symbol
- Key Metrics: 1 request per symbol
- Dividend History: 1 request per symbol

**Total: 5 requests per symbol + 1 screener request**

**Budget allocation:**
- Initial screener: 1 request
- Detailed analysis: 5 × N stocks = 5N requests
- **Maximum stocks per run**: (250 - 1) / 5 = ~49 stocks

**Script default**: Analyzes first 100 candidates but typically finds ~20-30 that pass all criteria

### Best Practices

1. **Run during off-peak hours**: Lower chance of rate limits
2. **Space out runs**: Once daily or weekly, not multiple times per hour
3. **Cache results**: Save JSON output and analyze locally
4. **Upgrade if needed**: If screening large universes frequently, consider paid tier

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
**Solution**: Script automatically retries after 60 seconds

**3. Symbol Not Found**
```json
{
  "Error Message": "Invalid ticker symbol"
}
```
**Solution**: Script skips symbol and continues (expected for delisted/invalid tickers)

**4. Insufficient Data**
- Empty array returned for financial statements
**Solution**: Script skips symbol (common for newly listed stocks or incomplete data)

### Debugging

**Check request count:**
```bash
# Count API calls in script output
python3 scripts/screen_dividend_stocks.py 2>&1 | grep "Analyzing" | wc -l
```

**Verbose mode (add to script if needed):**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Data Quality Considerations

### Data Freshness

- **Annual statements**: Updated after fiscal year end (delays possible)
- **Quarterly data**: Available ~1-2 months after quarter end
- **Real-time prices**: Updated during market hours
- **Dividend history**: Updated after declaration/payment

### Data Gaps

Some stocks may have:
- **Incomplete history**: < 4 years of data (newly public companies)
- **Missing dividends**: Not all dividend-paying stocks report via API
- **Inconsistent metrics**: Different accounting standards, restatements

**Script behavior**: Skips stocks with insufficient data (requires 4+ years)

### Data Accuracy

FMP sources data from:
- SEC EDGAR filings (US companies)
- Company investor relations
- Exchange data feeds

**Note**: Always verify critical investment decisions with company filings (10-K, 10-Q)

## API Documentation

**Official Docs**: https://financialmodelingprep.com/developer/docs

**Key Sections:**
- Stock Fundamentals API
- Stock Screener API
- Historical Dividend API
- Ratios API

**Support**: support@financialmodelingprep.com

## Alternative Data Sources

If FMP limits are restrictive:

1. **Alpha Vantage**: Free tier, 500 requests/day
2. **Yahoo Finance (yfinance)**: Free, unlimited (but less reliable)
3. **Quandl/Nasdaq Data Link**: Free tier available
4. **IEX Cloud**: Free tier, 50k messages/month

**Note**: Alternative sources may require script modifications for different data formats.
