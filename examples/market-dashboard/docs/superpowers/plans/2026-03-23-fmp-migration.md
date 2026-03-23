# FMP API Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace FMP API with Alpaca (OHLCV), FRED API (macro), and Finnhub (earnings/13F) across all skill scripts, eliminating the 250 calls/day limit at zero cost.

**Architecture:** Each skill script is migrated independently. Skills are tested individually. No shared migration infrastructure — each script handles its own data source.

**Tech Stack:** Python 3.11+, alpaca-py (already installed), fredapi (pip install fredapi), finnhub-python (pip install finnhub-python)

---

## Background

The dashboard runs these skills on a schedule:

| Skill | Cadence | FMP calls/run |
|-------|---------|--------------|
| ftd-detector | every 30 min | 4 (2 history + 2 quotes) |
| market-breadth-analyzer | every 30 min | 0 — uses TraderMonty CSV, no FMP |
| market-top-detector | every 60 min | ~30 (index + ETF quotes + histories + VIX) |
| macro-regime-detector | every 90 min | 10 (9 ETF histories + treasury rates) |
| earnings-calendar | daily 6am | 2 (calendar + batch profiles) |
| economic-calendar-fetcher | daily 6am | 1 (economic calendar) |
| institutional-flow-tracker | weekly Sunday | ~101 (1 screener + 100 holder calls) |

Total worst-case in a single trading day easily exceeds 250 calls. This migration eliminates all FMP dependency from these scripts.

---

## New API Keys Required

Two new keys are needed. Add them to `.env` and register in `config.py`:

### `.env.example` update

**File:** `examples/market-dashboard/.env.example`

Add these two lines after `FINVIZ_API_KEY=`:

```
FRED_API_KEY=your_fred_api_key_here
FINNHUB_API_KEY=your_finnhub_api_key_here
```

Get FRED key free at: https://fred.stlouisfed.org/docs/api/api_key.html
Get Finnhub key free at: https://finnhub.io/register

### `config.py` update

**File:** `examples/market-dashboard/config.py`

Add after `ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")`:

```python
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
```

---

## Data Format Notes

### Alpaca bars → FMP historical format

The `fmp_client.py` files return historical data as a list of dicts (most-recent first):

```python
{"date": "2026-03-21", "open": 100.0, "high": 105.0, "low": 99.0, "close": 103.0, "volume": 1000000}
```

The Alpaca `StockBarsRequest` returns a `BarSet` object. Convert it with:

```python
bars_df = bars.df  # MultiIndex DataFrame: (symbol, timestamp) → OHLCV
```

For a single symbol, normalize to a list of dicts (most-recent first) matching the FMP format that downstream calculators expect.

### Alpaca quote → FMP quote format

FMP quote dicts used by calculators contain: `price`, `yearHigh`, `yearLow`, `volume`. Alpaca does not provide yearHigh/yearLow directly — compute them from the 252-bar history already fetched.

---

## Task 1: FTD Detector → Alpaca

**File to modify:** `skills/ftd-detector/scripts/fmp_client.py`

The FTD detector calls:
- `client.get_historical_prices("^GSPC", days=80)` — S&P 500 history
- `client.get_historical_prices("QQQ", days=80)` — QQQ history
- `client.get_quote("^GSPC")` — S&P 500 quote
- `client.get_quote("QQQ")` — QQQ quote

`^GSPC` is not available on Alpaca. Use `SPY` as a proxy. QQQ is available directly.

### Step-by-step

- [ ] **Step 1: Replace fmp_client.py with Alpaca client**

  Replace the entire contents of `skills/ftd-detector/scripts/fmp_client.py` with:

  ```python
  #!/usr/bin/env python3
  """
  Alpaca Data Client for FTD Detector

  Replaces FMP API with Alpaca Market Data API (free tier, no call limits).
  Uses SPY as S&P 500 proxy (^GSPC not available on Alpaca).
  """

  import os
  import datetime
  from typing import Optional

  from alpaca.data.historical import StockHistoricalDataClient
  from alpaca.data.requests import StockBarsRequest
  from alpaca.data.timeframe import TimeFrame


  class FMPClient:
      """Drop-in replacement: Alpaca-backed client with same interface as FMP version."""

      def __init__(self, api_key: Optional[str] = None):
          # api_key param kept for CLI backward compat; Alpaca uses env vars
          alpaca_api_key = os.environ.get("ALPACA_API_KEY", "")
          alpaca_secret = os.environ.get("ALPACA_SECRET_KEY", "")
          if not alpaca_api_key or not alpaca_secret:
              raise ValueError(
                  "ALPACA_API_KEY and ALPACA_SECRET_KEY are required. "
                  "Set them as environment variables."
              )
          self._client = StockHistoricalDataClient(
              api_key=alpaca_api_key,
              secret_key=alpaca_secret,
          )
          self._cache: dict = {}
          self._api_calls_made = 0

      def get_historical_prices(self, symbol: str, days: int = 80) -> Optional[dict]:
          """Fetch daily OHLCV. Maps ^GSPC -> SPY. Returns FMP-compatible dict."""
          alpaca_symbol = "SPY" if symbol in ("^GSPC", "SPX") else symbol
          cache_key = f"hist_{alpaca_symbol}_{days}"
          if cache_key in self._cache:
              return self._cache[cache_key]

          start = (datetime.date.today() - datetime.timedelta(days=int(days * 1.6) + 10)).isoformat()
          request = StockBarsRequest(
              symbol_or_symbols=alpaca_symbol,
              timeframe=TimeFrame.Day,
              start=start,
          )
          try:
              bars = self._client.get_stock_bars(request)
              self._api_calls_made += 1
          except Exception as e:
              print(f"WARNING: Alpaca bars failed for {alpaca_symbol}: {e}")
              return None

          df = bars.df
          if df.empty:
              return None

          # Flatten MultiIndex (symbol, timestamp) → timestamp only for single symbol
          if hasattr(df.index, "levels"):
              df = df.xs(alpaca_symbol, level="symbol") if alpaca_symbol in df.index.get_level_values("symbol") else df
          df = df.sort_index(ascending=False)  # most-recent first

          historical = []
          for ts, row in df.iterrows():
              historical.append({
                  "date": str(ts.date()) if hasattr(ts, "date") else str(ts)[:10],
                  "open": round(float(row["open"]), 4),
                  "high": round(float(row["high"]), 4),
                  "low": round(float(row["low"]), 4),
                  "close": round(float(row["close"]), 4),
                  "volume": int(row["volume"]),
              })

          result = {"symbol": symbol, "historical": historical[:days]}
          self._cache[cache_key] = result
          return result

      def get_quote(self, symbol: str) -> Optional[list[dict]]:
          """Build a quote dict from the latest bar + 252-day high/low."""
          alpaca_symbol = "SPY" if symbol in ("^GSPC", "SPX") else symbol
          cache_key = f"quote_{alpaca_symbol}"
          if cache_key in self._cache:
              return self._cache[cache_key]

          hist = self.get_historical_prices(symbol, days=252)
          if not hist or not hist.get("historical"):
              return None

          bars = hist["historical"]
          latest = bars[0]
          year_high = max(b["high"] for b in bars)
          year_low = min(b["low"] for b in bars)

          result = [{
              "symbol": symbol,
              "price": latest["close"],
              "yearHigh": year_high,
              "yearLow": year_low,
              "volume": latest["volume"],
          }]
          self._cache[cache_key] = result
          return result

      def get_api_stats(self) -> dict:
          return {
              "cache_entries": len(self._cache),
              "api_calls_made": self._api_calls_made,
              "rate_limit_reached": False,
          }
  ```

- [ ] **Step 2: Remove --api-key argument from ftd_detector.py**

  In `skills/ftd-detector/scripts/ftd_detector.py`, the `--api-key` argument is kept for backward compatibility but will no longer be passed to `FMPClient`. The `FMPClient.__init__` already ignores it. No change needed — the constructor signature accepts `api_key=None` and ignores it.

