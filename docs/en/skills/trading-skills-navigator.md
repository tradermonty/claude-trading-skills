---
layout: default
title: "Trading Skills Navigator"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/trading-skills-navigator/
permalink: /en/skills/trading-skills-navigator/
---

# Trading Skills Navigator
{: .no_toc }

Recommend the right trading workflow, skillset, API profile, and setup path from a natural-language goal. Use this as the on-ramp when a user expresses a trading or investing goal and needs to know which skill/workflow to use, where to start, or whether something works without paid API keys — e.g. "where do I start", "which skill should I use", "I want to swing trade only when the market is favorable", "what works without API keys", "どれを使えばいい", "API キー無しで 使えるものは". Routes and explains only; it never executes trades or auto-runs other skills, and it is honest when no workflow has shipped yet.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trading-skills-navigator){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Trading Skills Navigator

---

## 2. When to Use

- The user expresses a trading/investing goal and asks where to start or which
  skill/workflow to use ("どれを使えばいい", "where do I start").
- The user asks what works **without paid API keys**.
- The user wants the no-API vs API path separated, or a beginner path.
- The user describes a persona ("part-time swing trader", "dividend investor",
  "I want to short", "I want to backtest ideas") and needs routing.

Do **not** use this skill to execute trades, place orders, or auto-run other
skills. It recommends and explains only.

---

## 3. Prerequisites

- Reads local skills-index.yaml + workflows/*.yaml (or bundled snapshot); no network
- Python 3.9+ recommended

---

## 4. Quick Start

```bash
python3 skills/trading-skills-navigator/scripts/recommend.py \
  --query "<the user's goal, verbatim>" \
  --format json
  # optional: --no-api  --time-budget 15m|30m|60m|90m|any
  #           --experience beginner|intermediate|advanced
```

---

## 5. Workflow

### Step 1 — Capture the goal and constraints

From the user's message, extract:

- The natural-language **goal** (verbatim is fine).
- Optional constraints: **no-API** only? a daily **time budget**
  (15m/30m/60m/90m)? **experience** level (beginner/intermediate/advanced)?

Ask at most one brief clarifying question only if the goal is empty or has no
discernible intent. Otherwise proceed — the recommender degrades gracefully.

### Step 2 — Run the recommender

```bash
python3 skills/trading-skills-navigator/scripts/recommend.py \
  --query "<the user's goal, verbatim>" \
  --format json
  # optional: --no-api  --time-budget 15m|30m|60m|90m|any
  #           --experience beginner|intermediate|advanced
```

- In **Claude Code** the script reads the repo-root SSoT
  (`skills-index.yaml` + `workflows/*.yaml`) automatically.
- In the **Claude Web App** there is no repo root; the script transparently
  falls back to the bundled `assets/metadata_snapshot.json`. The recommendation
  is byte-identical in both environments — no behavior change for the user.

### Step 3 — Narrate the result conversationally

Parse the JSON and explain, in the user's language:

- **Primary workflow** — `display_name`, `cadence`, `~estimated_minutes`,
  `api_profile`. State plainly what it does and when to run it.
- **Secondary workflows** — if any, how they relate (e.g. "run the regime
  check first, then this when it allows risk").
- **Skillset** — the `skillset.id` (skills-index category). Note
  `manifest_status: deferred` means a bundled skillset manifest is a later
  phase; today the recommendation is workflow-based.
- **No-API vs API** — if `no_api` is true, say it works without paid keys. If a
  workflow was excluded under `--no-api`, surface the `rationale` entry that
  explains which paid integration caused it (e.g. "swing-opportunity-daily
  needs FMP").
- **Honest gap** — if `honest_gap` is true there is **no shipped workflow** for
  this intent. Say so directly, then present `suggested_skills` from the
  relevant category and relay the `note`. Never invent a workflow.
- Always read the `rationale` array and explain *why* this was recommended.

### Step 4 — Explain the setup path

Read `references/setup_paths.md` and walk the user through the path for **their
recommended workflow's skills specifically** (the actual `required_skills` /
`optional_skills` from the JSON), for whichever environment they use
(Claude Web App `.skill` upload, or Claude Code folder copy). Call out any paid
API keys those skills need.

### Step 5 — Point to the learning loop

Close by pointing the user at `trader-memory-core` and the
`trade-memory-loop` / `monthly-performance-review` workflows so every
recommended path feeds the Plan → Trade → Record → Review → Improve loop.

---

## 6. Resources

**References:**

- `skills/trading-skills-navigator/references/intent_routing.md`
- `skills/trading-skills-navigator/references/setup_paths.md`

**Scripts:**

- `skills/trading-skills-navigator/scripts/build_snapshot.py`
- `skills/trading-skills-navigator/scripts/recommend.py`
