---
description: Record a closed/trimmed trade and run the postmortem (trade-memory-loop)
argument-hint: "<ticker or thesis id> <shares> @ <price> [date] [reason]"
---

# Close Trade

Run the `trade-memory-loop` workflow. The canonical definition is `workflows/trade-memory-loop.yaml` — read it first and follow its steps and manual_review items.

Trade details: $ARGUMENTS
If ticker, quantity, price, or date is missing, ask once before recording anything.

Steps:
1. `trader-memory-core` — find the thesis in `state/theses/`; use `trim` for a partial exit, `close` for a full exit. Record net P&L including 1 € per executed order (Trade Republic)
2. `signal-postmortem` — classify root cause: thesis, execution, market environment, or randomness
3. `trade-performance-coach` — propose next-session rules for me to accept/modify/defer
4. Skip `backtest-expert` unless I ask
5. `trader-memory-core` — append lessons to the journal

List every report from this run, one line per report, with the `.md` and `.html` links side by side as clickable local paths, e.g. `Postmortem: [md](reports/<file>.md) · [html](reports/<file>.html)`. Never replace a link with a note like "HTML version alongside"; a report with no HTML gets only its `.md` link.

Be honest about luck vs. skill, on winners too. If this was the last open thesis of the month, suggest running the `monthly-performance-review` workflow.