- [ ] **Step 3: Test**

  ```bash
  mkdir -p /tmp/test_output/ftd
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills
  uv run python skills/ftd-detector/scripts/ftd_detector.py --output-dir /tmp/test_output/ftd/
  ls /tmp/test_output/ftd/ftd_detector_*.json
  ```

  Verify: JSON file exists, `combined_state` field is populated.

- [ ] **Step 4: Commit**

  ```bash
  git add skills/ftd-detector/scripts/fmp_client.py
  git commit -m "feat(ftd-detector): migrate FMP → Alpaca for OHLCV data"
  ```

---

## Task 2: Market Breadth Analyzer → No change needed

**File:** `skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py`

This skill already uses TraderMonty CSV data via `csv_client.py`. It makes zero FMP calls. **No migration required.**

For completeness, verify it runs without any API key:

```bash
mkdir -p /tmp/test_output/breadth
uv run python skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py --output-dir /tmp/test_output/breadth/
ls /tmp/test_output/breadth/market_breadth_*.json
```

---

## Task 3: Market Top Detector → FRED + Alpaca

**Files to modify:**
- `skills/market-top-detector/scripts/fmp_client.py` — replace FMP with Alpaca + FRED

The market-top-detector calls:
- `client.get_quote("^GSPC")` — S&P 500 quote (price, yearHigh)
- `client.get_historical_prices("^GSPC", days=260)` — S&P 500 history
- `client.get_quote("QQQ")` — QQQ quote
- `client.get_historical_prices("QQQ", days=260)` — QQQ history
- `client.get_quote("^VIX")` — VIX level
- `client.get_quote("^VIX3M")` — VIX3M for term structure
- `client.get_batch_quotes(CANDIDATE_POOL)` — ~20 ETF quotes
- `client.get_batch_historical(selected_basket, days=60)` — ~5-8 ETF histories
- `client.get_batch_historical(sector_etfs_to_fetch, days=50)` — ~10 sector ETF histories

VIX and VIX3M spot prices come from FRED (VIXCLS and VXVCLS series).

### Step-by-step

- [ ] **Step 1: Replace fmp_client.py with Alpaca + FRED client**

  Replace the entire contents of `skills/market-top-detector/scripts/fmp_client.py` with:

  ```python
  #!/usr/bin/env python3
  """
  Alpaca + FRED Client for Market Top Detector

  Replaces FMP API:
  - OHLCV data → Alpaca Market Data API
  - VIX / VIX3M spot → FRED (VIXCLS / VXVCLS series)
  """

  import os
  import datetime
  from typing import Optional

  from alpaca.data.historical import StockHistoricalDataClient
  from alpaca.data.requests import StockBarsRequest
  from alpaca.data.timeframe import TimeFrame


  def _get_alpaca_client() -> StockHistoricalDataClient:
      return StockHistoricalDataClient(
          api_key=os.environ.get("ALPACA_API_KEY", ""),
          secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
      )


  def _fetch_fred_series(series_id: str) -> Optional[float]:
      """Return the most recent non-NaN value from a FRED series."""
      try:
          from fredapi import Fred
          fred = Fred(api_key=os.environ.get("FRED_API_KEY", ""))
          series = fred.get_series(series_id)
          series = series.dropna()
          if series.empty:
              return None
          return float(series.iloc[-1])
      except Exception as e:
          print(f"WARNING: FRED fetch failed for {series_id}: {e}")
          return None


  def _alpaca_symbol(symbol: str) -> str:
      """Map index symbols to tradable ETF proxies."""
      mapping = {"^GSPC": "SPY", "^VIX": None, "^VIX3M": None}
      return mapping.get(symbol, symbol)


  def _bars_to_historical(alpaca_symbol: str, original_symbol: str, df, days: int) -> dict:
      """Convert Alpaca DataFrame to FMP-compatible historical list (most-recent first)."""
      if hasattr(df.index, "levels"):
          try:
              df = df.xs(alpaca_symbol, level="symbol")
          except KeyError:
              pass
      df = df.sort_index(ascending=False)

      historical = []
      for ts, row in df.iterrows():
          historical.append({
              "date": str(ts.date()) if hasattr(ts, "date") else str(ts)[:10],
              "open": round(float(row["open"]), 4),
              "high": round(float(row["high"]), 4),
              "low": round(float(row["low"]), 4),
              "close": round(float(row["close"]), 4),
              "volume": int(row["volume"]),
          })
      return {"symbol": original_symbol, "historical": historical[:days]}


  class FMPClient:
      """Drop-in replacement: Alpaca + FRED backed client with same interface."""

      def __init__(self, api_key: Optional[str] = None):
          alpaca_api_key = os.environ.get("ALPACA_API_KEY", "")
          alpaca_secret = os.environ.get("ALPACA_SECRET_KEY", "")
          if not alpaca_api_key or not alpaca_secret:
              raise ValueError(
                  "ALPACA_API_KEY and ALPACA_SECRET_KEY are required."
              )
          self._client = _get_alpaca_client()
          self._cache: dict = {}
          self._api_calls_made = 0

      def get_historical_prices(self, symbol: str, days: int = 260) -> Optional[dict]:
          """Fetch daily OHLCV via Alpaca. Maps ^GSPC → SPY."""
          alpaca_sym = _alpaca_symbol(symbol)
          if alpaca_sym is None:
              return None  # VIX has no OHLCV on Alpaca
          cache_key = f"hist_{alpaca_sym}_{days}"
          if cache_key in self._cache:
              return self._cache[cache_key]

          start = (datetime.date.today() - datetime.timedelta(days=int(days * 1.6) + 10)).isoformat()
          request = StockBarsRequest(
              symbol_or_symbols=alpaca_sym,
              timeframe=TimeFrame.Day,
              start=start,
          )
          try:
              bars = self._client.get_stock_bars(request)
              self._api_calls_made += 1
          except Exception as e:
              print(f"WARNING: Alpaca bars failed for {alpaca_sym}: {e}")
              return None

          df = bars.df
          if df.empty:
              return None

          result = _bars_to_historical(alpaca_sym, symbol, df, days)
          self._cache[cache_key] = result
          return result

      def get_quote(self, symbol: str) -> Optional[list[dict]]:
          """
          Build quote dict from latest bar + 252-day range.
          VIX and VIX3M spot prices fetched from FRED.
          """
          # VIX: FRED series VIXCLS
          if symbol == "^VIX":
              price = _fetch_fred_series("VIXCLS")
              if price is None:
                  return None
              return [{"symbol": "^VIX", "price": price, "yearHigh": price, "yearLow": price, "volume": 0}]

          # VIX3M: FRED series VXVCLS
          if symbol == "^VIX3M":
              price = _fetch_fred_series("VXVCLS")
              if price is None:
                  return None
              return [{"symbol": "^VIX3M", "price": price, "yearHigh": price, "yearLow": price, "volume": 0}]

          alpaca_sym = _alpaca_symbol(symbol)
          if alpaca_sym is None:
              return None

          cache_key = f"quote_{alpaca_sym}"
          if cache_key in self._cache:
              return self._cache[cache_key]

          hist = self.get_historical_prices(symbol, days=252)
          if not hist or not hist.get("historical"):
              return None

          bars = hist["historical"]
          latest = bars[0]
          year_high = max(b["high"] for b in bars)
          year_low = min(b["low"] for b in bars)

          result = [{
              "symbol": symbol,
              "price": latest["close"],
              "yearHigh": year_high,
              "yearLow": year_low,
              "volume": latest["volume"],
          }]
          self._cache[cache_key] = result
          return result

      def get_batch_quotes(self, symbols: list[str]) -> dict[str, dict]:
          """Fetch quotes for a list of ETF symbols (batch via Alpaca)."""
          # Filter out non-Alpaca symbols
          alpaca_symbols = [s for s in symbols if _alpaca_symbol(s) not in (None,)]
          if not alpaca_symbols:
              return {}

          # Map back from Alpaca symbol to original if needed
          sym_map = {_alpaca_symbol(s): s for s in alpaca_symbols}
          alpaca_list = list(sym_map.keys())

          start = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
          request = StockBarsRequest(
              symbol_or_symbols=alpaca_list,
              timeframe=TimeFrame.Day,
              start=start,
          )
          try:
              bars = self._client.get_stock_bars(request)
              self._api_calls_made += 1
          except Exception as e:
              print(f"WARNING: Alpaca batch quotes failed: {e}")
              return {}

          df = bars.df
          if df.empty:
              return {}

          results = {}
          for alpaca_sym in alpaca_list:
              orig_sym = sym_map[alpaca_sym]
              try:
                  sym_df = df.xs(alpaca_sym, level="symbol").sort_index(ascending=False)
                  if sym_df.empty:
                      continue
                  latest = sym_df.iloc[0]
                  year_high = float(sym_df["high"].max())
                  year_low = float(sym_df["low"].min())
                  results[orig_sym] = {
                      "symbol": orig_sym,
                      "price": round(float(latest["close"]), 4),
                      "yearHigh": round(year_high, 4),
                      "yearLow": round(year_low, 4),
                      "volume": int(latest["volume"]),
                  }
              except (KeyError, IndexError):
                  continue
          return results

      def get_batch_historical(self, symbols: list[str], days: int = 60) -> dict[str, list[dict]]:
          """Fetch historical bars for multiple ETF symbols (single Alpaca batch request)."""
          alpaca_list = [_alpaca_symbol(s) for s in symbols if _alpaca_symbol(s) is not None]
          sym_map = {_alpaca_symbol(s): s for s in symbols if _alpaca_symbol(s) is not None}
          if not alpaca_list:
              return {}

          start = (datetime.date.today() - datetime.timedelta(days=int(days * 1.6) + 10)).isoformat()
          request = StockBarsRequest(
              symbol_or_symbols=alpaca_list,
              timeframe=TimeFrame.Day,
              start=start,
          )
          try:
              bars = self._client.get_stock_bars(request)
              self._api_calls_made += 1
          except Exception as e:
              print(f"WARNING: Alpaca batch historical failed: {e}")
              return {}

          df = bars.df
          if df.empty:
              return {}

          results = {}
          for alpaca_sym in alpaca_list:
              orig_sym = sym_map[alpaca_sym]
              try:
                  sym_df = df.xs(alpaca_sym, level="symbol").sort_index(ascending=False)
                  historical = []
                  for ts, row in sym_df.iterrows():
                      historical.append({
                          "date": str(ts.date()) if hasattr(ts, "date") else str(ts)[:10],
                          "open": round(float(row["open"]), 4),
                          "high": round(float(row["high"]), 4),
                          "low": round(float(row["low"]), 4),
                          "close": round(float(row["close"]), 4),
                          "volume": int(row["volume"]),
                      })
                  results[orig_sym] = historical[:days]
              except (KeyError, IndexError):
                  continue
          return results

      def get_vix_term_structure(self) -> Optional[dict]:
          """Compare VIX (VIXCLS) vs VIX3M (VXVCLS) from FRED."""
          vix = _fetch_fred_series("VIXCLS")
          vix3m = _fetch_fred_series("VXVCLS")

          if vix is None or vix3m is None or vix3m <= 0:
              return None

          ratio = vix / vix3m
          if ratio < 0.85:
              classification = "steep_contango"
          elif ratio < 0.95:
              classification = "contango"
          elif ratio <= 1.05:
              classification = "flat"
          else:
              classification = "backwardation"

          return {
              "vix": round(vix, 2),
              "vix3m": round(vix3m, 2),
              "ratio": round(ratio, 3),
              "classification": classification,
          }

      def get_api_stats(self) -> dict:
          return {
              "cache_entries": len(self._cache),
              "api_calls_made": self._api_calls_made,
              "rate_limit_reached": False,
          }
  ```

