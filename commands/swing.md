---
description: Swing Opportunity Daily — screen, validate, size, journal, discipline gate
argument-hint: "[EU/US tickers to evaluate instead of / in addition to screening]"
---

# Swing Opportunity Daily

Run the `swing-opportunity-daily` workflow. The canonical definition is `workflows/swing-opportunity-daily.yaml` — read it first and follow its steps, decision gates, and manual_review items exactly. Stop at any failed gate and say why.

Prerequisite: check `reports/` for today's market-regime / exposure-coach output. If missing, run `/regime` first. If the decision is restrict or cash-priority, do not stop: show the warning from the workflow's `when_not_to_run` at the top of the output (breakouts fail more often, sizing ignores the exposure ceiling, losses cluster), then continue. In step 9, `pre-trade-discipline-gate` returns REVIEW_REQUIRED for every candidate until it has `regime_override_confirmed: true`: ask the user for that extra confirmation per candidate (restate the warning and suggest a smaller size), set it only for candidates they explicitly confirm, and rerun the gate. Unconfirmed candidates stay watchlist-only.

Steps (invoke each skill via the Skill tool):
1. `drawdown-circuit-breaker` using `state/theses/` — must be TRADING_ALLOWED
2. `vcp-screener` (US only — FMP plan is US-only)
3. Optional: `stockbee-momentum-burst-screener`, `stockbee-exhaustion-hammer-screener`, `canslim-screener`, `theme-detector` — run only if the VCP list is thin
4. Tickers in `$ARGUMENTS` (e.g. EU names like RHM.DE) skip screening and go straight to step 5; fetch their data and earnings dates via yfinance
5. `technical-analyst` — weekly-chart validation; reject unclear setups. Also run its Catalyst & Event Check: search news for any gap or 2%+ candle (check publication dates against the move) and flag any candidate with earnings inside the planned holding period
6. `position-sizer` — account size from `state/portfolio.md`, 1% risk default
7. `breakout-trade-planner` for entry/stop/target and portfolio heat
8. `trader-memory-core` — register each surviving thesis in `state/theses/`
9. `pre-trade-discipline-gate` — only GO candidates are actionable; on restrict/cash-priority days a GO requires the user's per-candidate `regime_override_confirmed: true`, and the order table must repeat the bold **WARNING**

Broker adjustments (Trade Republic):
- No OCO/bracket orders: translate any Alpaca templates into "stop-loss order + price alert at target, swap to limit when alert fires"
- 1 € per executed order: show fees as % of planned risk; flag trades where round-trip fees exceed ~3% of risk

End with a table of GO candidates: ticker, entry, stop, target, shares, risk €, fees, and the exact Trade Republic orders to place. All orders are placed manually.

Then list the reports from this run, one line per report, with the `.md` and `.html` links side by side as clickable local paths, e.g. `VCP: [md](reports/<file>.md) · [html](reports/<file>.html)`. Never replace a link with a note like "HTML version alongside"; a report with no HTML gets only its `.md` link.
