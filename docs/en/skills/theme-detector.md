---
layout: default
title: "Theme Detector"
grand_parent: English
parent: Skill Guides
nav_order: 57
lang_peer: /ja/skills/theme-detector/
permalink: /en/skills/theme-detector/
---

# Theme Detector
{: .no_toc }

Detect and analyze trending market themes across sectors. Use when user asks about current market themes, trending sectors, sector rotation, thematic investing, what themes are hot or cold, or wants to identify bullish and bearish market narratives with lifecycle analysis.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span> <span class="badge badge-optional">FMP Optional</span> <span class="badge badge-optional">FINVIZ Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/theme-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/theme-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill detects and ranks trending market themes by analyzing cross-sector momentum, volume, and breadth signals. It identifies both bullish (upward momentum) and bearish (downward pressure) themes, assesses lifecycle maturity (Emerging/Accelerating/Trending/Mature/Exhausting), and provides a confidence score combining quantitative data with narrative analysis.

**3-Dimensional Scoring Model:**
1. **Theme Heat** (0-100): Direction-neutral strength of the theme (momentum, volume, uptrend ratio, breadth)
2. **Lifecycle Maturity**: Stage classification (Emerging / Accelerating / Trending / Mature / Exhausting) based on duration, extremity clustering, valuation, and ETF proliferation
3. **Confidence** (Low / Medium / High): Reliability of the detection, combining quantitative breadth with narrative confirmation. Script output is capped at Medium; Claude's WebSearch narrative confirmation step can elevate to High.

**Key Features:**
- Cross-sector theme detection using FINVIZ industry data
- Direction-aware scoring (bullish and bearish themes)
- Lifecycle maturity assessment to identify crowded vs. emerging trades
- ETF proliferation scoring (more ETFs = more mature/crowded theme)
- Integration with uptrend-dashboard for 3-point evaluation
- Dual-mode operation: FINVIZ Elite (fast) or public scraping (slower, limited)
- WebSearch-based narrative confirmation for top themes

---

---

## 2. When to Use

**Explicit Triggers:**
- "What market themes are trending right now?"
- "Which sectors are hot/cold?"
- "Detect current market themes"
- "What are the strongest bullish/bearish narratives?"
- "Is AI/clean energy/defense still a strong theme?"
- "Where is sector rotation heading?"
- "Show me thematic investing opportunities"

**Implicit Triggers:**
- User wants to understand broad market narrative shifts
- User is looking for thematic ETF or sector allocation ideas
- User asks about crowded trades or late-cycle themes
- User wants to know which themes are emerging vs. exhausted

**When NOT to Use:**
- Individual stock analysis (use us-stock-analysis instead)
- Specific sector deep-dive with chart reading (use sector-analyst instead)
- Portfolio rebalancing (use portfolio-manager instead)
- Dividend/income investing (use value-dividend-screener instead)

---

---

## 3. Prerequisites

**Required:**
- Python 3.7+ with core dependencies:
  ```bash
  pip install requests beautifulsoup4 lxml pandas numpy yfinance
  ```

**Optional API Keys:**

FINVIZ Elite (recommended for full industry coverage and speed):
```bash
export FINVIZ_API_KEY=your_finviz_elite_api_key_here
```

FMP API (optional, for P/E ratio valuation data):
```bash
export FMP_API_KEY=your_fmp_api_key_here
```

**Optional Python packages:**
- `finvizfinance` - Required for FINVIZ Elite mode
- `PyYAML` - Required for `--themes-config` custom themes

Without FINVIZ Elite, the skill uses public FINVIZ scraping (limited to ~20 stocks per industry, slower rate limits).

---

---

## 4. Quick Start

```bash
# Static mode (no API keys required)
python3 skills/theme-detector/scripts/theme_detector.py --output-dir reports/

# Dynamic stock selection (uses FINVIZ Public screener, no key needed)
python3 skills/theme-detector/scripts/theme_detector.py \
  --dynamic-stocks --output-dir reports/

# With FINVIZ Elite (faster, more reliable)
python3 skills/theme-detector/scripts/theme_detector.py \
  --dynamic-stocks --finviz-api-key $FINVIZ_API_KEY --output-dir reports/
```

---

## 5. Workflow

### Step 1: Verify Environment

Check that API keys are configured (see Prerequisites):

```bash
# Verify FINVIZ Elite API key (optional but recommended)
echo $FINVIZ_API_KEY

# Verify FMP API key (optional)
echo $FMP_API_KEY
```

### Step 2: Execute Theme Detection Script

Run the main detection script:

```bash
python3 skills/theme-detector/scripts/theme_detector.py \
  --output-dir reports/
```

