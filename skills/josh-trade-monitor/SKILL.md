---
name: josh-trade-monitor
description: Monitor one or more Stocks-With-Josh leaderboard traders and report trades that are new since the last run. Use when the user wants to track stockswithjosh.com leaderboard traders, get alerted to new signals/entries, watch for positions closing, or poll the leaderboard API on a schedule. Accepts multiple --target traders (id, id:period, or leaderboard URL); fetches each trader's trades endpoint, diffs against per-target saved state, and reports new entries plus positions closed since last run.
---

# Josh Trade Monitor

## Overview

Poll a single trader's feed on `leaderboard.stockswithjosh.com` and report only what
changed since the last run: newly posted trade signals and positions that closed. State
is a monotonic max-seen trade id plus the set of currently-open ids, so the local file
stays tiny no matter how much history accumulates.

Informational only — this mirrors the leaderboard's last completed fetch and is not
investment advice. Open trades carry `UNKNOWN` P&L until the trader closes them.

## When to Use

- User wants to track / follow a specific stockswithjosh.com leaderboard trader
- User asks "any new trades from Josh?" or wants alerts on new entries or closes
- Running on a schedule (cron) to surface new signals as they post

## Prerequisites

- Python 3.9+, standard library only (no third-party packages)
- A **session cookie** — the API returns `401` without one. Copy the `Cookie` header from
  a logged-in browser request to the leaderboard and set it as `JOSH_COOKIE`:
  ```bash
  export JOSH_COOKIE='olens_session=...; connect.sid=...'
  ```
  or add a `JOSH_COOKIE=...` line to a git-ignored `./.env`, or pass `--cookie`.
  Cookies expire; on `401` the script tells you to refresh it. **Never commit the cookie**
  — it is a live credential.

## Targets & Config

Which traders to watch comes from (in precedence order): explicit `--target` flags → a
`--targets-file` → the bundled **`config/targets.txt`** → trader `29`. To add traders long
term, just edit `config/targets.txt` (one per line — `id`, `id:period`, or a leaderboard URL;
`#` comments and blank lines ignored) — no command change, so a cron/routine keeps working as
you grow the list:

```
# skills/josh-trade-monitor/config/targets.txt
29:this_week
https://leaderboard.stockswithjosh.com/leaderboard/traders/13?period=all_time
```

## Workflow

First run per target records a baseline silently (does not flood you with the existing
history); every run after reports only the delta. Each target keeps its own state + events
file, so traders never mix.

```bash
# uses config/targets.txt (or trader 29 if the file is absent)
python3 skills/josh-trade-monitor/scripts/monitor_josh_trades.py

# override for a one-off — bare id, id:period, or a leaderboard URL (web or /api/…)
python3 skills/josh-trade-monitor/scripts/monitor_josh_trades.py \
  --target 29:this_week \
  --target "https://leaderboard.stockswithjosh.com/leaderboard/traders/13?period=all_time"

# a different targets file, or offline replay of one saved response (single target)
python3 skills/josh-trade-monitor/scripts/monitor_josh_trades.py --targets-file my_traders.txt
python3 skills/josh-trade-monitor/scripts/monitor_josh_trades.py --target 29 --fixture response.json
```

To monitor continuously, wrap in cron / `watch` (e.g. every 5 min during market hours):
```bash
*/5 9-16 * * 1-5 cd /path/to/repo && \
  python3 skills/josh-trade-monitor/scripts/monitor_josh_trades.py --target 29 --target 13:all_time \
    >> logs/josh.log 2>&1
```

## Output

Per target (files keyed by `trader_<id>_<period>`):

- **stdout:** human text (one section per target), or the JSON event contract with
  `--format json` (a single object for one target, an array for several).
- **State file** (`<state-dir>/trader_<id>_<period>.json`, default state-dir
  `state/josh-trade-monitor/`): `max_seen_id`, `open_positions` (full detail of each
  currently-open trade — ticker, direction, strike/strike_price, expiration, entry), and
  `last_run`. (Legacy `open_ids` state files are still read.)
- **Event contract file** (`<state-file-stem>_events.json`, always written): the
  machine-readable state change for a downstream executor — see below.
- **Markdown report** written to `reports/` (via `--output-dir`) only when there is
  something new — no empty-run clutter.

## Event Contract (for a downstream execution skill)

Every run writes `<state>_events.json` and, with `--format json`, prints the same object.
This is the interface an execution skill consumes to open/close positions:

```json
{
  "generated_at": "2026-07-12T02:02:16+00:00",
  "trader_id": 29, "period": "this_week", "trader": "Turbo Trader Guppy",
  "events": [
    {"action": "open",  "trade_id": 631, "ticker": "AMD", "instrument": "option",
     "direction": "call", "strike": "180 CALL", "strike_price": 180.0,
     "expiration": "2026-07-17", "entry_price": 2.1, "exit_price": null,
     "pnl_percent": null, "result": "UNKNOWN", "status": "open",
     "signal_time": "...", "closed_at": null},
    {"action": "close", "trade_id": 629, "ticker": "SKHYV", "instrument": "equity",
     "direction": "long", "strike": null, "exit_price": 185.0, "pnl_percent": 8.82,
     "result": "WIN", "status": "closed", ...}
  ]
}
```

- `action`: `open` → the trader posted a new signal (open a position); `close` → a
  position the trader closed (close ours).
- `instrument`: `option` (call/put, has a strike) or `equity` (the trader's `long`).
- **Emit-once guarantee:** each `trade_id` emits `open` **exactly once** and `close`
  **at most once** across the monitor's entire run history. A chained executor
  (executor runs right after each monitor run) therefore never double-acts.
- **First run emits `events: []`** (baseline) — the executor will *not* try to open the
  trader's pre-existing 20+ historical positions. Mirroring already-open positions is a
  deliberate, separate action.
- If the executor is **decoupled** (re-reads the same file without a monitor run between),
  it must dedup on `(trade_id, action)` itself, since re-reading a stale file would
  re-present the same events.

### Handoff pattern

Chain the monitor into an execution skill (`robinhood-trade-executor`, `portfolio-manager`
via Alpaca, or a purpose-built one). The execution skill reads `events[]`, maps `open`/
`close` + `instrument` to broker orders, and is responsible for position sizing and its
own idempotency. This monitor deliberately does **not** place orders — it only reports the
state change. Not investment advice; sizing, risk, and tradability checks are the
executor's job.

## Key Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--target` | config file | Repeatable: `id`, `id:period`, or a leaderboard URL; overrides the file |
| `--targets-file` | `config/targets.txt` | File of targets, one per line (`#` comments ok) |
| `--period` | `this_week` | Default period for bare ids/URLs without one |
| `--cookie` | — | Session cookie (prefer `JOSH_COOKIE` env / `.env`) |
| `--state-dir` | `state/josh-trade-monitor` | Per-target state/events dir |
| `--format` | `text` | `text` (human) or `json` (event contract to stdout) |
| `--output-dir` | `reports` | Markdown report dir (only written when there's news) |
| `--fixture` | — | Read one response from a JSON file (requires a single `--target`) |

## Notes & Limits

- "New" = trade id strictly greater than the highest id seen previously (ids are
  monotonic on the API). A trade that leaves the `this_week` window while still open is
  dropped silently rather than reported as a close.
- Deltas are only as fresh as your polling cadence; the endpoint itself reflects the
  trader's last completed activity.

## Resources

- `scripts/monitor_josh_trades.py` — fetch + diff + report
- `scripts/tests/test_monitor.py` — offline diff-logic checks
