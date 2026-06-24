---
layout: default
title: FinViz Screener
grand_parent: English
parent: Skill Guides
nav_order: 1
lang_peer: /ja/skills/finviz-screener/
permalink: /en/skills/finviz-screener/
---

# FinViz Screener
{: .no_toc }

Translate natural language stock screening requests into FinViz screener filter URLs and open them in Chrome. Supports both Japanese and English input.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span> <span class="badge badge-optional">FINVIZ Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/finviz-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/finviz-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

FinViz Screener bridges the gap between what you want to find and how FinViz expects filter codes. Instead of memorizing codes like `fa_epsqoq_o25` or `ta_sma200_pa`, describe your criteria in plain English (or Japanese) and Claude builds the URL for you.

**What it solves:**
- Eliminates the need to learn 500+ FinViz filter codes
- Handles bilingual input (Japanese and English)
- Auto-detects FINVIZ Elite from environment variables
- Validates all filter tokens to prevent URL injection
- Opens results directly in Chrome with OS-appropriate fallbacks

**Key capabilities:**
- 500+ filter codes across fundamentals (P/E, dividends, growth, margins), technicals (RSI, SMA, chart patterns), and descriptives (sector, market cap, country)
- **Theme & Sub-theme cross-screening** -- Combine 30+ investment themes and 268 sub-themes with any filter to screen for cross-sector narratives (e.g., "AI x Logistics", "Data Centers x Power Infrastructure", "Cybersecurity x Cloud")
- View type selection: Overview, Valuation, Financial, Technical, Ownership, Performance, Custom
- Sort order control (ascending or descending by any column)
- Range filter syntax for precise criteria (e.g., `fa_div_3to8` for dividend yield 3-8%)
- 14+ pre-built screening recipes in the reference knowledge base

---

## 2. Prerequisites

- **API Key:** None required for the public FinViz screener
- **FINVIZ Elite (Optional):** Set `$FINVIZ_API_KEY` (any non-empty value) to generate `elite.finviz.com` URLs. The value is not sent to FinViz -- it acts as a local flag for URL switching. You must be logged into an active FINVIZ Elite subscription in your browser
- **Python 3.9+:** Required to run the URL builder script
- **No additional Python dependencies** -- uses only the standard library

> FinViz Screener works entirely without API keys. FINVIZ Elite is only needed if you want real-time data and advanced screener features.
{: .tip }

---

## 3. Quick Start

Tell Claude:

```
Find oversold large caps near 52-week lows with insider buying
```

Claude maps this to filter codes, shows you a confirmation table, and opens the FinViz results page in Chrome. That is all you need to get started.

---

## 4. How It Works

1. **Load filter reference** -- Claude reads the internal filter knowledge base mapping natural language concepts to FinViz codes.
2. **Interpret your request** -- Your description is mapped to specific filter codes using a concept mapping table (e.g., "high dividend" maps to `fa_div_o3`, "large cap" maps to `cap_large`).
3. **Present filter selection** -- Before executing, Claude shows a table of selected filters for your confirmation.
4. **Execute script** -- The `open_finviz_screener.py` script validates filters, builds the URL, and opens Chrome.
5. **Report results** -- Claude reports the constructed URL, the mode used (Public or Elite), and suggests next steps.

**Elite auto-detection:** If the `$FINVIZ_API_KEY` environment variable is set (any non-empty value), the script generates `elite.finviz.com` URLs. The variable acts as a local URL-switch flag -- it is not sent to FinViz servers. You can also force Elite mode with `--elite`. To use Elite results, your browser must be logged into an active FINVIZ Elite subscription.

---

## 5. Usage Examples

### Example 1: Growth Momentum

**Prompt:**
```
Find stocks with quarterly EPS growth > 25%, price above SMA50 and SMA200, and positive performance over the last quarter
```

**Filter codes:** `fa_epsqoq_o25,ta_sma50_pa,ta_sma200_pa,ta_perf_13wup`