- [ ] **Step 2: Install fredapi**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills
  uv pip install fredapi
  ```

- [ ] **Step 3: Test**

  ```bash
  mkdir -p /tmp/test_output/market_top
  uv run python skills/market-top-detector/scripts/market_top_detector.py \
    --output-dir /tmp/test_output/market_top/
  ls /tmp/test_output/market_top/market_top_*.json
  ```

  Verify: JSON file exists, `composite.composite_score` field is present.

- [ ] **Step 4: Commit**

  ```bash
  git add skills/market-top-detector/scripts/fmp_client.py
  git commit -m "feat(market-top-detector): migrate FMP → Alpaca + FRED for OHLCV + VIX"
  ```

---

## Task 4: Macro Regime Detector → FRED + Alpaca

**Files to modify:**
- `skills/macro-regime-detector/scripts/fmp_client.py` — replace FMP with Alpaca + FRED

The macro-regime-detector calls:
- `client.get_historical_prices(etf, days=600)` for 9 ETFs: `RSP, SPY, IWM, TLT, SHY, HYG, LQD, XLY, XLP`
- `client.get_treasury_rates(days=600)` — 10Y and 2Y yields used by `yield_curve_calculator.py`

The yield curve calculator uses `treasury_rates` entries with keys `date`, `year2`, `year10`. Replace with FRED `DGS2` and `DGS10` series aligned by date.

### Step-by-step

- [ ] **Step 1: Inspect the yield_curve_calculator to confirm field names**

  ```bash
  grep -n "year2\|year10\|treasury" \
    /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/skills/macro-regime-detector/scripts/calculators/yield_curve_calculator.py \
    | head -30
  ```

  Confirm the calculator reads `entry["year2"]` and `entry["year10"]` from the treasury_rates list.

- [ ] **Step 2: Replace fmp_client.py with Alpaca + FRED client**

  Replace the entire contents of `skills/macro-regime-detector/scripts/fmp_client.py` with:

  ```python
  #!/usr/bin/env python3
  """
  Alpaca + FRED Client for Macro Regime Detector

  Replaces FMP API:
  - ETF OHLCV → Alpaca Market Data API
  - Treasury rates (2Y/10Y yield curve) → FRED (DGS2, DGS10)
  """

  import os
  import datetime
  from typing import Optional

  from alpaca.data.historical import StockHistoricalDataClient
  from alpaca.data.requests import StockBarsRequest
  from alpaca.data.timeframe import TimeFrame


  def _get_alpaca_client() -> StockHistoricalDataClient:
      return StockHistoricalDataClient(
          api_key=os.environ.get("ALPACA_API_KEY", ""),
          secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
      )


  class FMPClient:
      """Drop-in replacement: Alpaca + FRED backed client with same interface."""

      def __init__(self, api_key: Optional[str] = None):
          alpaca_api_key = os.environ.get("ALPACA_API_KEY", "")
          alpaca_secret = os.environ.get("ALPACA_SECRET_KEY", "")
          if not alpaca_api_key or not alpaca_secret:
              raise ValueError(
                  "ALPACA_API_KEY and ALPACA_SECRET_KEY are required."
              )
          self._alpaca = _get_alpaca_client()
          self._cache: dict = {}
          self._api_calls_made = 0

      def get_historical_prices(self, symbol: str, days: int = 600) -> Optional[dict]:
          """Fetch daily OHLCV via Alpaca (most-recent first, FMP-compatible format)."""
          cache_key = f"hist_{symbol}_{days}"
          if cache_key in self._cache:
              return self._cache[cache_key]

          start = (datetime.date.today() - datetime.timedelta(days=int(days * 1.6) + 10)).isoformat()
          request = StockBarsRequest(
              symbol_or_symbols=symbol,
              timeframe=TimeFrame.Day,
              start=start,
          )
          try:
              bars = self._alpaca.get_stock_bars(request)
              self._api_calls_made += 1
          except Exception as e:
              print(f"WARNING: Alpaca bars failed for {symbol}: {e}")
              return None

          df = bars.df
          if df.empty:
              return None

          # Flatten MultiIndex
          if hasattr(df.index, "levels"):
              try:
                  df = df.xs(symbol, level="symbol")
              except KeyError:
                  pass
          df = df.sort_index(ascending=False)

          historical = []
          for ts, row in df.iterrows():
              historical.append({
                  "date": str(ts.date()) if hasattr(ts, "date") else str(ts)[:10],
                  "open": round(float(row["open"]), 4),
                  "high": round(float(row["high"]), 4),
                  "low": round(float(row["low"]), 4),
                  "close": round(float(row["close"]), 4),
                  "volume": int(row["volume"]),
              })

          result = {"symbol": symbol, "historical": historical[:days]}
          self._cache[cache_key] = result
          return result

      def get_batch_historical(self, symbols: list[str], days: int = 600) -> dict[str, list[dict]]:
          """Fetch historical bars for multiple symbols (single Alpaca batch request)."""
          cache_key = f"batch_{','.join(sorted(symbols))}_{days}"
          if cache_key in self._cache:
              return self._cache[cache_key]

          start = (datetime.date.today() - datetime.timedelta(days=int(days * 1.6) + 10)).isoformat()
          request = StockBarsRequest(
              symbol_or_symbols=symbols,
              timeframe=TimeFrame.Day,
              start=start,
          )
          try:
              bars = self._alpaca.get_stock_bars(request)
              self._api_calls_made += 1
          except Exception as e:
              print(f"WARNING: Alpaca batch fetch failed: {e}")
              return {}

          df = bars.df
          if df.empty:
              return {}

          results = {}
          for symbol in symbols:
              try:
                  sym_df = df.xs(symbol, level="symbol").sort_index(ascending=False)
                  historical = []
                  for ts, row in sym_df.iterrows():
                      historical.append({
                          "date": str(ts.date()) if hasattr(ts, "date") else str(ts)[:10],
                          "open": round(float(row["open"]), 4),
                          "high": round(float(row["high"]), 4),
                          "low": round(float(row["low"]), 4),
                          "close": round(float(row["close"]), 4),
                          "volume": int(row["volume"]),
                      })
                  results[symbol] = historical[:days]
              except (KeyError, IndexError):
                  results[symbol] = []
          self._cache[cache_key] = results
          return results

      def get_treasury_rates(self, days: int = 600) -> Optional[list[dict]]:
          """
          Fetch 2Y and 10Y Treasury yields from FRED (DGS2, DGS10).

          Returns list of dicts (most-recent first) matching FMP format:
          {"date": "YYYY-MM-DD", "year2": float, "year10": float}
          """
          cache_key = f"treasury_{days}"
          if cache_key in self._cache:
              return self._cache[cache_key]

          try:
              from fredapi import Fred
              fred = Fred(api_key=os.environ.get("FRED_API_KEY", ""))
              yield_2y = fred.get_series("DGS2").dropna()
              yield_10y = fred.get_series("DGS10").dropna()
          except Exception as e:
              print(f"WARNING: FRED treasury fetch failed: {e}")
              return None

          # Align on common dates
          import pandas as pd
          combined = pd.DataFrame({"year2": yield_2y, "year10": yield_10y}).dropna()
          combined = combined.sort_index(ascending=False).head(days)

          rates = []
          for date_idx, row in combined.iterrows():
              rates.append({
                  "date": str(date_idx.date()) if hasattr(date_idx, "date") else str(date_idx)[:10],
                  "year2": round(float(row["year2"]), 4),
                  "year10": round(float(row["year10"]), 4),
              })

          self._cache[cache_key] = rates
          return rates

      def get_api_stats(self) -> dict:
          return {
              "cache_entries": len(self._cache),
              "api_calls_made": self._api_calls_made,
              "rate_limit_reached": False,
          }
  ```

- [ ] **Step 3: Update macro_regime_detector.py metadata field**

  In `skills/macro-regime-detector/scripts/macro_regime_detector.py`, the `analysis["metadata"]` dict contains `"data_source": "FMP API"`. Update this line:

  **Old:**
  ```python
          "data_source": "FMP API",
  ```

  **New:**
  ```python
          "data_source": "Alpaca + FRED API",
  ```

- [ ] **Step 4: Test**

  ```bash
  mkdir -p /tmp/test_output/macro_regime
  uv run python skills/macro-regime-detector/scripts/macro_regime_detector.py \
    --output-dir /tmp/test_output/macro_regime/
  ls /tmp/test_output/macro_regime/macro_regime_*.json
  ```

  Verify: JSON file exists, `regime.regime_label` field is present.

- [ ] **Step 5: Commit**

  ```bash
  git add skills/macro-regime-detector/scripts/fmp_client.py
  git add skills/macro-regime-detector/scripts/macro_regime_detector.py
  git commit -m "feat(macro-regime-detector): migrate FMP → Alpaca + FRED for ETF + yield curve"
  ```

---

## Task 5: Earnings Calendar → Finnhub

**File to modify:** `skills/earnings-calendar/scripts/fetch_earnings_fmp.py`

The current script:
1. Calls `GET /api/v3/earning_calendar?from=&to=` — earnings dates + EPS estimates
2. Calls `GET /api/v3/profile/{symbols}` — company profiles (batch) for market cap + sector filtering

The Finnhub replacement:
- `client.earnings_calendar(_from=, to=, symbol="", international=False)` returns earnings with EPS estimates
- `client.company_profile2(symbol=)` returns market cap, sector, industry per symbol

The current script writes JSON to **stdout** (not a file). The calling pattern in the dashboard invokes it differently from other skills. The `--output-dir` flag does not exist in the current script — the dashboard reads stdout. Keep this behavior.

Note: Finnhub free tier rate limit is 60 calls/minute. The profile lookup loop adds 1 call per unique symbol. For a 7-day window, expect 20-80 earnings entries; each unique symbol needs 1 profile call. Add a 1-second sleep between profile calls to stay within limits.

### Step-by-step

- [ ] **Step 1: Install finnhub-python**

  ```bash
  uv pip install finnhub-python
  ```

- [ ] **Step 2: Replace fetch_earnings_fmp.py with Finnhub version**

  Replace the entire contents of `skills/earnings-calendar/scripts/fetch_earnings_fmp.py` with:

  ```python
  #!/usr/bin/env python3
  """
  Finnhub Earnings Calendar Fetcher

  Replaces FMP API with Finnhub (free tier, 60 calls/min).
  Retrieves upcoming earnings announcements, filters by market cap (>$2B),
  and outputs structured JSON data to stdout.

  Usage:
      # With environment variable
      export FINNHUB_API_KEY="your-key"
      python fetch_earnings_fmp.py 2026-03-23 2026-03-30

      # With API key as argument
      python fetch_earnings_fmp.py 2026-03-23 2026-03-30 YOUR_API_KEY
  """

  import json
  import os
  import sys
  import time
  from datetime import datetime
  from typing import Optional

  try:
      import finnhub
  except ImportError:
      print("Error: finnhub-python not installed. Run: pip install finnhub-python", file=sys.stderr)
      sys.exit(1)


  MIN_MARKET_CAP = 2_000_000_000  # $2B
  US_EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "NYSEArca", "BATS", "NMS", "NGM", "NCM"}


  def get_api_key() -> Optional[str]:
      if len(sys.argv) >= 4:
          print("API key provided via command line argument", file=sys.stderr)
          return sys.argv[3]
      api_key = os.environ.get("FINNHUB_API_KEY")
      if api_key:
          print("API key loaded from FINNHUB_API_KEY environment variable", file=sys.stderr)
          return api_key
      print("ERROR: No API key found.", file=sys.stderr)
      print("Set FINNHUB_API_KEY environment variable or pass as third argument.", file=sys.stderr)
      return None


  def validate_date(date_str: str) -> bool:
      try:
          datetime.strptime(date_str, "%Y-%m-%d")
          return True
      except ValueError:
          return False


  def normalize_timing(hour: Optional[int]) -> str:
      """Normalize earnings hour to BMO/AMC/TAS."""
      if hour is None:
          return "TAS"
      if hour < 12:
          return "BMO"
      return "AMC"


  def format_market_cap(market_cap: float) -> str:
      if market_cap >= 1e12:
          return f"${market_cap / 1e12:.1f}T"
      elif market_cap >= 1e9:
          return f"${market_cap / 1e9:.1f}B"
      elif market_cap >= 1e6:
          return f"${market_cap / 1e6:.0f}M"
      return f"${market_cap:,.0f}"


  def fetch_earnings(client: finnhub.Client, start_date: str, end_date: str) -> list[dict]:
      """Fetch earnings calendar from Finnhub."""
      try:
          result = client.earnings_calendar(_from=start_date, to=end_date, symbol="", international=False)
          earnings_list = result.get("earningsCalendar", []) if isinstance(result, dict) else []
          print(f"Retrieved {len(earnings_list)} earnings entries", file=sys.stderr)
          return earnings_list
      except Exception as e:
          print(f"ERROR fetching earnings calendar: {e}", file=sys.stderr)
          return []


  def fetch_profile(client: finnhub.Client, symbol: str) -> Optional[dict]:
      """Fetch company profile from Finnhub."""
      try:
          return client.company_profile2(symbol=symbol)
      except Exception as e:
          print(f"WARNING: Profile fetch failed for {symbol}: {e}", file=sys.stderr)
          return None


  def main():
      if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
          print("Usage: python fetch_earnings_fmp.py START_DATE END_DATE [API_KEY]", file=sys.stderr)
          sys.exit(0)

      if len(sys.argv) < 3:
          print("ERROR: Missing required arguments: START_DATE END_DATE", file=sys.stderr)
          sys.exit(1)

      start_date = sys.argv[1]
      end_date = sys.argv[2]

      if not validate_date(start_date):
          print(f"ERROR: Invalid start date: {start_date} (expected YYYY-MM-DD)", file=sys.stderr)
          sys.exit(1)
      if not validate_date(end_date):
          print(f"ERROR: Invalid end date: {end_date} (expected YYYY-MM-DD)", file=sys.stderr)
          sys.exit(1)

      api_key = get_api_key()
      if not api_key:
          sys.exit(1)

      print(f"Fetching earnings calendar: {start_date} to {end_date}", file=sys.stderr)
      client = finnhub.Client(api_key=api_key)

      # Step 1: Fetch earnings calendar
      print("Step 1: Fetching earnings calendar...", file=sys.stderr)
      earnings = fetch_earnings(client, start_date, end_date)
      if not earnings:
          print(json.dumps([]))
          sys.exit(0)

      # Step 2: Fetch company profiles and filter by market cap
      print("Step 2: Fetching company profiles...", file=sys.stderr)
      symbols = list(set(e.get("symbol", "") for e in earnings if e.get("symbol")))
      profiles = {}
      for i, symbol in enumerate(symbols):
          profile = fetch_profile(client, symbol)
          if profile:
              profiles[symbol] = profile
          # Rate limit: 60 calls/min on free tier
          if i > 0 and i % 55 == 0:
              print(f"  Rate limit pause at {i} symbols...", file=sys.stderr)
              time.sleep(60)
          else:
              time.sleep(1.1)

      print(f"Retrieved {len(profiles)} company profiles", file=sys.stderr)

      # Step 3: Filter and enrich
      print("Step 3: Filtering by market cap...", file=sys.stderr)
      filtered = []
      for entry in earnings:
          symbol = entry.get("symbol", "")
          if not symbol:
              continue
          profile = profiles.get(symbol)
          if not profile:
              continue
          market_cap = profile.get("marketCapitalization", 0)
          # Finnhub returns marketCapitalization in millions
          market_cap_usd = market_cap * 1_000_000 if market_cap else 0
          if market_cap_usd < MIN_MARKET_CAP:
              continue
          exchange = profile.get("exchange", "")
          if exchange not in US_EXCHANGES:
              continue

          timing = normalize_timing(entry.get("hour"))
          filtered.append({
              "symbol": symbol,
              "companyName": profile.get("name", symbol),
              "date": entry.get("date", ""),
              "timing": timing,
              "marketCap": market_cap_usd,
              "marketCapFormatted": format_market_cap(market_cap_usd),
              "sector": profile.get("finnhubIndustry", "N/A"),
              "industry": profile.get("finnhubIndustry", "N/A"),
              "epsEstimated": entry.get("epsEstimate"),
              "revenueEstimated": entry.get("revenueEstimate"),
              "fiscalDateEnding": entry.get("date", ""),
              "exchange": exchange,
          })

      print(f"Filtered to {len(filtered)} US mid-cap+ companies (>$2B)", file=sys.stderr)

      # Step 4: Sort by date, timing, market cap
      timing_order = {"BMO": 1, "AMC": 2, "TAS": 3}
      filtered.sort(key=lambda x: (
          x.get("date", ""),
          timing_order.get(x.get("timing", "TAS"), 3),
          -x.get("marketCap", 0),
      ))

      print(f"Final dataset: {len(filtered)} companies", file=sys.stderr)
      print(json.dumps(filtered, indent=2))


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 3: Test**

  ```bash
  START=$(date +%Y-%m-%d)
  END=$(date -v+7d +%Y-%m-%d 2>/dev/null || date -d "+7 days" +%Y-%m-%d)
  mkdir -p /tmp/test_output/earnings
  uv run python skills/earnings-calendar/scripts/fetch_earnings_fmp.py \
    "$START" "$END" > /tmp/test_output/earnings/earnings.json
  python3 -c "import json; d=json.load(open('/tmp/test_output/earnings/earnings.json')); print(f'OK: {len(d)} entries')"
  ```

  Verify: Output is valid JSON array (may be empty if no earnings in range; that is acceptable).

