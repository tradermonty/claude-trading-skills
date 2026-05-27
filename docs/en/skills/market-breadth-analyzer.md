---
layout: default
title: "Market Breadth Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 38
lang_peer: /ja/skills/market-breadth-analyzer/
permalink: /en/skills/market-breadth-analyzer/
---

# Market Breadth Analyzer
{: .no_toc }

Quantifies market breadth health using TraderMonty's public CSV data. Generates a 0-100 composite score across 6 components (100 = healthy). No API key required. Use when user asks about market breadth, participation rate, advance-decline health, whether the rally is broad-based, or general market health assessment.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/market-breadth-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/market-breadth-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Market Breadth Analyzer Skill

---

## 2. When to Use

**English:**
- User asks "Is the market rally broad-based?" or "How healthy is market breadth?"
- User wants to assess market participation rate
- User asks about advance-decline indicators or breadth thrust
- User wants to know if the market is narrowing (fewer stocks participating)
- User asks about equity exposure levels based on breadth conditions

**Japanese:**
- 「マーケットブレッドスはどうですか？」「市場の参加率は？」
- 「上昇は広がっている？」「一部の銘柄だけの上昇？」
- ブレッドス指標に基づくエクスポージャー判断
- 市場の健康度をデータで確認したい

---

## 3. Prerequisites

- **Python 3.8+** with `requests` library (for fetching CSV data)
- **Internet access** to reach GitHub Pages URLs
- **No API keys required** - uses freely available public CSV data

---

## 4. Quick Start

```bash
python3 skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py \
  --detail-url "https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv" \
  --summary-url "https://tradermonty.github.io/market-breadth-analysis/market_breadth_summary.csv"
```

---

## 5. Workflow

### Phase 1: Execute Python Script

Run the analysis script:

```bash
python3 skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py \
  --detail-url "https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv" \
  --summary-url "https://tradermonty.github.io/market-breadth-analysis/market_breadth_summary.csv"
```

The script will:
1. Fetch detail CSV (~2,500 rows, 2016-present) and summary CSV (8 metrics)
2. Validate data freshness (warn if > 5 days old)
3. Calculate all 6 component scores (with automatic weight redistribution if any component lacks data)
4. Generate composite score with zone classification
5. Track score history and compute trend (improving/deteriorating/stable)
6. Output JSON and Markdown reports

### Phase 2: Present Results

Present the generated Markdown report to the user, highlighting:
- Composite score and health zone
- Strongest and weakest components
- Recommended equity exposure level
- Key breadth levels to watch
- Any data freshness warnings

---

---

## 6. Resources

**References:**

- `skills/market-breadth-analyzer/references/breadth_analysis_methodology.md`

**Scripts:**

- `skills/market-breadth-analyzer/scripts/csv_client.py`
- `skills/market-breadth-analyzer/scripts/history_tracker.py`
- `skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py`
- `skills/market-breadth-analyzer/scripts/report_generator.py`
- `skills/market-breadth-analyzer/scripts/scorer.py`
