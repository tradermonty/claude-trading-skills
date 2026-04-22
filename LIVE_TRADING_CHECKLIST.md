# LIVE TRADING CHECKLIST

> **Purpose:** This document is the hard gate between paper trading and real money.
> The orchestrator will refuse to flip `global.mode: live` in
> `config/trading_params.yaml` unless this file exists, every item is signed off,
> and the signature block at the bottom is filled in.
>
> **Default posture:** Paper only. `global.mode: paper`, `global.dry_run: true`.
> You should spend at least **30 consecutive trading days on paper** with a positive
> Sharpe, sub-5% max drawdown, and a passing EOD reconciliation every day before
> even considering promotion to live.

---

## Pre-deployment (one-time setup)

### Environment & credentials

- [ ] Python 3.10+ installed, `requests`, `pyyaml`, `pandas` available on system PATH
- [ ] `.envrc` committed only to local machine (listed in `.gitignore`)
- [ ] `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` set in `.envrc`
- [ ] `ALPACA_PAPER=true` set in `.envrc` (flip to `false` only when live-ready)
- [ ] `FRED_API_KEY=f2fd0f502d9d12b46d3a5c183dee9160` set in `.envrc`
- [ ] `FMP_API_KEY` set in `.envrc` (required by screeners)
- [ ] `direnv allow` run in project root, `echo $ALPACA_API_KEY` returns the key

### Config sanity

- [ ] `config/trading_params.yaml` `active_profile` is `ray_custom` (or another signed-off profile)
- [ ] `account_size_usd` matches the real Alpaca balance (±$1,000 tolerance)
- [ ] `risk_per_trade_pct` ≤ 2.0
- [ ] `max_daily_loss_pct` ≤ 5.0
- [ ] `max_positions` ≤ 6
- [ ] `max_sector_exposure_pct` ≤ 25
- [ ] `max_position_size_pct` ≤ 20
- [ ] `config/screener_weights.yaml` enabled screeners match what you intend to trade
- [ ] `config/sector_map.yaml` covers every ticker in your screener universes
- [ ] `YOLO_DO_NOT_USE` profile is still present as a safety marker

### Test suite

Run from the repo root:

```bash
python3 -m pytest skills/ scripts/ -q
```

- [ ] All skill-level tests pass (no failures, no errors)
- [ ] `skills/trade-loop-orchestrator/scripts/tests/` (38 tests) pass
- [ ] `skills/kill-switch/scripts/tests/` pass
- [ ] `skills/alpaca-executor/scripts/tests/` pass
- [ ] `skills/eod-reconciliation/scripts/tests/` pass
- [ ] `skills/paper-replay-harness/scripts/tests/` (31 tests) pass
- [ ] `skills/relative-strength-momentum-scanner/scripts/tests/` (35 tests) pass

### Paper-replay smoke test

- [ ] Run `paper-replay-harness` over at least 30 recent historical days
- [ ] Replay equity curve final drawdown < 10%
- [ ] Replay Sharpe > 0.5
- [ ] Replay win rate > 30% and avg R > 1.0 on closed trades
- [ ] No exceptions in replay stderr (run with `2>&1 | tee logs/replay.log`)

---

## Installation (launchd agents)

Install order matters — SOD must be in place before kill-switch fires.

From the repo root:

```bash
# 1. Substitute paths in plists and copy to LaunchAgents
for f in launchd/com.trade-analysis.sod-capture.plist \
         launchd/com.trade-analysis.kill-switch.plist \
         launchd/com.trade-analysis.trade-loop.plist \
         launchd/com.trade-analysis.eod-reconcile.plist \
         launchd/com.trade-analysis.macro-refresh.plist; do
  out="$HOME/Library/LaunchAgents/$(basename $f)"
  sed "s|\$HOME|$HOME|g; s|\$PROJECT_DIR|$(pwd)|g" "$f" > "$out"
done

# 2. Load all agents
for label in sod-capture kill-switch trade-loop eod-reconcile macro-refresh; do
  launchctl load "$HOME/Library/LaunchAgents/com.trade-analysis.${label}.plist"
done

# 3. Verify
launchctl list | grep trade-analysis
```

Expected schedule (Mac local time, assumed ET):

| Agent | Schedule | Purpose |
|---|---|---|
| `macro-refresh` | 07:00 weekday | Fetch FRED, recompute regime |
| `sod-capture` | 09:20 weekday | Snapshot Alpaca equity baseline |
| `kill-switch` | every 2 min weekday | Enforce drawdown / position limits (gate 09:30-16:00 ET) |
| `trade-loop` | every 5 min weekday | Score + rank + submit bracket orders (gate 09:45-15:45 ET) |
| `eod-reconcile` | 16:30 weekday | Fills → P&L → thesis postmortems |

Install checks:

- [ ] `launchctl list | grep trade-analysis` shows all 5 labels
- [ ] Each plist `/Users/<you>/Library/LaunchAgents/` file exists
- [ ] `logs/` directory exists and is writable
- [ ] `state/` directory exists and is writable
- [ ] Manually run each wrapper with `bash scripts/run_*.sh` to confirm no errors

---

## Daily operator checklist (premarket, before 09:30 ET)

