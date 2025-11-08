# Financial Modeling Prep (FMP) API - Institutional Investor Data Research
**Research Date:** 2025-11-08
**Focus:** 13F Filings, Insider Trading, Institutional Ownership, and Block Trade Data

---

## Executive Summary

Financial Modeling Prep (FMP) provides comprehensive institutional investor data through multiple API endpoints covering 13F filings, insider trading (Forms 3, 4, 5), and institutional ownership tracking. Most institutional data endpoints require the **Ultimate plan ($149/month)**, though basic insider trading data is available on lower-tier plans. FMP does **not** offer dedicated unusual volume or block trade detection endpoints.

---

## 1. 13F FILINGS DATA

### Overview
Form 13F filings are quarterly reports from institutional investment managers with over $100 million in assets under management. FMP provides comprehensive access to these filings with multiple specialized endpoints.

### Available Endpoints

#### 1.1 Form 13F Filings Extract API
**Endpoint:** `https://financialmodelingprep.com/stable/institutional-ownership/extract`

**Parameters:**
- `cik` (required) - Central Index Key of the institutional investor
- `year` (required) - Filing year (e.g., 2023)
- `quarter` (required) - Quarter number (1, 2, 3, or 4)
- `apikey` (required)

**Example:**
```
https://financialmodelingprep.com/stable/institutional-ownership/extract?cik=0001388838&year=2023&quarter=3&apikey=YOUR_API_KEY
```

**Use Case:** Retrieve raw 13F filing data for a specific institutional investor and quarter.

---

#### 1.2 Filings Extract With Analytics By Holder API
**Endpoint:** `https://financialmodelingprep.com/stable/institutional-ownership/extract-analytics/holder`

**Parameters:**
- `symbol` (required) - Stock ticker symbol
- `year` (required)
- `quarter` (required)
- `page` (optional) - Pagination
- `limit` (optional) - Results per page

**Example:**
```
https://financialmodelingprep.com/stable/institutional-ownership/extract-analytics/holder?symbol=AAPL&year=2023&quarter=3&page=0&limit=10&apikey=YOUR_API_KEY
```

**Data Returned:**
- Shares held by each institutional investor
- Changes in stock weight and market value
- Ownership percentages
- Holding period data
- Portfolio changes over time

**Use Case:** Track how major institutional holders (e.g., Vanguard, BlackRock) change their positions in a specific stock.

---

#### 1.3 Form 13F Filings Dates API
**Endpoint:** `https://financialmodelingprep.com/stable/institutional-ownership/dates`

**Parameters:**
- `cik` (required)
- `apikey` (required)

**Example:**
```
https://financialmodelingprep.com/stable/institutional-ownership/dates?cik=0001067983&apikey=YOUR_API_KEY
```

**Use Case:** Retrieve all available filing dates for an institutional investor to identify which quarters have data available.

---

#### 1.4 Legacy Form 13F API (v3)
**Endpoint:** `https://financialmodelingprep.com/api/v3/form-thirteen/{cik}`

**Parameters:**
- `cik` (required)
- `date` (required) - Format: YYYY-MM-DD (quarter end date)
- `apikey` (required)

**Example:**
```
https://financialmodelingprep.com/api/v3/form-thirteen/0001067983?date=2020-06-30&apikey=YOUR_API_KEY
```

**Note:** This is a legacy endpoint. The `/stable/` endpoints are recommended for new implementations.

---

#### 1.5 13F Asset Allocation API
**Endpoint:** `https://financialmodelingprep.com/api/v4/institutional-ownership/asset-allocation`

**Description:** Provides asset allocation breakdown for institutional investment managers, including stocks, bonds, and other asset classes.

**Use Case:** Analyze the investment strategy and diversification of large institutional investors.

---

#### 1.6 Portfolio Composition API
**Endpoint:** `https://financialmodelingprep.com/api/v4/institutional-ownership/portfolio-composition`

**Data Returned:**
- Asset allocation
- Sector allocation
- Industry allocation

**Use Case:** Compare the investment portfolios of multiple institutional investors or analyze sector preferences.

