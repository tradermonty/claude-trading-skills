# Multi-Market Trading — Design Spec

**Date:** 2026-03-23

## Goal

Extend the trading bot to support international equity markets (Oslo Børs, LSE, and any future exchange) alongside the existing US market, using Interactive Brokers (IBKR) as the international broker while keeping Alpaca for US trading. Also replace FMP with a free provider stack that eliminates daily call limits. Also replace the cramped settings modal with a dedicated `/settings` page with organised sections and a home button on all sub-pages.

## Context

The current system trades US equities only via Alpaca. Alpaca does not support non-US exchanges. IBKR supports 150+ exchanges across 33 countries and provides both brokerage and market data via a unified API. Adding IBKR as a second broker client enables trading on any global exchange with minimal per-market work.

The PDT (Pattern Day Trader) rule is a US SEC regulation and does not apply to non-US markets or IBKR accounts. All non-US monitor instances skip the PDT guard rail entirely.

## Data Provider Strategy

All data providers are free. FMP is replaced entirely.

| Data Type | Provider | Cost | Notes |
|-----------|----------|------|-------|
| US OHLCV daily bars + volume | **Alpaca Market Data** | $0 | Already available, 200 req/min, no daily cap |
| Market breadth (% above 50/200 MA) | **Computed from Alpaca data** | $0 | Derived in Python from existing OHLCV fetch |
| Earnings calendar | **Finnhub free tier** | $0 | 60 req/min, no daily cap, confirmed free |
| 13F institutional flow | **Finnhub free tier** | $0 | Same free tier, runs weekly |
| Macro data (GDP, CPI, Fed rates, VIX, yield curve) | **FRED API** | $0 | US Federal Reserve, 120 req/min, 840K+ series |
| Oslo Børs OHLCV | **IBKR market data** | $0 | Included with broker account, paced requests |
| LSE OHLCV | **IBKR market data** | $0 | Same account, same pacing strategy |
| Other global exchanges | **IBKR market data** | $0 | Covered by existing broker relationship |

**Total: $0/month**

### IBKR pacing strategy for international data

IBKR enforces a pacing limit of ~60 historical data requests per 10 minutes. International screeners run **once daily** (pre-market for each exchange) rather than every 30 minutes. Requests are spaced with a ~6-second delay between tickers. A universe of 100 stocks takes ~10 minutes to scan — right at the pacing limit but within it.

US trading continues on the 30-minute cycle via Alpaca, which has no pacing constraints.

### Skills migration from FMP

| Skill | Current provider | New provider |
|-------|-----------------|--------------|
| vcp-screener | FMP | Alpaca |
| canslim-screener | FMP | Alpaca |
| ftd-detector | FMP | Alpaca |
| uptrend-analyzer | FMP | Alpaca |
| market-breadth-analyzer | FMP | Computed from Alpaca |
| market-top-detector | FMP | FRED API (VIX) + Alpaca |
| macro-regime-detector | FMP | FRED API |
| earnings-calendar | FMP | Finnhub |
| institutional-flow-tracker | FMP | Finnhub |
| economic-calendar-fetcher | FMP | FRED API |

## Architecture Overview

Five subsystems are added or changed:

1. **Broker abstraction layer** — a shared interface both `AlpacaClient` and `IBKRClient` implement
2. **Universe builder** — weekly job that fetches and filters the tradeable stock universe per non-US market from IBKR data
3. **Multi-market orchestrator** — starts one `PivotWatchlistMonitor` instance per enabled market, wired to the correct broker and settings
4. **Settings page** — replaces the modal with a dedicated `/settings` route and full-page layout
5. **Data provider migration** — replaces FMP with Alpaca (OHLCV), Finnhub (earnings + 13F), and FRED API (macro), eliminating the 250 calls/day limit at zero cost

---

## Broker Abstraction Layer

### `broker_client.py` (new)

Defines `BrokerClient` — a Protocol with the interface both clients must implement:

```python
class BrokerClient(Protocol):
    def get_account(self) -> dict: ...
    def get_positions(self) -> list[dict]: ...
    def get_last_price(self, symbol: str) -> float: ...
    def get_current_volume(self, symbol: str) -> int: ...
    def place_bracket_order(self, symbol, qty, limit_price, stop_price, take_profit_price) -> dict: ...
    def place_market_sell(self, symbol: str, qty: int) -> dict: ...
    def replace_order_stop(self, order_id: str, new_stop: float) -> dict: ...
    @property
    def is_configured(self) -> bool: ...
```

`place_bracket_order` must return a dict containing at minimum:
- `id` — the primary order ID
- `stop_order_id` — the ID of the stop-loss leg (used by trailing stop logic)

### `alpaca_client.py` (modify)

