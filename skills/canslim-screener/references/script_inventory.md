# Script Inventory

Moved verbatim from `SKILL.md`.

**Main Scripts:**
- `screen_canslim.py` - Main orchestrator script
  - Entry point for screening workflow
  - Handles argument parsing, API coordination, ranking, reporting
  - Usage: `python3 screen_canslim.py --api-key KEY [options]`

- `fmp_client.py` - FMP API client wrapper
  - Rate limiting (0.3s between calls)
  - 429 error handling with 60s retry
  - Session-based caching
  - Methods: `get_income_statement()`, `get_quote()`, `get_historical_prices()`, `get_institutional_holders()`

- `finviz_stock_client.py` - Finviz web scraping client ← **NEW**
  - BeautifulSoup-based HTML parsing
  - Fetches institutional ownership % from Finviz.com
  - Rate limiting (2.0s between calls)
  - No API key required (free web scraping)
  - Methods: `get_institutional_ownership()`, `get_stock_data()`

**Calculators (`scripts/calculators/`):**
- `earnings_calculator.py` - C component (Current Earnings)
  - Quarterly EPS/revenue growth (YoY)
  - Scoring: 50%+ = 100pts, 30-49% = 80pts, 18-29% = 60pts

- `growth_calculator.py` - A component (Annual Growth)
  - 3-year EPS CAGR calculation
  - Stability check (no negative growth years)
  - Scoring: 40%+ = 90pts, 30-39% = 70pts, 25-29% = 50pts

- `new_highs_calculator.py` - N component (Newness)
  - Distance from 52-week high
  - Volume-confirmed breakout detection
  - Scoring: 5% of high + breakout = 100pts, 10% + breakout = 80pts

- `supply_demand_calculator.py` - S component (Supply/Demand) ← **NEW**
  - Volume-based accumulation/distribution analysis
  - Up-day volume vs down-day volume ratio (60-day lookback)
  - Scoring: ratio ≥2.0 = 100pts, 1.5-2.0 = 80pts, 1.0-1.5 = 60pts

- `leadership_calculator.py` - L component (Leadership/Relative Strength)
  - 52-week stock performance vs S&P 500 benchmark
  - RS Rank estimation (1-99 scale, O'Neil style)
  - Scoring: RS 90+ outperforming market = 100pts, RS 80-89 = 80pts

- `institutional_calculator.py` - I component (Institutional)
  - Institutional holder count (from FMP)
  - Ownership % (from FMP or Finviz fallback)
  - Superinvestor detection (Berkshire Hathaway, Baupost, etc.)
  - Scoring: 50-100 holders + 30-60% ownership = 100pts

- `market_calculator.py` - M component (Market Direction)
  - S&P 500 vs 50-day EMA
  - VIX-adjusted scoring
  - Scoring: Strong uptrend = 100pts, Uptrend = 80pts, Bear market = 0pts

**Supporting Modules:**
- `scorer.py` - Composite score calculation
  - Phase 3 weighted average: C×15% + A×20% + N×15% + S×15% + L×20% + I×10% + M×5%
  - Rating interpretation (Exceptional+/Exceptional/Strong/etc.)
  - Minimum threshold validation (all 7 components must meet baseline)

- `report_generator.py` - Output generation
  - JSON export (programmatic use)
  - Markdown export (human-readable)
  - Phase 3 component breakdown tables (all 7 components)
  - Summary statistics calculation