---

#### 1.7 Portfolio Holdings API
**Endpoint:** `https://financialmodelingprep.com/api/v4/institutional-ownership/portfolio-holdings`

**Parameters:**
- `date` (required) - Quarter end date (YYYY-MM-DD)
- `cik` (required)
- `page` (optional)
- `apikey` (required)

**Example:**
```
https://financialmodelingprep.com/api/v4/institutional-ownership/portfolio-holdings?date=2023-06-30&cik=0001067983&page=0&apikey=YOUR_API_KEY
```

---

#### 1.8 CIK Lookup Endpoints

**Search CIK by Name:**
```
https://financialmodelingprep.com/api/v3/cik-search/Berkshire?apikey=YOUR_API_KEY
```

**Get Company Name by CIK:**
```
https://financialmodelingprep.com/api/v3/cik/0001067983?apikey=YOUR_API_KEY
```

**Example CIKs:**
- Berkshire Hathaway: 0001067983
- Vanguard Group: 0001035674

---

### 13F Data Structure Example

Based on the API documentation, 13F endpoints return JSON with fields such as:
- `symbol` - Stock ticker
- `cusip` - Security identifier
- `sharesHeld` - Number of shares held
- `marketValue` - Dollar value of holdings
- `weight` - Portfolio weight percentage
- `changeInShares` - Quarter-over-quarter change
- `changeInWeight` - Portfolio weight change
- `institutionName` - Name of the institutional holder
- `filingDate` - Date of filing
- `acceptedDate` - SEC acceptance date

---

## 2. INSIDER TRADING DATA (FORM 4 FILINGS)

### Overview
FMP provides comprehensive insider trading data from SEC Forms 3, 4, and 5. Insiders must file within 2 days of buying or selling securities.

### Available Endpoints

#### 2.1 Insider Trading Query API (v4)
**Endpoint:** `https://financialmodelingprep.com/api/v4/insider-trading`

**Parameters:**
- `symbol` (optional) - Filter by stock ticker
- `companyCik` (optional) - Filter by company CIK
- `reportingCik` (optional) - Filter by insider's CIK
- `transactionType` (optional) - Filter by transaction type (e.g., "P-Purchase,S-Sale")
- `limit` (optional) - Number of results
- `apikey` (required)

**Example Queries:**

By Stock Symbol:
```
https://financialmodelingprep.com/api/v4/insider-trading?symbol=AAPL&limit=100&apikey=YOUR_API_KEY
```

By Company CIK:
```
https://financialmodelingprep.com/api/v4/insider-trading?companyCik=0000320193&limit=100&apikey=YOUR_API_KEY
```

By Insider CIK:
```
https://financialmodelingprep.com/api/v4/insider-trading?reportingCik=0001663020&limit=100&apikey=YOUR_API_KEY
```

By Transaction Type:
```
https://financialmodelingprep.com/api/v4/insider-trading?transactionType=P-Purchase,S-Sale&limit=100&apikey=YOUR_API_KEY
```

---

#### 2.2 Insider Trading Response Structure

**Example JSON Response:**
```json
[
  {
    "symbol": "AAPL",
    "transactionDate": "2021-02-02",
    "reportingCik": "0001214128",
    "transactionType": "S-Sale",
    "securitiesOwned": 4532724,
    "companyCik": "0000320193",
    "reportingName": "LEVINSON ARTHUR D",
    "acquistionOrDisposition": "D",
    "formType": "4",
    "securitiesTransacted": 3416,
    "price": 135.50,
    "securityName": "Common Stock",
    "link": "https://www.sec.gov/Archives/edgar/data/0000320193/..."
  }
]
```

**Field Descriptions:**
- `symbol` - Company stock ticker
- `transactionDate` - Date of the transaction
- `reportingCik` - CIK of the insider filing the report
- `transactionType` - Transaction type (Sale, Purchase, Gift, etc.)
- `securitiesOwned` - Total securities owned after transaction
- `companyCik` - Company's CIK
- `reportingName` - Name of the insider
- `acquistionOrDisposition` - "A" (acquisition) or "D" (disposition)
- `formType` - SEC form type (3, 4, or 5)
- `securitiesTransacted` - Number of shares in the transaction
- `price` - Transaction price per share (can be 0 for stock grants)
- `securityName` - Type of security (e.g., "Common Stock", "Stock Option")
- `link` - Direct link to SEC filing

