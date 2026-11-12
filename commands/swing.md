---
description: Swing Opportunity Daily — screen, validate, size, journal, discipline gate
argument-hint: "[EU/US tickers to evaluate in addition to screening; always ranked against other candidates]"
---

# Swing Opportunity Daily

Run the `swing-opportunity-daily` workflow. The canonical definition is `workflows/swing-opportunity-daily.yaml` — read it first and follow its steps, decision gates, and manual_review items exactly. Stop at any failed gate and say why.

Prerequisite: check `reports/` for today's market-regime / exposure-coach output. If missing, run `/regime` first. If the decision is restrict or cash-priority, do not stop: show the warning from the workflow's `when_not_to_run` at the top of the output (breakouts fail more often, sizing ignores the exposure ceiling, losses cluster), then continue. In step 10, `pre-trade-discipline-gate` returns REVIEW_REQUIRED for every candidate until it has `regime_override_confirmed: true`: ask the user for that extra confirmation per candidate (restate the warning and suggest a smaller size), set it only for candidates they explicitly confirm, and rerun the gate. Unconfirmed candidates stay watchlist-only.

Steps (invoke each skill via the Skill tool):
1. `drawdown-circuit-breaker` using `state/theses/` — must be TRADING_ALLOWED
2. `vcp-screener` (US only) — run a fresh full-universe screen in this run, even when tickers are given. Do not reuse an earlier run from today that used a custom or partial universe
3. Optional: `stockbee-momentum-burst-screener`, `stockbee-exhaustion-hammer-screener`, `canslim-screener`, `theme-detector` — run only if the VCP list is thin
4. Build the candidate pool from three sources:
   - screener output from steps 2–3
   - tickers in `$ARGUMENTS` (e.g. AAPL, RHM.DE): they skip the screener filters but are never evaluated alone; fetch EU names' data and earnings dates via yfinance
   - active setups with a pending trigger from `state/watchlist.md`, IDEA/ENTRY_READY theses in `state/theses/`, and saved watch plans from earlier sessions (e.g. a triangle breakout waiting for a close above its ceiling)

   Names that fail the Stage 2 trend template (post-earnings bases, range or triangle breakouts below a falling 200-day MA) stay in the pool, labeled as a different setup type instead of being dropped silently
5. `technical-analyst` — weekly-chart validation of every pool candidate; reject unclear setups. Also run its Catalyst & Event Check: search news for any gap or 2%+ candle (check publication dates against the move) and flag any candidate with earnings inside the planned holding period
6. **Candidate comparison** — before sizing anything, show a ranked table of all candidates that passed step 5 (or are one trigger away from passing): ticker, setup type, trigger status (fired / pending, with the level), reward:risk to the first target, stop distance %, relative strength vs SPY (3m and 6m), breakout volume vs 50-day average, regime fit, and overlap with open positions (same sector or factor, e.g. two mega-cap tech longs). Recommend the best one or two and say in one line why each ranks where it does. If a named ticker ranks below another candidate, say so plainly. Carry on with sizing only for the candidates the user picks
7. `position-sizer` — account size from `state/portfolio.md`, 1% risk default
8. `breakout-trade-planner` for entry/stop/target and portfolio heat
9. `trader-memory-core` — register each surviving thesis in `state/theses/`
10. `pre-trade-discipline-gate` — only GO candidates are actionable; on restrict/cash-priority days a GO requires the user's per-candidate `regime_override_confirmed: true`, and the order table must repeat the bold **WARNING**

Broker adjustments (Trade Republic):
- No OCO/bracket orders: translate any Alpaca templates into "stop-loss order + price alert at target, swap to limit when alert fires"
- 1 € per executed order: show fees as % of planned risk; flag trades where round-trip fees exceed ~3% of risk

End with a table of GO candidates: ticker, entry, stop, target, shares, risk €, fees, and the exact Trade Republic orders to place. All orders are placed manually.

Then list the reports from this run, one line per report, with the `.md` and `.html` links side by side as clickable local paths, e.g. `VCP: [md](reports/<file>.md) · [html](reports/<file>.html)`. Never replace a link with a note like "HTML version alongside"; a report with no HTML gets only its `.md` link.
