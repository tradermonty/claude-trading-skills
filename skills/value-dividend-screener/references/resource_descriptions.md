# Resource Descriptions

Moved verbatim from `SKILL.md`.

### scripts/screen_dividend_stocks.py

Comprehensive screening script that:
- Interfaces with FMP API for data retrieval
- Implements multi-phase filtering logic
- Calculates growth rates (CAGR) over 3-year periods
- Evaluates dividend sustainability via payout ratios and FCF coverage
- Assesses financial health (debt-to-equity, current ratio)
- Computes quality scores (ROE, profit margins)
- Ranks stocks by composite scoring system
- Outputs structured JSON results

**Dependencies:** `requests` library (install via `pip install -r skills/value-dividend-screener/requirements.txt`)

**Rate limiting:** Built-in delays to respect FMP API limits (250 requests/day free tier)

**Error handling:** Graceful degradation for missing data, rate limit retries, API errors

### references/screening_methodology.md

Comprehensive documentation of screening approach:

**Phase 1: Initial Quantitative Filters**
- Dividend yield >= 3.5% rationale and calculation
- P/E ratio <= 20 threshold justification
- P/B ratio <= 2 valuation logic

**Phase 2: Growth Quality Filters**
- Dividend growth (3-year CAGR >= 5%)
- Revenue positive trend analysis
- EPS positive trend analysis

**Phase 3: Quality & Sustainability Analysis**
- Dividend sustainability metrics (payout ratios, FCF coverage)
- Financial health indicators (D/E, current ratio)
- Quality scoring methodology (ROE, profit margins)

**Composite Scoring System (0-100 points)**
- Score component breakdown and weighting
- Interpretation guidelines

**Investment Philosophy**
- Why this approach works
- What this strategy avoids (dividend traps, value traps)
- Ideal candidate profile

**Usage Notes & Limitations**
- Best practices for portfolio construction
- When to sell criteria
- Historical context for threshold selection

### references/fmp_api_guide.md

Complete guide for Financial Modeling Prep API:

**API Key Setup**
- Obtaining free API key
- Setting environment variables
- Free tier limits (250 requests/day)

**Key Endpoints Used**
- Stock Screener API
- Income Statement API
- Balance Sheet API
- Cash Flow Statement API
- Key Metrics API
- Historical Dividend API

**Rate Limiting Strategy**
- Built-in protection in script
- Request budget management
- Best practices for free tier

**Error Handling**
- Common errors and solutions
- Debugging techniques

**Data Quality Considerations**
- Data freshness and gaps
- Data accuracy caveats
- When to verify with SEC filings
