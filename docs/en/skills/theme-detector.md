---
layout: default
title: Theme Detector
grand_parent: English
parent: Skill Guides
nav_order: 4
lang_peer: /ja/skills/theme-detector/
permalink: /en/skills/theme-detector/
---

# Theme Detector
{: .no_toc }

Detect and rank trending market themes across sectors using 3-dimensional scoring: Theme Heat, Lifecycle Maturity, and Confidence. Identifies both bullish and bearish themes.
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

The Theme Detector identifies which market themes (AI & Semiconductors, Clean Energy, Gold, Cybersecurity, Defense, etc.) are gaining or losing momentum right now. Instead of analyzing individual stocks, it operates at the theme level -- aggregating performance, volume, and breadth data across all constituent industries and ETFs within each theme.

**What it solves:**
- Staying current on which market narratives are driving capital flows
- Distinguishing early-stage themes from crowded trades approaching exhaustion
- Identifying bearish themes (sectors under pressure) with equal sensitivity to bullish themes
- Providing a structured, quantitative view of thematic investing opportunities

**3-Dimensional Scoring Model:**

| Dimension | Range | What It Measures |
|-----------|-------|-----------------|
| **Theme Heat** | 0-100 | Strength of the theme: momentum, volume intensity, uptrend ratio, breadth |
| **Lifecycle Maturity** | Emerging / Accelerating / Trending / Mature / Exhausting | How developed the theme is: duration, RSI extremity, valuation, ETF proliferation |
| **Confidence** | Low / Medium / High | Reliability of detection: quantitative breadth combined with narrative confirmation |

**14+ themes tracked:** AI & Semiconductors, Clean Energy & EV, Cybersecurity, Cloud Computing & SaaS, Biotech & Genomics, Infrastructure & Construction, Gold & Precious Metals, Defense & Aerospace, Energy (Oil & Gas), Consumer Staples & Defensive, Financial & Banking, Real Estate, Blockchain & Crypto, Healthcare Innovation.

---

## 2. Prerequisites

**Core functionality requires no API keys.** The skill uses FINVIZ public screener data and yfinance for ETF/stock metrics.

**Python Dependencies:**
- Python 3.7+
- `requests`
- `beautifulsoup4`
- `lxml`
- `pandas`
- `numpy`
- `yfinance`

```bash
pip install requests beautifulsoup4 lxml pandas numpy yfinance
```

**Optional Python packages:**
- `finvizfinance` (for FINVIZ Elite mode)
- `PyYAML` (for `--themes-config` custom themes)

**Optional APIs for enhanced results:**

| API | Benefit | Cost |
|-----|---------|------|
| FINVIZ Elite | Full stock universe per industry, faster execution (~2-3 min vs 5-8 min), real-time data | $39.50/mo |
| FMP API | P/E ratio valuation data for lifecycle assessment, ETF holdings for theme confirmation | Free tier: 250/day |

> The skill works fully without any API keys. FINVIZ Elite and FMP enhance coverage and speed but are not required.
{: .tip }

---

## 3. Quick Start

```bash
# No API key needed -- uses FINVIZ public scraping + yfinance
python3 skills/theme-detector/scripts/theme_detector.py --output-dir reports/

# Or tell Claude:
# "What market themes are trending right now?"
```

> **Note:** Script-only output caps Confidence at Medium (2 of 3 confirmation layers). Claude's WebSearch narrative confirmation can elevate to High.
{: .tip }

---

## 4. How It Works

1. **Industry data collection** -- Scans ~145 FINVIZ industries for performance, volume, and stock-level metrics (via FINVIZ Elite API or public scraping).
2. **Theme classification** -- Maps industries to cross-sector themes using definitions in `cross_sector_themes.md`. Each theme requires a minimum number of constituent industries to show activity before it is classified.
3. **Heat scoring** -- Calculates Theme Heat (0-100) from four sub-components:
   - **Momentum strength** -- Multi-timeframe performance weighting
   - **Volume intensity** -- Current volume vs historical average
   - **Uptrend ratio** -- Percentage of constituent stocks in technical uptrends
   - **Breadth** -- Ratio of matching industries with directionally-aligned weighted returns (positive for LEAD themes, negative for LAG themes). Industry-level participation rate, not stock-level
4. **Lifecycle assessment** -- Determines maturity stage from:
   - **Duration score** -- How long the theme has been active
   - **Extremity clustering** -- Concentration of RSI readings at extremes
   - **Price extreme saturation** -- Stocks at 52-week highs/lows
   - **Valuation premium** -- P/E premium vs historical norms (requires FMP)
   - **ETF proliferation** -- Number of thematic ETFs (more = more mature/crowded)
