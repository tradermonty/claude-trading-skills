---
layout: default
title: Market Breadth Analyzer
grand_parent: English
parent: Skill Guides
nav_order: 5
lang_peer: /ja/skills/market-breadth-analyzer/
permalink: /en/skills/market-breadth-analyzer/
---

# Market Breadth Analyzer
{: .no_toc }

Quantify market breadth health using a data-driven 6-component scoring system (0-100). Uses TraderMonty's publicly available CSV data to measure how broadly the market is participating in a rally or decline.
{: .fs-6 .fw-300 }

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

Market Breadth Analyzer answers the question every equity investor should ask before adding exposure: "Is this rally broad-based, or are a handful of mega-caps masking underlying weakness?"

**What it solves:**
- Provides a single composite score (0-100, where 100 = healthy) across 6 weighted components
- Eliminates subjective chart reading with a fully reproducible, quantitative approach
- Tracks score history across runs to detect improving or deteriorating trends
- Maps health zones directly to recommended equity exposure levels
- Handles missing data gracefully with automatic weight redistribution

**Key capabilities:**
- 6-component auto-weighted scoring: Breadth Level & Trend (25%), 8MA vs 200MA Crossover (20%), Peak/Trough Cycle (20%), Bearish Signal (15%), Historical Percentile (10%), S&P 500 Divergence (10%)
- 5 health zones: Strong (80-100), Healthy (60-79), Neutral (40-59), Weakening (20-39), Critical (0-19)
- Multi-window divergence detection (20-day + 60-day) between S&P 500 price and breadth
- Rolling score history (up to 20 entries) with trend labels: Improving, Stable, Deteriorating

<span class="badge badge-free">No API</span>

---

## 2. Prerequisites

- **API Key:** None required -- uses freely available CSV data from GitHub Pages
- **Python 3.9+:** Required to run the analysis script
- **Internet connection:** Needed to fetch CSV data from TraderMonty's public GitHub Pages site
- **No additional Python dependencies** -- uses only the standard library

> Market Breadth Analyzer works entirely without API keys or paid subscriptions. Data is updated twice daily via GitHub Actions and hosted publicly.
{: .tip }

---

## 3. Quick Start

Run the analysis script:

```bash
python3 skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py --output-dir reports/
```

The script fetches the latest CSV data, scores all 6 components, and outputs a composite health score with zone classification and recommended actions. That is all you need to get started.

---

## 4. How It Works

1. **Fetch data** -- The script downloads two CSV files from TraderMonty's GitHub Pages: a detail file (~2,500 rows from 2016 to present) and a summary file (8 aggregate metrics).
2. **Validate freshness** -- If the latest data point is more than 5 days old, a staleness warning is included in the report.
3. **Score 6 components** -- Each component is scored independently on a 0-100 scale using the latest data row plus historical context. Components that lack sufficient data are excluded, and their weights are proportionally redistributed among the remaining components.
4. **Compute composite score** -- The weighted average of all available component scores produces the final 0-100 composite.
5. **Classify health zone** -- The composite maps to one of 5 zones (Strong, Healthy, Neutral, Weakening, Critical), each with a recommended equity exposure range.
6. **Track history** -- The score is appended to a rolling history file. When multiple observations exist, the trend (Improving / Stable / Deteriorating) is computed from the delta between the first and last entries.
7. **Output reports** -- JSON and Markdown files are saved to the output directory.

**Weight redistribution:** If any component lacks data (e.g., too few rows for divergence analysis), its weight is excluded and the remaining weights rescale proportionally so they still sum to 100%.

---

## 5. Usage Examples

### Example 1: Morning Market Health Check

**Prompt:**
```
How healthy is market breadth right now?
```

**What happens:** The script runs with default settings, fetches the latest CSV, and returns the composite score, health zone, and recommended equity exposure. A quick daily check before the open.

**Why useful:** Establishes the baseline market environment in seconds. A score in the Strong zone (80-100) means growth and momentum strategies are well-supported; a Weakening zone (20-39) signals it is time to tighten stops and raise cash.

---

### Example 2: Rally Breadth Evaluation

**Prompt:**
```
The S&P 500 is at a new all-time high. Is the rally broad-based or narrow?
```

**What happens:** The analyzer evaluates the Breadth Level & Trend component (C1) alongside the S&P 500 Divergence component (C6). If the index is rising but breadth is declining, the divergence score drops sharply and the composite reflects the risk.

**Why useful:** New highs on narrow leadership are one of the most reliable warning signs of a market top. This analysis quantifies what chart readers see visually.

---

### Example 3: Narrow Leadership Warning Detection

