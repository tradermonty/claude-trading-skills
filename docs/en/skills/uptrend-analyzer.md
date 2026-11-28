---
layout: default
title: "Uptrend Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 43
lang_peer: /ja/skills/uptrend-analyzer/
permalink: /en/skills/uptrend-analyzer/
---

# Uptrend Analyzer
{: .no_toc }

Analyzes market breadth using Monty's Uptrend Ratio Dashboard data to diagnose the current market environment. Generates a 0-100 composite score from 5 components (breadth, sector participation, rotation, momentum, historical context). Use when asking about market breadth, uptrend ratios, or whether the market environment supports equity exposure. No API key required.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/uptrend-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/uptrend-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Fetches the CSV data behind Monty's Uptrend Ratio Dashboard and diagnoses market breadth and the market environment. It computes five component scores and a 0-100 composite score, and gives exposure guidance (Full/Normal/Reduced/Defensive/Preservation).

### Use case: Uptrend Ratio Dashboard

[Uptrend Ratio Dashboard](https://uptrend-dashboard.streamlit.app) is the live dashboard behind the data this skill analyzes: the uptrend ratio for the whole market and for each of the 11 sectors. Open it to see the latest readings and compare them with the skill's report.

---

## 2. When to Use

**English:**
- User asks "Is the market breadth healthy?" or "How broad is the rally?"
- User wants to assess uptrend ratios across sectors
- User asks about market participation or breadth conditions
- User needs exposure guidance based on breadth analysis
- User references Monty's Uptrend Dashboard or uptrend ratios


---

## 3. Prerequisites

- **API Key:** None required
- **Python 3.9+** recommended

---

## 4. Quick Start

```bash
python3 skills/uptrend-analyzer/scripts/uptrend_analyzer.py
```

---

## 5. Workflow

### Phase 1: Execute Python Script

Run the analysis script (no API key needed):

```bash
python3 skills/uptrend-analyzer/scripts/uptrend_analyzer.py
```

The script will:
1. Download CSV data from Monty's GitHub repository
2. Calculate 5 component scores
3. Generate composite score and reports

### Phase 2: Present Results

Present the generated Markdown report to the user, highlighting:
- Composite score and zone classification
- Exposure guidance (Full/Normal/Reduced/Defensive/Preservation)
- Sector heatmap showing strongest and weakest sectors
- Key momentum and rotation signals

### Phase 3: Read evaluation coverage

JSON carries a top-level schema 1.0 `evaluation_coverage` block (#711) over the
twelve declared worksheets: `all` plus the eleven sector worksheets. Markdown
prints evaluated / total beside the composite. A `partial` or `not_evaluable`
verdict means some worksheets were absent or unusable; the components they feed
used documented neutral defaults, so the composite is not a complete evaluation.

---

---

## 6. Resources

**References:**

- `skills/uptrend-analyzer/references/uptrend_methodology.md`

**Scripts:**

- `skills/uptrend-analyzer/scripts/data_fetcher.py`
- `skills/uptrend-analyzer/scripts/report_generator.py`
- `skills/uptrend-analyzer/scripts/scorer.py`
- `skills/uptrend-analyzer/scripts/uptrend_analyzer.py`

## Same-run provenance

Pass `--run-id daily-20261017-unique` to both required market-regime-daily
producers. Without it each producer generates its own unique ID. JSON includes
schema 1.0 `data_provenance` with actual primary timeseries business date,
UTC retrieval time, source and run ID. Unknown adjustment, point-in-time,
survivorship and corporate-action flags are false. Auxiliary summary dates
are unverified; this does not certify the freshness of every composite input.
Missing or malformed primary dates stop report generation.

Pass the exact JSON paths printed by these invocations to Exposure Coach's
`--require-provenance --run-id … --as-of …` mode. Run IDs are caller-provided
consistency markers, not authenticity or point-in-time proof.