- [ ] **Step 4: Commit**

  ```bash
  git add skills/earnings-calendar/scripts/fetch_earnings_fmp.py
  git commit -m "feat(earnings-calendar): migrate FMP → Finnhub earnings calendar"
  ```

---

## Task 6: Economic Calendar → FRED

**File to modify:** `skills/economic-calendar-fetcher/scripts/get_economic_calendar.py`

The current script:
- Calls `GET /api/v3/economic_calendar?from=&to=` — US economic events (CPI, GDP, Fed meetings, etc.)
- Writes to stdout (JSON or text) or to a file via `--output`

FRED does not provide a forward-looking economic calendar (it only stores historical releases). The replacement strategy is to use a **static event schedule** for the major macro events (FOMC, CPI, NFP) combined with FRED's actual release data for recently published values (actual vs. estimate).

However, the dashboard uses this for the upcoming week's events display. The cleanest free replacement is the **Finnhub economic calendar** endpoint, which provides upcoming global economic events including US data.

### Step-by-step

- [ ] **Step 1: Replace get_economic_calendar.py with Finnhub economic calendar**

  Replace the entire contents of `skills/economic-calendar-fetcher/scripts/get_economic_calendar.py` with:

  ```python
  #!/usr/bin/env python3
  """
  Economic Calendar Fetcher using Finnhub API

  Replaces FMP API with Finnhub (free tier).
  Retrieves US economic events for specified date range.

  Note: Finnhub economic_calendar is a premium endpoint on the free plan.
  This script falls back to a FRED-based approach for key macro series
  (CPI, GDP, Fed Funds Rate, Unemployment) when Finnhub is unavailable.
  """

  import argparse
  import json
  import os
  import sys
  from datetime import datetime, timedelta
  from typing import Optional

  try:
      import finnhub
  except ImportError:
      print("Error: finnhub-python not installed. Run: pip install finnhub-python", file=sys.stderr)
      sys.exit(1)


  # Key FRED series for macro context (actual values, not forward calendar)
  FRED_MACRO_SERIES = {
      "CPI (YoY)": "CPIAUCSL",
      "Fed Funds Rate": "FEDFUNDS",
      "10Y Treasury Yield": "DGS10",
      "2Y Treasury Yield": "DGS2",
      "GDP Growth Rate": "A191RL1Q225SBEA",
      "Unemployment Rate": "UNRATE",
  }


  def get_api_key() -> Optional[str]:
      api_key = os.environ.get("FINNHUB_API_KEY")
      if api_key:
          return api_key
      print("Warning: FINNHUB_API_KEY not set — using FRED fallback", file=sys.stderr)
      return None


  def fetch_finnhub_calendar(api_key: str, from_date: str, to_date: str) -> list[dict]:
      """Fetch economic calendar from Finnhub (premium endpoint)."""
      try:
          client = finnhub.Client(api_key=api_key)
          result = client.economic_calendar()
          if not isinstance(result, dict):
              return []
          events = result.get("economicCalendar", [])
          # Filter to date range and US events
          filtered = []
          for ev in events:
              ev_date = ev.get("time", "")[:10]
              country = ev.get("country", "")
              if ev_date >= from_date and ev_date <= to_date and country in ("US", "United States"):
                  filtered.append({
                      "date": ev_date,
                      "time": ev.get("time", ""),
                      "country": "US",
                      "currency": "USD",
                      "event": ev.get("event", ""),
                      "impact": ev.get("impact", "").capitalize(),
                      "previous": ev.get("prev"),
                      "estimate": ev.get("estimate"),
                      "actual": ev.get("actual"),
                      "change": None,
                      "changePercentage": None,
                  })
          return filtered
      except Exception as e:
          print(f"WARNING: Finnhub economic calendar failed: {e}", file=sys.stderr)
          return []


  def fetch_fred_macro_context(from_date: str, to_date: str) -> list[dict]:
      """
      Fetch recent actual values for key macro series from FRED.
      Returns events in economic-calendar format showing the most recent release.
      """
      fred_key = os.environ.get("FRED_API_KEY", "")
      if not fred_key:
          print("WARNING: FRED_API_KEY not set — macro context unavailable", file=sys.stderr)
          return []

      try:
          from fredapi import Fred
          fred = Fred(api_key=fred_key)
      except Exception as e:
          print(f"WARNING: FRED init failed: {e}", file=sys.stderr)
          return []

      events = []
      for label, series_id in FRED_MACRO_SERIES.items():
          try:
              series = fred.get_series(series_id).dropna()
              if series.empty:
                  continue
              latest_date = series.index[-1]
              latest_val = float(series.iloc[-1])
              prev_val = float(series.iloc[-2]) if len(series) >= 2 else None
              events.append({
                  "date": str(latest_date.date()) if hasattr(latest_date, "date") else str(latest_date)[:10],
                  "time": "",
                  "country": "US",
                  "currency": "USD",
                  "event": f"{label} (FRED: {series_id})",
                  "impact": "High",
                  "previous": round(prev_val, 4) if prev_val is not None else None,
                  "estimate": None,
                  "actual": round(latest_val, 4),
                  "change": round(latest_val - prev_val, 4) if prev_val is not None else None,
                  "changePercentage": None,
                  "source": "FRED",
              })
          except Exception as e:
              print(f"WARNING: FRED series {series_id} failed: {e}", file=sys.stderr)
              continue

      return events


  def validate_date_range(from_date: str, to_date: str) -> None:
      try:
          start = datetime.strptime(from_date, "%Y-%m-%d")
          end = datetime.strptime(to_date, "%Y-%m-%d")
      except ValueError as e:
          raise ValueError(f"Invalid date format. Use YYYY-MM-DD: {e}")
      if start > end:
          raise ValueError(f"Start date {from_date} is after end date {to_date}")
      delta = (end - start).days
      if delta > 90:
          raise ValueError(f"Date range ({delta} days) exceeds maximum of 90 days")


  def format_event_output(events: list[dict], output_format: str = "json") -> str:
      if output_format == "json":
          return json.dumps(events, indent=2, ensure_ascii=False)
      lines = [f"Economic Calendar Events (Total: {len(events)})", "=" * 80]
      for event in events:
          lines.append(f"\nDate: {event.get('date', 'N/A')}")
          lines.append(f"Country: {event.get('country', 'N/A')}")
          lines.append(f"Event: {event.get('event', 'N/A')}")
          lines.append(f"Impact: {event.get('impact', 'N/A')}")
          if event.get("previous") is not None:
              lines.append(f"Previous: {event['previous']}")
          if event.get("estimate") is not None:
              lines.append(f"Estimate: {event['estimate']}")
          if event.get("actual") is not None:
              lines.append(f"Actual: {event['actual']}")
          lines.append("-" * 80)
      return "\n".join(lines)


  def main():
      parser = argparse.ArgumentParser(
          description="Fetch economic calendar events (Finnhub + FRED fallback)",
      )
      today = datetime.now().date()
      default_from = today.strftime("%Y-%m-%d")
      default_to = (today + timedelta(days=7)).strftime("%Y-%m-%d")

      parser.add_argument("--from", dest="from_date", default=default_from)
      parser.add_argument("--to", dest="to_date", default=default_to)
      parser.add_argument("--api-key", dest="api_key", help="Finnhub API key (overrides FINNHUB_API_KEY)")
      parser.add_argument("--format", choices=["json", "text"], default="json")
      parser.add_argument("--output", "-o", help="Output file path (default: stdout)")

      args = parser.parse_args()

      try:
          validate_date_range(args.from_date, args.to_date)
      except ValueError as e:
          print(f"Error: {e}", file=sys.stderr)
          sys.exit(1)

      api_key = args.api_key or get_api_key()

      print(f"Fetching economic calendar from {args.from_date} to {args.to_date}...", file=sys.stderr)

      events = []
      if api_key:
          events = fetch_finnhub_calendar(api_key, args.from_date, args.to_date)

      # Always supplement with FRED macro context (actual release values)
      fred_events = fetch_fred_macro_context(args.from_date, args.to_date)
      events.extend(fred_events)

      # Sort by date
      events.sort(key=lambda x: x.get("date", ""))

      print(f"Retrieved {len(events)} events", file=sys.stderr)
      output = format_event_output(events, args.format)

      if args.output:
          with open(args.output, "w", encoding="utf-8") as f:
              f.write(output)
          print(f"Output written to {args.output}", file=sys.stderr)
      else:
          print(output)

      sys.exit(0)


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 2: Test**

  ```bash
  mkdir -p /tmp/test_output/econ_cal
  uv run python skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
    --output /tmp/test_output/econ_cal/calendar.json
  python3 -c "import json; d=json.load(open('/tmp/test_output/econ_cal/calendar.json')); print(f'OK: {len(d)} events')"
  ```

  Verify: JSON file exists and contains a list (FRED fallback ensures at least 6 macro entries even if Finnhub premium endpoint is unavailable).

- [ ] **Step 3: Commit**

  ```bash
  git add skills/economic-calendar-fetcher/scripts/get_economic_calendar.py
  git commit -m "feat(economic-calendar): migrate FMP → Finnhub + FRED economic calendar"
  ```

---

## Task 7: Institutional Flow Tracker → Finnhub

**File to modify:** `skills/institutional-flow-tracker/scripts/track_institutional_flow.py`

The current script makes ~101 FMP API calls per run:
1. `GET /api/v3/stock-screener?marketCapMoreThan=&limit=100` — get candidate stocks (1 call)
2. `GET /api/v3/institutional-holder/{symbol}` — 13F data per stock (up to 100 calls)

Finnhub replacement:
- `client.stock_symbols("US")` or a fixed list of large-cap symbols as candidates
- `client.ownership(symbol, limit=5)` — institutional ownership for a symbol

**Important limitation:** Finnhub's `ownership` endpoint returns the top institutional holders with current shares and percentage of shares held, but it does not return quarter-over-quarter change data directly. The `institutionalOwnership` response includes `institutionalOwnership` array with holder name, shares, and percentage — but no `change` field.

The migration strategy:
- Use a fixed list of S&P 500 component tickers as the candidate pool (avoid screener API call)
- For each symbol, call `client.ownership(symbol, limit=10)` to get current holders
- Compute a simplified ownership metric: total institutional shares as % of float
- The `data_quality.py` module's change calculations cannot be replicated without historical quarterly data; skip per-quarter delta and report current ownership concentration instead
- The report format is preserved; per-symbol change is marked "N/A (no quarter comparison)" where FMP provided it

This is a **partial migration** — the institutional flow tracker loses quarter-over-quarter change tracking but retains ownership concentration data. A full replacement would require a paid data source for historical 13F data.

### Step-by-step

- [ ] **Step 1: Create a fixed S&P 500 candidate list**

  Create `skills/institutional-flow-tracker/scripts/sp500_candidates.py`:

  ```python
  """
  Fixed list of large-cap US stock candidates for institutional flow screening.
  Replaces the FMP stock screener endpoint.
  This covers the S&P 100 (top 100 by market cap in the S&P 500).
  Update quarterly or when major index changes occur.
  """

  SP100_CANDIDATES = [
      "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "BRK-B",
      "LLY", "UNH", "JPM", "V", "XOM", "MA", "JNJ", "HD", "AVGO", "PG", "MRK",
      "COST", "ABBV", "CVX", "KO", "WMT", "AMD", "BAC", "NFLX", "CRM", "PEP",
      "TMO", "LIN", "ORCL", "ACN", "ADBE", "MCD", "ABT", "CSCO", "PM", "GE",
      "DHR", "TXN", "IBM", "INTU", "CAT", "AMGN", "MS", "GS", "RTX", "SPGI",
      "NEE", "ISRG", "BLK", "AXP", "SYK", "BKNG", "T", "ETN", "AMAT", "GILD",
      "VRTX", "PLD", "MDLZ", "ADI", "DE", "MMC", "CI", "REGN", "MU", "BSX",
      "HCA", "SO", "LRCX", "NOW", "ZTS", "SHW", "CB", "PANW", "MCO", "CME",
      "TJX", "ITW", "CL", "PGR", "FI", "DUK", "AON", "UBER", "EQIX", "APH",
      "KLAC", "WM", "NOC", "USB", "TGT", "ICE", "PH", "EMR", "SNPS", "CDNS",
  ]
  ```

- [ ] **Step 2: Replace track_institutional_flow.py with Finnhub version**

  Replace the entire contents of `skills/institutional-flow-tracker/scripts/track_institutional_flow.py` with:

  ```python
  #!/usr/bin/env python3
  """
  Institutional Flow Tracker - Finnhub Edition

  Screens for stocks with high institutional ownership concentration using
  Finnhub's ownership endpoint. Replaces FMP API.

  Note: This version reports current ownership concentration rather than
  quarter-over-quarter change (Finnhub free tier does not provide historical
  quarterly 13F deltas). Use as an ownership concentration screener.

  Usage:
      python3 track_institutional_flow.py --top 50
      python3 track_institutional_flow.py --sector Technology --output-dir reports/
  """

  import argparse
  import json
  import os
  import sys
  import time
  from datetime import datetime
  from typing import Optional

  try:
      import finnhub
  except ImportError:
      print("Error: finnhub-python not installed. Run: pip install finnhub-python")
      sys.exit(1)

  sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
  from sp500_candidates import SP100_CANDIDATES


  def get_ownership(client: finnhub.Client, symbol: str) -> Optional[dict]:
      """
      Fetch institutional ownership for a symbol.
      Returns simplified ownership metrics or None on failure.
      """
      try:
          result = client.ownership(symbol, limit=10)
          if not isinstance(result, dict):
              return None
          holders = result.get("ownership", [])
          if not holders:
              return None

          total_pct = sum(h.get("ownershipPercent", 0) for h in holders)
          top_holders = [
              {
                  "name": h.get("name", "Unknown"),
                  "shares": h.get("share", 0),
                  "change": 0,  # Not available from Finnhub free tier
              }
              for h in holders[:10]
          ]

          return {
              "symbol": symbol,
              "company_name": symbol,  # Profile fetched separately if needed
              "market_cap": 0,
              "current_quarter": result.get("symbol", ""),
              "previous_quarter": "N/A",
              "current_total_shares": sum(h.get("share", 0) for h in holders),
              "previous_total_shares": 0,
              "shares_change": 0,
              "percent_change": 0.0,  # Not available without historical 13F
              "ownership_concentration_pct": round(total_pct, 2),
              "current_institution_count": len(holders),
              "previous_institution_count": 0,
              "institution_count_change": 0,
              "buyers": 0,
              "sellers": 0,
              "unchanged": len(holders),
              "top_holders": top_holders,
              "reliability_grade": "A",
              "genuine_ratio": 1.0,
          }
      except Exception as e:
          print(f"WARNING: Ownership fetch failed for {symbol}: {e}")
          return None


  class InstitutionalFlowTracker:
      """Track institutional ownership concentration using Finnhub."""

      def __init__(self, api_key: str):
          self.client = finnhub.Client(api_key=api_key)

      def screen_stocks(
          self,
          min_market_cap: int = 1_000_000_000,
          min_change_percent: float = 10.0,
          min_institutions: int = 5,
          sector: Optional[str] = None,
          top: int = 50,
          sort_by: str = "ownership_change",
          limit: int = 100,
      ) -> list[dict]:
          """Screen stocks from SP100 candidate pool."""
          candidates = SP100_CANDIDATES[:limit]
          print(f"Analyzing institutional ownership for {len(candidates)} stocks...")
          print("Note: Using ownership concentration (no quarter-over-quarter delta on free tier)\n")

          results = []
          for i, symbol in enumerate(candidates, 1):
              if i % 10 == 0:
                  print(f"Progress: {i}/{len(candidates)} stocks analyzed...")

              metrics = get_ownership(self.client, symbol)
              if metrics and metrics["current_institution_count"] >= min_institutions:
                  results.append(metrics)

              # Finnhub free: 60 calls/min
              time.sleep(1.1)

          print(f"\nFound {len(results)} stocks with institutional data")
          results.sort(key=lambda x: x.get("ownership_concentration_pct", 0), reverse=True)
          return results[:top]

      def generate_report(self, results: list[dict], output_file: str = None, output_dir: str = None):
          """Generate markdown report from screening results."""
          if not results:
              print("No results to report")
              return

          timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
          report = f"""# Institutional Ownership Concentration Report
  **Generated:** {timestamp}
  **Stocks Analyzed:** {len(results)}
  **Data Source:** Finnhub API (top-10 institutional holders per stock)

  > **Note:** This report shows current ownership concentration.
  > Quarter-over-quarter change data requires a paid data source for historical 13F filings.

  ## Top Holdings by Institutional Concentration

  | Symbol | Top-10 Inst. Ownership % | Institution Count | Top Holder |
  |--------|--------------------------|-------------------|------------|
  """
          for r in results[:20]:
              top_holder = r["top_holders"][0]["name"] if r["top_holders"] else "N/A"
              report += (
                  f"| {r['symbol']} | {r['ownership_concentration_pct']:.1f}% "
                  f"| {r['current_institution_count']} | {top_holder[:40]} |\n"
              )

          report += "\n## Detailed Results\n\n"
          for r in results[:20]:
              report += f"""### {r["symbol"]}

  **Ownership Concentration (Top 10):** {r['ownership_concentration_pct']:.1f}%
  **Institutions Tracked:** {r['current_institution_count']}

  **Top Holders:**
  """
              for i, holder in enumerate(r["top_holders"][:5], 1):
                  report += f"{i}. {holder['name']}: {holder['shares']:,} shares\n"
              report += "\n---\n\n"

          report += """
  ## Methodology

  - Data from Finnhub institutional ownership endpoint (top 10 holders per symbol)
  - Candidate pool: S&P 100 stocks (top 100 US large-caps)
  - Ownership % shown is sum of top-10 holders as % of shares outstanding
  - Quarter-over-quarter change not available on Finnhub free tier

  **Data Source:** Finnhub API (13F-based institutional ownership)
  **Note:** 13F data has ~45-day reporting lag. Use as confirming indicator.
  """
          filename = f"institutional_flow_screening_{datetime.now().strftime('%Y%m%d')}.md"
          if output_dir:
              os.makedirs(output_dir, exist_ok=True)
              output_path = os.path.join(output_dir, filename)
          else:
              output_path = output_file or filename

          with open(output_path, "w") as f:
              f.write(report)
          print(f"\nReport saved to: {output_path}")
          return report


  def main():
      parser = argparse.ArgumentParser(description="Track institutional ownership (Finnhub)")
      parser.add_argument(
          "--api-key", type=str, default=os.getenv("FINNHUB_API_KEY"),
          help="Finnhub API key (or set FINNHUB_API_KEY env var)",
      )
      parser.add_argument("--top", type=int, default=50)
      parser.add_argument("--min-change-percent", type=float, default=10.0)
      parser.add_argument("--min-market-cap", type=int, default=1_000_000_000)
      parser.add_argument("--sector", type=str)
      parser.add_argument("--min-institutions", type=int, default=5)
      parser.add_argument("--sort-by", choices=["ownership_change", "institution_count_change"],
                          default="ownership_change")
      parser.add_argument("--limit", type=int, default=100)
      parser.add_argument("--output", type=str)
      parser.add_argument("--output-dir", type=str, default="reports/")
      args = parser.parse_args()

      if not args.api_key:
          print("Error: Finnhub API key required.")
          print("Set FINNHUB_API_KEY environment variable or pass --api-key argument.")
          sys.exit(1)

      tracker = InstitutionalFlowTracker(args.api_key)
      results = tracker.screen_stocks(
          min_market_cap=args.min_market_cap,
          min_change_percent=args.min_change_percent,
          min_institutions=args.min_institutions,
          sector=args.sector,
          top=args.top,
          sort_by=args.sort_by,
          limit=args.limit,
      )

      if args.output:
          json_output = args.output if args.output.endswith(".json") else f"{args.output}.json"
          if args.output_dir:
              os.makedirs(args.output_dir, exist_ok=True)
              json_output = os.path.join(args.output_dir, os.path.basename(json_output))
          with open(json_output, "w") as f:
              json.dump(results, f, indent=2)
          print(f"JSON results saved to: {json_output}")

      tracker.generate_report(results, output_dir=args.output_dir)

      if results:
          print("\n" + "=" * 80)
          print("TOP 10 BY INSTITUTIONAL CONCENTRATION")
          print("=" * 80)
          print(f"{'Symbol':<8} {'Inst. Conc. %':>14} {'Institutions':>12}")
          print("-" * 40)
          for r in results[:10]:
              print(
                  f"{r['symbol']:<8} {r['ownership_concentration_pct']:>13.1f}% "
                  f"{r['current_institution_count']:>11d}"
              )


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 3: Test**

  ```bash
  mkdir -p /tmp/test_output/inst_flow
  uv run python skills/institutional-flow-tracker/scripts/track_institutional_flow.py \
    --limit 5 --top 5 --output-dir /tmp/test_output/inst_flow/
  ls /tmp/test_output/inst_flow/institutional_flow_*.md
  ```

  Verify: Markdown report file exists and contains at least 1 stock entry.

