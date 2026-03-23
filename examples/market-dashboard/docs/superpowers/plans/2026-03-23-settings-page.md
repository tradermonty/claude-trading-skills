# Settings Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cramped settings modal with a dedicated `/settings` page and add a Home link to all sub-pages.

**Architecture:** Add `GET /settings` route that renders a full-page settings form. `POST /api/settings` saves and redirects to `/settings`. The mode-badge in `base.html` loses its `hx-get` and a Settings nav link is added. The modal and `GET /api/settings` endpoint are removed. A Home link is added to the topbar.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, existing `POST /api/settings` endpoint logic

**Spec:** `docs/superpowers/specs/2026-03-23-multi-market-trading-design.md` (Settings Page section)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `tests/test_routes.py` | Modify | Add `test_settings_route_returns_200` |
| `main.py` | Modify | Add `GET /settings` route; update `POST /api/settings` to redirect; add kelly/vix form params; remove `GET /api/settings` |
| `templates/settings.html` | Create | Full settings page with 5 sections |
| `templates/base.html` | Modify | Add Home + Settings links; remove hx-get from mode-badge; remove modal-container div |

---

## Task 1: Route + test

**Files:**
- Modify: `tests/test_routes.py`
- Modify: `main.py`

### Step 1.1 — Write the failing test

Add to `tests/test_routes.py` after `test_trades_route_returns_200`:

```python
def test_settings_route_returns_200():
    """GET /settings returns 200."""
    client = make_client()
    response = client.get("/settings")
    assert response.status_code == 200
```

- [ ] Add the test
- [ ] Run: `uv run pytest tests/test_routes.py::test_settings_route_returns_200 -v`
- [ ] Expected: **FAIL** with 404

### Step 1.2 — Add `GET /settings` route to `main.py`

Add after the `/trades` route (around line 244). Also update `POST /api/settings` to redirect to `/settings` on success instead of returning modal HTML. Add the missing kelly/vix form params.

**Add GET /settings route** (after the `/trades` route):

```python
@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    ctx = {
        "request": request,
        "market_state": _market_state(),
        "settings": settings_manager.load(),
    }
    return templates.TemplateResponse("settings.html", ctx)
```

**Replace the existing `POST /api/settings` handler** (lines 403–450) with:

```python
@app.post("/api/settings")
async def post_settings(
    request: Request,
    mode: str = Form(...),
    default_risk_pct: float = Form(...),
    max_positions: int = Form(...),
    max_position_size_pct: float = Form(...),
    environment: str = Form(...),
    live_confirm: str = Form(""),
    max_weekly_drawdown_pct: float = Form(10.0),
    max_daily_loss_pct: float = Form(5.0),
    earnings_blackout_days: int = Form(5),
    min_volume_ratio: float = Form(1.5),
    avoid_open_close_minutes: int = Form(30),
    breadth_threshold_pct: float = Form(60.0),
    breadth_size_reduction_pct: float = Form(50.0),
    trailing_stop_enabled: str = Form("true"),
    partial_exit_enabled: str = Form("true"),
    partial_exit_at_r: float = Form(1.0),
    partial_exit_pct: int = Form(50),
    time_stop_days: int = Form(5),
    kelly_sizing_enabled: str = Form("false"),
    kelly_max_multiplier: float = Form(2.0),
    vix_sizing_enabled: str = Form("true"),
):
    from fastapi.responses import RedirectResponse
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
        "max_weekly_drawdown_pct": max_weekly_drawdown_pct,
        "max_daily_loss_pct": max_daily_loss_pct,
        "earnings_blackout_days": earnings_blackout_days,
        "min_volume_ratio": min_volume_ratio,
        "avoid_open_close_minutes": avoid_open_close_minutes,
        "breadth_threshold_pct": breadth_threshold_pct,
        "breadth_size_reduction_pct": breadth_size_reduction_pct,
        "trailing_stop_enabled": trailing_stop_enabled == "true",
        "partial_exit_enabled": partial_exit_enabled == "true",
        "partial_exit_at_r": partial_exit_at_r,
        "partial_exit_pct": partial_exit_pct,
        "time_stop_days": time_stop_days,
        "kelly_sizing_enabled": kelly_sizing_enabled == "true",
        "kelly_max_multiplier": kelly_max_multiplier,
        "vix_sizing_enabled": vix_sizing_enabled == "true",
    })
    return RedirectResponse(url="/settings", status_code=303)
```

