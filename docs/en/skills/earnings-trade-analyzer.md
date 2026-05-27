---
layout: default
title: "Earnings Trade Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 20
lang_peer: /ja/skills/earnings-trade-analyzer/
permalink: /en/skills/earnings-trade-analyzer/
---

# Earnings Trade Analyzer
{: .no_toc }

Analyze recent post-earnings stocks using a 5-factor scoring system (Gap Size, Pre-Earnings Trend, Volume Trend, MA200 Position, MA50 Position). Scores each stock 0-100 and assigns A/B/C/D grades. Use when user asks about earnings trade analysis, post-earnings momentum screening, earnings gap scoring, or finding best recent earnings reactions.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/earnings-trade-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/earnings-trade-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Earnings Trade Analyzer - Post-Earnings 5-Factor Scoring

---

## 2. When to Use

- User asks for post-earnings trade analysis or earnings gap screening
- User wants to find the best recent earnings reactions
- User requests earnings momentum scoring or grading
- User asks about post-earnings accumulation day (PEAD) candidates

---

## 3. Prerequisites

- FMP API key (set `FMP_API_KEY` environment variable or pass `--api-key`)
- Free tier (250 calls/day) is sufficient for default screening (lookback 2 days, top 20)
- Paid tier recommended for larger lookback windows or full screening

---

## 4. Quick Start

```bash
# Default: 2-day lookback, top 20 results
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --output-dir reports/

# Custom parameters with entry quality filter
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --lookback-days 3 --top 10 --max-api-calls 200 \
  --apply-entry-filter --output-dir reports/
```

---

## 5. Workflow

### Step 1: Run the Earnings Trade Analyzer

Execute the analyzer script:

```bash
# Default: last 2 days of earnings, top 20 results
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py --output-dir reports/

# Custom lookback and market cap filter
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --lookback-days 5 \
  --min-market-cap 1000000000 \
  --top 30 \
  --output-dir reports/

# With entry quality filter
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --apply-entry-filter \
  --output-dir reports/
```

### Step 2: Review Results

1. Read the generated JSON and Markdown reports
2. Load `references/scoring_methodology.md` for scoring interpretation context
3. Focus on Grade A and B stocks for actionable setups

### Step 3: Present Analysis

For each top candidate, present:
- Composite score and letter grade (A/B/C/D)
- Earnings gap size and direction
- Pre-earnings 20-day trend
- Volume ratio (20-day vs 60-day average)
- Position relative to 200-day and 50-day moving averages
- Weakest and strongest scoring components

### Step 4: Provide Actionable Guidance

Based on grades:
- **Grade A (85+):** Strong earnings reaction with institutional accumulation - consider entry
- **Grade B (70-84):** Good earnings reaction worth monitoring - wait for pullback or confirmation
- **Grade C (55-69):** Mixed signals - use caution, additional analysis needed
- **Grade D (<55):** Weak setup - avoid or wait for better conditions

---

## 6. Resources

**References:**

- `skills/earnings-trade-analyzer/references/scoring_methodology.md`

**Scripts:**

- `skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py`
- `skills/earnings-trade-analyzer/scripts/fmp_client.py`
- `skills/earnings-trade-analyzer/scripts/report_generator.py`
- `skills/earnings-trade-analyzer/scripts/scorer.py`
