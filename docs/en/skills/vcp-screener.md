---
layout: default
title: "VCP Screener"
grand_parent: English
parent: Skill Guides
nav_order: 65
lang_peer: /ja/skills/vcp-screener/
permalink: /en/skills/vcp-screener/
---

# VCP Screener
{: .no_toc }

Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP). Identifies Stage 2 uptrend stocks forming tight bases with contracting volatility near breakout pivot points. Use when user requests VCP screening, Minervini-style setups, tight base patterns, volatility contraction breakout candidates, or Stage 2 momentum stock scanning.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/vcp-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/vcp-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# VCP Screener - Minervini Volatility Contraction Pattern

---

## 2. When to Use

- User asks for VCP screening or Minervini-style setups
- User wants to find tight base / volatility contraction patterns
- User requests Stage 2 momentum stock scanning
- User asks for breakout candidates with defined risk

---

## 3. Prerequisites

- FMP API key (set `FMP_API_KEY` environment variable or pass `--api-key`)
- Free tier (250 calls/day) is sufficient for default screening (top 100 candidates)
- Paid tier recommended for full S&P 500 screening (`--full-sp500`)

---

## 4. Quick Start

```bash
# Default: S&P 500, top 100 candidates
python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir skills/vcp-screener/scripts

# Custom universe
python3 skills/vcp-screener/scripts/screen_vcp.py --universe AAPL NVDA MSFT AMZN META --output-dir skills/vcp-screener/scripts

# Full S&P 500 (paid API tier)
python3 skills/vcp-screener/scripts/screen_vcp.py --full-sp500 --output-dir skills/vcp-screener/scripts
```

---

## 5. Workflow

### Step 1: Prepare and Execute Screening

Run the VCP screener script:

```bash
# Default: S&P 500, top 100 candidates
python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir skills/vcp-screener/scripts

# Custom universe
python3 skills/vcp-screener/scripts/screen_vcp.py --universe AAPL NVDA MSFT AMZN META --output-dir skills/vcp-screener/scripts

# Full S&P 500 (paid API tier)
python3 skills/vcp-screener/scripts/screen_vcp.py --full-sp500 --output-dir skills/vcp-screener/scripts
```

### Strict Mode (Minervini pure setup)

Only return stocks with `valid_vcp=True` AND `execution_state` in `(Pre-breakout, Breakout)`:

```bash
python3 skills/vcp-screener/scripts/screen_vcp.py --strict --output-dir reports/
```

### Advanced Tuning (for backtesting)

Adjust VCP detection parameters for research and backtesting:

```bash
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --min-contractions 3 \
  --t1-depth-min 12.0 \
  --breakout-volume-ratio 2.0 \
  --trend-min-score 90 \
  --atr-multiplier 1.5 \
  --output-dir reports/
```

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| `--min-contractions` | 2 | 2-4 | Higher = fewer but higher-quality patterns |
| `--t1-depth-min` | 10.0% | 1-50 | Higher = excludes shallow first corrections |
| `--breakout-volume-ratio` | 1.5x | 0.5-10 | Higher = stricter volume confirmation |
| `--trend-min-score` | 85 | 0-100 | Higher = stricter Stage 2 filter |
| `--atr-multiplier` | 1.5 | 0.5-5 | Lower = more sensitive swing detection |
| `--contraction-ratio` | 0.70 | 0.1-1 | Lower = requires tighter contractions |
| `--min-contraction-days` | 5 | 1-30 | Higher = longer minimum contraction |
| `--lookback-days` | 120 | 30-365 | Longer = finds older patterns |
| `--max-sma200-extension` | 50.0% | — | SMA200 distance threshold for Overextended state and penalty |
| `--wide-and-loose-threshold` | 15.0% | — | Final contraction depth above which wide-and-loose flag triggers |
| `--strict` | off | — | Minervini strict mode: only Pre-breakout or Breakout with valid VCP |

### Step 2: Review Results

1. Read the generated JSON and Markdown reports
2. Load `references/vcp_methodology.md` for pattern interpretation context
3. Load `references/scoring_system.md` for score threshold guidance

### Step 3: Present Analysis

For each top candidate, present:
- **Quality** (`composite_score` / rating) — how well-formed is the VCP pattern?
- **Execution State** (`execution_state`) — is the setup in an actionable stage for manual evaluation? (Pre-breakout / Breakout = evaluate now; all entries require manual broker placement)
- **Pattern Type** (`pattern_type`) — Textbook VCP / VCP-adjacent / Post-breakout / Extended Leader / Damaged
- `★` marker if a State Cap was applied (raw score was downgraded)
- Contraction details (T1/T2/T3 depths and ratios)
- Trade setup: pivot price, stop-loss, risk percentage
- Volume dry-up ratio and breakout_volume_score
- Relative strength rank

### Step 4: Provide Actionable Guidance

**By Execution State (primary filter):**
- **Pre-breakout / Breakout:** Pattern is in the active entry window — apply rating-based sizing
- **Early-post-breakout:** Breakout underway but above ideal entry — reduced size or wait for pullback
- **Extended / Overextended:** Trade missed — add to watchlist for next base
- **Damaged / Invalid:** Setup invalidated — do not enter

**By Rating (secondary, after state confirms manual evaluation is warranted):**

All sizing below is a starting reference for manual position sizing. No order is placed
by this skill — all entries require manual confirmation and placement at the broker.

- **Textbook VCP (90+):** Evaluate entry at pivot — reference sizing 1.5-2x standard
- **Strong VCP (80-89):** Evaluate entry at pivot — reference sizing 1x standard
- **Good VCP (70-79):** Evaluate entry on volume confirmation above pivot — reference sizing 0.75x
- **Developing (60-69):** Add to watchlist, wait for tighter contraction
- **Weak/No VCP (<60):** Monitor only or skip

---

## 6. Resources

**References:**

- `skills/vcp-screener/references/fmp_api_endpoints.md`
- `skills/vcp-screener/references/scoring_system.md`
- `skills/vcp-screener/references/vcp_methodology.md`

**Scripts:**

- `skills/vcp-screener/scripts/fmp_client.py`
- `skills/vcp-screener/scripts/report_generator.py`
- `skills/vcp-screener/scripts/scorer.py`
- `skills/vcp-screener/scripts/screen_vcp.py`
