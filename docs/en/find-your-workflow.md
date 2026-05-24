---
layout: default
title: Find Your Workflow
parent: English
nav_order: 6
lang_peer: /ja/find-your-workflow/
permalink: /en/find-your-workflow/
---

# Find Your Workflow
{: .no_toc }

A static "choose-your-entry-point" guide for the Solo Trader OS. Before you
browse the [Skill Catalog](skill-catalog.md) or [Workflows](workflows.md)
page, this page maps your situation to the right starting workflow in one
short scan.

If your situation does not match any line below, jump to
[**`trading-skills-navigator`**](skills/trading-skills-navigator.md) and
describe your goal in natural language — it returns the same workflow
recommendations programmatically.

---

## Pick by daily rhythm

| Your situation | Start with |
|---|---|
| I have 15 minutes each morning before the open | [`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml) |
| I want to swing trade only when the regime allows it | [`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml) → [`swing-opportunity-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/swing-opportunity-daily.yaml) |
| I review my long-term portfolio weekly | [`core-portfolio-weekly`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/core-portfolio-weekly.yaml) |
| I just closed a trade and want to learn from it | [`trade-memory-loop`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/trade-memory-loop.yaml) |
| I want to look back on the month and adjust my rules | [`monthly-performance-review`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/monthly-performance-review.yaml) |

> Not sure which one applies? Use [`trading-skills-navigator`](skills/trading-skills-navigator.md)
> and describe your daily rhythm in natural language.

---

## Pick by goal

| Your goal | Skillset | Driving workflow |
|---|---|---|
| Know whether today is risk-on or risk-off before doing anything else | [`market-regime`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/market-regime.yaml) | `market-regime-daily` |
| Run a Core long-term portfolio (dividends, ETFs, long holdings) | [`core-portfolio`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/core-portfolio.yaml) | `core-portfolio-weekly` |
| Find disciplined Satellite swing-trade candidates only when conditions allow | [`swing-opportunity`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/swing-opportunity.yaml) | `swing-opportunity-daily` |
| Record every trade, generate postmortems, and journal lessons | [`trade-memory`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/trade-memory.yaml) | `trade-memory-loop`, `monthly-performance-review` |

> Still unsure which goal you fit? [`trading-skills-navigator`](skills/trading-skills-navigator.md)
> can match your free-form goal to a skillset and workflow.

---

## When the existing workflows don't fit

### No-API-key starter path

If you do not have FMP / FINVIZ / Alpaca subscriptions yet, run these five
skills manually — the same minimum loop powers the
[`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml)
and [`trade-memory-loop`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/trade-memory-loop.yaml)
workflows without paid data:

1. [`market-breadth-analyzer`](skills/market-breadth-analyzer.md) — public CSV breadth scoring
2. [`uptrend-analyzer`](skills/uptrend-analyzer.md) — public CSV uptrend participation
3. [`position-sizer`](skills/position-sizer.md) — pure calculation
4. [`trader-memory-core`](skills/trader-memory-core.md) — local YAML journaling
5. [`signal-postmortem`](skills/signal-postmortem.md) — review framework

"No API" does not mean "no external data" — these skills still need public
CSVs, chart screenshots, or local files. See each skill's `integrations:`
entry in [`skills-index.yaml`](https://github.com/tradermonty/claude-trading-skills/blob/main/skills-index.yaml)
for exact input requirements.

### Honest gaps

Some use cases do not yet have a packaged workflow. These are tracked
explicitly as upcoming work in
[`PROJECT_VISION.md`](https://github.com/tradermonty/claude-trading-skills/blob/main/PROJECT_VISION.md):

- **Short-only / risk-off intraday** — covered partially by
  `parabolic-short-trade-planner`, but no end-to-end short workflow yet
- **Earnings-week intraday** — covered partially by `earnings-trade-analyzer`
  and `pead-screener`, but no weekly orchestration workflow yet
- **Strategy research pipeline** — `edge-pipeline-orchestrator` exists, but
  there is no canonical "find a new edge" workflow manifest yet

If your situation maps to one of these gaps, treat it as exploratory: pick
the individual skills you need from the [Skill Catalog](skill-catalog.md)
and run them ad-hoc until a dedicated workflow ships.

### Free-form natural-language entry

For any situation that does not match the tables above, use the
[`trading-skills-navigator`](skills/trading-skills-navigator.md) skill. Pass
it your free-form goal and it returns the most appropriate workflow,
skillset, API profile, and setup path — backed by the same
[`skills-index.yaml`](https://github.com/tradermonty/claude-trading-skills/blob/main/skills-index.yaml)
single source of truth that powers this page.

---

## See also

- [Getting Started](getting-started.md) — install paths for Claude Code,
  Claude web app, and CLI
- [Skill Catalog](skill-catalog.md) — full alphabetical catalog of every skill
- [Workflows](workflows.md) — auto-generated manifest reference for every
  workflow
- [Skillsets](skillsets.md) — goal-oriented install bundles
