---
name: ftd-detector
description: Detects Follow-Through Day (FTD) signals for market bottom confirmation using William O'Neil's methodology. Dual-index tracking (S&P 500 + NASDAQ) with state machine for rally attempt, FTD qualification, and post-FTD health monitoring. Use when user asks about market bottom signals, follow-through days, rally attempts, re-entry timing after corrections, or whether it's safe to increase equity exposure. Complementary to market-top-detector (defensive) - this skill is offensive (bottom confirmation).
---

# FTD Detector Skill

## Purpose

Detect Follow-Through Day (FTD) signals that confirm a market bottom, using William O'Neil's proven methodology. Generates a quality score (0-100) with exposure guidance for re-entering the market after corrections.

**Complementary to Market Top Detector:**
- Market Top Detector = defensive (detects distribution, rotation, deterioration)
- FTD Detector = offensive (detects rally attempts, bottom confirmation)

## When to Use This Skill

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

## Difference from Market Top Detector

| Aspect | FTD Detector | Market Top Detector |
|--------|-------------|-------------------|
| Focus | Bottom confirmation (offensive) | Top detection (defensive) |
| Trigger | Market correction (3%+ decline) | Market at/near highs |
| Signal | Rally attempt → FTD → Re-entry | Distribution → Deterioration → Exit |
| Score | 0-100 FTD quality | 0-100 top probability |
| Action | When to increase exposure | When to reduce exposure |

---

## Execution Workflow

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

## State Machine

```
NO_SIGNAL → CORRECTION → RALLY_ATTEMPT → FTD_WINDOW → FTD_CONFIRMED
                ↑              ↓               ↓              ↓
                └── RALLY_FAILED ←─────────────┘     FTD_INVALIDATED
```

| State | Definition |
|-------|-----------|
| NO_SIGNAL | Uptrend, no qualifying correction |
| CORRECTION | 3%+ decline with 3+ down days |
| RALLY_ATTEMPT | Day 1-3 of rally from swing low |
| FTD_WINDOW | Day 4-10, waiting for qualifying FTD |
| FTD_CONFIRMED | Valid FTD signal detected |
| RALLY_FAILED | Rally broke below swing low |
| FTD_INVALIDATED | Close below FTD day's low |

## Quality Score (0-100)

| Score | Signal | Exposure |
|-------|--------|----------|
| 80-100 | Strong FTD | 75-100% |
| 60-79 | Moderate FTD | 50-75% |
| 40-59 | Weak FTD | 25-50% |
| <40 | No FTD / Failed | 0-25% |

---

## API Requirements

**Required:** FMP API key (free tier sufficient: 4 calls per execution)

## Output Files

- JSON: `ftd_detector_YYYY-MM-DD_HHMMSS.json`
- Markdown: `ftd_detector_YYYY-MM-DD_HHMMSS.md`

## Reference Documents

### `references/ftd_methodology.md`
- O'Neil's FTD rules in detail
- Rally attempt mechanics and day counting
- Historical FTD examples (2020 March, 2022 October)

### `references/post_ftd_guide.md`
- Post-FTD distribution day failure rates
- Power Trend definition and conditions
- Success vs failure pattern comparison

### When to Load References
- **First use:** Load `ftd_methodology.md` for full understanding
- **Post-FTD questions:** Load `post_ftd_guide.md`
- **Regular execution:** References not needed - script handles analysis