**Remove the `GET /api/settings` route** (lines 397–400 — the one that returned the modal fragment). It is no longer needed.

- [ ] Add `GET /settings` route
- [ ] Replace `POST /api/settings` handler
- [ ] Remove `GET /api/settings` route
- [ ] Run: `uv run pytest tests/test_routes.py::test_settings_route_returns_200 -v`
- [ ] Expected: **FAIL** with Jinja2 TemplateNotFound

### Step 1.3 — Create minimal `templates/settings.html` to make test pass

```html
{% extends "base.html" %}
{% block content %}
<div style="padding: 16px;">
  <h2 style="color:#e2e8f0; margin-bottom:16px;">Settings</h2>
  <p style="color:#64748b;">Settings page coming soon.</p>
</div>
{% endblock %}
```

- [ ] Create `templates/settings.html` with stub above
- [ ] Run: `uv run pytest tests/test_routes.py::test_settings_route_returns_200 -v`
- [ ] Expected: **PASS**

### Step 1.4 — Run full suite to check for regressions

- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures beyond pre-existing

### Step 1.5 — Commit

```bash
git add tests/test_routes.py main.py templates/settings.html
git commit -m "feat: add /settings route and migrate POST /api/settings to redirect"
```

- [ ] Commit

---

## Task 2: Full settings template + nav links

**Files:**
- Modify: `templates/settings.html`
- Modify: `templates/base.html`

### Step 2.1 — Replace stub with full settings template

Replace `templates/settings.html` with the complete template below. It contains all settings grouped into 5 cards. The form POSTs to `/api/settings` which redirects back to `/settings` on save. The live trading confirmation is handled by JavaScript exactly as the modal did.