5. **Direction detection** -- Classifies each theme as bullish, bearish, or neutral based on weighted industry performance, uptrend ratio, and volume confirmation.
6. **Narrative confirmation** -- For top 5 themes, Claude performs WebSearch queries to validate whether the quantitative signal aligns with real-world news and analyst coverage.

---

## 5. Usage Examples

### Example 1: Quick Theme Scan (No API Needed)

**Prompt:**
```
Detect current market themes
```

**What happens:** The detector scans all ~145 FINVIZ industries using public scraping, classifies them into 14+ themes, scores each on Heat/Lifecycle/Confidence, and generates a ranked report. Takes about 5-8 minutes in public mode.

**Why useful:** The fastest way to get a birds-eye view of where capital is flowing across the market without needing any API subscriptions.

---

### Example 2: Enhanced with FINVIZ Elite

**Command:**
```bash
python3 skills/theme-detector/scripts/theme_detector.py \
  --finviz-api-key $FINVIZ_API_KEY \
  --output-dir reports/
```

**Why useful:** FINVIZ Elite provides the full stock universe per industry (vs ~20 stocks in public mode), real-time data, and faster execution (~2-3 minutes). Results are more accurate, especially for themes with many small-cap constituents.

---

### Example 3: Lifecycle Assessment

**Prompt:**
```
Is the AI theme still early or getting crowded?
```

**What Claude analyzes:**
- **Duration:** How many months has AI been trending?
- **RSI extremity:** Are AI stocks clustered at overbought levels?
- **ETF proliferation:** Count of AI-themed ETFs (SMH, SOXX, AIQ, BOTZ, CHAT) -- more ETFs = more retail participation = more mature
- **Valuation premium:** Current P/E vs historical average for semiconductor/software stocks

**Interpretation:**
- **Emerging (0-20 maturity):** Few participants, low ETF count, theme just starting -- best time to enter
- **Accelerating (20-40):** Growing participation, some ETFs launched, media coverage increasing
- **Trending (40-60):** Strong momentum, broad analyst coverage, mainstream theme
- **Mature (60-80):** Broad participation, multiple ETFs, consensus trade, valuations stretched
- **Exhausting (80-100):** Maximum ETF proliferation, extreme valuations, contrarian signals appearing

---

### Example 4: Bearish Theme Identification

**Prompt:**
```
What are the strongest bearish themes in the market right now?
```

**What happens:** The detector identifies themes with negative weighted performance where uptrend ratios are below 50% and volume confirms distribution (selling pressure). These are presented with the same Heat/Lifecycle/Confidence scoring as bullish themes, using inverted indicators.

**Why useful:** Bearish themes reveal which sectors to avoid, hedge against, or watch for mean-reversion opportunities if the lifecycle reaches Exhausting.

---

### Example 5: Heat Score Interpretation

The Heat score combines four sub-components:

| Heat Score | Interpretation | Action |
|------------|---------------|--------|
| 80-100 | Extremely strong momentum + volume + breadth | Consider exposure if lifecycle is Emerging/Accelerating |
| 60-79 | Solid theme momentum with broad participation | Standard allocation, monitor lifecycle |
| 40-59 | Moderate theme signal, may be emerging or fading | Watchlist, wait for confirmation |
| 20-39 | Weak theme signal | Do not allocate, monitor for reversal |
| 0-19 | No meaningful theme activity | Ignore |

**The golden combination:** High Heat + Emerging lifecycle = Best opportunity. The theme has strong momentum but has not yet attracted the crowd.

> High Heat + Mature/Exhausting lifecycle = Caution. Strong momentum but the trade is crowded and at risk of reversal.
{: .warning }

---

### Example 6: Theme to Individual Stock Pipeline

**Step 1 -- Detect theme:**
```
What market themes are trending right now?
```

Suppose Theme Detector identifies "AI & Semiconductors" as the top bullish theme (Heat: 85, Lifecycle: Accelerating, Confidence: Medium).

**Step 2 -- Research individual stocks:**
```
Analyze NVDA using CANSLIM methodology
```

or

```
Screen for AI semiconductor stocks with strong momentum on FinViz
```

**Why useful:** Theme Detector provides the top-down view (which sectors/themes are hot), and then you drill down to individual stocks using CANSLIM, VCP, or FinViz screeners. This ensures your stock picks align with the dominant market narrative.