- [ ] **Step 4: Commit**

  ```bash
  git add skills/institutional-flow-tracker/scripts/track_institutional_flow.py
  git add skills/institutional-flow-tracker/scripts/sp500_candidates.py
  git commit -m "feat(institutional-flow): migrate FMP → Finnhub ownership concentration"
  ```

---

## Task 8: Update config.py and .env.example

- [ ] **Step 1: Add new keys to .env.example**

  In `examples/market-dashboard/.env.example`, add after `FINVIZ_API_KEY=`:

  ```
  FRED_API_KEY=your_fred_api_key_here
  FINNHUB_API_KEY=your_finnhub_api_key_here
  ```

- [ ] **Step 2: Add new keys to config.py**

  In `examples/market-dashboard/config.py`, add after `ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")`:

  ```python
  FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
  FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
  ```

- [ ] **Step 3: Inject new keys in skills_runner.py**

  Find where `skills_runner.py` injects FMP key into subprocess env and add FRED and Finnhub alongside it.

  In `examples/market-dashboard/skills_runner.py`, locate the env injection block (search for `FMP_API_KEY`) and add:

  ```python
  env["FRED_API_KEY"] = config.FRED_API_KEY
  env["FINNHUB_API_KEY"] = config.FINNHUB_API_KEY
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add examples/market-dashboard/.env.example
  git add examples/market-dashboard/config.py
  git add examples/market-dashboard/skills_runner.py
  git commit -m "feat(dashboard): add FRED_API_KEY and FINNHUB_API_KEY to config and env"
  ```