```html
{% extends "base.html" %}
{% block content %}
<div style="padding: 16px; max-width: 700px;">
  <h2 style="color:#e2e8f0; margin-bottom:16px;">⚙️ Settings</h2>

  {% if settings.environment == 'live' and settings.mode == 'auto' %}
  <div style="background:#3a1a1a; border:1px solid #f87171; border-radius:4px; padding:8px; margin-bottom:16px; font-size:11px; color:#f87171;">
    ⚠️ LIVE TRADING + AUTO MODE ACTIVE — red border indicates real money is at risk
  </div>
  {% endif %}

  <form method="post" action="/api/settings" onsubmit="return handleSettingsSubmit(this)">
    <input type="hidden" name="live_confirm" id="live-confirm-input" value="">

    <!-- Section 1: Mode -->
    <div class="bottom-panel" style="margin-bottom:16px;">
      <div class="panel-title">Trading Mode</div>
      <div class="form-row">
        <div class="form-label">Mode</div>
        <select name="mode" class="form-input">
          <option value="advisory" {% if settings.mode == 'advisory' %}selected{% endif %}>Level 1 — Advisory</option>
          <option value="semi_auto" {% if settings.mode == 'semi_auto' %}selected{% endif %}>Level 2 — Semi-Auto</option>
          <option value="auto" {% if settings.mode == 'auto' %}selected{% endif %}>Level 3 — Auto ⚠️</option>
        </select>
      </div>
      <div class="form-row">
        <div class="form-label">Environment</div>
        <select name="environment" class="form-input">
          <option value="paper" {% if settings.environment == 'paper' %}selected{% endif %}>📄 Paper Trading</option>
          <option value="live" {% if settings.environment == 'live' %}selected{% endif %}>💰 Live Trading</option>
        </select>
        {% if settings.environment == 'paper' %}
        <div style="font-size:10px; color:#4ade80; margin-top:4px;">Switching to Live requires typing CONFIRM LIVE TRADING</div>
        {% endif %}
      </div>
    </div>

    <!-- Section 2: Risk -->
    <div class="bottom-panel" style="margin-bottom:16px;">
      <div class="panel-title">Risk</div>
      <div class="form-row">
        <div class="form-label">Default Risk % per Trade</div>
        <input type="number" name="default_risk_pct" class="form-input"
               value="{{ settings.default_risk_pct }}" min="0.1" max="5.0" step="0.1">
      </div>
      <div class="form-row">
        <div class="form-label">Max Open Positions</div>
        <input type="number" name="max_positions" class="form-input"
               value="{{ settings.max_positions }}" min="1" max="20">
      </div>
      <div class="form-row">
        <div class="form-label">Max Position Size (% of account)</div>
        <input type="number" name="max_position_size_pct" class="form-input"
               value="{{ settings.max_position_size_pct }}" min="1" max="50" step="0.5">
      </div>
    </div>

    <!-- Section 3: Guard Rails -->
    <div class="bottom-panel" style="margin-bottom:16px;">
      <div class="panel-title">Guard Rails</div>
      <div class="form-row">
        <div class="form-label">Max Weekly Drawdown % (100 = off)</div>
        <input type="number" name="max_weekly_drawdown_pct" class="form-input"
               value="{{ settings.max_weekly_drawdown_pct }}" min="1" max="100" step="0.5">
      </div>
      <div class="form-row">
        <div class="form-label">Max Daily Loss % (100 = off)</div>
        <input type="number" name="max_daily_loss_pct" class="form-input"
               value="{{ settings.max_daily_loss_pct }}" min="1" max="100" step="0.5">
      </div>
      <div class="form-row">
        <div class="form-label">Earnings Blackout Days (0 = off)</div>
        <input type="number" name="earnings_blackout_days" class="form-input"
               value="{{ settings.earnings_blackout_days }}" min="0" max="30">
      </div>
      <div class="form-row">
        <div class="form-label">Min Volume Ratio (× 20d avg, 0 = off)</div>
        <input type="number" name="min_volume_ratio" class="form-input"
               value="{{ settings.min_volume_ratio }}" min="0" max="5" step="0.1">
      </div>
      <div class="form-row">
        <div class="form-label">Avoid Open/Close (minutes, 0 = off)</div>
        <input type="number" name="avoid_open_close_minutes" class="form-input"
               value="{{ settings.avoid_open_close_minutes }}" min="0" max="60" step="5">
      </div>
      <div class="form-row">
        <div class="form-label">Breadth Threshold (% above 50MA)</div>
        <input type="number" name="breadth_threshold_pct" class="form-input"
               value="{{ settings.breadth_threshold_pct }}" min="0" max="100" step="5">
      </div>
      <div class="form-row">
        <div class="form-label">Breadth Size Reduction (%, 0 = off)</div>
        <input type="number" name="breadth_size_reduction_pct" class="form-input"
               value="{{ settings.breadth_size_reduction_pct }}" min="0" max="100" step="5">
      </div>
    </div>

    <!-- Section 4: Exit Management -->
    <div class="bottom-panel" style="margin-bottom:16px;">
      <div class="panel-title">Exit Management</div>
      <div class="form-row">
        <div class="form-label">Trailing Stop</div>
        <select name="trailing_stop_enabled" class="form-input">
          <option value="true" {% if settings.trailing_stop_enabled %}selected{% endif %}>Enabled</option>
          <option value="false" {% if not settings.trailing_stop_enabled %}selected{% endif %}>Disabled</option>
        </select>
      </div>
      <div class="form-row">
        <div class="form-label">Partial Exit</div>
        <select name="partial_exit_enabled" class="form-input">
          <option value="true" {% if settings.partial_exit_enabled %}selected{% endif %}>Enabled</option>
          <option value="false" {% if not settings.partial_exit_enabled %}selected{% endif %}>Disabled</option>
        </select>
      </div>
      <div class="form-row">
        <div class="form-label">Partial Exit at R</div>
        <input type="number" name="partial_exit_at_r" class="form-input"
               value="{{ settings.partial_exit_at_r }}" min="0.5" max="3.0" step="0.25">
      </div>
      <div class="form-row">
        <div class="form-label">Partial Exit Size (%)</div>
        <input type="number" name="partial_exit_pct" class="form-input"
               value="{{ settings.partial_exit_pct }}" min="10" max="90" step="5">
      </div>
      <div class="form-row">
        <div class="form-label">Time Stop (days, 0 = off)</div>
        <input type="number" name="time_stop_days" class="form-input"
               value="{{ settings.time_stop_days }}" min="0" max="30">
      </div>
    </div>

    <!-- Section 5: Smart Sizing -->
    <div class="bottom-panel" style="margin-bottom:16px;">
      <div class="panel-title">Smart Sizing</div>
      <div class="form-row">
        <div class="form-label">Kelly Sizing</div>
        <select name="kelly_sizing_enabled" class="form-input">
          <option value="false" {% if not settings.kelly_sizing_enabled %}selected{% endif %}>Disabled (recommended until 20+ trades)</option>
          <option value="true" {% if settings.kelly_sizing_enabled %}selected{% endif %}>Enabled</option>
        </select>
      </div>
      <div class="form-row">
        <div class="form-label">Kelly Max Multiplier</div>
        <input type="number" name="kelly_max_multiplier" class="form-input"
               value="{{ settings.kelly_max_multiplier }}" min="0.5" max="5.0" step="0.5">
      </div>
      <div class="form-row">
        <div class="form-label">VIX-Based Sizing</div>
        <select name="vix_sizing_enabled" class="form-input">
          <option value="true" {% if settings.vix_sizing_enabled %}selected{% endif %}>Enabled</option>
          <option value="false" {% if not settings.vix_sizing_enabled %}selected{% endif %}>Disabled</option>
        </select>
      </div>
    </div>

    <div style="display:flex; gap:8px; margin-top:8px;">
      <button type="submit" class="btn-primary">Save Settings</button>
    </div>
  </form>
</div>

<script>
function handleSettingsSubmit(form) {
  var mode = form.querySelector('[name=mode]').value;
  var env = form.querySelector('[name=environment]').value;

  if (mode === 'auto') {
    var ok = confirm(
      'Enable Level 3 Auto Trading?\n\n' +
      'The bot will place bracket orders automatically when VCP pivot ' +
      'breakouts are detected.\n\n' +
      'Recommended: test on Paper first. Click OK to enable Auto mode.'
    );
    if (!ok) return false;
  }

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
{% endblock %}
```