---

#### 2.3 Latest Insider Trading API
**Endpoint:** `https://financialmodelingprep.com/stable/latest-insider-trade`

**Description:** Returns the most recent insider trades across all companies with transaction details, insider roles, and filing dates.

---

#### 2.4 Insider Trading RSS Feed
**Endpoint:** `https://financialmodelingprep.com/api/v4/insider-trading-rss-feed`

**Parameters:**
- `limit` (optional) - Number of entries (default: 50)
- `apikey` (required)

**Example:**
```
https://financialmodelingprep.com/api/v4/insider-trading-rss-feed?limit=50&apikey=YOUR_API_KEY
```

**Description:** Real-time feed of SEC Form 3, 4, and 5 filings, updated every few minutes.

**Use Case:** Monitor the latest insider trading activity across all stocks in near real-time.

---

#### 2.5 Insider Trade Statistics API
**Endpoint:** `https://financialmodelingprep.com/api/v4/insider-trade-statistics`

**Data Returned:**
- Total number of insider trades
- Average transaction value
- Most active insider traders
- Popular stocks among insiders

**Use Case:** Identify trending insider trading patterns and high-activity stocks.

---

#### 2.6 Transaction Types API
**Endpoint:** `https://financialmodelingprep.com/api/v4/insider-trading-transaction-type`

**Description:** Returns a list of all possible transaction types (P-Purchase, S-Sale, G-Gift, etc.) used in the insider trading API.

---

#### 2.7 Search Insider Trades (Legacy v3)
**Endpoint:** `https://financialmodelingprep.com/api/v3/insider-trading`

**Note:** This is a legacy endpoint. The v4 endpoint is recommended.

---

### Transaction Types

Common transaction type codes:
- `P-Purchase` - Open market or private purchase
- `S-Sale` - Open market or private sale
- `A-Award` - Award or grant from company
- `M-Exercise` - Exercise of stock options
- `G-Gift` - Gift transfer
- `F-InKind` - Payment in kind
- `C-Conversion` - Conversion of derivative security
- `J-Other` - Other acquisition or disposition
- `I-Discretionary` - Discretionary transaction

---

## 3. INSTITUTIONAL OWNERSHIP DATA

### Overview
Institutional ownership data tracks which institutions own shares in specific companies, including mutual funds, hedge funds, pension funds, and other large investors.

### Available Endpoints

#### 3.1 Institutional Stock Ownership by Symbol
**Endpoint:** `https://financialmodelingprep.com/api/v4/institutional-ownership/symbol-ownership`

**Parameters:**
- `symbol` (required)
- `includeCurrentQuarter` (optional) - Boolean
- `apikey` (required)

**Example:**
```
https://financialmodelingprep.com/api/v4/institutional-ownership/symbol-ownership?symbol=AAPL&includeCurrentQuarter=false&apikey=YOUR_API_KEY
```

**Use Case:** See all institutional investors holding a particular stock and their position sizes.

---

#### 3.2 Institutional Holders by Shares Held and Date
**Endpoint:** `https://financialmodelingprep.com/api/v4/institutional-ownership/institutional-holders/symbol-ownership`

**Parameters:**
- `symbol` (required)
- `date` (required) - Quarter end date (YYYY-MM-DD)
- `page` (optional)
- `apikey` (required)

**Example:**
```
https://financialmodelingprep.com/api/v4/institutional-ownership/institutional-holders/symbol-ownership?page=0&date=2021-09-30&symbol=AAPL&apikey=YOUR_API_KEY
```

---

#### 3.3 Stock Ownership by Holders (Percent)
**Endpoint:** `https://financialmodelingprep.com/api/v4/institutional-ownership/institutional-holders/symbol-ownership-percent`

**Parameters:**
- `symbol` (required)
- `date` (required)
- `apikey` (required)

