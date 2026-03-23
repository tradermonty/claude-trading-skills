# Trade Log Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/trades` page showing all auto trades from `cache/auto_trades.json` with a summary bar and sortable table.

**Architecture:** Single FastAPI route reads `cache/auto_trades.json`, computes summary stats in Python, passes data to a Jinja2 template. A nav link in `base.html` provides access. No new classes — all logic in the route handler.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, standard library (json, datetime)

**Spec:** `docs/superpowers/specs/2026-03-22-trades-log-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `tests/test_routes.py` | Modify | Add `test_trades_route_returns_200` |
| `main.py` | Modify | Add `GET /trades` route |
| `templates/trades.html` | Create | Trades page template |
| `templates/base.html` | Modify | Add "Trades" nav link |

---

## Task 1: Route + test

**Files:**
- Modify: `tests/test_routes.py`
- Modify: `main.py`

### Step 1.1 — Write the failing test

Add to `tests/test_routes.py` (after `test_stats_route_returns_200`):

```python
def test_trades_route_returns_200():
    """GET /trades returns 200."""
    client = make_client()
    response = client.get("/trades")
    assert response.status_code == 200
```

- [ ] Add the test
- [ ] Run: `uv run pytest tests/test_routes.py::test_trades_route_returns_200 -v`
- [ ] Expected: **FAIL** with 404 (route not yet defined)

### Step 1.2 — Add the `/trades` route to `main.py`

Add after the `/stats` route (around line 197). The route reads `auto_trades.json`, computes summary stats, and passes everything to the template:

```python
@app.get("/trades", response_class=HTMLResponse)
async def trades_page(request: Request):
    trades_file = CACHE_DIR / "auto_trades.json"
    trades = []
    try:
        if trades_file.exists():
            data = json.loads(trades_file.read_text())
            trades = data.get("trades", [])
    except Exception:
        trades = []

    # Newest first
    trades = list(reversed(trades))

    # Compute summary stats
    closed = [t for t in trades if t.get("outcome") in ("win", "loss")]
    open_trades = [t for t in trades if not t.get("outcome")]
    wins = [t for t in closed if t.get("outcome") == "win"]
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else None

    # Avg R for closed trades that have exit_price
    r_values = []
    for t in closed:
        try:
            risk = t["entry_price"] - t["stop_price"]
            if risk > 0 and t.get("exit_price"):
                r_values.append((t["exit_price"] - t["entry_price"]) / risk)
        except Exception:
            pass
    avg_r = round(sum(r_values) / len(r_values), 2) if r_values else None

    ctx = {
        "request": request,
        "settings": settings_manager.load(),
        "trades": trades,
        "total_trades": len(trades),
        "open_count": len(open_trades),
        "win_rate": win_rate,
        "avg_r": avg_r,
    }
    return templates.TemplateResponse("trades.html", ctx)
```

Note: `json` is already imported in `main.py`. `CACHE_DIR` and `settings_manager` are already defined at module level.

- [ ] Add the route to `main.py`
- [ ] Run: `uv run pytest tests/test_routes.py::test_trades_route_returns_200 -v`
- [ ] Expected: **FAIL** with Jinja2 TemplateNotFound (template doesn't exist yet)

### Step 1.3 — Create minimal `templates/trades.html` to make the test pass

```html
{% extends "base.html" %}
{% block content %}
<div style="padding: 16px;">
  <h2 style="color:#e2e8f0; margin-bottom:16px;">Trade Log</h2>
  <p style="color:#64748b;">No trades recorded yet.</p>
</div>
{% endblock %}
```

- [ ] Create `templates/trades.html` with the stub above
- [ ] Run: `uv run pytest tests/test_routes.py::test_trades_route_returns_200 -v`
- [ ] Expected: **PASS**

### Step 1.4 — Run full suite to check for regressions

- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures (pre-existing ~10 failures are fine)

### Step 1.5 — Commit

```bash
git add tests/test_routes.py main.py templates/trades.html
git commit -m "feat: add /trades route with summary stats"
```

- [ ] Commit

---

## Task 2: Template + nav link

**Files:**
- Modify: `templates/trades.html`
- Modify: `templates/base.html`

### Step 2.1 — Update `main.py` to pre-compute R for each trade

Add this loop to the route handler in `main.py`, after the `trades = list(reversed(trades))` line and before the `closed = ...` line:

```python
# Pre-compute R for each trade (Jinja2 can't call .get() on dicts)
for t in trades:
    try:
        risk = t["entry_price"] - t["stop_price"]
        if risk > 0 and t.get("exit_price"):
            t["r"] = round((t["exit_price"] - t["entry_price"]) / risk, 2)
        else:
            t["r"] = None
    except Exception:
        t["r"] = None
