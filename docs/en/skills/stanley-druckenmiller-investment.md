---
layout: default
title: "Stanley Druckenmiller Investment"
grand_parent: English
parent: Skill Guides
nav_order: 54
lang_peer: /ja/skills/stanley-druckenmiller-investment/
permalink: /en/skills/stanley-druckenmiller-investment/
---

# Stanley Druckenmiller Investment
{: .no_toc }

Druckenmiller Strategy Synthesizer - Integrates 8 upstream skill outputs (Market Breadth, Uptrend Analysis, Market Top, Macro Regime, FTD Detector, VCP Screener, Theme Detector, CANSLIM Screener) into a unified conviction score (0-100), pattern classification, and allocation recommendation. Use when user asks about overall market conviction, portfolio positioning, asset allocation, strategy synthesis, or Druckenmiller-style analysis. Triggers on queries like "What is my conviction level?", "How should I position?", "Run the strategy synthesizer", "Druckenmiller analysis", "総合的な市場判断", "確信度スコア", "ポートフォリオ配分", "ドラッケンミラー分析".
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stanley-druckenmiller-investment.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stanley-druckenmiller-investment){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Druckenmiller Strategy Synthesizer

---

## 2. When to Use

**English:**
- User asks "What's my overall conviction?" or "How should I be positioned?"
- User wants a unified view synthesizing breadth, uptrend, top risk, macro, and FTD signals
- User asks about Druckenmiller-style portfolio positioning
- User requests strategy synthesis after running individual analysis skills
- User asks "Should I increase or decrease exposure?"
- User wants pattern classification (policy pivot, distortion, contrarian, wait)

**Japanese:**
- 「総合的な市場判断は？」「今のポジショニングは？」
- ブレッドス、アップトレンド、天井リスク、マクロの統合判断
- 「エクスポージャーを増やすべき？減らすべき？」
- 「ドラッケンミラー分析を実行して」
- 個別スキル実行後の戦略統合レポート

---

---

## 3. Prerequisites

- Synthesizes outputs from upstream skills; pure calculation
- Python 3.9+ recommended

---

## 4. Quick Start

```bash
python3 skills/stanley-druckenmiller-investment/scripts/strategy_synthesizer.py \
  --reports-dir reports/ \
  --output-dir reports/ \
  --max-age 72
```

---

## 5. Workflow

### Phase 1: Verify Prerequisites

Check that the 5 required skill JSON reports exist in `reports/` and are recent (< 72 hours). If any are missing, run the corresponding skill first.

### Phase 2: Execute Strategy Synthesizer

```bash
python3 skills/stanley-druckenmiller-investment/scripts/strategy_synthesizer.py \
  --reports-dir reports/ \
  --output-dir reports/ \
  --max-age 72
```

The script will:
1. Load and validate all upstream skill JSON reports
2. Extract normalized signals from each skill
3. Calculate 7 component scores (weighted 0-100)
4. Compute composite conviction score
5. Classify into one of 4 Druckenmiller patterns
6. Generate target allocation and position sizing
7. Output JSON and Markdown reports

### Phase 3: Present Results

Present the generated Markdown report, highlighting:
- Conviction score and zone
- Detected pattern and match strength
- Strongest and weakest components
- Target allocation (equity/bonds/alternatives/cash)
- Position sizing parameters
- Relevant Druckenmiller principle

### Phase 4: Provide Druckenmiller Context

Load appropriate reference documents to provide philosophical context:
- **High conviction:** Emphasize concentration and "fat pitch" principles
- **Low conviction:** Emphasize capital preservation and patience
- **Pattern-specific:** Apply relevant case study from `references/case-studies.md`

---

---

## 6. Resources

**References:**

- `skills/stanley-druckenmiller-investment/references/case-studies.md`
- `skills/stanley-druckenmiller-investment/references/conviction_matrix.md`
- `skills/stanley-druckenmiller-investment/references/investment-philosophy.md`
- `skills/stanley-druckenmiller-investment/references/market-analysis-guide.md`

**Scripts:**

- `skills/stanley-druckenmiller-investment/scripts/allocation_engine.py`
- `skills/stanley-druckenmiller-investment/scripts/report_generator.py`
- `skills/stanley-druckenmiller-investment/scripts/report_loader.py`
- `skills/stanley-druckenmiller-investment/scripts/scorer.py`
- `skills/stanley-druckenmiller-investment/scripts/strategy_synthesizer.py`