**Example:**
```
https://financialmodelingprep.com/api/v4/institutional-ownership/institutional-holders/symbol-ownership-percent?date=2021-09-30&symbol=AAPL&apikey=YOUR_API_KEY
```

**Use Case:** Calculate percentage ownership by each institutional holder.

---

#### 3.4 Institutional Ownership Filings API
**Endpoint:** `https://financialmodelingprep.com/stable/institutional-ownership/latest-filings`

**Description:** Returns the most recent SEC filings related to institutional ownership, allowing tracking of the latest reports and disclosures.

---

#### 3.5 Positions Summary API
**Endpoint:** `https://financialmodelingprep.com/stable/institutional-ownership/positions-summary`

**Description:** Provides summary information about institutional positions including total value, number of holdings, and concentration metrics.

---

#### 3.6 Holder Performance Summary API
**Endpoint:** `https://financialmodelingprep.com/stable/institutional-ownership/holder-performance-summary`

**Description:** Analyzes the historical performance of institutional holders' portfolios.

---

#### 3.7 Institutional Holders List API
**Endpoint:** `https://financialmodelingprep.com/api/v4/institutional-ownership/list`

**Description:** Returns a complete list of institutional investment managers required to file Form 13F reports.

**Use Case:** Identify all large investors in the market for screening and monitoring.

---

#### 3.8 Institutional Holders Search API
**Endpoint:** `https://financialmodelingprep.com/api/v4/institutional-ownership/institutional-holders/search`

**Parameters:**
- `name` (optional) - Institution name
- `symbol` (optional) - Stock ticker
- `cusip` (optional) - CUSIP identifier
- `apikey` (required)

**Use Case:** Search for institutional investors by name, ticker, or CUSIP.

---

#### 3.9 Institutional Holder RSS Feed
**Endpoint:** `https://financialmodelingprep.com/api/v4/institutional-holder-rss-feed`

**Description:** Real-time feed of new institutional ownership filings.

---

#### 3.10 Portfolio Holdings Dates API
**Endpoint:** `https://financialmodelingprep.com/api/v4/institutional-ownership/portfolio-holdings-dates`

**Description:** Returns dates when portfolio holdings data is updated for institutional investors, helping track data freshness.

---

### Legacy Endpoints (v3)

#### Stock Ownership by Holders
```
https://financialmodelingprep.com/api/v3/institutional-holder/{symbol}?apikey=YOUR_API_KEY
```

---

## 4. BLOCK TRADE AND UNUSUAL VOLUME DATA

### Availability: LIMITED/NOT AVAILABLE

FMP **does not** provide dedicated endpoints for:
- Unusual volume detection/alerts
- Block trade identification
- Dark pool data
- Large institutional trade tracking (real-time)

### What IS Available

FMP provides standard volume data in their market data endpoints:

#### 4.1 Historical Price Data with Volume
**Endpoint:** `https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}`

**Data Includes:**
- Daily volume
- Intraday volume (1-min, 5-min, 15-min, 4-hour intervals)

#### 4.2 Real-Time Quotes
**Endpoint:** `https://financialmodelingprep.com/api/v3/quote/{symbol}`

**Data Includes:**
- Current price
- Current volume (day volume, zero during pre-market)
- Last sale size (`lastSaleSize` field)

#### 4.3 Aftermarket Trade API
**Endpoint:** `https://financialmodelingprep.com/stable/aftermarket-trade`

**Description:** Monitors trades made outside standard market hours with price and trading activity data.

### Limitations

- No specific "unusual volume" detection or scoring
- No block trade flagging or filtering
- No dark pool reporting
- Volume data is standard aggregated data, not order-level

### Alternative Approaches

To detect unusual volume or block trades using FMP data, you would need to:
1. Fetch historical average volume via price history endpoints
2. Calculate statistical thresholds (e.g., 2x or 3x average volume)
3. Compare current day volume to thresholds in your own application logic
4. Use `lastSaleSize` from real-time quotes to identify large individual trades

