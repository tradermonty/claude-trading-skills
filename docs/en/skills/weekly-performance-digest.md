---
layout: default
title: "Weekly Performance Digest"
grand_parent: English
parent: Skill Guides
nav_order: 70
lang_peer: /ja/skills/weekly-performance-digest/
permalink: /en/skills/weekly-performance-digest/
generated: true
---

# Weekly Performance Digest
{: .no_toc }

Generate a weekly performance summary from closed trader-memory-core theses — win rate, expectancy, profit factor, R-multiple, MAE/MFE, and win/loss pattern analysis by source skill, exit reason, thesis type, sector, and mechanism. No API required; pure local calculation.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/weekly-performance-digest.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/weekly-performance-digest){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Weekly Performance Digest aggregates the trades you closed during a week into a single
performance report. It reads CLOSED theses tracked by `trader-memory-core`
(`state/theses/th_*.yaml`), computes headline metrics (win rate, expectancy, profit
factor, R-multiple, MAE/MFE), breaks results down across several pattern dimensions
(source skill, exit reason, thesis type, sector, mechanism tag, screening grade), and
surfaces the week's biggest winners, losers, and lessons. Output is a JSON record plus
a human-readable Markdown report. Pure calculation — no API key required.

---

## 2. When to Use

- At the end of a trading week to review aggregate realized performance
- To measure win rate and expectancy across all closed positions
- To see which source skills, exit reasons, sectors, or mechanisms drove wins vs losses
- To feed a month-end review (combine four weekly digests) or a postmortem
- For a quick "what worked / what didn't" snapshot grounded in real closed trades

---

## 3. Prerequisites

- Python 3.9+ with `PyYAML` (already a repo dependency)
- A `trader-memory-core` state directory of thesis YAML files (`state/theses/`)
- No API key required

---

## 4. Quick Start

```bash
python3 skills/weekly-performance-digest/scripts/generate_weekly_digest.py \
  --state-dir state/theses \
  --from-date 2026-06-13 --to-date 2026-06-20 \
  --output-dir reports/ -v
```

---

## 5. Workflow

### Step 1: Run the digest for a week

```bash
python3 skills/weekly-performance-digest/scripts/generate_weekly_digest.py \
  --state-dir state/theses \
  --from-date 2026-06-13 --to-date 2026-06-20 \
  --output-dir reports/ -v
```

Defaults: `--state-dir state/theses`, `--from-date` = 7 days before `--to-date`,
`--to-date` = today, `--output-dir reports/`. With no date flags it digests the
trailing 7 days.

### Step 2: Read the report

The run writes `reports/weekly_digest_<to-date>.json` and
`reports/weekly_digest_<to-date>.md`. Review the Markdown for the executive summary,
metrics table, pattern breakdowns, and top winners/losers; consume the JSON downstream.

### Step 3 (optional): Feed downstream

Combine several weekly JSON digests for a monthly review, or pass the JSON to a
postmortem/coach step. The skill is descriptive — act on its findings via your normal
review process.

---

## 6. Resources

**References:**

- `skills/weekly-performance-digest/references/weekly-digest-metrics.md`

**Scripts:**

- `skills/weekly-performance-digest/scripts/generate_weekly_digest.py`
