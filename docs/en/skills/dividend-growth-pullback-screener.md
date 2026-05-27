---
layout: default
title: "Dividend Growth Pullback Screener"
grand_parent: English
parent: Skill Guides
nav_order: 16
lang_peer: /ja/skills/dividend-growth-pullback-screener/
permalink: /en/skills/dividend-growth-pullback-screener/
---

# Dividend Growth Pullback Screener
{: .no_toc }

Use this skill to find high-quality dividend growth stocks (12%+ annual dividend growth, 1.5%+ yield) that are experiencing temporary pullbacks, identified by RSI oversold conditions (RSI ≤40). This skill combines fundamental dividend analysis with technical timing indicators to identify buying opportunities in strong dividend growers during short-term weakness.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span> <span class="badge badge-optional">FINVIZ Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/dividend-growth-pullback-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/dividend-growth-pullback-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill screens for dividend growth stocks that exhibit strong fundamental characteristics but are experiencing temporary technical weakness. It targets stocks with exceptional dividend growth rates (12%+ CAGR) that have pulled back to RSI oversold levels (≤40), creating potential entry opportunities for long-term dividend growth investors.

**Investment Thesis:** High-quality dividend growth stocks (often yielding 1-2.5%) compound wealth through dividend increases rather than high current yield. Buying these stocks during temporary pullbacks (RSI ≤40) can enhance total returns by combining strong fundamental growth with favorable technical entry timing.

---

## 2. When to Use

Use this skill when:
- Looking for dividend growth stocks with exceptional compounding potential (12%+ dividend CAGR)
- Seeking entry opportunities in quality stocks during temporary market weakness
- Willing to accept lower current yields (1.5-3%) for higher dividend growth
- Focusing on total return over 5-10 years rather than current income
- Market conditions show sector rotations or broad pullbacks affecting quality names

**Do NOT use when:**
- Seeking high current income (use value-dividend-screener instead)
- Requiring immediate dividend yields >3%
- Looking for deep value plays with strict P/E or P/B requirements
- Short-term trading focus (<6 months)

---

## 3. Prerequisites

- **FMP API key** (required): Set `FMP_API_KEY` environment variable or pass `--fmp-api-key`. Free tier (250 calls/day) is sufficient for FMP-only mode (≤40 stocks). [Sign up](https://site.financialmodelingprep.com/developer/docs).
- **FINVIZ Elite API key** (optional, recommended): Set `FINVIZ_API_KEY` environment variable or pass `--finviz-api-key`. Reduces execution time from 10–15 min to 2–3 min. [Sign up](https://elite.finviz.com/).
- Python 3.8+ with `requests` and `pandas` libraries installed.

---

## 4. Quick Start

```bash
# Two-stage screening with RSI filter (RECOMMENDED)
python3 dividend-growth-pullback-screener/scripts/screen_dividend_growth.py --use-finviz

# FMP-only screening (limited to ~40 stocks due to API limits)
python3 dividend-growth-pullback-screener/scripts/screen_dividend_growth.py --max-candidates 40

# Custom RSI threshold and dividend growth requirements
python3 dividend-growth-pullback-screener/scripts/screen_dividend_growth.py \
  --use-finviz \
  --rsi-threshold 35 \
  --min-div-growth 15
```

---

## 5. Workflow

### Step 1: Set API Keys

#### Two-Stage Approach (RECOMMENDED)

For optimal performance, use FINVIZ Elite API for pre-screening + FMP API for detailed analysis:

```bash
# Set both API keys as environment variables
export FMP_API_KEY=your_fmp_key_here
export FINVIZ_API_KEY=your_finviz_key_here
```

**Why Two-Stage?**
- **FINVIZ**: Fast pre-screening with RSI filter (1 API call → ~10-50 candidates)
- **FMP**: Detailed fundamental analysis only on pre-screened candidates
- **Result**: Analyze more stocks with fewer FMP API calls (stays within free tier limits)

#### FMP-Only Approach (Original Method)

If you don't have FINVIZ Elite access:

```bash
export FMP_API_KEY=your_key_here
```

**Limitation**: FMP free tier (250 requests/day) limits analysis to ~40 stocks. Use `--max-candidates 40` to stay within limits.

### Step 2: Execute Screening

**Two-Stage Screening (RECOMMENDED):**

```bash
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py --use-finviz
```

This executes:
1. FINVIZ pre-screen: Dividend yield 0.5-3%, Dividend growth 10%+, EPS growth 5%+, Sales growth 5%+, RSI <40
2. FMP detailed analysis: Verify 12%+ dividend CAGR, calculate exact RSI, analyze fundamentals

**FMP-Only Screening:**

```bash
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py --max-candidates 40
```

**Customization Options:**

```bash
# Two-stage with custom parameters
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py \
  --use-finviz --min-yield 2.0 --min-div-growth 15.0 --rsi-max 35

# FMP-only with custom parameters
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py \
  --min-yield 2.0 --min-div-growth 10.0 --max-candidates 30

# Provide API keys as arguments (instead of environment variables)
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py \
  --use-finviz --fmp-api-key YOUR_FMP_KEY --finviz-api-key YOUR_FINVIZ_KEY
```

### Step 3: Review Results

The script generates two outputs:

1. **JSON file:** `dividend_growth_pullback_results_YYYY-MM-DD.json`
   - Structured data with all metrics for further analysis
   - Includes dividend growth rates, RSI values, financial health metrics

2. **Markdown report:** `dividend_growth_pullback_screening_YYYY-MM-DD.md`
   - Human-readable analysis with stock profiles
   - Scenario-based probability assessments
   - Entry timing recommendations

### Step 4: Analyze Qualified Stocks

For each qualified stock, the report includes:

**Dividend Growth Profile:**
- Current yield and annual dividend
- 3-year dividend CAGR and consistency
- Payout ratio and sustainability assessment

**Technical Timing:**
- Current RSI value (≤40 = oversold)
- RSI context (extreme oversold <30 vs. early pullback 30-40)
- Price action relative to recent trend

**Quality Metrics:**
- Revenue and EPS growth (confirms business momentum)
- Financial health (debt levels, liquidity ratios)
- Profitability (ROE, profit margins)

**Investment Recommendation:**
- Entry timing assessment (immediate vs. wait for confirmation)
- Risk factors specific to the stock
- Upside scenarios based on dividend growth compounding

---

## 6. Resources

**References:**

- `skills/dividend-growth-pullback-screener/references/dividend_growth_compounding.md`
- `skills/dividend-growth-pullback-screener/references/fmp_api_guide.md`
- `skills/dividend-growth-pullback-screener/references/rsi_oversold_strategy.md`

**Scripts:**

- `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py`
