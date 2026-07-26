---
layout: default
title: Your First Week
parent: English
nav_order: 8
lang_peer: /ja/your-first-week/
permalink: /en/your-first-week/
---

# Your First Week
{: .no_toc }

A seven-day path from installation to a repeatable market check, first journal entry,
and first weekly review.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Before You Start

This guide needs a Claude plan that supports Skills, Python 3.9+, `git`, `uv`, and
internet access to public CSV files. It needs **no paid market-data API** and no FMP,
FINVIZ Elite, or broker credentials.

> "No paid API" does not mean "offline." The two market analyzers download public CSV
> files. The journal and weekly review stay local. Nothing in this guide places an order
> or turns a report into a buy/sell signal.
{: .note }

The copy-and-paste commands below are for Claude Code or a terminal at the repository
root. Web App users can upload the corresponding `.skill` files from
[`skill-packages/`](https://github.com/tradermonty/claude-trading-skills/tree/main/skill-packages):
`trading-skills-navigator`, `market-breadth-analyzer`, `uptrend-analyzer`,
`exposure-coach`, `trader-memory-core`, and `weekly-performance-digest`.

## Day 1 — Install a Reproducible Environment

Clone the repository if you have not already done so, then install the locked runtime
dependencies:

```bash
git clone https://github.com/tradermonty/claude-trading-skills.git
cd claude-trading-skills
uv sync --locked
mkdir -p reports/first-week state/first-week-theses first-week-inputs
```

Keep every command in this guide at the repository root. We use `uv run python`
consistently so `requests`, `PyYAML`, and `jsonschema` come from the locked project
environment.

## Day 2 — Let the Navigator Choose the Path

Ask the deterministic Navigator for a beginner-friendly 15-minute routine:

<!-- first-week-navigator-command:start -->
```bash
uv run python skills/trading-skills-navigator/scripts/recommend.py \
  --query "I want a 15-minute daily market check without paid API keys" \
  --no-api \
  --time-budget 15m \
  --experience beginner \
  --format json
```
<!-- first-week-navigator-command:end -->

Confirm these fields in the JSON:

```text
primary_workflow.id = market-regime-daily
primary_workflow.api_profile = no-api-basic
no_api_path = true
```

The Navigator recommends; it does not execute other skills. The
[`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml)
manifest remains the source of truth for step order and required artifacts.

## Day 3 — Run the No-Paid-API Market Check

Run the two required public-data analyzers:

```bash
uv run python skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py \
  --output-dir reports/first-week

uv run python skills/uptrend-analyzer/scripts/uptrend_analyzer.py \
  --output-dir reports/first-week
```

Select exactly one timestamped output from each analyzer. The breadth pattern
deliberately excludes `market_breadth_history.json`.

```bash
breadth_json="$(find reports/first-week -maxdepth 1 -type f \
  -name 'market_breadth_????-??-??_??????.json' -print | sort | tail -n 1)"
uptrend_json="$(find reports/first-week -maxdepth 1 -type f \
  -name 'uptrend_analysis_????-??-??_??????.json' -print | sort | tail -n 1)"

test -n "$breadth_json" && test -f "$breadth_json"
test -n "$uptrend_json" && test -f "$uptrend_json"
```

The workflow's market-top step is optional, so the minimal path skips it. Pass only
the two available artifacts to Exposure Coach:

```bash
uv run python skills/exposure-coach/scripts/calculate_exposure.py \
  --breadth "$breadth_json" \
  --uptrend "$uptrend_json" \
  --output-dir reports/first-week
```

Inspect the newest `exposure_posture_*.json`:

```bash
exposure_json="$(find reports/first-week -maxdepth 1 -type f \
  -name 'exposure_posture_????-??-??_??????.json' -print | sort | tail -n 1)"
test -n "$exposure_json" && test -f "$exposure_json"

uv run python - "$exposure_json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as report_file:
    report = json.load(report_file)

for key in (
    "inputs_provided",
    "inputs_missing",
    "confidence",
    "recommendation",
    "exposure_ceiling_pct",
):
    print(f"{key}: {report[key]}")
PY
```

Expect `breadth` and `uptrend` in `inputs_provided`, the omitted dimensions in
`inputs_missing`, and `confidence: LOW`. With the critical regime and top-risk inputs
missing, the fail-safe recommendation is `REDUCE_ONLY` or `CASH_PRIORITY`, never
`NEW_ENTRY_ALLOWED`. This is a **degraded, incomplete-input posture**, not a complete
market verdict and not evidence that the market is bearish. Optional enhancements may
have additional data requirements; check their current skill guides before using them.

## Day 4 — Create Your First Journal Entry

Create a manual IDEA. Use a real ticker and a falsifiable statement, but do not invent
an entry or position just to complete the tutorial.

<!-- first-week-manual-json:start -->
```json
{
  "ticker": "AMD",
  "thesis_statement": "Observe whether AMD holds above the prior breakout area for five sessions.",
  "thesis_type": "growth_momentum"
}
```
<!-- first-week-manual-json:end -->

Save that JSON and ingest it:

```bash
cat > first-week-inputs/manual-idea.json <<'JSON'
{
  "ticker": "AMD",
  "thesis_statement": "Observe whether AMD holds above the prior breakout area for five sessions.",
  "thesis_type": "growth_momentum"
}
JSON
```

<!-- first-week-ingest-command:start -->
```bash
uv run python skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source manual \
  --input first-week-inputs/manual-idea.json \
  --state-dir state/first-week-theses
```
<!-- first-week-ingest-command:end -->

The command prints the generated thesis ID and creates an `IDEA`. It does not mark a
trade active and does not place an order.

## Day 5 — Read the Journal Before Changing It

List the state you actually recorded:

```bash
uv run python skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/first-week-theses \
  list

uv run python skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/first-week-theses \
  review-due
```

Check that the ticker, thesis type, and status match your input. Leave the thesis as
`IDEA` until you have separately validated a setup. Never edit the YAML state files by
hand; the CLI preserves schema and lifecycle checks.

## Day 6 — Turn the Steps into a Routine

Repeat Day 3 before considering new swing-trade risk. Keep this short checklist:

1. Read both analyzer freshness warnings.
2. Confirm which inputs Exposure Coach actually accepted.
3. Treat missing inputs as missing; do not fill them with assumptions.
4. Record the posture and your reasoning, not a prediction.
5. Make every order and risk decision outside this workflow under your own rules.

The daily output is useful when it changes your process: reduce research when the
posture is restrictive, or proceed to separate stock-level analysis when a complete
review allows it. It is never a standalone signal.

## Day 7 — Run Your First Weekly Review

Generate the trailing-seven-day digest from the local journal:

```bash
uv run python skills/weekly-performance-digest/scripts/generate_weekly_digest.py \
  --state-dir state/first-week-theses \
  --output-dir reports/first-week \
  --verbose
```

If you closed no trades, a zero-trade report is the correct result. Do not create a fake
trade to populate the metrics. Read the generated `weekly_digest_*.md` and answer:

1. Did I run the market check before considering risk?
2. Did I distinguish missing inputs from neutral signals?
3. Did I write a falsifiable thesis instead of a story?
4. What one process rule will I keep or change next week?

You have now completed the smallest Plan → Record → Review → Improve loop without a
paid data API. Continue with [Find Your Workflow]({{ '/en/find-your-workflow/' | relative_url }})
only after this routine feels repeatable.