```

- [ ] Add the R pre-computation loop to `main.py`

### Step 2.2 — Replace stub with full template

Replace `templates/trades.html` with the complete template below. R values come from `t.r` (pre-computed in Python — never use `.get()` in Jinja2):

```html
{% extends "base.html" %}
{% block content %}
<div style="padding: 16px;">
  <h2 style="color:#e2e8f0; margin-bottom:16px;">Trade Log</h2>

  <!-- Summary bar -->
  <div class="bottom-panel" style="margin-bottom:16px; display:flex; gap:32px; align-items:center;">
    <div>
      <div style="font-size:11px; color:#94a3b8; margin-bottom:2px;">Total Trades</div>
      <div style="font-size:20px; color:#e2e8f0; font-weight:600;">{{ total_trades }}</div>
    </div>
    <div>
      <div style="font-size:11px; color:#94a3b8; margin-bottom:2px;">Open</div>
      <div style="font-size:20px; color:#fbbf24; font-weight:600;">{{ open_count }}</div>
    </div>
    <div>
      <div style="font-size:11px; color:#94a3b8; margin-bottom:2px;">Win Rate</div>
      <div style="font-size:20px; font-weight:600;
        {% if win_rate is not none and win_rate >= 50 %}color:#4ade80;
        {% elif win_rate is not none %}color:#f87171;
        {% else %}color:#64748b;{% endif %}">
        {% if win_rate is not none %}{{ win_rate }}%{% else %}—{% endif %}
      </div>
    </div>
    <div>
      <div style="font-size:11px; color:#94a3b8; margin-bottom:2px;">Avg R</div>
      <div style="font-size:20px; font-weight:600;
        {% if avg_r is not none and avg_r >= 0 %}color:#4ade80;
        {% elif avg_r is not none %}color:#f87171;
        {% else %}color:#64748b;{% endif %}">
        {% if avg_r is not none %}{{ avg_r }}R{% else %}—{% endif %}
      </div>
    </div>
  </div>

  <!-- Trades table -->
  <div class="bottom-panel">
    <div class="panel-title">All Trades (newest first)</div>
    <table style="width:100%; border-collapse:collapse; font-size:12px; color:#cbd5e1;">
      <thead>
        <tr style="color:#94a3b8; border-bottom:1px solid #334155;">
          <th style="padding:6px; text-align:left;">Time</th>
          <th style="padding:6px; text-align:left;">Symbol</th>
          <th style="padding:6px; text-align:left;">Screener</th>
          <th style="padding:6px; text-align:left;">Tag</th>
          <th style="padding:6px; text-align:left;">Regime</th>
          <th style="padding:6px; text-align:right;">Entry</th>
          <th style="padding:6px; text-align:right;">Stop</th>
          <th style="padding:6px; text-align:right;">Qty</th>
          <th style="padding:6px; text-align:right;">Outcome</th>
          <th style="padding:6px; text-align:right;">R</th>
        </tr>
      </thead>
      <tbody>
        {% for t in trades %}
        <tr style="border-bottom:1px solid #1e293b;">
          <td style="padding:6px; color:#94a3b8;">
            {{ t.entry_time[:16] | replace("T", " ") if t.entry_time else "—" }}
          </td>
          <td style="padding:6px; font-weight:600;">{{ t.symbol }}</td>
          <td style="padding:6px; color:#94a3b8;">{{ t.screener | default("—") }}</td>
          <td style="padding:6px;
            {% if t.confidence_tag == 'HIGH_CONVICTION' %}color:#4ade80;
            {% elif t.confidence_tag == 'UNCERTAIN' %}color:#94a3b8;
            {% else %}color:#cbd5e1;{% endif %}">
            {{ t.confidence_tag | default("—") }}
          </td>
          <td style="padding:6px; color:#94a3b8;">{{ t.regime | default("—") }}</td>
          <td style="padding:6px; text-align:right;">${{ t.entry_price }}</td>
          <td style="padding:6px; text-align:right;">${{ t.stop_price }}</td>
          <td style="padding:6px; text-align:right;">{{ t.qty }}</td>
          <td style="padding:6px; text-align:right;
            {% if t.outcome == 'win' %}color:#4ade80;
            {% elif t.outcome == 'loss' %}color:#f87171;
            {% else %}color:#94a3b8;{% endif %}">
            {% if t.outcome == 'win' %}Win
            {% elif t.outcome == 'loss' %}Loss
            {% else %}Open{% endif %}
          </td>
          <td style="padding:6px; text-align:right;
            {% if t.r is not none and t.r >= 0 %}color:#4ade80;
            {% elif t.r is not none %}color:#f87171;
            {% else %}color:#94a3b8;{% endif %}">
            {% if t.r is not none %}{{ t.r }}R{% else %}—{% endif %}
          </td>
        </tr>
        {% else %}
        <tr>
          <td colspan="10" style="padding:12px; color:#64748b; text-align:center;">
            No trades recorded yet.
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

</div>
{% endblock %}
```

- [ ] Replace `templates/trades.html` with the full template above

### Step 2.2 — Add nav link to `templates/base.html`

In `base.html`, find the topbar div (around line 12). Add a "Trades" link after the mode badge:

```html
<a href="/trades" style="font-size:12px; color:#94a3b8; text-decoration:none; margin-left:12px;">Trades</a>
<a href="/stats" style="font-size:12px; color:#94a3b8; text-decoration:none; margin-left:12px;">Stats</a>
```

Read `base.html` first to find the exact insertion point — place both links together after the mode badge `</span>` and before the clock `<div>`.

- [ ] Add nav links to `templates/base.html`

### Step 2.3 — Run the full test suite

- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures

### Step 2.4 — Commit

```bash
git add templates/trades.html templates/base.html main.py
git commit -m "feat: complete trades log UI with summary bar, table, and nav links"
```

- [ ] Commit

---

## Acceptance Criteria

- `GET /trades` returns 200
- Page shows summary bar: total trades, open count, win rate, avg R
- Table shows all trades newest-first with correct color coding
- Empty state shows "No trades recorded yet." when `auto_trades.json` is missing or empty
- Nav links to `/trades` and `/stats` visible on all pages
- `test_trades_route_returns_200` passes
- Full test suite: zero new failures
