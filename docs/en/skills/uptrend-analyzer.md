---
layout: default
title: "Uptrend Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 61
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

# Uptrend Analyzer Skill

---

## 2. When to Use

**English:**
- User asks "Is the market breadth healthy?" or "How broad is the rally?"
- User wants to assess uptrend ratios across sectors
- User asks about market participation or breadth conditions
- User needs exposure guidance based on breadth analysis
- User references Monty's Uptrend Dashboard or uptrend ratios

**Japanese:**
- 「市場のブレドスは健全？」「上昇の裾野は広い？」
- セクター別のアップトレンド比率を確認したい
- 相場参加率・ブレドス状況を診断したい
- ブレドス分析に基づくエクスポージャーガイダンスが欲しい
- Montyのアップトレンドダッシュボードについて質問

---

## 3. Prerequisites

- Monty Uptrend Ratio Dashboard CSV; no API key required
- Python 3.9+ recommended

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
