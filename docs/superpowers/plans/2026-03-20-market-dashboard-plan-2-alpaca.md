# Market Dashboard — Plan 2: Alpaca Integration + Semi-Auto

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live Alpaca portfolio strip (HTMX 5s poll), Semi-Auto Execute buttons with a three-button order-preview slider, bracket order placement, and a Paper→Live switching guard.

**Architecture:** `alpaca_client.py` wraps alpaca-py `TradingClient` (orders, account, positions) and `StockHistoricalDataClient` (last-trade price). Portfolio state is fetched on-demand via REST on each `/api/portfolio` request — no in-memory polling loop. Order preview is server-rendered HTML with vanilla JS for the slider. A trading stream WebSocket task runs in the background capturing fill events. All new routes are wired into the existing FastAPI app in `main.py`.

**Tech Stack:** FastAPI, alpaca-py, HTMX, vanilla JS

**Spec:** `docs/superpowers/specs/2026-03-20-market-dashboard-design.md`

**Scope note:** Plan 2 of 3. Plan 1 was advisory-only. Plan 3 adds Auto trading with PivotWatchlistMonitor.

---

## File Map

```
examples/market-dashboard/
├── alpaca_client.py                    # NEW: AlpacaClient — TradingClient + DataClient + trading stream
├── main.py                             # MODIFY: wire AlpacaClient, add portfolio + order routes, update post_settings
├── config.py                           # MODIFY: add ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER
├── requirements.txt                    # MODIFY: add alpaca-py
├── templates/
│   ├── dashboard.html                  # MODIFY: portfolio panel → HTMX 5s poll
│   ├── fragments/
│   │   ├── portfolio.html              # NEW: P&L strip fragment
│   │   └── order_preview.html          # NEW: inline order preview + three-button slider
│   └── detail/
│       ├── vcp.html                    # MODIFY: Execute button → HTMX form
│       ├── canslim.html                # MODIFY: Execute button → HTMX form
│       └── pead.html                   # MODIFY: Execute button → HTMX form
└── tests/
    ├── test_alpaca_client.py           # NEW
    └── test_routes.py                  # MODIFY: add portfolio + order route tests
```

---

## Task 1: AlpacaClient

**Files:**
- Create: `examples/market-dashboard/alpaca_client.py`
- Modify: `examples/market-dashboard/config.py`
- Modify: `examples/market-dashboard/requirements.txt`
- Create: `examples/market-dashboard/tests/test_alpaca_client.py`

- [ ] **Step 1: Add `alpaca-py` to `requirements.txt`**

Append one line:
```
alpaca-py
```

- [ ] **Step 2: Add Alpaca env vars to `config.py`**

After the existing `ANTHROPIC_API_KEY` line, add:
```python
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
```

(`.env.example` already has `ALPACA_API_KEY=`, `ALPACA_SECRET_KEY=`, `ALPACA_PAPER=true` — no change needed.)

- [ ] **Step 3: Write failing tests**

Create `examples/market-dashboard/tests/test_alpaca_client.py`:

```python
# tests/test_alpaca_client.py
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _mock_trading_client():
    m = MagicMock()
    acct = MagicMock()
    acct.portfolio_value = "100000.00"
    acct.buying_power = "50000.00"
    acct.cash = "50000.00"
    m.get_account.return_value = acct
    m.get_all_positions.return_value = []
    return m


def _mock_data_client(price=150.25):
    m = MagicMock()
    trade = MagicMock()
    trade.price = price
    m.get_stock_latest_trade.return_value = {"AAPL": trade}
    return m


def test_get_account_returns_floats():
    from alpaca_client import AlpacaClient
    client = AlpacaClient(api_key="k", secret_key="s", _trading_client=_mock_trading_client())
    acct = client.get_account()
    assert acct["portfolio_value"] == 100000.0
    assert acct["buying_power"] == 50000.0
    assert acct["cash"] == 50000.0


def test_get_positions_empty():
    from alpaca_client import AlpacaClient
    client = AlpacaClient(api_key="k", secret_key="s", _trading_client=_mock_trading_client())
    assert client.get_positions() == []


def test_get_positions_with_data():
    from alpaca_client import AlpacaClient
    mock_tc = _mock_trading_client()
    pos = MagicMock()
    pos.symbol = "AAPL"
    pos.qty = "10"
    pos.market_value = "1502.50"
    pos.unrealized_pl = "52.50"
    pos.unrealized_plpc = "0.0362"
    pos.avg_entry_price = "145.00"
    pos.current_price = "150.25"
    mock_tc.get_all_positions.return_value = [pos]
    client = AlpacaClient(api_key="k", secret_key="s", _trading_client=mock_tc)
    positions = client.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "AAPL"
    assert positions[0]["qty"] == 10.0
    assert positions[0]["unrealized_pl"] == 52.50


def test_get_last_price():
    from alpaca_client import AlpacaClient
    client = AlpacaClient(api_key="k", secret_key="s", _data_client=_mock_data_client(150.25))
    assert client.get_last_price("AAPL") == 150.25


def test_place_bracket_order():
    from alpaca_client import AlpacaClient
    from alpaca.trading.requests import LimitOrderRequest
    mock_tc = _mock_trading_client()
    order = MagicMock()
    order.id = "order-123"
    order.symbol = "AAPL"
    order.qty = "10"
    order.limit_price = "150.25"
    order.status = "accepted"
    mock_tc.submit_order.return_value = order
    client = AlpacaClient(api_key="k", secret_key="s", _trading_client=mock_tc)
    result = client.place_bracket_order(symbol="AAPL", qty=10, limit_price=150.25, stop_price=145.00)
    assert result["id"] == "order-123"
    assert result["symbol"] == "AAPL"
    mock_tc.submit_order.assert_called_once()
    # Verify bracket order includes both stop_loss and take_profit (Alpaca requires both)
    submitted: LimitOrderRequest = mock_tc.submit_order.call_args[0][0]
    assert submitted.stop_loss is not None
    assert submitted.take_profit is not None


def test_is_configured_false_when_keys_empty():
    from alpaca_client import AlpacaClient
    client = AlpacaClient(api_key="", secret_key="")
    assert not client.is_configured


def test_is_configured_true_when_keys_present():
    from alpaca_client import AlpacaClient
    client = AlpacaClient(api_key="key", secret_key="secret")
    assert client.is_configured
```