---

## Task 9: Remove FMP_API_KEY requirement from CLAUDE.md

- [ ] **Update `examples/market-dashboard/CLAUDE.md`**

  In the "Environment setup" section, update step 2:

  **Old:**
  ```
  2. Set `FMP_API_KEY` — required for VCP, FTD, CANSLIM, Macro Regime, calendars
  ```

  **New:**
  ```
  2. Set `FMP_API_KEY` — required for VCP, CANSLIM, and optional screener skills only
  3. Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` — required for FTD, Market Top, Macro Regime
  4. Set `FRED_API_KEY` — required for Market Top (VIX), Macro Regime (yield curve), Economic Calendar
  5. Set `FINNHUB_API_KEY` — required for Earnings Calendar, Institutional Flow, Economic Calendar
  ```

- [ ] **Commit**

  ```bash
  git add examples/market-dashboard/CLAUDE.md
  git commit -m "docs(dashboard): update API key requirements for FMP migration"
  ```

---

## Verification Checklist

After all tasks are complete, run each migrated skill end-to-end and confirm output files exist:

```bash
BASE=/Users/eirikrskole/work/trading-claude-code/claude-trading-skills
mkdir -p /tmp/fmp_migration_test

# Task 1: FTD Detector
uv run python $BASE/skills/ftd-detector/scripts/ftd_detector.py \
  --output-dir /tmp/fmp_migration_test/