**Why useful:** Identifies stocks with strong earnings momentum confirmed by multiple moving average support and sustained quarterly outperformance -- a classic growth momentum setup.

---

### Example 2: CANSLIM + Minervini + VCP Integrated Filter

**Prompt:**
```
Screen for stocks with EPS growth over 25%, revenue growth over 15%, above all major moving averages,
near 52-week high, and with relative volume above 1.5x -- combining CANSLIM fundamentals with
Minervini trend template criteria in a single FinViz screen
```

**Filter codes:** `fa_epsqoq_o25,fa_salesqoq_o15,ta_sma20_pa,ta_sma50_pa,ta_sma200_pa,ta_highlow52w_b0to10h,sh_relvol_o1.5`

**Why useful:** Combines O'Neil-style fundamental growth criteria with Minervini's trend template and VCP-like volume characteristics in one URL, enabling a rapid first-pass filter before running dedicated CANSLIM or VCP screeners.

---

### Example 3: High Dividend Value

**Prompt:**
```
Screen for dividend yield > 4% with P/E under 15
```

**Filter codes:** `fa_div_o4,fa_pe_u15`

**Why useful:** Quick income-oriented screen that targets high-yield stocks with reasonable valuations. A solid starting point for dividend portfolio construction.

---

### Example 4: Oversold Bounce

**Prompt:**
```
Find oversold large caps near 52-week lows with insider buying
```

**Filter codes:** `cap_large,ta_rsi_os30,ta_highlow52w_a0to5l,sh_insidertrans_verypos`

**Why useful:** Identifies large-cap stocks at technical extremes where insiders are buying -- a contrarian signal that can mark reversal points.

---

### Example 5: AI Theme Stocks

**Prompt:**
```
Show me AI and semiconductor stocks with strong momentum
```

**Filter codes:** `theme_artificialintelligence,ta_perf_13wup,ta_sma50_pa,ta_sma200_pa`

**Note:** Theme codes are passed via `--themes "artificialintelligence"`, not `--filters`. The `theme_` prefix is added automatically in the URL.

**Why useful:** Uses FinViz's theme filter to target the AI/semiconductor space, overlaid with momentum confirmation. Quickly surfaces the strongest players in a trending theme.

---

### Example 6: Small Cap Breakout

**Prompt:**
```
Find small cap stocks making new 52-week highs on high relative volume
```

**Filter codes:** `cap_small,ta_highlow52w_b0to5h,sh_relvol_o1.5`

**Why useful:** Targets small-cap breakout candidates where high relative volume confirms genuine buying interest -- a classic momentum entry setup.

---

### Example 7: Japanese Input

**Prompt:**
```
配当利回り5%以上でROE15%以上の大型株を探して
```

**Filter codes:** `fa_div_o5,fa_roe_o15,cap_large`

**Why useful:** Demonstrates full Japanese language support. Claude parses Japanese financial terms and maps them to the same FinViz filter codes, making the skill accessible to bilingual users.

---

### Example 8: Programmatic Use (URL Only)

**Command:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --filters "fa_div_o3,fa_pe_u20,cap_large" \
  --view valuation \
  --order dividendyield \
  --url-only
```

**Output:**
```
[Public] https://finviz.com/screener.ashx?v=121&f=cap_large,fa_div_o3,fa_pe_u20&o=dividendyield
```

**Why useful:** The `--url-only` flag prints the URL without opening a browser, making it suitable for scripting, logging, or embedding in other workflows.

---

### Example 9: Theme Cross-Screening (AI x Logistics, Data Centers x Power)

Traditional sector/industry filters limit you to a single dimension. FinViz's theme and sub-theme filters let you screen along *narrative* axes that cut across sectors.

**Prompt A: AI x Logistics**
```
Find mid-cap and above stocks in both AI and logistics themes with strong quarterly performance
```

**Command:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --themes "artificialintelligence" \
  --subthemes "ecommercelogistics" \
  --filters "cap_midover,ta_perf_13wup" \
  --url-only
```