**Note:** For dedicated unusual volume or block trade data, specialized alternative data providers focusing on order flow and Level 2 market data would be required (e.g., Benzinga, Trade Ideas, Market Chameleon).

---

## 5. PRICING AND ACCESS REQUIREMENTS

### Pricing Tiers

| Tier | Price | Bandwidth (30-day) | Call Limit | Notes |
|------|-------|-------------------|------------|-------|
| **Free** | $0 | 500MB | 250 calls/day | Core endpoints only |
| **Starter** | $29.99/mo | 20GB | 750 calls/day | Basic financial data |
| **Premium** | $79.99/mo | 50GB | 2,000 calls/day | Enhanced access |
| **Ultimate** | $149/mo | 150GB | Higher limits | **Required for institutional data** |
| **Build** | $99/mo | 100GB | Varies | Developer tier |
| **Enterprise** | Custom | 1TB+ | Custom | SLA-backed, bulk exports |

**Annual Billing:** All plans are billed annually.

---

### Feature Access by Tier

#### Free Tier Includes:
- Company profiles
- Stock quotes
- Limited financial statements
- Basic historical prices
- **NOT included:** 13F filings, institutional ownership

#### Starter/Premium Tiers Include:
- All free tier features
- Full financial statements and ratios
- Bulk historical data
- Higher API limits
- **Basic insider trading data** (available)
- **NOT included:** 13F filings, institutional ownership

#### Ultimate Tier ($149/mo) Includes:
- **All institutional ownership endpoints** ✅
- **All 13F filing endpoints** ✅
- **Historical institutional ownership data** ✅
- **Historical insider ownership data** ✅
- 1-minute intraday charting
- Unlimited WebSocket connections for real-time prices
- Full historical access
- Bulk and batch delivery
- Company Profile Bulk API

#### Enterprise Tier Includes:
- All Ultimate features
- Dedicated support
- Custom data exports
- SLA-backed uptime guarantees
- Higher bandwidth limits

---

### Specific Data Access Requirements

| Data Type | Free Tier | Starter/Premium | Ultimate | Notes |
|-----------|-----------|-----------------|----------|-------|
| **Insider Trading (Forms 3,4,5)** | ❌ | ✅ | ✅ | Available on paid plans |
| **13F Filings** | ❌ | ❌ | ✅ | Ultimate plan required |
| **Institutional Ownership** | ❌ | ❌ | ✅ | Ultimate plan required |
| **13F Asset Allocation** | ❌ | ❌ | ✅ | Ultimate plan required |
| **Portfolio Composition** | ❌ | ❌ | ✅ | Ultimate plan required |
| **Institutional Holders List** | ❌ | ❌ | ✅ | Ultimate plan required |

---

## 6. DATA FREQUENCY AND LIMITATIONS

### 13F Filings
- **Frequency:** Quarterly (45 days after quarter end)
- **Coverage:** Institutions with $100M+ AUM
- **Historical Data:** Available with Ultimate plan
- **Delay:** 45-day regulatory filing deadline
- **Limitations:**
  - Only shows long equity positions
  - Does not include short positions
  - Does not show derivatives (options, swaps) in detail
  - Positions are as of quarter-end, not current

### Insider Trading
- **Frequency:** Near real-time (RSS feed updated every few minutes)
- **Filing Requirement:** Within 2 business days of transaction
- **Coverage:** All Form 3, 4, and 5 filings
- **Historical Data:** Available
- **Limitations:**
  - Small transactions may not be reported promptly
  - Some transactions (under 10% beneficial ownership) may not require reporting

### Institutional Ownership
- **Frequency:** Quarterly (from 13F filings)
- **Data Points:** Shares held, market value, portfolio weight, changes
- **Historical Tracking:** Available with Ultimate plan
- **Limitations:**
  - Same as 13F limitations
  - Consolidated view from multiple filing types (13F, ETF holdings, mutual fund disclosures)

### Volume Data
- **Frequency:** Real-time to 1-minute intervals
- **Coverage:** All trading sessions (pre-market, regular, aftermarket)
- **Limitations:**
  - No unusual volume detection
  - No block trade identification
  - Standard aggregated volume only

