---
name: ibd-distribution-day-monitor
description: Detect IBD-style Distribution Days for QQQ/SPY (close down at least 0.2% on higher volume), track 25-session expiration and 5% invalidation, count d5/d15/d25 clusters, classify market risk (NORMAL/CAUTION/HIGH/SEVERE), and emit TQQQ/QQQ exposure recommendations. Use after market close, before TQQQ exposure changes, or as input to FTD/market-state frameworks. Does not execute trades.
---

# IBD Distribution Day Monitor

## Purpose
Detect IBD-style Distribution Days for major market ETFs (QQQ as Nasdaq proxy, SPY as S&P 500 proxy) and produce a daily market deterioration signal plus a TQQQ/QQQ exposure recommendation. Designed for post-market review.

## When to Use
Invoke this skill:
- Daily after the US market close.
- Before increasing TQQQ exposure or rebalancing leveraged positions.
- When evaluating whether an uptrend is becoming vulnerable to a correction.
- As an upstream input to FTD (Follow-Through Day) detection or other market-state frameworks.

Do NOT use this skill to:
- Execute trades or modify orders.
- Generate discretionary market predictions outside of the IBD ruleset.

## Inputs
- Symbols (default: QQQ, SPY) and lookback (default 80 trading sessions).
- Optional `--as-of YYYY-MM-DD` for backtesting against a historical session.
- Strategy context: instrument (TQQQ or QQQ), current exposure %, base trailing stop %.
- FMP API key via `--api-key`, `config.data.api_key`, or `FMP_API_KEY` env var (in that priority order).

## Core Rules
A Distribution Day is detected when:
1. Today's close is at least 0.2% below yesterday's close.
2. Today's volume is greater than yesterday's volume.

A Distribution Day is removed from the active count when either:
- More than 25 trading sessions have elapsed since the DD.
- The index has gained 5% from the DD close (using post-DD high by default; configurable to close-source).

Today's DD is never invalidated immediately because there are no post-DD sessions to evaluate the 5% gain against.

## Counting Conventions
- `d5_count` / `d15_count` / `d25_count` count active records with `age_sessions <= N`.
- This means **N+1 sessions** are inspected (age 0..N inclusive). Reports therefore say "within N elapsed sessions" rather than "直近 N 取引日" to avoid ambiguity.

## Risk Classification
| Risk | Trigger |
|------|---------|
| NORMAL | `d25 <= 2` |
| CAUTION | `d25 >= 3` |
| HIGH | `d25 >= 5` OR `d15 >= 3` OR `d5 >= 2` |
| SEVERE | `d25 >= 6` OR `d15 >= 4` OR (`market_below_21ema_or_50ma` AND `d25 >= 5`) |

When both QQQ and SPY are loaded, QQQ-weighted overall logic applies (TQQQ-aware): a single SEVERE escalates to SEVERE; QQQ HIGH escalates to overall HIGH; QQQ NORMAL + SPY HIGH still escalates to HIGH (broad-market spillover).

## TQQQ Exposure Policy
| Risk | Action | Target Exposure | Trailing Stop |
|------|--------|-----------------|---------------|
| NORMAL | HOLD_OR_FOLLOW_BASE_STRATEGY | 100% | base |
| CAUTION | AVOID_NEW_ADDS | 75% | min(base, 7%) |
| HIGH | REDUCE_EXPOSURE | 50% | min(base, 5%) |
| SEVERE | CLOSE_TQQQ_OR_HEDGE | 25% | min(base, 3%) |

QQQ uses a less aggressive policy (HIGH=75%, SEVERE=50%) since it lacks 3x leverage.

## Workflow
1. Load OHLCV for the configured symbols via FMP (`get_historical_prices`).
2. Validate data quality; record skipped sessions in audit.
3. Rebase via `prepare_effective_history` so `effective_history[0]` is the evaluation session.
4. Detect raw Distribution Days; enrich with `high_since`, invalidation event, and status.
5. Count `d5` / `d15` / `d25` active records.
6. Compute 21EMA and 50SMA filters; flag `market_below_21ema_or_50ma` (None if data insufficient).
7. Classify each index, then combine using QQQ-weighted policy.
8. Generate portfolio action for the configured instrument.
9. Write JSON + Markdown reports to `--output-dir` with API keys redacted.

## Outputs
Saved to `reports/` (or `--output-dir`):
- `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.json`
- `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.md`

JSON is UTF-8 with `ensure_ascii=False` (Japanese explanations preserved). Sensitive keys (`api_key`, `fmp_api_key`, `token`, etc.) are redacted automatically.

## Operating Principles
- Do not override the IBD rule definitions unless `config/default.yaml` is changed deliberately.
- Always explain which dates contributed to the active count.
- Treat missing or unreliable volume data as a warning (audit_flag), not as a Distribution Day.
- Do not place trades. The portfolio action is a risk-management suggestion, not an execution instruction.

## CLI
```bash
python3 skills/ibd-distribution-day-monitor/scripts/ibd_monitor.py \
  --symbols QQQ,SPY \
  --lookback-days 80 \
  --instrument TQQQ \
  --current-exposure 100 \
  --base-trailing-stop 10 \
  --output-dir reports/
```

## API Requirements
FMP API key required. Free tier (250 calls/day) is sufficient for daily QQQ + SPY runs.

## Related Skills
- `ftd-detector`: Bottom confirmation via Follow-Through Days (counterpart of this top-side signal).
- `market-top-detector`: Composite 0-100 top probability score using O'Neil distribution + other components.
- `position-sizer`: Convert risk-management recommendations into share counts.

## Data Gaps

Explicit behavior when required data is unavailable — do not substitute neutrals silently.

| Scenario | Severity | Behavior |
|----------|----------|----------|
| `FMP_API_KEY` env var missing | CRITICAL | Halt — exit 1; print setup instructions; do not write output |
| FMP returns HTTP error or empty list | HIGH | Halt — log `[DATA GAP HIGH]`; do not fabricate candidates |
| Individual ticker data unavailable | LOW | Skip ticker; list missing symbols in output under `data_gaps[]` |
| Fewer than 30 qualifying candidates | MEDIUM | Continue; note reduced sample; mark `confidence: LOW` in output |
| Data timestamp >1 trading day old | MEDIUM | Warn in output; proceed only with user confirmation |

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `breadth_assessment` | `BreadthAssessment` | Market breadth composite score and component breakdown |

Schema: `schemas/json/breadth_assessment.json`