**Prompt:**
```
Are fewer stocks participating in the current advance? Check for narrowing breadth.
```

**What happens:** The analyzer examines the 8MA level relative to the 200MA, checks for bearish divergence in the 20-day and 60-day windows, and flags any Early Warning signals where short-term breadth is deteriorating while structural breadth looks healthy.

**Why useful:** Narrowing breadth often precedes corrections by weeks. Detecting the Early Warning flag gives time to adjust portfolio exposure before the decline becomes obvious.

---

### Example 4: S&P 500 Divergence Analysis

**Prompt:**
```
Is there a divergence between S&P 500 price action and market breadth?
```

**What happens:** Component C6 uses multi-window analysis (20-day at 40% weight, 60-day at 60% weight) to measure whether price and breadth are moving in the same direction. Four patterns are identified: healthy alignment, dangerous narrow market, bullish divergence (potential bottom), and consistent decline.

**Why useful:** The dual-window approach catches both emerging short-term divergence and structural medium-term divergence. The most dangerous pattern -- S&P up while breadth declines -- preceded major tops in 2000, 2007, and 2021.

---

### Example 5: Historical Percentile Comparison

**Prompt:**
```
Where does current breadth rank compared to the last 10 years?
```

**What happens:** Component C5 places the current 8MA reading into the full historical distribution (2016-present). The report shows the percentile rank and flags whether breadth is near the average peak level (overheated, -10 adjustment) or near the average trough level (contrarian opportunity, +10 adjustment).

**Why useful:** Context matters. An 8MA of 0.55 might feel neutral, but if historical peaks average 0.73, there is still meaningful room for improvement. Conversely, readings near historical trough levels (~0.23) have historically been excellent long-term entry points.

---

### Example 6: Zone Transition for Exposure Decisions

**Prompt:**
```
Breadth was Weakening last week. Has it improved enough to add positions?
```

**What happens:** The analyzer computes today's score and compares it against the stored history. The trend label (Improving, Stable, or Deteriorating) plus the zone transition (e.g., Weakening to Neutral) guides the exposure decision. If the score crossed from 39 to 42, the zone changed from Weakening to Neutral, suggesting a cautious increase in equity exposure from the 40-60% range to the 60-75% range.

**Why useful:** Zone transitions are actionable signals. Rather than reacting to a single reading, the history-based trend ensures you are responding to a genuine shift in market breadth, not noise.

---

## 6. Understanding the Output

After execution, the script produces two files and prints a summary to the console:

1. **Composite Score** -- A single 0-100 number representing overall market health (100 = maximum health).
2. **Health Zone** -- One of 5 zones with recommended equity exposure: Strong (90-100%), Healthy (75-90%), Neutral (60-75%), Weakening (40-60%), Critical (25-40%).
3. **Component Breakdown** -- Each of the 6 components with its individual score, effective weight, and a brief interpretation.
4. **Data Quality Label** -- Complete (6/6 components), Partial (4-5/6), or Limited (0-3/6), indicating confidence level.
5. **Score History & Trend** -- Previous scores and the trend direction (Improving / Stable / Deteriorating).
6. **Recommended Actions** -- Concrete steps based on the current zone (e.g., "Full position sizing; growth/momentum favored" in Strong zone).
7. **Key Levels to Watch** -- Important thresholds such as 8MA crossing 200MA or approaching historical peak/trough averages.

### Health Zone Quick Reference

| Score | Zone | Equity Exposure | Action |
|-------|------|-----------------|--------|
| 80-100 | Strong | 90-100% | Full positions, growth/momentum favored |
| 60-79 | Healthy | 75-90% | Normal operations |
| 40-59 | Neutral | 60-75% | Selective positioning, tighten stops |
| 20-39 | Weakening | 40-60% | Profit-taking, raise cash |
| 0-19 | Critical | 25-40% | Capital preservation, watch for trough |

---

## 7. Tips & Best Practices

- **Run daily before the open.** Breadth conditions change gradually, but checking daily ensures you catch zone transitions early. A single run takes only a few seconds.
- **Combine with the Breadth Chart Analyst skill.** The Analyzer gives you a quantitative score; the Chart Analyst provides qualitative visual pattern recognition. Together they offer a complete breadth picture.
- **Watch for Early Warning flags.** When the 20-day divergence window turns bearish while the 60-day window is still healthy, short-term deterioration has begun. This is the earliest actionable signal.
- **Do not over-react to single readings.** Use the score history trend (Improving / Stable / Deteriorating) to confirm direction before changing exposure. A single-day dip in score does not warrant a portfolio overhaul.
- **Pay attention to weight redistribution notes.** If the report shows fewer than 6 components available, interpret the composite with appropriate caution. A "Partial" data quality label means the score is less reliable.
- **Use zone-based exposure as a guideline, not a rule.** The recommended equity exposure ranges are starting points. Adjust based on your individual risk tolerance, portfolio composition, and conviction level.

