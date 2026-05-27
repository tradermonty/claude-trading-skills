---
layout: default
title: "Market Top Detector"
grand_parent: English
parent: Skill Guides
nav_order: 41
lang_peer: /ja/skills/market-top-detector/
permalink: /en/skills/market-top-detector/
---

# Market Top Detector
{: .no_toc }

Detects market top probability using O'Neil Distribution Days, Minervini Leading Stock Deterioration, and Monty Defensive Sector Rotation. Generates a 0-100 composite score with risk zone classification. Use when user asks about market top risk, distribution days, defensive rotation, leadership breakdown, or whether to reduce equity exposure. Focuses on 2-8 week tactical timing signals for 10-20% corrections.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/market-top-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/market-top-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Market Top Detector Skill

---

## 2. When to Use

**English:**
- User asks "Is the market topping?" or "Are we near a top?"
- User notices distribution days accumulating
- User observes defensive sectors outperforming growth
- User sees leading stocks breaking down while indices hold
- User asks about reducing equity exposure timing
- User wants to assess correction probability for the next 2-8 weeks

**Japanese:**
- 「天井が近い？」「今は利確すべき？」
- ディストリビューションデーの蓄積を懸念
- ディフェンシブセクターがグロースをアウトパフォーム
- 先導株が崩れ始めているが指数はまだ持ちこたえている
- エクスポージャー縮小のタイミング判断
- 今後2〜8週間の調整確率を評価したい

---

## 3. Prerequisites

**Required:**
- **FMP API Key:** Set `$FMP_API_KEY` environment variable or pass `--api-key`. Free tier sufficient (~33 API calls per execution).
- **WebSearch Access:** Required to collect S&P 500 breadth (50DMA %) and CBOE Put/Call ratio data.

**Optional:**
- **Margin Debt Data:** Enhances sentiment scoring but typically 1-2 months lagged.
- **VIX Term Structure:** Auto-detected from FMP API if VIX3M quote available; manual override via `--vix-term`.

**Data Freshness:** All manually collected data should be from the most recent 3 business days for accurate analysis.

---

## 4. Quick Start

```bash
1. S&P 500 Breadth (200DMA above %)
   AUTO-FETCHED from TraderMonty CSV (no WebSearch needed)
   The script fetches this automatically from GitHub Pages CSV data.
   Override: --breadth-200dma [VALUE] to use a manual value instead.
   Disable: --no-auto-breadth to skip auto-fetch entirely.

2. [REQUIRED] S&P 500 Breadth (50DMA above %)
   Valid range: 20-100
   Primary search: "S&P 500 percent stocks above 50 day moving average"
   Fallback: "market breadth 50dma site:barchart.com"
   Record the data date

3. [REQUIRED] CBOE Equity Put/Call Ratio
   Valid range: 0.30-1.50
   Primary search: "CBOE equity put call ratio today"
   Fallback: "CBOE total put call ratio current"
   Fallback: "put call ratio site:cboe.com"
   Record the data date

4. [OPTIONAL] VIX Term Structure
   Values: steep_contango / contango / flat / backwardation
   Primary search: "VIX VIX3M ratio term structure today"
   Fallback: "VIX futures term structure contango backwardation"
   Note: Auto-detected from FMP API if VIX3M quote available.
   CLI --vix-term overrides auto-detection.

5. [OPTIONAL] Margin Debt YoY %
   Primary search: "FINRA margin debt latest year over year percent"
   Fallback: "NYSE margin debt monthly"
   Note: Typically 1-2 months lagged. Record the reporting month.
```

---

## 5. Workflow

### Phase 1: Data Collection via WebSearch

Before running the Python script, collect the following data using WebSearch.
**Data Freshness Requirement:** All data must be from the most recent 3 business days. Stale data degrades analysis quality.

```
1. S&P 500 Breadth (200DMA above %)
   AUTO-FETCHED from TraderMonty CSV (no WebSearch needed)
   The script fetches this automatically from GitHub Pages CSV data.
   Override: --breadth-200dma [VALUE] to use a manual value instead.
   Disable: --no-auto-breadth to skip auto-fetch entirely.

2. [REQUIRED] S&P 500 Breadth (50DMA above %)
   Valid range: 20-100
   Primary search: "S&P 500 percent stocks above 50 day moving average"
   Fallback: "market breadth 50dma site:barchart.com"
   Record the data date

3. [REQUIRED] CBOE Equity Put/Call Ratio
   Valid range: 0.30-1.50
   Primary search: "CBOE equity put call ratio today"
   Fallback: "CBOE total put call ratio current"
   Fallback: "put call ratio site:cboe.com"
   Record the data date

4. [OPTIONAL] VIX Term Structure
   Values: steep_contango / contango / flat / backwardation
   Primary search: "VIX VIX3M ratio term structure today"
   Fallback: "VIX futures term structure contango backwardation"
   Note: Auto-detected from FMP API if VIX3M quote available.
   CLI --vix-term overrides auto-detection.

5. [OPTIONAL] Margin Debt YoY %
   Primary search: "FINRA margin debt latest year over year percent"
   Fallback: "NYSE margin debt monthly"
   Note: Typically 1-2 months lagged. Record the reporting month.
```

### Phase 2: Execute Python Script

Run the script with collected data as CLI arguments:

```bash
python3 skills/market-top-detector/scripts/market_top_detector.py \
  --api-key $FMP_API_KEY \
  --breadth-50dma [VALUE] --breadth-50dma-date [YYYY-MM-DD] \
  --put-call [VALUE] --put-call-date [YYYY-MM-DD] \
  --vix-term [steep_contango|contango|flat|backwardation] \
  --margin-debt-yoy [VALUE] --margin-debt-date [YYYY-MM-DD] \
  --output-dir reports/ \
  --context "Consumer Confidence=[VALUE]" "Gold Price=[VALUE]"
# 200DMA breadth is auto-fetched from TraderMonty CSV.
# Override with --breadth-200dma [VALUE] if needed.
# Disable with --no-auto-breadth to skip auto-fetch.
```

The script will:
1. Fetch S&P 500, QQQ, VIX quotes and history from FMP API
2. Fetch Leading ETF (ARKK, WCLD, IGV, XBI, SOXX, SMH, KWEB, TAN) data
3. Fetch Sector ETF (XLU, XLP, XLV, VNQ, XLK, XLC, XLY) data
4. Calculate all 6 components
5. Generate composite score and reports

### Phase 3: Present Results

Present the generated Markdown report to the user, highlighting:
- Composite score and risk zone
- Data freshness warnings (if any data older than 3 days)
- Strongest warning signal (highest component score)
- Historical comparison (closest past top pattern)
- What-if scenarios (sensitivity to key changes)
- Recommended actions based on risk zone
- Follow-Through Day status (if applicable)
- Delta vs previous run (if prior report exists)

---

---

## 6. Resources

**References:**

- `skills/market-top-detector/references/distribution_day_guide.md`
- `skills/market-top-detector/references/historical_tops.md`
- `skills/market-top-detector/references/market_top_methodology.md`

**Scripts:**

- `skills/market-top-detector/scripts/breadth_csv_client.py`
- `skills/market-top-detector/scripts/fmp_client.py`
- `skills/market-top-detector/scripts/historical_comparator.py`
- `skills/market-top-detector/scripts/market_top_detector.py`
- `skills/market-top-detector/scripts/report_generator.py`
- `skills/market-top-detector/scripts/scenario_engine.py`
- `skills/market-top-detector/scripts/scorer.py`
- `skills/market-top-detector/scripts/utils.py`
