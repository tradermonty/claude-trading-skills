---
name: ftd-detector
description: Detects Follow-Through Day (FTD) signals for market bottom confirmation using William O'Neil's methodology. Dual-index tracking (S&P 500 + NASDAQ) with state machine for rally attempt, FTD qualification, and post-FTD health monitoring. Use when user asks about market bottom signals, follow-through days, rally attempts, re-entry timing after corrections, or whether it's safe to increase equity exposure. Complementary to market-top-detector (defensive) - this skill is offensive (bottom confirmation).
---

# FTD Detector Skill

## FTD lifecycle and evidence contract (#765)

- Keep the FTD event separate from its current health. A close below the FTD-day low is a warning, not automatic rally failure. A later intraday low strictly below the rally low (the low of the pullback the rally attempt started from, frozen on Day 1; not the lowest low of the whole correction) fails that rally, before and after an FTD; equality holds. Day 1 low is informational only, not an interchangeable failure level.
- Missing/non-finite/nonpositive low evidence on any replayed bar means unavailable. Never substitute a close for a missing low.
- Default Nasdaq evidence is `^IXIC` (Composite). Use `--nasdaq-symbol QQQ` only for a labeled Nasdaq-100 ETF proxy. Never substitute its volume or price into an index series or claim its DD count is the Composite count. No automatic fallback.
- `quality_score` is an uncalibrated technical heuristic, not success probability. `exposure_range` is `Not assessed` in every state. Do not derive portfolio percentages from the score; assess breadth, leadership, portfolio limits and operator decisions separately.
- Day 4–10 is this model's normal FTD window. The model no longer ends an attempt at Day 10: an FTD on Day 11 or later is allowed, flagged `ftd.late` and scored with the lowest base (40). IBD is reported to note that most FTDs come on days 4-7 and some come later (secondary report, IBD's official rule text not verified).


## Purpose

Detect Follow-Through Day (FTD) signals that confirm a market bottom, using an explicit O'Neil-style technical model. Generates a quality score (0-100) with technical health warnings; portfolio exposure is not assessed.

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
| Focus | Rally-event confirmation | Market deterioration assessment |
| Trigger | Market correction (3%+ decline) | Market at/near highs |
| Signal | Rally attempt → FTD → health assessment | Distribution → deterioration evidence |
| Score | 0-100 heuristic FTD quality | Separate heuristic market-risk score |
| Action | When technical confirmation appears | When deterioration appears |

---

## Execution Workflow

### Phase 1: Execute Python Script

Run the FTD detector script:

```bash
python3 skills/ftd-detector/scripts/ftd_detector.py --api-key $FMP_API_KEY
```

The script will:
1. Fetch S&P 500 (^GSPC) and Nasdaq Composite (^IXIC) historical data (500 trading sessions; the whole history is replayed) from FMP API
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
- Exposure not assessed: breadth, leadership and portfolio risk require separate inputs
- Key watch levels (swing low, FTD day low)
- Post-FTD health (distribution days, power trend)

### Phase 3: Contextual Guidance

Based on the market state, provide additional guidance:

**If FTD Confirmed (score 60+):**
- Suggest looking at leading stocks in proper bases
- Reference CANSLIM screener for candidate stocks
- State that portfolio sizing and stop placement are not assessed by this score

**If Rally Attempt (Day 1-3):**
- Advise patience, do not buy ahead of FTD
- Suggest building watchlists

**If No Correction:**
- FTD analysis is not applicable in uptrend
- Redirect to Market Top Detector for defensive signals

---

## State Machine

The model replays the whole supplied history (500 sessions are fetched) oldest to
newest and carries state, so a confirmed FTD stays confirmed until a defined event ends
it and the result does not depend on a window length.

```
NO_SIGNAL → CORRECTION → RALLY_ATTEMPT → FTD_WINDOW → FTD_CONFIRMED
                ↑              ↓               ↓              ↓
                └── RALLY_FAILED ←─────────────┘     FTD_INVALIDATED
```

`market_status` maps the states onto IBD's three tiers (additive field on every
`analyze_single_index` result, per index in the JSON, and combined in `market_state`):

| market_status | Legacy states |
|---------------|---------------|
| `confirmed_uptrend` | FTD_CONFIRMED |
| `uptrend_under_pressure` | FTD_CONFIRMED (`cycle.uptrend_status` = `under_pressure`) |
| `market_in_correction` | CORRECTION, RALLY_ATTEMPT, FTD_WINDOW, RALLY_FAILED, FTD_INVALIDATED |
| `null` | NO_SIGNAL: warm-up before the first qualifying correction, data gap, insufficient data |

Only an FTD leaves a correction; a rise above the old peak does not. IBD sets one status
from either major index, so the combined status follows the better confirmed index.
A close below the 50-session SMA puts it under pressure only after the index has closed above that SMA once since the FTD (`cycle.regained_50sma_since_ftd`), as an FTD normally comes from below it. The uptrend ends (market in correction) on 6+ active distribution days with a close below the 50-day line, even if the SMA was never regained, or on a 10% drawdown from the post-FTD peak. Secondary sources describe IBD's trigger variously (one cites the 21-day EMA); the 50-day line avoids declaring corrections on shallow pullbacks, and the threshold is unverified. A close below the FTD-day low also puts the uptrend under pressure (warning only, never a failure); `cycle.pressure_reasons` records the cause. See `references/ftd_methodology.md` for the transition rules (uncalibrated model choices).