---

## 8. Combining with Other Skills

| Workflow | How to Combine |
|----------|---------------|
| **Daily market assessment** | Run Market Breadth Analyzer for the quantitative score, then Breadth Chart Analyst for visual confirmation if the zone is near a transition |
| **Sector rotation timing** | When breadth shifts from Strong to Weakening, use Sector Analyst to identify defensive rotation candidates |
| **Position sizing adjustment** | Feed the health zone into Position Sizer decisions: use tighter risk (0.5%) in Weakening/Critical zones, standard risk (1%) in Healthy/Strong zones |
| **Growth stock screening** | In Strong/Healthy zones, CANSLIM and VCP screens have higher success rates. In Weakening zones, favor dividend and value screens instead |
| **Top detection** | If breadth is Weakening AND Market Bubble Detector shows Orange/Red, treat this as strong confirmation of topping conditions |

---

## 9. Troubleshooting

### "Data appears stale" warning

**Cause:** The latest row in the CSV is more than 5 days old, typically because TraderMonty's GitHub Actions pipeline has not run.

**Fix:** This is a warning, not an error. The analysis still runs using the most recent available data. Check the [source repository](https://github.com/sydcurie/market-breadth-analysis) for update status. During market holidays, staleness is expected.

### "Component X excluded (insufficient data)" message

**Cause:** A component could not be scored because the data lacked the necessary rows or markers (e.g., no peak/trough markers detected in the dataset).

**Fix:** This is handled automatically via weight redistribution. The remaining components absorb the excluded weight proportionally. Check the Data Quality label in the output: "Complete" means all 6 components scored; "Partial" or "Limited" means reduced confidence.

### Network errors fetching CSV

**Cause:** Unable to reach GitHub Pages (network issues, corporate firewall, or the hosting service is temporarily down).

**Fix:** Verify your internet connection. Try opening the data URL directly in a browser: `https://sydcurie.github.io/market-breadth-analysis/market_breadth_data.csv`. If blocked by a firewall, download the CSV manually and pass its local path (the script currently expects URLs; you may need to modify the fetch logic for local files).

### Score seems unexpectedly low despite market rally

**Cause:** The S&P 500 may be rising on narrow leadership (few large-cap stocks driving the index). The breadth score correctly reflects weak participation even when the index looks strong.

**Fix:** This is the intended behavior -- it is the primary value of breadth analysis. Check Component C6 (S&P 500 Divergence) for confirmation of the narrow-market condition.

---

## 10. Reference

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--detail-url` | No | TraderMonty GitHub Pages URL | URL for the detail CSV (market_breadth_data.csv) |
| `--summary-url` | No | TraderMonty GitHub Pages URL | URL for the summary CSV (market_breadth_summary.csv) |
| `--output-dir` | No | `.` (current directory) | Output directory for JSON and Markdown reports |

### 6-Component Scoring Summary

| # | Component | Weight | What It Measures |
|---|-----------|--------|-----------------|
| 1 | Breadth Level & Trend | 25% | Current 8MA level + 200MA trend direction + 8MA direction modifier |
| 2 | 8MA vs 200MA Crossover | 20% | Momentum via MA gap and direction |
| 3 | Peak/Trough Cycle | 20% | Position in the breadth cycle (early recovery, mature, post-peak, etc.) |
| 4 | Bearish Signal | 15% | Backtested bearish signal flag, context-adjusted |
| 5 | Historical Percentile | 10% | Current 8MA vs full historical distribution |
| 6 | S&P 500 Divergence | 10% | Multi-window (20d + 60d) price vs breadth divergence |

### Key Breadth Thresholds

| 8MA Level | Interpretation |
|-----------|---------------|
| > 0.70 | Very strong -- broad rally |
| > 0.60 | Healthy -- above average participation |
| > 0.50 | Neutral -- about half of stocks participating |
| > 0.40 | Weakening -- below average participation |
| < 0.40 | Extreme weakness -- potential trough formation |
| < 0.20 | Crisis levels -- rare, precedes major bottoms |

### Output Files

| File | Description |
|------|-------------|
| `market_breadth_YYYY-MM-DD_HHMMSS.json` | Structured JSON with all component scores, composite, and metadata |
| `market_breadth_YYYY-MM-DD_HHMMSS.md` | Human-readable Markdown report |
| `market_breadth_history.json` | Rolling history of composite scores (max 20 entries) |