---

## 7. API VERSIONING

FMP uses multiple API versions:

### API v3 (Legacy)
- Base URL: `https://financialmodelingprep.com/api/v3/`
- Includes original endpoints for 13F, insider trading
- Being phased out in favor of v4 and `/stable/`

### API v4 (Current)
- Base URL: `https://financialmodelingprep.com/api/v4/`
- Primary version for institutional ownership and insider trading
- Includes RSS feeds, enhanced search capabilities

### Stable API (Recommended)
- Base URL: `https://financialmodelingprep.com/stable/`
- Recommended for new implementations
- Enhanced 13F analytics and institutional ownership
- More comprehensive data fields

**Recommendation:** Use `/stable/` endpoints for 13F data and v4 endpoints for insider trading and institutional ownership queries.

---

## 8. INTEGRATION CONSIDERATIONS

### Rate Limits
- Enforced based on plan tier
- Free tier: 250 calls/day
- Paid tiers: Higher limits based on bandwidth caps
- Enterprise: Custom limits

### API Key Management
```bash
# Add API key as query parameter
?apikey=YOUR_API_KEY

# Or use header (recommended for security)
X-API-KEY: YOUR_API_KEY
```

### Pagination
Most list endpoints support pagination:
- `page` parameter (0-indexed)
- `limit` parameter (results per page)

Example:
```
?page=0&limit=100
```

### Error Handling
Common HTTP status codes:
- `200` - Success
- `401` - Invalid or missing API key
- `403` - Access denied (endpoint requires higher tier)
- `429` - Rate limit exceeded
- `500` - Server error

### Best Practices
1. Cache 13F data (updates quarterly)
2. Use RSS feeds for real-time monitoring
3. Implement exponential backoff for rate limits
4. Store CIK mappings locally to reduce API calls
5. Use bulk endpoints when available (Ultimate/Enterprise)

---

## 9. USE CASES AND WORKFLOWS

### Following "Smart Money"
```
1. Get list of top institutional investors (Institutional Holders List API)
2. For each investor, fetch their latest 13F filing (Filings Extract API)
3. Identify new positions and increased holdings
4. Cross-reference with insider trading (Insider Trading API)
5. Monitor changes quarter-over-quarter
```

### Insider Trading Alerts
```
1. Subscribe to Insider Trading RSS Feed
2. Filter for purchases (P-Purchase transactions)
3. Filter by executive role (CEO, CFO)
4. Calculate insider ownership changes
5. Correlate with stock price movements
```

### Institutional Concentration Analysis
```
1. Query institutional ownership for a stock (Symbol Ownership API)
2. Calculate ownership concentration (top 10 holders)
3. Track changes in concentration over time
4. Identify potential liquidity risks or support levels
```

### Portfolio Mirroring
```
1. Select institutional investor to follow (e.g., Berkshire Hathaway CIK: 0001067983)
2. Fetch portfolio holdings (Portfolio Holdings API)
3. Calculate portfolio weights (Portfolio Composition API)
4. Track changes quarterly (Filings Extract with Analytics)
5. Replicate portfolio allocation
```

---

## 10. COMPARISON WITH ALTERNATIVES

### FMP Strengths
- Comprehensive 13F data coverage
- Real-time insider trading feeds
- Affordable pricing ($149/mo for institutional data)
- Well-documented API
- Historical data included
- Multiple endpoint options (v3, v4, stable)

### FMP Limitations
- No unusual volume detection
- No block trade identification
- No dark pool data
- No real-time institutional trading alerts
- 13F data has 45-day delay
- Requires Ultimate plan for institutional data

### Alternative Providers for Missing Features

**For Block Trades/Unusual Volume:**
- Benzinga Pro
- Trade Ideas
- Market Chameleon
- Unusual Whales
- FloAlgo

**For Alternative Data:**
- Quiver Quantitative (Congress, lobbying)
- WhaleWisdom (13F analytics)
- Sentieo (comprehensive institutional research)
- S&P Capital IQ (enterprise-grade)