| State | Definition |
|-------|-----------|
| NO_SIGNAL | Warm-up (no qualifying correction since the replay start), data gap or insufficient data |
| CORRECTION | 3%+ decline with 3+ down closes, or a confirmed uptrend ended by distribution or a 10% drawdown |
| RALLY_ATTEMPT | Day 1-3 of rally from the recent pullback low |
| FTD_WINDOW | Day 4 onward (no upper limit), waiting for a qualifying FTD; an FTD after Day 10 is flagged late |
| FTD_CONFIRMED | Valid FTD; stays until the rally low is undercut or the uptrend ends (see `market_status`) |
| RALLY_FAILED | Rally undercut the rally low |
| FTD_INVALIDATED | Intraday low below the rally low of the attempt that produced the FTD |

## Quality Score (0-100)

| Score | Signal | Exposure |
|-------|--------|----------|
| 80-100 | Strong FTD | Not assessed |
| 60-79 | Moderate FTD | Not assessed |
| 40-59 | Weak FTD | Not assessed |
| <40 | Very weak FTD (unless explicitly invalidated) | Not assessed |
| 0 | No FTD, Failed/Invalidated, Unavailable: data gap, a Very weak FTD at the floor, or FTD under pressure at the floor | Not assessed |

A score of 0 alone does not mean a data gap. Read `signal`, the market state and
the quality score's `data_gap` (set only with `Unavailable: data gap`) before
interpreting it.

---

## Prerequisites

- **FMP API Key:** Required. Set `FMP_API_KEY` environment variable or pass via `--api-key` flag.
- **Python 3.9+:** With `requests` library installed.
- **API Budget:** Four logical data requests per execution; retries may add calls. Endpoint entitlement depends on the provider plan.

## Output Files

- JSON: `ftd_detector_YYYY-MM-DD_HHMMSS.json`
- Markdown: `ftd_detector_YYYY-MM-DD_HHMMSS.md`

### Data gaps (missing or invalid price bars)

A missing or non-finite close/volume (or a non-positive close) is never read as 0, and bars are never dropped. Bar fields are read through the vendored `scripts/_price_bars.py` helper.

- **JSON `data_gap`** (bool, every run, at the top level and in `market_state`): true when an index replay hit a bad bar it could not restart past (a bad close, volume or low restarts the replay after it, which needs 60 clean sessions) or a post-FTD check hit a bad bar.
- **JSON `data_quality`** (every run): per index, the window check (`window_sessions`, `bad_bars`, `bad_dates`, `latest_bad`) plus `sp500.power_trend_bad_bars` for the power-trend input (counted only when the power trend runs, 50+ bars). Each index block also carries its own `data_quality`, and `error` when the analysis failed ("Insufficient data" or "Data gap: ...").
- **Close/volume-gapped index:** `NO_SIGNAL` with `current_price` / `lookback_high` / `correction_depth_pct` set to `null`; no rally or FTD logic runs for it. With any gapped index the run's `combined_state` is reported as `NO_SIGNAL` with `data_gap: true`, meaning *state unavailable* (not an uptrend), with `ftd_index: null` and no post-FTD checks. The other index is never promoted, because the gap could be hiding the gapped index's own (possibly invalidated) FTD. Each index's own analysis stays in the JSON. The Markdown headline reads "State unavailable (data gap)".
- **Unavailable score:** if any index is gapped, or the post-FTD distribution or invalidation check has a gap, `quality_score` is `total_score: 0` (always an int, never `null`), `signal: "Unavailable: data gap"`, `exposure_range: "Not assessed"`, `data_gap: true`. Treat this as "no usable confirmation": do not increase exposure on it. A gapped distribution check keeps `distribution_count: 0` (int) with `data_gap: true`; a gapped invalidation check reports `invalidated: null`. A post-FTD gap also reports the combined state as `NO_SIGNAL` with `data_gap: true` (state unavailable), since the FTD can be neither confirmed nor invalidated.
- **Power trend:** a bad close anywhere in its input gives `power_trend: null` with a `reason`; this alone does not set `data_gap` or change the score.
- **Volume 0 is a data gap.** For ^GSPC and the selected Nasdaq instrument a zero session volume is provider missing data, so a missing, invalid or zero volume within the replayed history (or the post-FTD checks) marks a data gap. This is a behavior change from earlier versions, which read volume 0 as real.

## Reference Documents

### `skills/ftd-detector/references/ftd_methodology.md`
- O'Neil's FTD rules in detail
- Rally attempt mechanics and day counting
- Historical FTD examples (2020 March, 2022 October)

### `skills/ftd-detector/references/post_ftd_guide.md`
- Post-FTD distribution timing and heuristic penalties
- Power Trend definition and conditions
- Qualitative favorable/adverse context (not calibrated outcome predictors)

### When to Load References
- **First use:** Load `skills/ftd-detector/references/ftd_methodology.md` for full understanding
- **Post-FTD questions:** Load `skills/ftd-detector/references/post_ftd_guide.md`
- **Regular execution:** References not needed - script handles analysis

FTD-day-low pressure caps published quality at 59 (uncalibrated conservative heuristic); it does not erase the event or imply rally failure.

- **Lifecycle-low gap:** If only a Day 1/post-FTD low is missing, per-index and combined state are `NO_SIGNAL` with `data_gap: true`. Known prices and any already-established historical event evidence may remain visible; this does not mean the lifecycle is assessable.