Confirm it satisfies `BrokerClient`. Ensure `place_bracket_order` returns `stop_order_id` from the Alpaca bracket order response. No other logic changes.

### `ibkr_client.py` (new)

Implements `BrokerClient` using IBKR's `ib_insync` Python library. Connects to IB Gateway running on the Pi (`localhost:4002` for paper, `localhost:4001` for live).

Key notes:
- `is_configured` returns True only when IB Gateway connection is live
- Symbol format: `symbol.exchange` suffix (e.g. `EQNR.OSE`, `SHEL.LSE`) — handled internally, callers pass plain symbol
- IBKR bracket orders are three linked orders (parent + take-profit child + stop child). `place_bracket_order` returns `{"id": parent_id, "stop_order_id": stop_child_id}`
- `replace_order_stop` modifies the stop child order by `stop_order_id`
- Market data (last price, volume) uses `ib_insync` snapshot requests, not streaming
- `ib_insync` runs its own internal event loop; all calls are synchronous from the caller's perspective via `ib.run_until_complete()`

---

## `pivot_monitor.py` Migration

This is the largest change. Every `self._alpaca` reference must be replaced with `self._broker`. The full list of call sites and their replacements:

| Location | Old call | New call |
|----------|----------|----------|
| `__init__` | `alpaca_client: AlpacaClient` param | `broker_client: BrokerClient` param |
| `__init__` | `self._alpaca = alpaca_client` | `self._broker = broker_client` |
| `_guard_rails_allow` | `self._alpaca.get_positions()` | `self._broker.get_positions()` |
| `_guard_rails_allow` | `self._alpaca.get_account()` | `self._broker.get_account()` |
| `_guard_rails_allow` | `self._alpaca.get_current_volume()` | `self._broker.get_current_volume()` |
| `_fire_order` | `self._alpaca.get_last_price()` | `self._broker.get_last_price()` |
| `_fire_order` | `self._alpaca.get_account()` | `self._broker.get_account()` |
| `_fire_order` | `self._alpaca.place_bracket_order()` | `self._broker.place_bracket_order()` |
| `_apply_trailing_stop` | `self._alpaca.get_last_price()` | `self._broker.get_last_price()` |
| `_apply_trailing_stop` | `self._alpaca.replace_order_stop()` | `self._broker.replace_order_stop()` |
| `_apply_partial_exit` | `self._alpaca.get_last_price()` | `self._broker.get_last_price()` |
| `_apply_partial_exit` | `self._alpaca.place_market_sell()` | `self._broker.place_market_sell()` |
| `_apply_time_stop` | `self._alpaca.get_last_price()` | `self._broker.get_last_price()` |
| `_apply_time_stop` | `self._alpaca.place_market_sell()` | `self._broker.place_market_sell()` |
| `start()` | `self._alpaca.is_configured` | `self._broker.is_configured` |
| `start()` | `StockDataStream(api_key=self._alpaca.api_key, ...)` | See data streaming below |

### Market hours — two hardcoded locations to fix

**Location 1:** Module-level `_market_is_open_now()` free function (lines 649–654). Convert to instance method `_is_market_open_now()` that reads hours and timezone from `self._market_config`. Remove the self-import in `_check_exit_management`.

**Location 2:** Time-of-day soft lock inside `_guard_rails_allow` (lines 262–269). Replace hardcoded `hour=9, minute=30`, `hour=16, minute=0`, and `ZoneInfo("America/New_York")` with values parsed from `self._market_config["open"]`, `self._market_config["close"]`, and `self._market_config["tz"]`.

### Data streaming for IBKR

The `start()` method constructs an Alpaca `StockDataStream` using `self._alpaca.api_key` and `self._alpaca.secret_key`. IBKR does not use a WebSocket stream — it uses `ib_insync` bar subscriptions.

Solution: `start()` delegates to a `_run_stream(symbols)` method on the broker client itself:

```python
# In BrokerClient Protocol:
async def subscribe_bars(self, symbols: list[str], callback) -> None: ...
```

`AlpacaClient.subscribe_bars` wraps the existing `StockDataStream` logic. `IBKRClient.subscribe_bars` uses `ib_insync` real-time bar subscriptions. `start()` in `pivot_monitor.py` calls `await self._broker.subscribe_bars(symbols, self._check_breakout)`.

### PDT guard rail

Accept `pdt_enabled: bool` in `__init__`. Wrap the PDT block in `_guard_rails_allow` with `if self._pdt_enabled:`.

---

## Market Configuration

### `settings.json` (extend)

Add a `markets` list to the settings schema:

