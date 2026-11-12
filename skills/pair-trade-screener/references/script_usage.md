# Script Usage

Available scripts, moved verbatim from `SKILL.md`.

### scripts/find_pairs.py

**Purpose:** Screen for cointegrated pairs within a sector or custom list.

**Usage:**
```bash
# Sector-based screening
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/find_pairs.py \
  --sector Technology \
  --min-correlation 0.70 \
  --output /tmp/pair-trade/technology.json

# Custom stock list
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/find_pairs.py \
  --symbols AAPL,MSFT,GOOGL,META \
  --min-correlation 0.75 \
  --output /tmp/pair-trade/custom.json

# Full options
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/find_pairs.py \
  --sector Financials \
  --min-correlation 0.70 \
  --min-market-cap 2000000000 \
  --lookback-days 730 \
  --output /tmp/pair-trade/financials.json
```

**Parameters:**
- `--sector`: Sector name (Technology, Financials, etc.)
- `--symbols`: Comma-separated list of tickers (alternative to sector)
- `--min-correlation`: Minimum correlation threshold (default: 0.70)
- `--min-market-cap`: Minimum market cap filter (default: $2B)
- `--lookback-days`: Historical data period (default: 730 days)
- `--output`: Output JSON file (default: `pair_analysis.json`)
- `--api-key`: FMP API key (or set FMP_API_KEY env var)

**Output:**
```json
[
  {
    "pair": "AAPL/MSFT",
    "stock_a": "AAPL",
    "stock_b": "MSFT",
    "correlation": 0.87,
    "beta": 1.15,
    "cointegration_pvalue": 0.012,
    "adf_statistic": -3.45,
    "half_life_days": 42,
    "current_zscore": -2.3,
    "signal": "LONG",
    "strength": "Strong"
  }
]
```

### scripts/analyze_spread.py

**Purpose:** Analyze a specific pair's spread behavior and generate trading signals.

**Usage:**
```bash
# Analyze specific pair
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/analyze_spread.py \
  --stock-a AAPL \
  --stock-b MSFT

# Custom lookback period
uv run --with 'statsmodels>=0.14,<0.15' python \
  skills/pair-trade-screener/scripts/analyze_spread.py \
  --stock-a JPM \
  --stock-b BAC \
  --lookback-days 365 \
  --entry-zscore 2.0 \
  --exit-zscore 0.5
```

**Parameters:**
- `--stock-a`: First stock ticker
- `--stock-b`: Second stock ticker
- `--lookback-days`: Analysis period (default: 365)
- `--entry-zscore`: Z-score threshold for entry (default: 2.0)
- `--exit-zscore`: Z-score threshold for exit (default: 0.0)
- `--api-key`: FMP API key

**Output:**
- Current spread analysis
- Z-score calculation
- Entry/exit recommendations
- Position sizing
- Historical z-score chart (text)
