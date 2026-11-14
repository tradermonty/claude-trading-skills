---
layout: default
title: "FTD Detector"
grand_parent: English
parent: Skill Guides
nav_order: 24
lang_peer: /ja/skills/ftd-detector/
permalink: /en/skills/ftd-detector/
---

# FTD Detector
{: .no_toc }

Detects Follow-Through Day (FTD) signals for market bottom confirmation using William O'Neil's methodology. Dual-index tracking (S&P 500 + NASDAQ) with state machine for rally attempt, FTD qualification, and post-FTD health monitoring. Use when user asks about market bottom signals, follow-through days, rally attempts, re-entry timing after corrections, or whether it's safe to increase equity exposure. Complementary to market-top-detector (defensive) - this skill is offensive (bottom confirmation).
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/ftd-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/ftd-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

FTD Detector identifies market bottom signals using William O'Neil's Follow-Through Day methodology. It tracks S&P 500 and NASDAQ/QQQ simultaneously through a state machine that progresses from correction to rally attempt to FTD confirmation, with post-FTD health monitoring including distribution day counting, invalidation detection, and power trend analysis.

---

## 2. When to Use

- User asks "Is the market bottoming?" or "Is it safe to buy again?"
- User observes a market correction (3%+ decline) and wants re-entry timing
- User asks about Follow-Through Days or rally attempts
- User wants to assess if a recent bounce is sustainable
- User asks about increasing equity exposure after a correction
- Market Top Detector shows elevated risk and user wants bottom signals

---

## 3. Prerequisites

- **FMP API Key:** Required. Set `FMP_API_KEY` environment variable or pass via `--api-key` flag.
- **Python 3.8+:** With `requests` library installed.
- **API Budget:** 4 calls per execution (well within FMP free tier of 250/day).

---

## 4. Quick Start

```bash
python3 skills/ftd-detector/scripts/ftd_detector.py --api-key $FMP_API_KEY
```

---

## 5. Workflow

### Phase 1: Execute Python Script

Run the FTD detector script:

```bash
python3 skills/ftd-detector/scripts/ftd_detector.py --api-key $FMP_API_KEY
```

The script will:
1. Fetch S&P 500 and QQQ historical data (60+ trading days) from FMP API
2. Fetch current quotes for both indices
3. Run dual-index state machine (correction → rally → FTD detection)
4. Assess post-FTD health (distribution days, invalidation, power trend)
5. Calculate quality score (0-100)
6. Generate JSON and Markdown reports

**API Budget:** 4 calls (well within free tier of 250/day)

### Phase 2: Present Results

Present the generated Markdown report to the user, highlighting:
- Current market state (correction, rally attempt, FTD confirmed, etc.)
- Quality score and signal strength
- Recommended exposure level
- Key watch levels (swing low, FTD day low)
- Post-FTD health (distribution days, power trend)

**Data gaps.** A missing or non-finite close/volume is never read as 0, and bars are never dropped (dropping one can fabricate an FTD). Every run writes:

- `data_gap` (bool, top level and in `market_state`): true when an index's 60-session window or a post-FTD check hit a bad bar.
- `data_quality`: per index, the window check (`window_sessions`, `bad_bars`, `bad_dates`, `latest_bad`), plus `sp500.power_trend_bad_bars` for the power-trend input (counted only when the power trend runs, 50+ bars). Each index block also has `error` when its analysis failed ("Insufficient data" or "Data gap: ...").

A gapped index is reported as `NO_SIGNAL` with null prices, and no FTD logic runs for it. The run's `combined_state` is then reported as `NO_SIGNAL` with `data_gap: true`, meaning state unavailable rather than uptrend, with no FTD index and no post-FTD checks. The other index is never promoted, because the gap could hide the gapped index's own, possibly invalidated, FTD. Each index's own analysis stays in the JSON, and the Markdown headline reads "State unavailable (data gap)". If any index or a post-FTD check is gapped, the quality score is **Unavailable**: `total_score` 0 (always an int), signal `Unavailable: data gap`, exposure `0-25%`. The Markdown shows "Unavailable (reason)" and an Action Guidance line "Data gap: confirmation unavailable — do not increase exposure on this signal". A power-trend-only gap shows the power trend as Unavailable without changing the score. A zero volume counts as missing data (for ^GSPC and QQQ it is a provider gap), unlike earlier versions.

### Phase 3: Contextual Guidance

Based on the market state, provide additional guidance:

**If FTD Confirmed (score 60+):**
- Suggest looking at leading stocks in proper bases
- Reference CANSLIM screener for candidate stocks
- Remind about position sizing and stops

**If Rally Attempt (Day 1-3):**
- Advise patience, do not buy ahead of FTD
- Suggest building watchlists

**If No Correction:**
- FTD analysis is not applicable in uptrend
- Redirect to Market Top Detector for defensive signals

---

## 6. Resources

**References:**

- `skills/ftd-detector/references/ftd_methodology.md`
- `skills/ftd-detector/references/post_ftd_guide.md`

**Scripts:**

- `skills/ftd-detector/scripts/_price_bars.py` (generated from `scripts/price_bars/`; do not edit)
- `skills/ftd-detector/scripts/fmp_client.py`
- `skills/ftd-detector/scripts/ftd_detector.py`
- `skills/ftd-detector/scripts/post_ftd_monitor.py`
- `skills/ftd-detector/scripts/rally_tracker.py`
- `skills/ftd-detector/scripts/report_generator.py`