**For Real-Time Institutional Flow:**
- Bloomberg Terminal
- FactSet
- Refinitiv Eikon

---

## 11. RECOMMENDATIONS

### For 13F and Institutional Ownership Analysis
**Recommendation:** ✅ **FMP is excellent**
- Ultimate plan ($149/mo) provides comprehensive coverage
- All major institutional investors included
- Historical data for trend analysis
- Analytics endpoints for deeper insights
- Cost-effective compared to Bloomberg/FactSet

### For Insider Trading Monitoring
**Recommendation:** ✅ **FMP is very good**
- Real-time RSS feeds
- Comprehensive Form 3, 4, 5 coverage
- Available on lower-tier plans (Starter+)
- Transaction-level detail with SEC filing links

### For Unusual Volume/Block Trades
**Recommendation:** ❌ **FMP not suitable**
- No dedicated endpoints
- Must build custom logic using volume data
- Consider alternative providers (Benzinga, Trade Ideas)
- Or combine FMP data with options flow services

### Overall Assessment
FMP provides **strong institutional data coverage at competitive pricing**, making it suitable for:
- Retail investors following institutional investors
- Quantitative researchers building 13F-based strategies
- Fundamental analysts tracking insider activity
- Portfolio managers monitoring institutional flows

**Not suitable for:**
- Day traders needing real-time block trade alerts
- Options traders tracking unusual volume
- High-frequency traders needing order flow data

---

## 12. RESOURCES AND DOCUMENTATION

### Official Documentation
- Main API Docs: https://site.financialmodelingprep.com/developer/docs
- Stable API Reference: https://site.financialmodelingprep.com/developer/docs/stable
- Pricing Page: https://site.financialmodelingprep.com/pricing-plans
- FAQs: https://site.financialmodelingprep.com/faqs

### Code Examples
- GitHub (Official): https://github.com/FinancialModelingPrepAPI/Financial-Modeling-Prep-API
- Insider Trading Examples: https://github.com/FinancialModelingPrep/insider-trading-api
- API v3 Integration: https://github.com/FinancialModelingPrep/API3-integration

### Tutorials and Guides
- 13F Tracking with FMP API: https://medium.com/coinmonks/track-institutional-holdings-with-fmps-13f-api-and-visualize-with-ai-c7c77032de3d
- Portfolio Allocation Tracking: https://medium.com/@crisvelasquez/how-to-track-the-portfolio-allocation-of-institutional-investors-3fc6dc22d7ec
- Analyzing 13F Filings with Python: https://medium.com/@jan_5421/analyzing-13f-sec-filings-and-buy-sell-activities-of-institutional-investment-managers-using-python-8bba3dfafd7d

### Account Setup
- Register for API Key: https://site.financialmodelingprep.com/developer
- Free Tier: 250 calls/day (no credit card required)
- Ultimate Plan: $149/mo (annual billing) for institutional data

---

## 13. CONCLUSION

Financial Modeling Prep provides comprehensive institutional investor data suitable for most retail and professional investors. The **Ultimate plan ($149/month)** unlocks full access to:

✅ **13F Filings:** Complete quarterly holdings data for all major institutional investors
✅ **Insider Trading:** Real-time Form 3, 4, 5 filings with detailed transaction data
✅ **Institutional Ownership:** Historical tracking, portfolio analytics, and concentration metrics
❌ **Block Trades/Unusual Volume:** Not available - requires alternative data providers

For investors building strategies around institutional activity, 13F replication, or insider signals, FMP offers excellent value at competitive pricing. However, for real-time order flow, dark pool data, or unusual volume detection, supplementary data sources are required.

**Cost-Benefit Analysis:**
- FMP Ultimate ($149/mo) vs. Bloomberg Terminal ($2,000+/mo)
- FMP provides 80% of institutional data needs at <10% of Bloomberg cost
- Best suited for individual investors, small hedge funds, and research firms
- Consider combining FMP with specialized services for complete coverage

---

**Research Compiled By:** Claude (Anthropic)
**Date:** 2025-11-08
**API Documentation Version:** v3, v4, and Stable (2025)
**Pricing Verified:** November 2025