**Script Options:**
```bash
# Full run (public FINVIZ mode, no API key required)
python3 skills/theme-detector/scripts/theme_detector.py \
  --output-dir reports/

# With FINVIZ Elite API key
python3 skills/theme-detector/scripts/theme_detector.py \
  --finviz-api-key $FINVIZ_API_KEY \
  --output-dir reports/

# With FMP API key for enhanced stock data
python3 skills/theme-detector/scripts/theme_detector.py \
  --fmp-api-key $FMP_API_KEY \
  --output-dir reports/

# Custom limits
python3 skills/theme-detector/scripts/theme_detector.py \
  --max-themes 5 \
  --max-stocks-per-theme 10 \
  --output-dir reports/

# Explicit FINVIZ mode
python3 skills/theme-detector/scripts/theme_detector.py \
  --finviz-mode public \
  --output-dir reports/
```

**Expected Execution Time:**
- FINVIZ Elite mode: ~2-3 minutes (14+ themes)
- Public FINVIZ mode: ~5-8 minutes (rate-limited scraping)

### Step 3: Read and Parse Detection Results

The script generates two output files:
- `theme_detector_YYYY-MM-DD_HHMMSS.json` - Structured data for programmatic use
- `theme_detector_YYYY-MM-DD_HHMMSS.md` - Human-readable report

Read the JSON output to understand quantitative results:

```bash
# Find the latest report
ls -lt reports/theme_detector_*.json | head -1

# Read the JSON output
cat reports/theme_detector_YYYY-MM-DD_HHMMSS.json
```

### Step 4: Perform Narrative Confirmation via WebSearch

For the top 5 themes (by Theme Heat score), execute WebSearch queries to confirm narrative strength:

**Search Pattern:**
```
"[theme name] stocks market [current month] [current year]"
"[theme name] sector momentum [current month] [current year]"
```

**Evaluate narrative signals:**
- **Strong narrative**: Multiple major outlets covering the theme, analyst upgrades, policy catalysts
- **Moderate narrative**: Some coverage, mixed sentiment, no clear catalyst
- **Weak narrative**: Little coverage, or predominantly contrarian/skeptical tone

Update Confidence levels based on findings:
- Quantitative High + Narrative Strong = **High** confidence
- Quantitative High + Narrative Weak = **Medium** confidence (possible momentum divergence)
- Quantitative Low + Narrative Strong = **Medium** confidence (narrative may lead price)
- Quantitative Low + Narrative Weak = **Low** confidence

### Step 5: Analyze Results and Provide Recommendations

Cross-reference detection results with knowledge bases:

**Reference Documents to Consult:**
1. `references/cross_sector_themes.md` - Theme definitions and constituent industries
2. `references/thematic_etf_catalog.md` - ETF exposure options by theme
3. `references/theme_detection_methodology.md` - Scoring model details
4. `references/finviz_industry_codes.md` - Industry classification reference

**Analysis Framework:**

For **Hot Bullish Themes** (Heat >= 70, Direction = Bullish):
- Identify lifecycle stage (Emerging = opportunity, Mature/Exhausting = caution)
- List top-performing industries within the theme
- Recommend proxy ETFs for exposure
- Flag if ETF proliferation is high (crowded trade warning)

For **Hot Bearish Themes** (Heat >= 70, Direction = Bearish):
- Identify industries under pressure
- Assess if bearish momentum is accelerating or decelerating
- Recommend hedging strategies or sectors to avoid
- Note potential mean-reversion opportunities if lifecycle is Mature/Exhausting

For **Emerging Themes** (Heat 40-69, Lifecycle = Emerging):
- These may represent early rotation signals
- Recommend monitoring with watchlist
- Identify catalyst events that could accelerate the theme

For **Exhausted Themes** (Heat >= 60, Lifecycle = Exhausting):
- Warn about crowded trade risk
- High ETF count confirms excessive retail participation
- Consider contrarian positioning or reducing exposure

### Step 6: Generate Final Report

Present the final report to the user using the report template structure:

```markdown
# Theme Detection Report
**Date:** YYYY-MM-DD
**Mode:** FINVIZ Elite / Public
**Themes Analyzed:** N
**Data Quality:** [note any limitations]

---

## 6. Resources

**References:**

- `skills/theme-detector/references/cross_sector_themes.md`
- `skills/theme-detector/references/finviz_industry_codes.md`
- `skills/theme-detector/references/thematic_etf_catalog.md`
- `skills/theme-detector/references/theme_detection_methodology.md`

**Scripts:**

- `skills/theme-detector/scripts/config_loader.py`
- `skills/theme-detector/scripts/default_theme_config.py`
- `skills/theme-detector/scripts/etf_scanner.py`
- `skills/theme-detector/scripts/finviz_performance_client.py`
- `skills/theme-detector/scripts/report_generator.py`
- `skills/theme-detector/scripts/representative_stock_selector.py`
- `skills/theme-detector/scripts/scorer.py`
- `skills/theme-detector/scripts/theme_detector.py`
- `skills/theme-detector/scripts/uptrend_client.py`