**Prompt B: Data Centers x Power Infrastructure**
```
Show me data center and power infrastructure stocks
```

**Command:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --subthemes "clouddatacenters,aienergy" \
  --url-only
```

**Prompt C: Cybersecurity x Cloud**
```
Cybersecurity and cloud stocks with high ROE
```

**Command:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --themes "cybersecurity" \
  --subthemes "aicloud" \
  --filters "fa_roe_o15" \
  --url-only
```

**Why useful:** Sector filters group companies by what they *are* (Technology, Utilities, Real Estate). Theme filters group companies by what *trend* they ride. Combining themes and sub-themes uncovers stocks at the intersection of secular growth narratives -- e.g., logistics companies investing in AI automation, or utilities exposed to data center power demand -- that traditional sector filters would miss entirely.

---

### Screening Recipes

Ready-to-use filter combinations for common investment strategies. Each recipe includes iterative refinement tips.

#### Recipe 1: High-Dividend Growth Stocks (Kanchi-Style)

**Goal:** High yield + dividend growth + earnings growth, excluding yield traps.

**Filters:** `fa_div_3to8,fa_sales5years_pos,fa_eps5years_pos,fa_divgrowth_5ypos,fa_payoutratio_u60,geo_usa`
**View:** Financial

| Filter | Purpose |
|--------|---------|
| `fa_div_3to8` | Yield 3-8% (caps high-yield traps) |
| `fa_sales5years_pos` | Positive 5Y revenue growth |
| `fa_eps5years_pos` | Positive 5Y EPS growth |
| `fa_divgrowth_5ypos` | Positive 5Y dividend growth |
| `fa_payoutratio_u60` | Payout ratio < 60% (sustainability) |
| `geo_usa` | US-listed stocks |

**Refinement:** Start with `fa_div_o3` → add `fa_div_3to8` to cap yield → add `fa_payoutratio_u60` to exclude traps.

#### Recipe 2: Minervini Trend Template + VCP

**Goal:** Stage 2 uptrend stocks with volatility contraction.

**Filters:** `ta_sma50_pa,ta_sma200_pa,ta_sma200_sb50,ta_highlow52w_0to25-bhx,ta_perf_26wup,sh_avgvol_o300,cap_midover`
**View:** Technical

| Filter | Purpose |
|--------|---------|
| `ta_sma50_pa` | Price above 50-day SMA |
| `ta_sma200_pa` | Price above 200-day SMA |
| `ta_sma200_sb50` | 200 SMA below 50 SMA (uptrend) |
| `ta_highlow52w_0to25-bhx` | Within 25% of 52W high |
| `ta_perf_26wup` | Positive 26-week performance |
| `sh_avgvol_o300` | Avg volume > 300K |
| `cap_midover` | Mid cap and above |

**VCP tightening:** Add `ta_volatility_wo3,ta_highlow20d_b0to5h,sh_relvol_u1` for low volatility + near 20-day high + below-average volume.

#### Recipe 3: Unfairly Sold-Off Growth Stocks

**Goal:** Fundamentally strong companies with recent sharp declines.

**Filters:** `fa_sales5years_o5,fa_eps5years_o10,fa_roe_o15,fa_salesqoq_pos,fa_epsqoq_pos,ta_perf_13wdown,ta_highlow52w_10to30-bhx,cap_large,sh_avgvol_o200`
**View:** Overview → switch to Valuation after reviewing candidates

| Filter | Purpose |
|--------|---------|
| `fa_sales5years_o5` | 5Y sales growth > 5% |
| `fa_eps5years_o10` | 5Y EPS growth > 10% |
| `fa_roe_o15` | ROE > 15% |
| `fa_salesqoq_pos` | Positive QoQ sales growth |
| `fa_epsqoq_pos` | Positive QoQ EPS growth |
| `ta_perf_13wdown` | Negative 13-week performance |
| `ta_highlow52w_10to30-bhx` | 10-30% below 52W high |
| `cap_large` | Large cap |
| `sh_avgvol_o200` | Avg volume > 200K |