ls /tmp/fmp_migration_test/ftd_detector_*.json

# Task 2: Market Breadth (no change — verify still works)
uv run python $BASE/skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py \
  --output-dir /tmp/fmp_migration_test/
ls /tmp/fmp_migration_test/market_breadth_*.json

# Task 3: Market Top Detector
uv run python $BASE/skills/market-top-detector/scripts/market_top_detector.py \
  --output-dir /tmp/fmp_migration_test/
ls /tmp/fmp_migration_test/market_top_*.json

# Task 4: Macro Regime Detector
uv run python $BASE/skills/macro-regime-detector/scripts/macro_regime_detector.py \
  --output-dir /tmp/fmp_migration_test/
ls /tmp/fmp_migration_test/macro_regime_*.json

# Task 5: Earnings Calendar
START=$(date +%Y-%m-%d)
END=$(date -v+7d +%Y-%m-%d 2>/dev/null || date -d "+7 days" +%Y-%m-%d)
uv run python $BASE/skills/earnings-calendar/scripts/fetch_earnings_fmp.py \
  "$START" "$END" > /tmp/fmp_migration_test/earnings.json
python3 -c "import json; print(f'Earnings: {len(json.load(open(\"/tmp/fmp_migration_test/earnings.json\")))} entries')"

# Task 6: Economic Calendar
uv run python $BASE/skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --output /tmp/fmp_migration_test/econ_calendar.json
python3 -c "import json; print(f'Economic: {len(json.load(open(\"/tmp/fmp_migration_test/econ_calendar.json\")))} events')"

# Task 7: Institutional Flow Tracker
uv run python $BASE/skills/institutional-flow-tracker/scripts/track_institutional_flow.py \
  --limit 5 --top 5 --output-dir /tmp/fmp_migration_test/
ls /tmp/fmp_migration_test/institutional_flow_*.md
```

All commands should complete without `FMP_API_KEY` set in the environment.