```json
{
  "markets": [
    {
      "id": "us",
      "label": "US (NYSE/NASDAQ)",
      "broker": "alpaca",
      "exchange": "SMART",
      "currency": "USD",
      "tz": "America/New_York",
      "open": "09:30",
      "close": "16:00",
      "pdt_enabled": true,
      "enabled": true
    },
    {
      "id": "oslo",
      "label": "Oslo Børs",
      "broker": "ibkr",
      "exchange": "OSE",
      "currency": "NOK",
      "tz": "Europe/Oslo",
      "open": "09:00",
      "close": "16:30",
      "pdt_enabled": false,
      "enabled": true
    },
    {
      "id": "lse",
      "label": "London Stock Exchange",
      "broker": "ibkr",
      "exchange": "LSE",
      "currency": "GBP",
      "tz": "Europe/London",
      "open": "08:00",
      "close": "16:30",
      "pdt_enabled": false,
      "enabled": true
    }
  ]
}
```

Adding a new market = adding one entry to this list. No code changes required.

### `settings_manager.py` (modify)

- Add `markets` to `_DEFAULTS` with the three entries above
- Add `get_enabled_markets() -> list[dict]` helper
- `save()` validation: reject saves where all markets are disabled; reject unknown `broker` values (must be `"alpaca"` or `"ibkr"`)

---

## Universe Builder

### `universe_builder.py` (new)

Weekly job that builds and caches the tradeable universe for each non-US market.

**For each enabled non-US market:**
1. Fetch all listed stocks from IBKR for the configured exchange
2. Filter by:
   - Minimum market cap (configurable per market, stored in market config)
   - Minimum average daily volume (configurable, default: 100,000 shares/day)
   - Price above 50-day moving average (uptrend filter)
3. Save to `cache/<market-id>-universe.json`

**Output format:**
```json
{
  "market": "oslo",
  "updated": "2026-03-23T06:00:00Z",
  "symbols": [
    {"symbol": "EQNR", "name": "Equinor ASA", "market_cap": 850000000000, "avg_volume": 4200000},
    ...
  ]
}
```

US market continues to use the VCP screener output directly — no universe builder needed.

**Scheduling:** Universe builder runs weekly (Sunday night) via the existing scheduler.

### Earnings blackout for non-US markets

`ib_insync` provides earnings date data per symbol. For each non-US market, `universe_builder.py` also writes `cache/<market-id>-earnings-calendar.json` in the same format as the existing `earnings-calendar.json`. `EarningsBlackout` is modified to accept a `calendar_file` path so each monitor instance can point to the correct file.

---

## Trade Log

Each market writes to its own file: `cache/<market-id>-auto_trades.json`. The US market writes to `cache/us-auto_trades.json` (renamed from `cache/auto_trades.json` — backward-compatible migration: if `us-auto_trades.json` is missing, fall back to `auto_trades.json`).

Each monitor instance has its own file path — no concurrent write conflicts. The `/trades` page reads all `cache/*-auto_trades.json` files, merges them, and adds a `market` field to each row.

---

## Multi-Market Orchestrator

### `main.py` (modify)

On startup, reads `settings.markets`, creates one `PivotWatchlistMonitor` per enabled market:

```python
for market in settings_manager.get_enabled_markets():
    broker = alpaca_client if market["broker"] == "alpaca" else ibkr_client
    monitor = PivotWatchlistMonitor(
        broker_client=broker,
        market_config=market,
        pdt_enabled=market["pdt_enabled"],
        cache_dir=CACHE_DIR,
        ...
    )
    monitors.append(monitor)
```

Each monitor runs independently — separate asyncio tasks, separate triggered sets, separate trade log files.

---

## Guard Rails — Changes

| Guard Rail | US | Non-US |
|------------|-----|--------|
| Market hours | From market config (ET 9:30–16:00) | From market config per exchange |
| PDT | ✅ Applied | ❌ Skipped |
| Max positions | Per broker account | Per broker account (separate IBKR account) |
| Drawdown | Alpaca account value | IBKR account value |
| Earnings blackout | `cache/us-earnings-calendar.json` | `cache/<market-id>-earnings-calendar.json` |
| Volume confirmation | Via broker client | Via broker client |
| Time-of-day soft lock | From market config hours | From market config hours |
| Market Top Detector | ✅ Applied | ✅ Applied (US-centric — known limitation) |

**`max_positions` is per-market** — each monitor checks only its own broker's open positions. A market config entry may include an optional `max_positions` override; otherwise falls back to the global setting.

---

## Settings Page (replaces modal)

The current settings modal is cramped and has no scroll. Replace it with a dedicated `/settings` page with sections.

### Route

`GET /settings` — renders `templates/settings.html`, extends `base.html`.

### Page sections