#### Recipe 4: Turnaround Stocks

**Goal:** Companies with previously declining earnings now showing recovery.

**Filters:** `fa_eps5years_neg,fa_epsqoq_pos,fa_salesqoq_pos,ta_highlow52w_b30h,ta_perf_13wup,cap_smallover,sh_avgvol_o200`
**View:** Performance

| Filter | Purpose |
|--------|---------|
| `fa_eps5years_neg` | Negative 5Y EPS growth (prior decline) |
| `fa_epsqoq_pos` | Positive QoQ EPS growth (recovery) |
| `fa_salesqoq_pos` | Positive QoQ sales growth (recovery) |
| `ta_highlow52w_b30h` | Within 30% of 52W high |
| `ta_perf_13wup` | Positive 13-week performance |
| `cap_smallover` | Small cap and above |
| `sh_avgvol_o200` | Avg volume > 200K |

#### Recipe 5: Momentum Trade Candidates

**Goal:** Short-term momentum leaders near 52W highs with increasing volume.

**Filters:** `ta_sma50_pa,ta_sma200_pa,ta_highlow52w_b0to3h,ta_perf_4wup,sh_relvol_o1.5,sh_avgvol_o1000,cap_midover`
**View:** Technical

| Filter | Purpose |
|--------|---------|
| `ta_sma50_pa` | Price above 50-day SMA |
| `ta_sma200_pa` | Price above 200-day SMA |
| `ta_highlow52w_b0to3h` | Within 3% of 52W high |
| `ta_perf_4wup` | Positive 4-week performance |
| `sh_relvol_o1.5` | Relative volume > 1.5x |
| `sh_avgvol_o1000` | Avg volume > 1M |
| `cap_midover` | Mid cap and above |

#### Tips: Iterative Refinement

Screening works best as a dialogue:

1. **Start broad** — 3-4 core filters for an initial set
2. **Check count** — >100 results? add filters. <5 results? relax constraints
3. **Switch views** — `overview` first, then `financial` or `valuation` for depth
4. **Layer technicals** — after confirming fundamentals, add `ta_` filters to time entries

---

## 6. Understanding the Output

After execution, Claude reports:

1. **Constructed URL** -- The full FinViz screener URL with all applied filters.
2. **Mode** -- Whether Public or Elite mode was used.
3. **Filter summary** -- A table listing each applied filter code and its meaning.
4. **Suggested next steps** -- Recommendations like "Sort by dividend yield" or "Switch to Financial view for detailed ratios."

The FinViz results page itself shows stocks in a sortable table. Use the view selector (Overview, Valuation, Financial, Technical, Ownership, Performance) to examine different data points.

---

## 7. Tips & Best Practices

- **Use range filters for precision.** Instead of combining separate "greater than" and "less than" filters, use range syntax: `fa_div_3to8` for dividend yield between 3% and 8%. This eliminates dividend yield traps at extreme levels.
- **Combine fundamental and technical filters.** Growth momentum setups that pair earnings growth (`fa_epsqoq_o25`) with trend confirmation (`ta_sma50_pa,ta_sma200_pa`) are more reliable than either alone.
- **Start broad, then narrow.** Begin with 2-3 filters and add more only if the result set is too large. Over-filtering can eliminate good candidates.
- **Use `--view` strategically.** The `valuation` view is best for dividend/value screens; `technical` view works best for momentum and breakout screens.
- **Check the `--order` option.** Sorting by the metric most relevant to your strategy (e.g., `dividendyield`, `-marketcap`, `change`) surfaces the best candidates first.
- **Japanese users:** The skill handles full-width characters and Japanese financial terminology natively. No translation step needed.

---

## 8. Combining with Other Skills