- [ ] Replace `templates/settings.html` with full template above

### Step 2.2 — Update `templates/base.html`

Make these three changes to `base.html`:

**1. Replace the mode-badge span** (currently has `hx-get="/api/settings"`) with a plain span (no HTMX):

Old:
```html
    <span class="mode-badge"
          hx-get="/api/settings"
          hx-target="#modal-container"
          hx-swap="innerHTML">
      {% if settings.mode == 'auto' %}🤖 Auto
      {% elif settings.mode == 'semi_auto' %}✅ Semi-Auto
      {% else %}👁 Advisory{% endif %}
    </span>
```

New:
```html
    <span class="mode-badge">
      {% if settings.mode == 'auto' %}🤖 Auto
      {% elif settings.mode == 'semi_auto' %}✅ Semi-Auto
      {% else %}👁 Advisory{% endif %}
    </span>
```

**2. Add Home and Settings links** after the mode-badge and before the existing Trades link:

```html
    <a href="/" style="font-size:12px; color:#94a3b8; text-decoration:none; margin-left:12px;">Home</a>
    <a href="/settings" style="font-size:12px; color:#94a3b8; text-decoration:none; margin-left:12px;">Settings</a>
```

**3. Remove the modal-container div** at the bottom of the body (line 70):

Old:
```html
  <!-- Modal container (settings modal appears here) -->
  <div id="modal-container"></div>
```

New: delete these two lines entirely.

- [ ] Apply all three changes to `templates/base.html`

### Step 2.3 — Run full suite

- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures

### Step 2.4 — Commit

```bash
git add templates/settings.html templates/base.html
git commit -m "feat: full settings page with 5 sections and Home/Settings nav links"
```

- [ ] Commit

---

## Acceptance Criteria

- `GET /settings` returns 200
- Page shows 5 sections: Mode, Risk, Guard Rails, Exit Management, Smart Sizing
- Saving settings redirects back to `/settings`
- Live trading confirmation prompt still works
- Kelly and VIX sizing settings appear on the page (were missing from the old modal)
- Home link visible on all pages (/, /trades, /stats, /settings)
- Settings link visible on all pages
- No modal-container div in the DOM
- `test_settings_route_returns_200` passes
- Full test suite: zero new failures