- [ ] Mac is awake (check `pmset -g` if unsure) and plugged in
- [ ] No macOS updates pending that require reboot
- [ ] Internet connection confirmed (`curl -I https://paper-api.alpaca.markets/v2/clock`)
- [ ] Yesterday's `logs/launchd_eod_reconcile.log` shows a clean EOD run
- [ ] Yesterday's `reports/eod/` has a markdown + JSON file
- [ ] No open `URGENT` items in trader-memory-core review queue
- [ ] No pending macOS code-sign / quarantine dialogs for python3 / launchd
- [ ] `tail -n 50 logs/launchd_sod_capture_error.log` is empty / from prior OK run
- [ ] FOMC / CPI / NFP on today's calendar — if yes, consider disabling trade-loop for the day:
  `launchctl unload ~/Library/LaunchAgents/com.trade-analysis.trade-loop.plist`

---

## Daily operator checklist (midday spot check, ~12:00 ET)

- [ ] `state/kill_switch_status.json` exists and `status` is `OK` or `WARN`
  (if `TRIPPED`: stop, investigate, do not reset without reading the audit log)
- [ ] `tail -n 20 logs/launchd_trade_loop.log` — no Python tracebacks
- [ ] `tail -n 20 logs/launchd_kill_switch_error.log` — no stack traces
- [ ] Alpaca dashboard matches `state/loop/latest_decisions.json` for open positions

---

## Daily operator checklist (post-close, 17:00 ET)

- [ ] `reports/eod/eod_<today>.md` exists
- [ ] Day's closed trades match expected R-multiples (spot check 3 random trades)
- [ ] Attribution P&L in EOD report reconciles with Alpaca account activity (±$5)
- [ ] No kill-switch trips today, OR if there were, the root cause is understood
- [ ] If any trade-loop iteration failed, issue is diagnosed before market open tomorrow

---

## Emergency procedures

### Immediate flatten (manual kill switch)

```bash
python3 skills/alpaca-executor/scripts/flatten_all.py \
    --reason "manual_operator_intervention" \
    --yes
```

Then:

```bash
launchctl unload ~/Library/LaunchAgents/com.trade-analysis.trade-loop.plist
```

### Suspend the entire stack (market holiday, travel, system maintenance)

```bash
for label in trade-loop kill-switch sod-capture eod-reconcile macro-refresh; do
  launchctl unload "$HOME/Library/LaunchAgents/com.trade-analysis.${label}.plist"
done
```

Re-enable with `launchctl load ...` in the reverse order (macro-refresh → eod-reconcile → sod-capture → kill-switch → trade-loop).

### Reset a kill-switch trip (only after root-cause analysis)

```bash
python3 skills/kill-switch/scripts/reset.py \
    --reason "investigated_drawdown_cause_resolved" \
    --yes
```

---

## Paper → Live promotion gate

**Do not sign this section until you have met every condition.** Each gate is a hard
requirement — no substitutions, no "close enough."

### Minimum paper track record

- [ ] Paper mode active for **≥ 30 consecutive trading days**
- [ ] No kill-switch hard trips in the last 10 trading days
- [ ] EOD reconciliation passed every day with diff ≤ $5 vs Alpaca
- [ ] At least 20 closed trades
- [ ] Paper Sharpe (daily) > 0.5
- [ ] Paper max drawdown < 5% of starting equity
- [ ] Paper win rate × avg-R > 0.15 (positive expectancy after costs)

### Operational readiness

- [ ] Operator (Raymond) has personally responded to 2+ real kill-switch trips in paper
- [ ] Operator has walked through the emergency flatten once under non-emergency conditions
- [ ] Phone notifications set up for `launchd_*_error.log` growth (e.g. via `launchd` + `osascript notification`)
- [ ] Spouse/trusted contact knows the emergency flatten command and has a laminated copy

### Size transition plan

Even after every box above is checked, promote gradually:

- [ ] Week 1 of live: `risk_per_trade_pct: 0.25`, `max_positions: 2`
- [ ] Week 2: `risk_per_trade_pct: 0.5`, `max_positions: 3`
- [ ] Week 3: `risk_per_trade_pct: 1.0`, `max_positions: 4`
- [ ] Week 4+: Full `ray_custom` profile only after 15+ live days with zero operational incidents

---

## Signatures

By signing this section I confirm that:
1. Every checkbox in the **Pre-deployment**, **Installation**, and **Paper → Live promotion gate**
   sections above is checked with my initials.
2. I understand this system can and will lose money.
3. I have read every SKILL.md under `skills/` for the automated-trader stack
   (alpaca-executor, kill-switch, trade-loop-orchestrator, eod-reconciliation,
   paper-replay-harness, macro-indicator-dashboard, relative-strength-momentum-scanner).
4. I am not signing this while tired, intoxicated, or under time pressure.

| Role | Name | Date | Paper-start date | Live-start date | Signature |
|------|------|------|------------------|-----------------|-----------|
| Operator | | | | | |
| Reviewer (optional) | | | | | |

---

**Current status:** PAPER ONLY. Do not modify `config/trading_params.yaml` to
`global.mode: live` until this signature block is filled in with real dates.
