---
description: Daily market regime check (breadth, uptrend, top risk → exposure posture)
argument-hint: "[--full to include macro-regime-detector]"
---

# Market Regime Daily

Run the `market-regime-daily` workflow. The canonical definition is `workflows/market-regime-daily.yaml` — read it first and follow its steps, decision gates, and manual_review items exactly.

Steps (in order, invoke each skill via the Skill tool):
1. `market-breadth-analyzer`
2. `uptrend-analyzer`
3. `market-top-detector` (optional step — run it by default)
4. `exposure-coach` — consume steps 1–3 and produce the exposure decision

If `$ARGUMENTS` contains `--full`, also run `macro-regime-detector` before step 4.

Save reports to `reports/`. End with a short summary:
- Exposure decision: **allow / restrict / cash-priority** (posture, not a buy/sell signal)
- The 2–3 numbers that drove it
- Next step: on `allow`, suggest `/swing`; otherwise say no new swing risk today
- Reports: one line per report from this run, with the `.md` and `.html` links side by side as clickable local paths, e.g. `Uptrend: [md](reports/uptrend_analysis_<ts>.md) · [html](reports/uptrend_analysis_<ts>.html)`. The HTML versions (market_breadth, uptrend_analysis) explain every metric in plain language ("What it measures" / "Today"). Never replace a link with a note like "HTML version alongside"; a report with no HTML gets only its `.md` link
