---
layout: default
title: "Morning Note Briefing"
grand_parent: English
parent: Skill Guides
nav_order: 46
lang_peer: /ja/skills/morning-note-briefing/
permalink: /en/skills/morning-note-briefing/
generated: true
---

# Morning Note Briefing
{: .no_toc }

Assemble a fixed-format, two-minute pre-market morning note by composing the JSON outputs of existing skills — overnight earnings beats/misses and guidance (earnings-calendar), pre-market/overnight movers and sector-level performance (sector-analyst + price data), today's macro calendar (economic-calendar-fetcher), and live catalysts (market-news-analyst / gdelt-news-catalyst). Use when the user asks for a "morning note", "morning meeting", "pre-market briefing", "daily note", "what happened overnight", or "morning call prep". Leads with the single most important development, then a directional Top Call and actionable long/short ideas with catalysts.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/morning-note-briefing.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/morning-note-briefing){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Morning Note Briefing gives the solo trader the one daily cadence the toolkit
otherwise lacks: a compressed, opinionated pre-market brief that a PM can read in
two minutes. It does **not** fetch data itself. Instead it composes the
already-produced JSON outputs of existing skills into a single fixed-format note,
led by the single most important development, followed by a **Top Call** and any
actionable long/short ideas with catalyst.

Fetching remains the responsibility of the upstream skills (which carry the FMP
dependency); this skill is pure, offline assembly and ranking.

---

## 2. When to Use

- At the start of the trading day, once the upstream skills have produced their JSON
- When the user asks for a "morning note", "pre-market briefing", "daily note", or "what happened overnight"
- When several data feeds need to be compressed into one prioritized, PM-facing page

---

## 3. Prerequisites

- Python 3.9+ (standard library only — `argparse`, `json`, `dataclasses`, `datetime`, `pathlib`)
- No API key of its own. Data comes from upstream skills; FMP is required only by those upstream skills (earnings-calendar, economic-calendar-fetcher, and any price/mover feed).

---

## 4. Quick Start

```bash
python3 skills/morning-note-briefing/scripts/build_morning_note.py \
  --earnings reports/earnings_calendar_latest.json \
  --sector reports/sector_latest.json \
  --economic reports/economic_calendar_latest.json \
  --news reports/gdelt_FCTA.json reports/gdelt_FRTL.json \
  --movers reports/premarket_movers.json \
  --as-of 2026-07-03 --analyst "Desk" --coverage "US Equities" \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Gather Upstream Skill Outputs

Run the source skills first (or reuse today's reports). Each contributes one slice:

| Skill | Output consumed | Contributes |
|-------|-----------------|-------------|
| earnings-calendar | array of `{symbol, companyName, date, timing, epsEstimated, epsActual?, guidance?, reaction?}` | overnight beats/misses + guidance changes |
| sector-analyst | `{groups:{regime,score}, ranking[], overbought[], oversold[], cycle_phase{}}` | sector-level daily performance / rotation regime |
| economic-calendar-fetcher | array of `{date, country, event, impact, previous, estimate, actual}` | today's macro calendar |
| market-news-analyst / gdelt-news-catalyst | `{ticker, coverage:{surge_x,breaking,severity}, blackout_signal{}, headlines[]}` or compact `{ticker, blackout, catalyst_type, severity, headline}` | live catalysts (coverage surge / breaking) |
| movers (price data) | array of `{ticker, pct_change, price?, session?, catalyst?}` | pre-market / overnight movers |

The assembler accepts **partial** inputs. Missing files are recorded in
`inputs_missing` and simply contribute no developments — an empty note is a valid
"nothing material overnight, maintain positioning" briefing, not an error.

`earnings-calendar` is forward-looking (estimates only). To surface a genuine
beat/miss and set trade direction, enrich its records with `epsActual` and/or
`guidance` (`raised`/`lowered`/`maintained`) before feeding them in; estimate-only
records still appear as scheduled events at low priority.

### Step 2: Assemble the Note

```bash
python3 skills/morning-note-briefing/scripts/build_morning_note.py \
  --earnings reports/earnings_calendar_latest.json \
  --sector reports/sector_latest.json \
  --economic reports/economic_calendar_latest.json \
  --news reports/gdelt_FCTA.json reports/gdelt_FRTL.json \
  --movers reports/premarket_movers.json \
  --as-of 2026-07-03 --analyst "Desk" --coverage "US Equities" \
  --output-dir reports/
```

`--news` accepts multiple files (one per watched ticker). All arguments are
optional; omit any feed you do not have. Use `--json-only` to skip the markdown.

### Step 3: Ranking and Selection

The script decomposes every input into **developments** scored 0-100 (see
`references/development_ranking.md`), then:

1. **Lead** = the single highest-priority development (may be a directionless
   catalyst or macro print). This heads the note.
2. **Top Call** = the highest-priority development that carries a long/short
   direction. When the lead is directionless, the Top Call is a different,
   actionable item. If nothing is directional, the note says so explicitly.
3. **Actionable Ideas** = directional developments with a ticker, de-duplicated
   by ticker, capped at four, each with a catalyst and a risk line.

### Step 4: Review and Distribute

Read the generated `reports/morning_note_YYYY-MM-DD.md`. It is one screen,
email/Slack-ready. Be opinionated when editing: lead with the one thing that
matters, keep each line to a sentence, and note that pre-market moves may change
by the open.

---

## 6. Resources

**References:**

- `skills/morning-note-briefing/references/development_ranking.md`
- `skills/morning-note-briefing/references/note_template.md`

**Scripts:**

- `skills/morning-note-briefing/scripts/build_morning_note.py`
