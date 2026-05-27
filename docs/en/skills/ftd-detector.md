---
layout: default
title: "FTD Detector"
grand_parent: English
parent: Skill Guides
nav_order: 31
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

# FTD Detector Skill

---

## 2. When to Use

**English:**
- User asks "Is the market bottoming?" or "Is it safe to buy again?"
- User observes a market correction (3%+ decline) and wants re-entry timing
- User asks about Follow-Through Days or rally attempts
- User wants to assess if a recent bounce is sustainable
- User asks about increasing equity exposure after a correction
- Market Top Detector shows elevated risk and user wants bottom signals

**Japanese:**
- 「底打ちした？」「買い戻して良い？」
- 調整局面（3%以上の下落）からのエントリータイミング
- フォロースルーデーやラリーアテンプトについて
- 直近の反発が持続可能か評価したい
- 調整後のエクスポージャー拡大の判断
- Market Top Detectorが高リスク表示の後の底打ちシグナル確認

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

---

## 6. Resources

**References:**

- `skills/ftd-detector/references/ftd_methodology.md`
- `skills/ftd-detector/references/post_ftd_guide.md`

**Scripts:**

- `skills/ftd-detector/scripts/fmp_client.py`
- `skills/ftd-detector/scripts/ftd_detector.py`
- `skills/ftd-detector/scripts/post_ftd_monitor.py`
- `skills/ftd-detector/scripts/rally_tracker.py`
- `skills/ftd-detector/scripts/report_generator.py`