- [ ] **Step 4: Run — expect ImportError**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard && uv run pytest tests/test_alpaca_client.py -v 2>&1 | tail -5
```

Expected: `ImportError: No module named 'alpaca_client'`

- [ ] **Step 5: Implement `alpaca_client.py`**

```python
"""Alpaca trading and data client wrapper."""
from __future__ import annotations

import sys


class AlpacaClient:
    """Wraps alpaca-py TradingClient + StockHistoricalDataClient.

    Pass _trading_client / _data_client in tests to inject mocks without
    making real API calls.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        _trading_client=None,
        _data_client=None,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self._trading_client = _trading_client
        self._data_client = _data_client
        self._last_fill: dict | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    @property
    def trading_client(self):
        if self._trading_client is None:
            from alpaca.trading.client import TradingClient
            self._trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )
        return self._trading_client

    @property
    def data_client(self):
        if self._data_client is None:
            from alpaca.data.historical import StockHistoricalDataClient
            self._data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )
        return self._data_client

    def get_account(self) -> dict:
        account = self.trading_client.get_account()
        return {
            "portfolio_value": float(account.portfolio_value),
            "buying_power": float(account.buying_power),
            "cash": float(account.cash),
        }

    def get_positions(self) -> list[dict]:
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
            }
            for p in self.trading_client.get_all_positions()
        ]

    def get_last_price(self, symbol: str) -> float:
        from alpaca.data.requests import StockLatestTradeRequest
        request = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trade = self.data_client.get_stock_latest_trade(request)
        return float(trade[symbol].price)

    def place_bracket_order(
        self,
        symbol: str,
        qty: int,
        limit_price: float,
        stop_price: float,
        take_profit_price: float | None = None,
    ) -> dict:
        from alpaca.trading.requests import LimitOrderRequest, StopLossRequest, TakeProfitRequest
        from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
        # Alpaca requires both stop_loss AND take_profit for bracket orders.
        # Default: 2:1 risk-reward (take_profit = entry + 2 × risk).
        if take_profit_price is None:
            risk = limit_price - stop_price
            take_profit_price = round(limit_price + risk * 2, 2)
        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=round(limit_price, 2),
            order_class=OrderClass.BRACKET,
            stop_loss=StopLossRequest(stop_price=round(stop_price, 2)),
            take_profit=TakeProfitRequest(limit_price=round(take_profit_price, 2)),
        )
        order = self.trading_client.submit_order(order_data)
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "qty": float(order.qty),
            "limit_price": float(order.limit_price),
            "status": str(order.status),
        }

    async def start_trading_stream(self) -> None:
        """Subscribe to order fill events. Runs as a background asyncio task.

        Uses run_in_executor so the blocking public stream.run() API runs in a
        thread — avoids depending on the private _run_forever() method.
        Disconnections are logged to stderr but do not crash the server.
        """
        import asyncio as _asyncio
        from alpaca.trading.stream import TradingStream
        stream = TradingStream(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=self.paper,
        )

        @stream.subscribe_trade_updates
        async def handle_update(data):
            self._last_fill = {
                "symbol": data.order.symbol,
                "side": str(data.order.side),
                "qty": float(data.order.qty or 0),
                "event": str(data.event),
            }

        loop = _asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, stream.run)
        except Exception as e:
            print(f"[alpaca_stream] disconnected: {e}", file=sys.stderr)
```

- [ ] **Step 6: Run tests — expect all green**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard && uv run pytest tests/test_alpaca_client.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills && git add examples/market-dashboard/alpaca_client.py examples/market-dashboard/config.py examples/market-dashboard/requirements.txt examples/market-dashboard/tests/test_alpaca_client.py && git commit -m "feat(market-dashboard): AlpacaClient — trading REST + data client + trading stream"
```

---

## Task 2: Portfolio Route + Fragment

**Files:**
- Modify: `examples/market-dashboard/main.py`
- Create: `examples/market-dashboard/templates/fragments/portfolio.html`
- Modify: `examples/market-dashboard/templates/dashboard.html`
- Modify: `examples/market-dashboard/tests/test_routes.py`

- [ ] **Step 1: Write failing test**

Append to `examples/market-dashboard/tests/test_routes.py`:

```python
import pytest
from config import SETTINGS_FILE


@pytest.fixture(autouse=True)
def clean_settings():
    """Delete settings.json before each test so mode defaults to 'advisory'."""
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()
    yield
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()


def test_api_portfolio_returns_html():
    client = make_client()
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # Alpaca is not configured in test env → "connect Alpaca" message renders
    assert b"ALPACA_API_KEY" in r.content
```

> Note: The `clean_settings` fixture is `autouse=True` — it applies to ALL tests in this file,
> including all existing tests. This is safe: all existing tests that save settings use
> `environment=paper` which passes without `live_confirm`, and mode tests save + read within
> the same test. Deleting `settings.json` before each test ensures the default `advisory` mode
> is always in effect at the start of each test.

Run: `uv run pytest tests/test_routes.py::test_api_portfolio_returns_html -v 2>&1 | tail -5`

Expected: FAIL (404 — route not yet defined).

- [ ] **Step 2: Wire AlpacaClient into `main.py`**

Read `main.py` first. Then make these edits:

**Add to imports** (after the existing `from skills_runner import SkillsRunner` line):
```python
from alpaca_client import AlpacaClient
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER
```

**Add module-level instance** (after the `runner = SkillsRunner(cache_dir=CACHE_DIR, skills_root=SKILLS_ROOT)` line):
```python
alpaca = AlpacaClient(
    api_key=ALPACA_API_KEY,
    secret_key=ALPACA_SECRET_KEY,
    paper=ALPACA_PAPER,
)
```

**Update `startup()`** — add trading stream start after `asyncio.create_task(_refresh_stale_on_startup())`:
```python
    if alpaca.is_configured:
        asyncio.create_task(alpaca.start_trading_stream())
```

- [ ] **Step 3: Add `/api/portfolio` route to `main.py`**

Add after the `api_market_state` route:

```python
@app.get("/api/portfolio", response_class=HTMLResponse)
async def api_portfolio(request: Request):
    portfolio: dict = {"account": None, "positions": [], "error": None}
    if alpaca.is_configured:
        try:
            portfolio["account"] = alpaca.get_account()
            portfolio["positions"] = alpaca.get_positions()
        except Exception as e:
            portfolio["error"] = str(e)
    ctx = {"request": request, "portfolio": portfolio, "settings": settings_manager.load()}
    return templates.TemplateResponse("fragments/portfolio.html", ctx)
```

- [ ] **Step 4: Create `templates/fragments/portfolio.html`**

```html
{% set account = portfolio.account %}
{% set positions = portfolio.positions %}
{% set error = portfolio.error %}

{% if not account and not error %}
  <div style="color:#8b949e; font-size:11px;">
    Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env to connect
  </div>
{% elif error %}
  <div style="color:#f87171; font-size:11px;">⚠️ {{ error[:100] }}</div>
{% else %}
  <div style="display:flex; gap:16px; align-items:baseline; margin-bottom:8px; flex-wrap:wrap;">
    <div>
      <div style="font-size:10px; color:#8b949e; text-transform:uppercase; margin-bottom:2px;">Portfolio</div>
      <div style="font-size:16px; font-weight:bold; color:#4ade80;">${{ "{:,.0f}".format(account.portfolio_value) }}</div>
    </div>
    <div>
      <div style="font-size:10px; color:#8b949e; text-transform:uppercase; margin-bottom:2px;">Buying Power</div>
      <div style="font-size:14px; color:#e6edf3;">${{ "{:,.0f}".format(account.buying_power) }}</div>
    </div>
    {% if positions %}
    <div>
      <div style="font-size:10px; color:#8b949e; text-transform:uppercase; margin-bottom:2px;">Positions</div>
      <div style="font-size:14px; color:#e6edf3;">{{ positions | length }}</div>
    </div>
    {% endif %}
  </div>

  {% if positions %}
  <table style="width:100%; border-collapse:collapse; font-size:10px;">
    <thead>
      <tr>
        <th style="text-align:left; color:#8b949e; padding:2px 4px; font-weight:normal; border-bottom:1px solid #30363d;">Sym</th>
        <th style="text-align:right; color:#8b949e; padding:2px 4px; font-weight:normal; border-bottom:1px solid #30363d;">Qty</th>
        <th style="text-align:right; color:#8b949e; padding:2px 4px; font-weight:normal; border-bottom:1px solid #30363d;">Value</th>
        <th style="text-align:right; color:#8b949e; padding:2px 4px; font-weight:normal; border-bottom:1px solid #30363d;">P&amp;L</th>
      </tr>
    </thead>
    <tbody>
      {% for p in positions %}
      <tr>
        <td style="padding:2px 4px; color:#38bdf8; font-weight:bold;">{{ p.symbol }}</td>
        <td style="padding:2px 4px; text-align:right;">{{ p.qty | int }}</td>
        <td style="padding:2px 4px; text-align:right;">${{ "{:,.0f}".format(p.market_value) }}</td>
        <td style="padding:2px 4px; text-align:right; color:{% if p.unrealized_pl >= 0 %}#4ade80{% else %}#f87171{% endif %};">
          {{ "+" if p.unrealized_pl >= 0 else "" }}${{ "{:,.0f}".format(p.unrealized_pl) }}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div style="color:#8b949e; font-size:11px;">No open positions</div>
  {% endif %}
{% endif %}
```

- [ ] **Step 5: Update the portfolio panel in `templates/dashboard.html`**

Find:
```html
    <div class="bottom-panel" id="portfolio-panel">
      <div class="panel-title">Portfolio (Alpaca)</div>
      <div style="color:#8b949e; font-size:11px;">Connect Alpaca in Plan 2</div>
    </div>
```

Replace with:
```html
    <div class="bottom-panel" id="portfolio-panel"
         hx-get="/api/portfolio"
         hx-trigger="every 5s, load"
         hx-swap="innerHTML">
      <div class="panel-title">Portfolio (Alpaca)</div>
      <div style="color:#8b949e; font-size:11px;">Loading…</div>
    </div>
```

- [ ] **Step 6: Run tests — expect all green**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard && uv run pytest tests/ -v 2>&1 | tail -10
```

Expected: all tests PASS including `test_api_portfolio_returns_html`.

- [ ] **Step 7: Commit**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills && git add examples/market-dashboard/main.py examples/market-dashboard/templates/fragments/portfolio.html examples/market-dashboard/templates/dashboard.html examples/market-dashboard/tests/test_routes.py && git commit -m "feat(market-dashboard): portfolio strip — Alpaca P&L panel with HTMX 5s refresh"
```

---

## Task 3: Execute Buttons + Order Preview Route

**Files:**
- Modify: `examples/market-dashboard/main.py`
- Create: `examples/market-dashboard/templates/fragments/order_preview.html`
- Modify: `examples/market-dashboard/templates/detail/vcp.html`
- Modify: `examples/market-dashboard/templates/detail/canslim.html`
- Modify: `examples/market-dashboard/templates/detail/pead.html`
- Modify: `examples/market-dashboard/tests/test_routes.py`

This task replaces the no-op `<button class="execute-btn">Execute</button>` buttons (already rendered in vcp/canslim/pead when mode ≠ advisory) with HTMX form-based buttons, and adds the `/api/order/preview` route that returns the inline preview fragment.

- [ ] **Step 1: Write failing test**

Append to `tests/test_routes.py`:

```python
def test_order_preview_endpoint_exists():
    """POST /api/order/preview returns 403 in advisory mode (the default)."""
    client = make_client()
    r = client.post("/api/order/preview", data={
        "symbol": "AAPL",
        "entry_price": "150.0",
        "stop_price": "145.0",
        "skill": "vcp-screener",
    })
    # Default mode is advisory (DEFAULT_TRADING_MODE = "advisory" in config.py)
    assert r.status_code == 403
```

Run: `uv run pytest tests/test_routes.py::test_order_preview_endpoint_exists -v 2>&1 | tail -5`

Expected: FAIL (405 or 404 — route not yet defined).

- [ ] **Step 2: Add `/api/order/preview` route to `main.py`**

Add after the `api_portfolio` route:

```python
@app.post("/api/order/preview", response_class=HTMLResponse)
async def order_preview(
    request: Request,
    symbol: str = Form(...),
    entry_price: float = Form(...),
    stop_price: float = Form(...),
    skill: str = Form(...),
):
    settings = settings_manager.load()
    if settings.get("mode") == "advisory":
        raise HTTPException(status_code=403, detail="Execute not available in Advisory mode")

    # Fetch live last price; fall back to screener's entry_price if Alpaca unavailable.
    # CANSLIM/PEAD screeners submit entry_price=0 since they have no price data.
    # When Alpaca is configured we always fetch live price (overrides any screener value).
    # When Alpaca is not configured, live_price stays at entry_price (0 for CANSLIM/PEAD).
    live_price = entry_price
    if alpaca.is_configured:
        try:
            live_price = alpaca.get_last_price(symbol)
        except Exception:
            pass

    # Default stop to 3% below entry when screener doesn't provide one (e.g. CANSLIM, PEAD).
    # This gives a reasonable starting point; the slider lets the user adjust position size.
    effective_stop = stop_price if stop_price > 0 else round(live_price * 0.97, 2)

    account_value = 100_000.0  # fallback for unconfigured Alpaca
    if alpaca.is_configured:
        try:
            account_value = alpaca.get_account()["portfolio_value"]
        except Exception:
            pass

    ctx = {
        "request": request,
        "symbol": symbol,
        "skill": skill,
        "entry_price": round(live_price, 2),
        "stop_price": effective_stop,
        "account_value": account_value,
        "default_risk_pct": settings.get("default_risk_pct", 1.0),
    }
    return templates.TemplateResponse("fragments/order_preview.html", ctx)
```

- [ ] **Step 3: Create `templates/fragments/order_preview.html`**

```html
<div id="order-preview-{{ symbol }}" style="
  background:#1e2a3a; border:1px solid #30363d; border-radius:6px;
  padding:12px; margin-top:8px;
  font-family:'Consolas','Menlo',monospace; font-size:11px;
">
  <div style="font-size:12px; color:#4ade80; margin-bottom:8px; font-weight:bold;">
    Order Preview — {{ symbol }}
  </div>

  <div style="display:flex; gap:20px; margin-bottom:10px;">
    <div><span style="color:#8b949e;">Entry:</span> ${{ "%.2f"|format(entry_price) }}</div>
    <div><span style="color:#8b949e;">Stop:</span> <span style="color:#f87171;">${{ "%.2f"|format(stop_price) }}</span></div>
    <div><span style="color:#8b949e;">Risk/sh:</span> ${{ "%.2f"|format(entry_price - stop_price) }}</div>
  </div>

  <!-- Three-button mode selector -->
  <div style="display:flex; gap:4px; margin-bottom:10px;">
    <button class="op-btn op-active" id="op-btn-risk-{{ symbol }}"
            onclick="opSetMode('{{ symbol }}','risk_pct')">Risk %</button>
    <button class="op-btn" id="op-btn-shares-{{ symbol }}"
            onclick="opSetMode('{{ symbol }}','shares')">Shares</button>
    <button class="op-btn" id="op-btn-dollars-{{ symbol }}"
            onclick="opSetMode('{{ symbol }}','dollars')">$ Amount</button>
  </div>

  <!-- Slider -->
  <div style="margin-bottom:8px;">
    <input type="range" id="op-slider-{{ symbol }}" style="width:100%; accent-color:#4ade80;"
           oninput="opUpdateSlider('{{ symbol }}', this.value)">
    <div style="display:flex; justify-content:space-between; font-size:10px; color:#8b949e; margin-top:2px;">
      <span id="op-min-{{ symbol }}"></span>
      <span id="op-cur-{{ symbol }}" style="color:#4ade80; font-weight:bold;"></span>
      <span id="op-max-{{ symbol }}"></span>
    </div>
  </div>

  <!-- Calculated values -->
  <div style="display:flex; gap:16px; margin-bottom:10px; flex-wrap:wrap;">
    <div><span style="color:#8b949e;">Shares:</span> <span id="op-shares-{{ symbol }}">—</span></div>
    <div><span style="color:#8b949e;">$ Amount:</span> <span id="op-dollars-{{ symbol }}">—</span></div>
    <div><span style="color:#8b949e;">Risk:</span> <span id="op-riskpct-{{ symbol }}" style="color:#facc15;">—</span>%</div>
    <div><span style="color:#8b949e;">Risk $:</span> <span id="op-riskdol-{{ symbol }}" style="color:#f87171;">—</span></div>
  </div>

  <div style="display:flex; gap:8px;">
    <button class="btn-primary" id="op-confirm-{{ symbol }}"
            onclick="opConfirm('{{ symbol }}', {{ entry_price }}, {{ stop_price }})">
      Confirm Order
    </button>
    <button class="btn-secondary"
            onclick="document.getElementById('order-preview-{{ symbol }}').remove()">
      Cancel
    </button>
  </div>
</div>

<style>
.op-btn {
  background:#1e2a3a; border:1px solid #30363d; border-radius:4px;
  padding:3px 10px; color:#8b949e; cursor:pointer; font-size:11px;
  font-family:'Consolas','Menlo',monospace;
}
.op-btn.op-active { border-color:#4ade80; color:#4ade80; }
</style>

<script>
(function() {
  var SYM = "{{ symbol }}";
  var ENTRY = {{ entry_price }};
  var STOP = {{ stop_price }};
  var RISK_PER_SH = ENTRY - STOP;
  var ACCOUNT = {{ account_value }};
  var DEFAULT_RISK = {{ default_risk_pct }};
  var mode = 'risk_pct';

  if (RISK_PER_SH <= 0 || ENTRY <= 0) {
    document.getElementById('order-preview-' + SYM).innerHTML =
      '<div style="color:#f87171; padding:8px;">⚠️ Cannot preview: entry price unavailable.' +
      ' Ensure Alpaca API keys are configured in .env.</div>';
    return;
  }

  function calcShares(riskPct) {
    var riskDollars = ACCOUNT * riskPct / 100;
    return Math.max(1, Math.floor(riskDollars / RISK_PER_SH));
  }

  function display(shares) {
    var dollars = shares * ENTRY;
    var riskD = shares * RISK_PER_SH;
    var riskPct = riskD / ACCOUNT * 100;
    document.getElementById('op-shares-' + SYM).textContent = shares;
    document.getElementById('op-dollars-' + SYM).textContent = '$' + dollars.toFixed(0);
    document.getElementById('op-riskpct-' + SYM).textContent = riskPct.toFixed(2);
    document.getElementById('op-riskdol-' + SYM).textContent = '$' + riskD.toFixed(0);
    window['_opShares_' + SYM] = shares;
  }

  window.opSetMode = function(sym, m) {
    if (sym !== SYM) return;
    mode = m;
    ['risk_pct','shares','dollars'].forEach(function(k) {
      var el = document.getElementById('op-btn-' + k.replace('_','-') + '-' + sym);
      if (el) el.classList.toggle('op-active', k === m);
    });
    initSlider();
  };

  function initSlider() {
    var s = document.getElementById('op-slider-' + SYM);
    if (mode === 'risk_pct') {
      s.min = 0.1; s.max = 5.0; s.step = 0.1; s.value = DEFAULT_RISK;
      document.getElementById('op-min-' + SYM).textContent = '0.1%';
      document.getElementById('op-max-' + SYM).textContent = '5%';
    } else if (mode === 'shares') {
      var mx = calcShares(5.0);
      s.min = 1; s.max = mx; s.step = 1; s.value = calcShares(DEFAULT_RISK);
      document.getElementById('op-min-' + SYM).textContent = '1 sh';
      document.getElementById('op-max-' + SYM).textContent = mx + ' sh';
    } else {
      var maxD = Math.floor(ACCOUNT * 0.25 / ENTRY) * ENTRY;
      s.min = ENTRY; s.max = maxD; s.step = ENTRY;
      s.value = calcShares(DEFAULT_RISK) * ENTRY;
      document.getElementById('op-min-' + SYM).textContent = '$' + ENTRY.toFixed(0);
      document.getElementById('op-max-' + SYM).textContent = '$' + (maxD / 1000).toFixed(0) + 'k';
    }
    window.opUpdateSlider(SYM, s.value);
  }

  window.opUpdateSlider = function(sym, val) {
    if (sym !== SYM) return;
    var shares;
    if (mode === 'risk_pct') {
      shares = calcShares(parseFloat(val));
      document.getElementById('op-cur-' + SYM).textContent = parseFloat(val).toFixed(2) + '%';
    } else if (mode === 'shares') {
      shares = parseInt(val);
      document.getElementById('op-cur-' + SYM).textContent = val + ' sh';
    } else {
      shares = Math.max(1, Math.floor(parseFloat(val) / ENTRY));
      document.getElementById('op-cur-' + SYM).textContent = '$' + parseFloat(val).toFixed(0);
    }
    display(shares);
  };

  window.opConfirm = function(sym, entry, stop) {
    if (sym !== SYM) return;
    var shares = window['_opShares_' + sym];
    var btn = document.getElementById('op-confirm-' + sym);
    btn.disabled = true;
    btn.textContent = 'Placing…';
    fetch('/api/order/confirm', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({symbol: sym, qty: shares, limit_price: entry, stop_price: stop})
    }).then(function(r) { return r.json(); }).then(function(data) {
      var el = document.getElementById('order-preview-' + sym);
      if (data.ok) {
        el.innerHTML = '<div style="color:#4ade80; padding:8px;">✅ Order placed — ' + data.order_id + '</div>';
      } else {
        el.innerHTML = '<div style="color:#f87171; padding:8px;">❌ ' + data.error + '</div>';
      }
    });
  };

  initSlider();
})();
</script>
```

- [ ] **Step 4: Update Execute buttons in detail pages**

**In `templates/detail/vcp.html`**, find the Execute button cell (inside the `{% if settings.mode != 'advisory' %}` block) and replace:

```html
{% if settings.mode != 'advisory' %}<td><button class="execute-btn">Execute</button></td>{% endif %}
```

with:

```html
{% if settings.mode != 'advisory' %}
<td>
  <form style="display:inline"
        hx-post="/api/order/preview"
        hx-target="closest tr"
        hx-swap="afterend">
    <input type="hidden" name="symbol" value="{{ c.get('ticker', '') }}">
    <input type="hidden" name="entry_price" value="{{ c.get('entry_price', 0) }}">
    <input type="hidden" name="stop_price" value="{{ c.get('stop_price', 0) }}">
    <input type="hidden" name="skill" value="vcp-screener">
    <button type="submit" class="execute-btn">Execute</button>
  </form>
</td>
{% endif %}
```

**In `templates/detail/canslim.html`**, apply the same pattern (skill: `canslim-screener`).

Note: CANSLIM candidates have no `entry_price`/`stop_price` fields. Submit `0` for both — the
`/api/order/preview` route fetches the live price from Alpaca and computes a 3% default stop:

```html
{% if settings.mode != 'advisory' %}
<td>
  <form style="display:inline"
        hx-post="/api/order/preview"
        hx-target="closest tr"
        hx-swap="afterend">
    <input type="hidden" name="symbol" value="{{ c.get('ticker', '') }}">
    <input type="hidden" name="entry_price" value="0">
    <input type="hidden" name="stop_price" value="0">
    <input type="hidden" name="skill" value="canslim-screener">
    <button type="submit" class="execute-btn">Execute</button>
  </form>
</td>
{% endif %}
```

**In `templates/detail/pead.html`**, apply the same pattern (skill: `pead-screener`).

Note: PEAD candidates have no `entry_price`/`stop_price` fields either. Same 0-submit pattern:

```html
{% if settings.mode != 'advisory' %}
<td>
  <form style="display:inline"
        hx-post="/api/order/preview"
        hx-target="closest tr"
        hx-swap="afterend">
    <input type="hidden" name="symbol" value="{{ c.get('ticker', c.get('symbol', '')) }}">
    <input type="hidden" name="entry_price" value="0">
    <input type="hidden" name="stop_price" value="0">
    <input type="hidden" name="skill" value="pead-screener">
    <button type="submit" class="execute-btn">Execute</button>
  </form>
</td>
{% endif %}
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard && uv run pytest tests/ -v 2>&1 | tail -10
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills && git add examples/market-dashboard/main.py examples/market-dashboard/templates/fragments/order_preview.html examples/market-dashboard/templates/detail/vcp.html examples/market-dashboard/templates/detail/canslim.html examples/market-dashboard/templates/detail/pead.html examples/market-dashboard/tests/test_routes.py && git commit -m "feat(market-dashboard): order preview — three-button slider + HTMX Execute buttons"
```

---

## Task 4: Order Confirm Route

**Files:**
- Modify: `examples/market-dashboard/main.py`
- Modify: `examples/market-dashboard/tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_routes.py`:

```python
def test_order_confirm_advisory_mode_returns_403():
    """Advisory mode (the default) never executes orders — must return 403."""
    client = make_client()
    # Default mode is advisory (DEFAULT_TRADING_MODE = "advisory" in config.py)
    r = client.post("/api/order/confirm", json={
        "symbol": "AAPL",
        "qty": 10,
        "limit_price": 150.0,
        "stop_price": 145.0,
    })
    assert r.status_code == 403
```

Run: `uv run pytest tests/test_routes.py::test_order_confirm_advisory_mode_returns_403 -v 2>&1 | tail -5`

Expected: FAIL (404 — route not yet defined).

- [ ] **Step 2: Add Pydantic model and route to `main.py`**

**First**, add `from pydantic import BaseModel` to the top-of-file imports block in `main.py`, alongside the existing FastAPI imports. The current `from fastapi import FastAPI, Form, HTTPException, Request, Response` line is the right block to add it after:

```python
from pydantic import BaseModel
```

**Then**, add the route after the `order_preview` route:

```python
class OrderConfirmRequest(BaseModel):
    symbol: str
    qty: int
    limit_price: float
    stop_price: float


@app.post("/api/order/confirm")
async def order_confirm(body: OrderConfirmRequest):
    settings = settings_manager.load()
    if settings.get("mode") == "advisory":
        raise HTTPException(status_code=403, detail="Execute not available in Advisory mode")
    if not alpaca.is_configured:
        return JSONResponse({"ok": False, "error": "Alpaca not configured — set API keys in .env"})
    try:
        result = alpaca.place_bracket_order(
            symbol=body.symbol,
            qty=body.qty,
            limit_price=body.limit_price,
            stop_price=body.stop_price,
        )
        return JSONResponse({"ok": True, "order_id": result["id"], "status": result["status"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
```

> Note: `BaseModel` is imported from pydantic. Do NOT add a duplicate `from pydantic import BaseModel` if it is already imported — just add the `OrderConfirmRequest` class.

- [ ] **Step 3: Run all tests**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard && uv run pytest tests/ -v 2>&1 | tail -10
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills && git add examples/market-dashboard/main.py examples/market-dashboard/tests/test_routes.py && git commit -m "feat(market-dashboard): order confirm — bracket order placement via Alpaca"
```

---

## Task 5: Paper→Live Switching Guard

**Files:**
- Modify: `examples/market-dashboard/main.py`
- Modify: `examples/market-dashboard/templates/fragments/settings_modal.html`
- Modify: `examples/market-dashboard/tests/test_routes.py`

The guard has two parts:
1. **Server-side:** `POST /api/settings` requires `live_confirm=CONFIRM LIVE TRADING` when `environment=live`.
2. **Client-side:** The settings modal intercepts the form submit in JS, shows a `prompt()` when switching to live, and populates the hidden field if the user types the phrase correctly.

- [ ] **Step 1: Verify existing tests pass**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard && uv run pytest tests/ -v 2>&1 | tail -5
```

Expected: all tests PASS. Confirm before writing the new failing tests below.

- [ ] **Step 2: Write failing tests**

Append to `tests/test_routes.py`:

```python
def test_post_settings_live_without_confirm_returns_400():
    client = make_client()
    r = client.post("/api/settings", data={
        "mode": "advisory",
        "default_risk_pct": "1.0",
        "max_positions": "5",
        "max_position_size_pct": "10.0",
        "environment": "live",
        # live_confirm absent → must be rejected
    })
    assert r.status_code == 400


def test_post_settings_live_with_correct_confirm_succeeds():
    client = make_client()
    r = client.post("/api/settings", data={
        "mode": "advisory",
        "default_risk_pct": "1.0",
        "max_positions": "5",
        "max_position_size_pct": "10.0",
        "environment": "live",
        "live_confirm": "CONFIRM LIVE TRADING",
    })
    assert r.status_code == 200


def test_post_settings_paper_needs_no_confirm():
    client = make_client()
    r = client.post("/api/settings", data={
        "mode": "advisory",
        "default_risk_pct": "1.0",
        "max_positions": "5",
        "max_position_size_pct": "10.0",
        "environment": "paper",
    })
    assert r.status_code == 200
```

Run: `uv run pytest tests/test_routes.py::test_post_settings_live_without_confirm_returns_400 -v 2>&1 | tail -5`

Expected: FAIL (returns 200 — guard not yet implemented).

- [ ] **Step 3: Update `post_settings` in `main.py`**

Find the existing `post_settings` function (currently at the bottom of the route definitions). Add `live_confirm: str = Form("")` parameter and a guard before saving:

Replace the function signature and body:

```python
@app.post("/api/settings", response_class=HTMLResponse)
async def post_settings(
    request: Request,
    mode: str = Form(...),
    default_risk_pct: float = Form(...),
    max_positions: int = Form(...),
    max_position_size_pct: float = Form(...),
    environment: str = Form(...),
    live_confirm: str = Form(""),
):
    if environment == "live" and live_confirm != "CONFIRM LIVE TRADING":
        raise HTTPException(
            status_code=400,
            detail="Switching to Live requires typing 'CONFIRM LIVE TRADING'",
        )
    settings_manager.save({
        "mode": mode,
        "default_risk_pct": default_risk_pct,
        "max_positions": max_positions,
        "max_position_size_pct": max_position_size_pct,
        "environment": environment,
    })
    ctx = {"request": request, "settings": settings_manager.load()}
    return templates.TemplateResponse("fragments/settings_modal.html", ctx)
```

- [ ] **Step 4: Update `templates/fragments/settings_modal.html`**

Read the current file first. Make two targeted edits:

**Edit 1:** Find these lines (the `<form>` tag on line 11 followed by the mode comment):
```html
    <form hx-post="/api/settings" hx-target="#modal-container" hx-swap="innerHTML">
      <!-- Trading Mode -->
```
Replace with (adding `onsubmit` attribute and hidden input as first child of form, before the mode comment):
```html
    <form hx-post="/api/settings" hx-target="#modal-container" hx-swap="innerHTML"
          onsubmit="return handleSettingsSubmit(this)">
      <input type="hidden" name="live_confirm" id="live-confirm-input" value="">
      <!-- Trading Mode -->
```

**Edit 2:** Find the `</form>` closing tag followed by the closing `</div>` of `.modal-box`:
```html
    </form>
  </div>
</div>
```
Insert the `<script>` between `</form>` and `</div>` (i.e., as the last child of `.modal-box`, after the form):
```html
    <script>
    function handleSettingsSubmit(form) {
      var env = form.querySelector('[name=environment]').value;
      if (env === 'live') {
        var typed = prompt('Type exactly to confirm:\n\nCONFIRM LIVE TRADING');
        if (typed !== 'CONFIRM LIVE TRADING') {
          alert('Confirmation did not match. Live trading not enabled.');
          return false;
        }
        document.getElementById('live-confirm-input').value = typed;
      }
      return true;
    }
    </script>
```

- [ ] **Step 5: Run all tests**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard && uv run pytest tests/ -v --tb=short 2>&1 | tail -15
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills && git add examples/market-dashboard/main.py examples/market-dashboard/templates/fragments/settings_modal.html examples/market-dashboard/tests/test_routes.py && git commit -m "feat(market-dashboard): Paper→Live guard — CONFIRM LIVE TRADING confirmation required"
```

---

## Implementation Notes

**alpaca-py import pattern:** All alpaca imports are deferred inside methods (`from alpaca.trading.client import TradingClient` inside the property). This means the app imports and tests work even if `alpaca-py` is not yet installed — the error only surfaces when a route actually tries to connect.

**Advisory mode default:** `settings.json` is auto-created on first save. Before first save, the default is `advisory`. This means `/api/order/preview` and `/api/order/confirm` will return 403 on a fresh install — this is correct behavior.

**Alpaca unconfigured:** When `ALPACA_API_KEY` is empty, `alpaca.is_configured` is `False`. All routes gracefully handle this: portfolio shows a "connect Alpaca" message, order confirm returns `{"ok": False, "error": "..."}`. The dashboard works without Alpaca configured.

**Trading stream:** `start_trading_stream()` runs as a fire-and-forget `asyncio.create_task`. If it disconnects (market closed, network blip), it logs to stderr and exits silently — the server keeps running. `_last_fill` on the AlpacaClient can be read by a future `/api/fills` route (Plan 3).

**Order preview entry price:** The server fetches the live last-trade price from Alpaca REST at the moment Execute is clicked. Screeners that don't provide price data (CANSLIM, PEAD) submit `entry_price=0` — the route treats 0 as "always fetch live price". If Alpaca is unavailable and the screener provided no price, the entry shows as 0.

**Default stop price for CANSLIM/PEAD:** When `stop_price=0`, the route defaults to `live_price * 0.97` (3% below entry). This gives a reasonable starting point; the user can see the risk calculation in the preview.

**Bracket order take_profit:** Alpaca API requires both `stop_loss` and `take_profit` for bracket orders. `place_bracket_order` defaults `take_profit_price` to entry + 2× risk (2:1 R/R). `order_confirm` passes `take_profit_price=None` so the method computes the default automatically.
