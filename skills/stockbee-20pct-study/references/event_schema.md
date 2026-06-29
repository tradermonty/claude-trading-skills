# Event Schema

The durable model book is stored as JSONL at `state/stockbee/20pct_study_events.jsonl`. Each line is one event record. Records are upserted by `record_id`.

## Identity Fields

```json
{
  "schema_version": "1.0",
  "source_skill": "stockbee-20pct-study",
  "record_id": "AAPL:2026-06-28:UP:5D",
  "episode_id": "AAPL:2026-06-24:UP",
  "symbol": "AAPL",
  "event_date": "2026-06-28",
  "direction": "UP",
  "window_days": 5,
  "event_day_index": 1
}
```

`record_id` identifies a single detection window. `episode_id` groups consecutive detections for the same symbol and direction into the same market episode.

## Price Snapshot

```json
{
  "price_snapshot": {
    "open": 100.0,
    "high": 126.0,
    "low": 98.0,
    "close": 124.0,
    "previous_close": 100.0,
    "lookback_close": 100.0,
    "return_pct": 24.0,
    "day_return_pct": 18.0,
    "gap_pct": 5.0,
    "range_pct": 28.0,
    "close_location_pct": 92.8
  }
}
```

`return_pct` is measured from the lookback close to the event close. `close_location_pct` is 0 at the low of the event-day range and 100 at the high.

## Liquidity

```json
{
  "liquidity": {
    "volume": 50000000,
    "avg_volume_20d": 12000000,
    "volume_ratio_20d": 4.17,
    "dollar_volume": 6200000000,
    "avg_dollar_volume_20d": 1500000000,
    "price_pass": true,
    "liquidity_pass": true
  }
}
```

## Technical Context

```json
{
  "technical_context": {
    "distance_to_52w_high_pct": -2.1,
    "distance_to_52w_low_pct": 88.0,
    "prior_20d_return_pct": 8.5,
    "prior_50d_return_pct": 22.0,
    "base_length_days": 25,
    "base_depth_pct": 14.0,
    "pattern_label": "BASE_BREAKOUT",
    "close_quality": "STRONG_CLOSE",
    "extension_risk": "MODERATE"
  }
}
```

## Catalyst

```json
{
  "catalyst": {
    "label": "EARNINGS_REVALUATION",
    "confidence": 0.82,
    "source_type": "news_events_json",
    "summary": "Large gap after earnings and guidance raise."
  }
}
```

If no catalyst source is provided, records default to `NO_CLEAR_NEWS` with `source_type=price_only`.

## Scores and Handoffs

```json
{
  "scores": {
    "continuation_quality_score": 78,
    "reversal_risk_score": 31,
    "study_priority_score": 91,
    "data_quality_score": 86
  },
  "labels": ["UP", "BASE_BREAKOUT", "STRONG_CLOSE", "A_REVALUATION_OR_HIGH_QUALITY_EVENT"],
  "handoffs": {
    "stockbee_episodic_pivot": true,
    "pead_screener": true,
    "theme_detector": true,
    "edge_candidate_agent": false,
    "parabolic_short_watch": false
  }
}
```

## Outcomes

```json
{
  "outcomes": {
    "1d": {
      "status": "MATURED",
      "horizon_days": 1,
      "entry_close": 124.0,
      "close_date": "2026-06-29",
      "close": 130.0,
      "close_return_pct": 4.84,
      "mfe_pct": 6.45,
      "mae_pct": -2.1,
      "directional_close_return_pct": 4.84,
      "directional_mfe_pct": 6.45,
      "directional_mae_pct": -2.1,
      "outcome_tag": "CONTINUED"
    },
    "5d": {
      "status": "PENDING",
      "reason": "insufficient_future_bars"
    }
  }
}
```

For `DOWN` events, direction-adjusted returns treat further downside as positive continuation. Raw `close_return_pct`, `mfe_pct`, and `mae_pct` remain long-side price movement from the event close.

## Data Quality

```json
{
  "data_quality": {
    "flags": ["SHORT_HISTORY_LT_260_BARS", "LOW_AVG_DOLLAR_VOLUME"],
    "data_quality_score": 70
  }
}
```

Common flags include:

- `SHORT_HISTORY_LT_260_BARS`
- `LOW_AVG_DOLLAR_VOLUME`
- `MISSING_VOLUME`
- `EXTREME_MOVE_CHECK_SPLIT_OR_CORPORATE_ACTION`
- `POSSIBLE_SPLIT_OR_SPECIAL_DISTRIBUTION`
- `CURRENT_UNIVERSE_BACKFILL_SURVIVORSHIP_BIAS`
