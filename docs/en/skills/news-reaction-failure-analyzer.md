---
layout: default
title: "News Reaction Failure Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 43
lang_peer: /ja/skills/news-reaction-failure-analyzer/
permalink: /en/skills/news-reaction-failure-analyzer/
generated: true
---

# News Reaction Failure Analyzer
{: .no_toc }

Judge whether a market FAILED to react to news favorable to a crowded speculative position — step 2 of Jason Shapiro's COT contrarian process. Consumes a cot-contrarian-detector report (or an explicit direction) plus a Claude-curated events JSON, fetches the underlying price series with a documented fallback chain, and produces a fail-closed CONFIRMED / NOT_CONFIRMED / INSUFFICIENT_EVIDENCE verdict using a statistically validated drift-significance test (not a naive failure-ratio, which false-confirms on pure noise). Generic beyond COT — reusable for PEAD and macro-crowding news-failure checks. Use when the user asks to check news-failure confirmation, whether a crowded market "shrugged off" good/bad news, or wants to run Shapiro step 2 on a CROWDED_LONG/CROWDED_SHORT market.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/news-reaction-failure-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/news-reaction-failure-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Implements step 2 of Jason Shapiro's COT contrarian process: once a market
is flagged as crowded (`cot-contrarian-detector`, step 1), check whether it
FAILED to react to news that should have rewarded the crowd. A crowded-long
market that doesn't rally on genuinely bullish news, or a crowded-short
market that doesn't sell off on genuinely bearish news, is the core
behavioral tell that the crowd has run out of buying/selling power — this
is the confirmation step that turns "crowded" into a contrarian setup
candidate (steps 3-5, still manual: price-action confirmation, entry, exit).

**Why this isn't a naive failure-ratio check:** an earlier design flagged
"news failure" whenever fewer than half the relevant events "responded" —
but under pure noise, roughly 69% of individual events fail to respond by
chance, so that rule would CONFIRM on random noise 48-83% of the time
depending on sample size. This skill instead requires the market to have
moved *significantly against* the crowd's favorable news (a drift-
significance test with a Monte-Carlo-verified null false-positive bound),
never merely "didn't respond enough." See
`references/news-failure-patterns.md` for the full statistical rationale.

---

## 2. When to Use

**English:**
- "Did the market shrug off [event] even though [asset] is crowded long/short?"
- "Run a news-failure check on [symbol]"
- "Is [symbol] confirmed for a Shapiro-style contrarian setup?"
- After `cot-contrarian-detector` flags a market CROWDED_LONG / CROWDED_SHORT
  and the user wants to move to step 2

**Japanese:**
- 「この市場は好材料に反応しなかった？」
- 「COTで偏っているこの銘柄のニュース失敗を確認して」

**Do NOT use when:**
- The market isn't crowded (NEUTRAL classification) — this skill refuses
  fail-closed without an explicit `--direction` override
- No curated events JSON exists yet — WebSearch must run first (Phase 2
  below); never fabricate events or URLs to get a verdict

---

## 3. Prerequisites

- **FMP API Key:** Required. Set `FMP_API_KEY` or pass `--api-key`. Used
  for price data only (`stable/historical-price-eod/light`) — coverage
  varies by symbol; see `references/price-source-map.md`.
- **Python 3.9+** with `requests` installed.
- **WebSearch access** to curate the events JSON (Phase 2). Skill degrades
  gracefully without it (states the limitation; never fabricates events).
- **Optional:** a `cot-contrarian-detector` JSON report (`--detector-json`)
  to auto-resolve symbol + direction, or supply `--direction` explicitly.

---

## 4. Quick Start

```bash
python3 skills/news-reaction-failure-analyzer/scripts/analyze_news_reaction.py \
  --symbol B6 --detector-json reports/cot_crowding_2026-07-12.json \
  --events-json reports/nrf_events_B6_2026-07-12.json \
  --output-dir reports/
```

---

## 5. Workflow

### Phase 1: Obtain symbol + direction

From a `cot-contrarian-detector` report (`--detector-json`, symbol looked
up in `markets[]`) or directly from the user (`--symbol` + `--direction`).
A `NEUTRAL` classification, a symbol missing from the report, or a report
older than `--max-detector-age-days` (default 10) all refuse fail-closed
with a specific reason — only an explicit `--direction` overrides.

### Phase 2: Curate the events JSON via WebSearch

Search news in the evaluation window (`--window-days`, default 10) using
the 4-tier source hierarchy (issuer/primary → SEC/official stats → wire →
portal — see `references/news-failure-patterns.md`). Write findings into
an events JSON from `references/news-failure-patterns.md`'s template —
`event`, `event_time` (ISO8601 with explicit UTC offset), `source_url`,
`source_tier`, `expected_impact` (BULLISH/BEARISH) per event.

**Never fabricate events or URLs.** WebSearch unavailable → state it
explicitly; proceed without an events JSON only if the user accepts an
`INSUFFICIENT_EVIDENCE` result (reason `no_events_provided`) — the CLI
never raises an exception for a missing events file, it always exits 0
with a documented reason.

### Phase 3: Run the CLI

```bash
python3 skills/news-reaction-failure-analyzer/scripts/analyze_news_reaction.py \
  --symbol B6 --detector-json reports/cot_crowding_2026-07-12.json \
  --events-json reports/nrf_events_B6_2026-07-12.json \
  --output-dir reports/
```

The script fetches the price series (documented fallback chain — futures
symbol first, ETF proxy if 402/restricted or `rows == 0`; see
`references/price-source-map.md`), computes effective dates / returns /
z-scores per event, clusters events whose 3-trading-day windows overlap
(independence guard), and synthesizes the verdict.

### Phase 4: Present verdict + handoff

Present the verdict, aggregate stats (`drift_stat`, `responded_ratio`), and
the evidence table (per-event returns/z-scores/reaction labels, with any
`dropped_events` reasons shown — never silently hidden). If a proxy
(`run_context.proxy_used`) was used, note the tracking-error caveat.

Emit a handoff block for `contrarian-setup-gate` (#241, not yet built):

```json
{"news_failure": {"verdict": "CONFIRMED", "confidence": "HIGH", "report_path": "reports/nrf_B6_2026-07-12.json"}}
```

---

## 6. Resources

**References:**

- `skills/news-reaction-failure-analyzer/references/news-failure-patterns.md`
- `skills/news-reaction-failure-analyzer/references/price-source-map.md`

**Scripts:**

- `skills/news-reaction-failure-analyzer/scripts/analyze_news_reaction.py`
- `skills/news-reaction-failure-analyzer/scripts/reaction_math.py`
