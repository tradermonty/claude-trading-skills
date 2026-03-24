---
name: signal-postmortem
description: "Use when the user wants to review trade performance, analyze signal accuracy, track trading outcomes, or evaluate edge pipeline results. Record post-trade outcomes by comparing predicted direction against 5-day and 20-day realized returns. Classify signals as true positive, false positive, missed opportunity, or regime mismatch. Generate weight adjustment feedback for edge-signal-aggregator and skill improvement backlog entries."
---

# Signal Postmortem

Compare predicted signal direction against realized returns, classify outcomes, and generate feedback for signal weight calibration and skill improvement.

## When to Use

- Review trade performance after a position is closed
- Analyze signal accuracy for a batch that reached its 5-day or 20-day holding period
- Track trading outcomes to find systematic false positive patterns by skill
- Evaluate edge pipeline results for weekly or monthly signal quality audits
- Generate weight calibration feedback for edge-signal-aggregator

## Prerequisites

- Python 3.9+
- FMP API key (optional, for fetching realized returns if not provided manually)
- Standard library + `requests` for API calls
- Input: signal records in JSON format (from edge-signal-aggregator or screener outputs)

## Workflow

### Step 1: Prepare Signal Records

Gather closed or matured signal records. Each record should include:
- `signal_id`: Unique identifier
- `ticker`: Stock symbol
- `signal_date`: Date signal was generated
- `predicted_direction`: LONG or SHORT
- `source_skill`: Which skill generated the signal
- `entry_price`: Price at signal generation (optional, for manual override)

```bash
# Example: List signals ready for postmortem (5+ days old)
python3 skills/signal-postmortem/scripts/postmortem_recorder.py \
  --list-ready \
  --signals-dir state/signals/ \
  --min-days 5
```

### Step 2: Record Outcomes

Run the postmortem recorder to fetch realized returns and classify outcomes.

```bash
python3 skills/signal-postmortem/scripts/postmortem_recorder.py \
  --signals-file state/signals/aggregated_signals_2026-03-10.json \
  --holding-periods 5,20 \
  --output-dir reports/
```

For manual outcome recording (when price data is already available):

```bash
python3 skills/signal-postmortem/scripts/postmortem_recorder.py \
  --signal-id sig_aapl_20260310_abc \
  --exit-price 178.50 \
  --exit-date 2026-03-15 \
  --outcome-notes "Closed at target, +3.2% in 5 days" \
  --output-dir reports/
```

### Step 3: Classify Outcomes

The recorder automatically classifies each signal into one of four categories:

| Category | Definition |
|----------|------------|
| TRUE_POSITIVE | Predicted direction matched realized return sign |
| FALSE_POSITIVE | Predicted direction opposite to realized return |
| MISSED_OPPORTUNITY | Signal not taken but would have been profitable |
| REGIME_MISMATCH | Signal failed due to market regime change |

Classification rules are documented in `references/outcome-classification.md`.

### Step 4: Generate Feedback Files

Generate feedback for downstream consumers:

```bash
# Generate weight adjustment suggestions for edge-signal-aggregator
python3 skills/signal-postmortem/scripts/postmortem_analyzer.py \
  --postmortems-dir reports/postmortems/ \
  --generate-weight-feedback \
  --output-dir reports/

# Generate skill improvement backlog entries
python3 skills/signal-postmortem/scripts/postmortem_analyzer.py \
  --postmortems-dir reports/postmortems/ \
  --generate-improvement-backlog \
  --output-dir reports/
```

### Step 5: Review Summary Statistics

Generate aggregate statistics by skill, by ticker, and by time period:

```bash
python3 skills/signal-postmortem/scripts/postmortem_analyzer.py \
  --postmortems-dir reports/postmortems/ \
  --summary \
  --group-by skill,month \
  --output-dir reports/
```

## Output Format

### Postmortem Record (JSON)

```json
{
  "schema_version": "1.0",
  "postmortem_id": "pm_sig_aapl_20260310_abc",
  "signal_id": "sig_aapl_20260310_abc",
  "ticker": "AAPL",
  "signal_date": "2026-03-10",
  "source_skill": "edge-signal-aggregator",
  "predicted_direction": "LONG",
  "entry_price": 172.50,
  "realized_returns": {
    "5d": 0.032,
    "20d": 0.058
  },
  "exit_price": 178.50,
  "exit_date": "2026-03-15",
  "holding_days": 5,
  "outcome_category": "TRUE_POSITIVE",
  "regime_at_signal": "RISK_ON",
  "regime_at_exit": "RISK_ON",
  "outcome_notes": "Clean breakout, held through minor pullback",
  "recorded_at": "2026-03-17T10:30:00Z"
}
```

### Weight Feedback (JSON)

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-03-17T10:35:00Z",
  "analysis_period": {
    "from": "2026-02-01",
    "to": "2026-03-15"
  },
  "skill_adjustments": [
    {
      "skill": "vcp-screener",
      "current_weight": 1.0,
      "suggested_weight": 0.85,
      "reason": "15% false positive rate in RISK_OFF regime",
      "sample_size": 42
    }
  ],
  "confidence": "MEDIUM",
  "min_sample_threshold": 20
}
```

### Skill Improvement Backlog Entry (YAML)

```yaml
- skill: vcp-screener
  issue_type: false_positive_cluster
  severity: medium
  evidence:
    false_positive_rate: 0.15
    sample_size: 42
    regime_correlation: RISK_OFF
  suggested_action: "Add regime filter or reduce signal confidence in RISK_OFF"
  generated_by: signal-postmortem
  generated_at: "2026-03-17T10:35:00Z"
```

### Summary Report (Markdown)

Reports are saved to `reports/` with filenames `postmortem_summary_YYYY-MM-DD.md`.

## Resources

- `scripts/postmortem_recorder.py` -- Records individual signal outcomes
- `scripts/postmortem_analyzer.py` -- Generates feedback and summary statistics
- `references/outcome-classification.md` -- Classification rules and edge cases
- `references/feedback-integration.md` -- How to integrate feedback with downstream skills

## Key Principles

1. **Honest Attribution** -- Every outcome is attributed to its source skill for accountability
2. **Regime Awareness** -- Regime context is recorded to distinguish skill failure from market regime shifts
3. **Minimum Sample Size** -- Weight adjustments require 20+ signals for statistical validity
4. **Feedback Loop Closure** -- Results flow back to improve both signal aggregation and skill quality