---

## 6. Understanding the Output

The detector generates:
- `theme_detector_YYYY-MM-DD_HHMMSS.json` -- Structured data for programmatic use
- `theme_detector_YYYY-MM-DD_HHMMSS.md` -- Human-readable report

**Report sections:**

1. **Theme Dashboard** -- Top themes table with Heat, Direction, Lifecycle, and Confidence columns
2. **Bullish Themes Detail** -- Each bullish theme with:
   - Heat score breakdown (momentum, volume, uptrend, breadth sub-scores)
   - Lifecycle maturity assessment with stage classification
   - Top-performing industries within the theme
   - Representative stocks and proxy ETFs
   - Narrative confirmation from WebSearch
3. **Bearish Themes Detail** -- Same structure for bearish themes
4. **All Themes Summary** -- Complete ranking table for all detected themes
5. **Industry Rankings** -- Top and bottom performing individual industries
6. **Sector Uptrend Ratios** -- Sector-level breadth aggregation (when uptrend data is available)
7. **Methodology Notes** -- Brief explanation of the scoring model

**Direction classification:**

Direction is determined by majority vote of constituent industries' relative rank:
1. All ~145 industries are ranked by multi-timeframe momentum score
2. Top-half industries = "bullish", bottom-half = "bearish"
3. Each theme's direction is the majority vote of its matched industries

**Display mapping:**
- "bullish" → **LEAD** (relative outperformance of matched industries)
- "bearish" → **LAG** (relative underperformance of matched industries)
- A LAG theme may have positive absolute returns -- it indicates relative underperformance, not a short signal

---

## 7. Tips & Best Practices

- **Run weekly for strategic allocation.** Theme trends shift on a weekly-to-monthly timeframe. Daily scans add noise without changing conclusions.
- **Combine Heat with Lifecycle for decision-making.** Heat alone can be misleading -- a theme with Heat 90 and Exhausting lifecycle may be about to reverse.
- **Use proxy ETFs for quick exposure.** Each theme includes proxy ETFs (e.g., SMH/SOXX for AI & Semiconductors, XBI/IBB for Biotech). These provide immediate, diversified theme exposure.
- **Watch ETF proliferation as a contrarian signal.** When many new thematic ETFs launch, it typically indicates late-cycle retail participation. The more ETFs tracking a theme, the closer it may be to exhaustion.
- **Cross-reference with narrative.** Quantitative High + Narrative Weak is a divergence signal (momentum without conviction). Quantitative Low + Narrative Strong may indicate an emerging theme where price action has not yet caught up.
- **Public mode is sufficient for weekly analysis.** The ~20 stocks per industry in public mode capture the major players. Elite mode adds value for small-cap themes or when you need real-time data.

---

## 8. Combining with Other Skills

| Workflow | Steps |
|----------|-------|
| **Theme-first investing** | Theme Detector (identify hot theme) > FinViz Screener (filter theme-specific stocks) > US Stock Analysis (deep dive on top picks) |
| **Theme + CANSLIM** | Identify strong themes, then run CANSLIM Screener with a custom `--universe` of stocks from that theme to find the best growth candidates |
| **Macro alignment** | Run Theme Detector alongside Market Environment Analysis and Sector Analyst to verify that theme strength aligns with broader macro conditions |
| **Bearish theme hedging** | When bearish themes are detected, use Options Strategy Advisor to evaluate protective strategies (puts, put spreads) on exposed holdings |
| **Lifecycle monitoring** | Track theme lifecycle stage monthly. When a previously Emerging theme moves to Mature, consider reducing exposure and rotating into newer themes |
| **Scenario analysis** | Use Scenario Analyzer to project how current news headlines may affect specific themes, then cross-check with Theme Detector's quantitative scoring |

---

## 9. Troubleshooting

### Slow execution in public mode

**Expected behavior:** Public FINVIZ mode takes 5-8 minutes due to rate limiting (2.0 seconds between requests for ~145 industries).

**Fix:** If speed is critical, set up FINVIZ Elite ($39.50/mo) for 2-3 minute execution with `--finviz-api-key`.

### Missing Python dependencies

```
ModuleNotFoundError: No module named 'pandas'
```

Install all required packages:
```bash
pip install requests beautifulsoup4 lxml pandas numpy yfinance
```

### "Theme not detected" for a specific theme

