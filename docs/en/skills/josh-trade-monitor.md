---
layout: default
title: "Josh Trade Monitor"
grand_parent: English
parent: Skill Guides
nav_order: 37
lang_peer: /ja/skills/josh-trade-monitor/
permalink: /en/skills/josh-trade-monitor/
generated: true
---

# Josh Trade Monitor
{: .no_toc }

Monitor one or more Stocks-With-Josh leaderboard traders and report trades that are new since the last run. Use when the user wants to track stockswithjosh.com leaderboard traders, get alerted to new signals/entries, watch for positions closing, or poll the leaderboard API on a schedule. Accepts multiple --target traders (id, id:period, or leaderboard URL); fetches each trader's trades endpoint, diffs against per-target saved state, and reports new entries plus positions closed since last run.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/josh-trade-monitor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/josh-trade-monitor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Poll a single trader's feed on `leaderboard.stockswithjosh.com` and report only what
changed since the last run: newly posted trade signals and positions that closed. State
is a monotonic max-seen trade id plus the set of currently-open ids, so the local file
stays tiny no matter how much history accumulates.

Informational only — this mirrors the leaderboard's last completed fetch and is not
investment advice. Open trades carry `UNKNOWN` P&L until the trader closes them.

---

## 2. When to Use

- User wants to track / follow a specific stockswithjosh.com leaderboard trader
- User asks "any new trades from Josh?" or wants alerts on new entries or closes
- Running on a schedule (cron) to surface new signals as they post

---

## 3. Prerequisites

- Python 3.9+, standard library only (no third-party packages)
- A **session cookie** — the API returns `401` without one. Copy the `Cookie` header from
  a logged-in browser request to the leaderboard and set it as `JOSH_COOKIE`:
  ```bash
  export JOSH_COOKIE='olens_session=...; connect.sid=...'
  ```
  or add a `JOSH_COOKIE=...` line to a git-ignored `./.env`, or pass `--cookie`.
  Cookies expire; on `401` the script tells you to refresh it. **Never commit the cookie**
  — it is a live credential.

---

## 4. Quick Start

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

---

## 5. Workflow

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

---

## 6. Resources

**Scripts:**

- `skills/josh-trade-monitor/scripts/monitor_josh_trades.py`