| Workflow | How to Combine |
|----------|---------------|
| **Growth stock deep dive** | Use FinViz Screener to build an initial universe, then feed top results into CANSLIM Screener for rigorous 7-component scoring |
| **Dividend portfolio building** | Screen with FinViz (`fa_div_o3,fa_pe_u20`), then run Value Dividend Screener for sustainability analysis |
| **Theme-based investing** | Use Theme Detector to identify hot themes, then use FinViz Screener with theme filters (`--themes "artificialintelligence"`) to find individual stocks |
| **Technical confirmation** | After FinViz surfaces candidates, use Technical Analyst for detailed chart reading on the top picks |
| **Position sizing** | Once you identify entry candidates, pass them to Position Sizer for risk-based share count calculation |

---

## 9. Troubleshooting

### Chrome does not open

**Cause:** Chrome is not installed, or the path is not detected.

**Fix:** The script falls back through: Chrome > default browser > `webbrowser.open()`. On macOS, ensure Google Chrome is installed in `/Applications/`. On Linux, ensure `google-chrome` or `chromium-browser` is in your PATH.

### "Invalid filter token" error

**Cause:** A filter code contains invalid characters (spaces, `&`, `=`).

**Fix:** Filter tokens must only contain lowercase letters, digits, underscores, and dots. Check for typos in manually entered filter codes.

### "Unknown filter prefix" warning

**Cause:** A filter uses a prefix not in the known set.

**Fix:** This is a warning, not an error. The URL is still built. The warning alerts you that the filter prefix is unrecognized, which may indicate a typo or a new FinViz filter not yet cataloged.

### Elite mode not activating

**Cause:** `$FINVIZ_API_KEY` environment variable is not set, or you are not logged into FINVIZ Elite in your browser.

**Fix:** Set `export FINVIZ_API_KEY=1` (any non-empty value) to switch to Elite URLs. Then ensure you are logged into your FINVIZ Elite account in Chrome. The env var is a local flag -- it does not authenticate with FinViz.

---

## 10. Reference

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--filters` | No* | -- | Comma-separated FinViz filter codes |
| `--themes` | No* | -- | Comma-separated theme slugs (e.g., `artificialintelligence,cybersecurity`) |
| `--subthemes` | No* | -- | Comma-separated sub-theme slugs (e.g., `aicloud,aienergy`) |
| `--elite` | No | Auto-detected | Force Elite mode (`elite.finviz.com`) |
| `--view` | No | `overview` | View type: overview, valuation, financial, technical, ownership, performance, custom |
| `--order` | No | None | Sort order code (e.g., `-marketcap`, `dividendyield`). Prefix `-` for descending |
| `--url-only` | No | `false` | Print URL without opening a browser |

\* At least one of `--filters`, `--themes`, or `--subthemes` is required.

### View Type Codes

| Name | Code | Best For |
|------|------|----------|
| Overview | `111` | General screening, first look |
| Valuation | `121` | P/E, P/B, PEG, dividend analysis |
| Ownership | `131` | Institutional holdings, insider activity |
| Performance | `141` | Returns across timeframes |
| Custom | `152` | User-defined columns |
| Financial | `161` | Revenue, margins, ROE, debt ratios |
| Technical | `171` | RSI, SMA, beta, volatility |

### Common Filter Codes Quick Reference

| Concept | Filter Code |
|---------|-------------|
| High dividend (>3%) | `fa_div_o3` |
| Low P/E (<20) | `fa_pe_u20` |
| EPS growth >25% QoQ | `fa_epsqoq_o25` |
| Price above SMA200 | `ta_sma200_pa` |
| RSI oversold (<30) | `ta_rsi_os30` |
| Large cap | `cap_large` |
| Insider buying | `sh_insidertrans_verypos` |
| AI theme | `theme_artificialintelligence` |
| Near 52W high | `ta_highlow52w_b0to5h` |
| High relative volume | `sh_relvol_o1.5` |

> **Note:** Theme and sub-theme codes use `--themes` / `--subthemes` options, not `--filters`. The script adds the `theme_` / `subtheme_` prefix automatically when building the URL.