**Cause:** Theme detection requires a minimum number of matching industries with activity. The global `cross_sector_min_matches` setting (default: 2, configurable in themes.yaml) controls this threshold. If too few industries have meaningful data, the theme is not classified.

**Fix:** This is expected behavior for themes with narrow industry representation. Check `references/cross_sector_themes.md` for design-intent minimums. FINVIZ Elite provides better coverage and may resolve this.

### Limited data in public mode

Public FINVIZ scraping returns ~20 stocks per industry (first page only). This can miss small-cap signals within a theme.

**Fix:** For comprehensive analysis, use FINVIZ Elite which returns the full stock universe per industry. For most theme-level decisions, however, the large-cap representation from public mode is sufficient.

### Narrative confirmation unavailable

WebSearch-based narrative confirmation depends on internet connectivity and search result quality. If WebSearch returns limited results:
- Confidence level defaults to the quantitative assessment only
- This is noted in the report as a data quality limitation
- The quantitative scoring remains fully valid

---

## 10. Reference

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--output-dir` | No | `reports/` | Output directory for reports |
| `--finviz-api-key` | No | `$FINVIZ_API_KEY` | FINVIZ Elite API key |
| `--fmp-api-key` | No | `$FMP_API_KEY` | FMP API key for valuation data |
| `--finviz-mode` | No | Auto-detected | Force `public` or `elite` mode |
| `--max-themes` | No | `10` | Maximum themes in report |
| `--max-stocks-per-theme` | No | `10` | Max representative stocks per theme |
| `--top` | No | `3` | Top N themes in detail sections |
| `--themes-config` | No | bundled `themes.yaml` | Custom themes YAML path |
| `--discover-themes` | No | `false` | Auto-discover themes from unmatched industries |
| `--dynamic-stocks` | No | `false` | Dynamic stock selection via FINVIZ |
| `--dynamic-min-cap` | No | `small` | Min market cap for dynamic stocks (micro/small/mid) |

### FINVIZ Mode Comparison

| Feature | Elite Mode | Public Mode |
|---------|-----------|-------------|
| Industry coverage | All ~145 industries | All ~145 industries |
| Stocks per industry | Full universe | ~20 stocks (page 1) |
| Rate limiting | 0.5s between requests | 2.0s between requests |
| Data freshness | Real-time | 15-minute delayed |
| API key required | Yes ($39.50/mo) | No |
| Execution time | ~2-3 minutes | ~5-8 minutes |

### Theme Heat Sub-Components

| Sub-Component | What It Measures |
|---------------|-----------------|
| Momentum Strength | Multi-timeframe performance weighting across theme industries |
| Volume Intensity | Current volume vs historical average for theme stocks |
| Uptrend Ratio | Percentage of theme stocks in technical uptrends |
| Breadth | Ratio of matching industries with directionally-aligned weighted returns (industry-level participation) |

### Lifecycle Stages

| Stage | Maturity | Characteristics |
|-------|----------|----------------|
| Emerging | 0-20 | Few participants, low ETF count, limited media coverage |
| Accelerating | 20-40 | Growing participation, ETFs launching, analyst upgrades |
| Trending | 40-60 | Strong momentum, broad analyst coverage, mainstream theme |
| Mature | 60-80 | Broad participation, many ETFs, consensus trade, elevated valuations |
| Exhausting | 80-100 | Max ETF proliferation, extreme valuations, contrarian signals |

### Cross-Sector Themes Reference

| Theme | Key Industries | Proxy ETFs |
|-------|---------------|------------|
| AI & Semiconductors | Semiconductors, Software - Application/Infrastructure, IT Services | SMH, SOXX, AIQ, BOTZ |
| Clean Energy & EV | Solar, Utilities - Renewable, Auto Manufacturers, Electrical Equipment | ICLN, TAN, DRIV, LIT |
| Cybersecurity | Software - Infrastructure, IT Services, Communication Equipment | CIBR, HACK, BUG |
| Cloud & SaaS | Software - Application/Infrastructure, IT Services | SKYY, WCLD, CLOU |
| Biotech & Genomics | Biotechnology, Drug Manufacturers, Medical Devices, Diagnostics | XBI, IBB, ARKG |
| Infrastructure | Engineering & Construction, Building Materials, Heavy Machinery, Steel | PAVE, IFRA |
| Gold & Precious Metals | Gold, Silver, Mining | GLD, GDX, SIL |
| Defense & Aerospace | Aerospace & Defense, Communication Equipment | ITA, XAR, PPA |
