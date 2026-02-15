# FMP API Endpoints Used by VCP Screener

## Endpoints

### 1. S&P 500 Constituents
- **URL:** `GET /api/v3/sp500_constituent`
- **Calls:** 1 (cached)
- **Returns:** `[{symbol, name, sector, subSector}, ...]`
- **Used in:** Phase 1 - Universe definition

### 2. Batch Quote
- **URL:** `GET /api/v3/quote/{symbols}` (comma-separated, max 5)
- **Calls:** ~101 (503 stocks / 5 per batch)
- **Returns:** `[{symbol, price, yearHigh, yearLow, avgVolume, marketCap, ...}]`
- **Used in:** Phase 1 - Pre-filter

### 3. Historical Prices
- **URL:** `GET /api/v3/historical-price-full/{symbol}?timeseries=260`
- **Calls:** 1 (SPY) + up to 100 (candidates)
- **Returns:** `{symbol, historical: [{date, open, high, low, close, adjClose, volume}, ...]}`
- **Used in:** Phase 2 - Trend Template, Phase 3 - VCP detection

## API Budget Summary

| Phase | Operation | API Calls |
|-------|-----------|-----------|
| 1 | S&P 500 constituents | 1 |
| 1 | Batch quotes (503 / 5) | ~101 |
| 2 | SPY 260-day history | 1 |
| 2 | Candidate histories (max 100) | 100 |
| **Total (default)** | | **~203** |
| **Total (--full-sp500)** | | **~350** |

## Rate Limits

- **Free tier:** 250 API calls/day - Default screening fits within this limit
- **Starter tier ($29.99/mo):** 750 calls/day
- **Rate limiting:** 0.3s delay between requests, automatic retry on 429
- **Caching:** In-memory session cache prevents duplicate requests

## Notes

- All historical data uses `timeseries=260` parameter (260 trading days = ~1 year)
- Phase 3 (VCP detection, scoring, reporting) requires NO additional API calls
- The `--full-sp500` flag fetches histories for all pre-filter passers (~250 stocks)