1. **Mode** — Advisory / Paper / Auto toggle
2. **Risk** — account size, risk per trade, max positions, max position size
3. **Guard Rails** — toggles for each guard rail (drawdown, PDT, volume, time-of-day, etc.)
4. **Exit Management** — trailing stop, partial exit, time stop settings
5. **Smart Sizing** — Kelly, VIX sizing, max multiplier
6. **Markets** — enable/disable toggle per market, with status indicator (active/offline). The active/offline status is checked at page load via a new `GET /api/broker-status` endpoint that calls `is_configured` on each broker client and returns a dict `{"alpaca": true, "ibkr": false}`. The `/settings` route passes this to the template. No credentials are shown for IBKR — it connects via IB Gateway on localhost with no API key, so there are no fields to configure. Alpaca credentials are set via `.env` on the Pi, not the UI.

Each section is a card. Settings are saved via the existing `POST /api/settings` endpoint — one new endpoint (`GET /api/broker-status`) is added for the Markets status indicator.

### Navigation

- Remove the gear icon modal from all pages
- Add a **Settings** nav link in `base.html` topbar alongside Trades and Stats
- Add a **Home** nav link (or "←" back to `/`) in `base.html` topbar so sub-pages always have a way back

---

## Dashboard Changes

### `templates/dashboard.html` (modify)

Signals table gets a **Market** column. Rows labeled by market.

### `templates/trades.html` (modify)

Trades table gets a **Market** column. Summary bar shows global stats across all markets.

### `templates/base.html` (modify)

- Replace gear icon with **Settings** text link pointing to `/settings`
- Add **Home** link pointing to `/`
- Keep existing Trades and Stats links

---

## IBKR Setup on Raspberry Pi

IB Gateway (headless, Pi-compatible) runs as a background process on the Pi. It connects to IBKR servers and exposes a local API on port 4001 (live) or 4002 (paper).

`IBKRClient` connects to `localhost:4002` for paper, `localhost:4001` for live, based on the `environment` setting. `is_configured` returns True only when IB Gateway connection is live. If IB Gateway is not running, IBKR markets are silently skipped — US trading via Alpaca continues normally.

---

## Files

| File | Action | Responsibility |
|------|--------|----------------|
| `broker_client.py` | Create | BrokerClient Protocol definition |
| `ibkr_client.py` | Create | IBKR broker implementation |
| `universe_builder.py` | Create | Weekly universe fetch and filter for non-US markets |
| `alpaca_client.py` | Modify | Add `subscribe_bars`, confirm BrokerClient compliance, return `stop_order_id` |
| `pivot_monitor.py` | Modify | Replace all `self._alpaca` → `self._broker`; dynamic market hours; PDT flag; per-market earnings file |
| `settings_manager.py` | Modify | Add markets to defaults, `get_enabled_markets()`, validate `markets` on save |
| `main.py` | Modify | Instantiate IBKRClient, create monitor per enabled market, add `/settings` route |
| `templates/settings.html` | Create | Full settings page with sections |
| `templates/trades.html` | Modify | Add Market column, read all `*-auto_trades.json` files |
| `templates/dashboard.html` | Modify | Add Market column to signals |
| `templates/base.html` | Modify | Replace gear with Settings link, add Home link |
| `scheduler.py` | Modify | Add weekly universe builder job |
| `tests/test_ibkr_client.py` | Create | IBKRClient unit tests |
| `tests/test_universe_builder.py` | Create | Universe builder unit tests |
| `tests/test_pivot_monitor.py` | Modify | Multi-market test cases, broker abstraction |
| `tests/test_routes.py` | Modify | Add `test_settings_route_returns_200`, `test_broker_status_endpoint` |
| Skill scripts (vcp, canslim, ftd, uptrend, breadth, macro, earnings, 13F, economic-cal) | Modify | Replace FMP API calls with Alpaca / Finnhub / FRED equivalents |

---

## Error Handling

- IB Gateway not running → `is_configured` returns False → IBKR markets skipped, US continues
- Universe file missing → market skips that cycle, logs warning
- IBKR order failure → logged to stderr, trade not recorded
- New market with no universe yet → skips until first weekly build completes
- All markets disabled in settings → `save()` rejects the update

---

## Known Limitations

- Market Top Detector uses US equity data to gate non-US trades — acceptable initially, revisit once non-US trade history accumulates
- No FX hedging or currency conversion between NOK/GBP/USD accounts
- Non-US news sentiment not available — volume + price confirmation only
- IBKR pacing limit means international universe scans take ~10 minutes per exchange — run once daily pre-market only
- FRED API data is end-of-day for most series (VIX updates daily at market close) — not real-time

---

## Out of Scope

- Options or futures on international markets
- Short positions on any market (long-only system)
- Per-market dashboard pages (all markets on single dashboard)
- Mobile app or notifications
- FX hedging
