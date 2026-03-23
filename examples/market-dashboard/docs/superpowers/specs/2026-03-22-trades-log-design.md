# Trade Log Page — Design Spec

**Date:** 2026-03-22

## Goal

Add a `/trades` page to the market dashboard that displays all auto trades recorded in `cache/auto_trades.json`, giving the user a readable audit trail of what the bot has done.

## Context

The auto trading infrastructure is fully built: `_fire_order()` places real bracket orders, the scheduler gates on `mode == "auto"`, and all 5-tier guard rails protect every order. Every order is logged to `cache/auto_trades.json` after placement. Currently there is no UI to view this data.

## What Gets Built

### Route

`GET /trades` — reads `cache/auto_trades.json`, passes trades to a Jinja2 template, returns HTML.

### Page Sections

**1. Summary bar** (top of page)
- Total trades
- Open positions (outcome is null)
- Win rate (closed trades only, wins / total closed)
- Average R achieved (closed trades only)

**2. Trades table** (one row per trade, newest first)

| Column | Source field | Notes |
|--------|-------------|-------|
| Time | `entry_time` | Format: `YYYY-MM-DD HH:MM` |
| Symbol | `symbol` | |
| Screener | `screener` | e.g. `vcp` |
| Tag | `confidence_tag` | HIGH_CONVICTION / CLEAR / UNCERTAIN |
| Regime | `regime` | |
| Entry | `entry_price` | |
| Stop | `stop_price` | |
| Qty | `qty` | |
| Outcome | `outcome` | Color: green=win, red=loss, grey=open |
| R | Computed: `(exit_price - entry_price) / (entry_price - stop_price)` | Long-only system; only for closed trades with `exit_price` present; show `—` otherwise |

Real trade objects contain additional fields (`pivot_price`, `risk_pct`, `market_top_score`, `breadth_score`, `ftd_score`, `partial_exit_done`, `trailing_stop_level`) that are not displayed in the table — they are safely ignored by the template.

### Styling

- Dark theme matching existing dashboard (`base.html`, same card/table style as `stats.html`)
- Outcome column: green for win, red for loss, grey/italic for open
- Positive R: green. Negative R: red.
- Empty state: "No trades recorded yet." if file is missing or empty.
- Graceful handling: if `auto_trades.json` is missing or corrupt, show empty state (never 500 error).

## Data Source

`cache/auto_trades.json` — written by `pivot_monitor._log_trade()` and `main._log_manual_trade()`. Structure:

```json
{
  "trades": [
    {
      "symbol": "AAPL",
      "order_id": "abc123",
      "entry_time": "2026-03-22T14:30:00",
      "entry_price": 150.0,
      "stop_price": 145.5,
      "qty": 10,
      "confidence_tag": "CLEAR",
      "regime": "bull",
      "outcome": "win",
      "exit_price": 159.0
    }
  ]
}
```

`outcome` is null for open trades. `exit_price` is present only for closed trades.

## Files

| File | Action |
|------|--------|
| `main.py` | Add `GET /trades` route |
| `templates/trades.html` | Create page template — extends `base.html` |
| `templates/base.html` | Add "Trades" nav link pointing to `/trades` |
| `tests/test_routes.py` | Add `test_trades_route_returns_200` |

## Error Handling

- Missing `auto_trades.json`: show empty state, no error
- Corrupt JSON: show empty state, no error
- Missing `exit_price` on closed trade: skip R calculation, show `—`

## Out of Scope

- Filtering or sorting trades in the UI
- Pagination (acceptable for now — dashboard is single-user)
- Push notifications for new trades
- Manual trade entry from this page
