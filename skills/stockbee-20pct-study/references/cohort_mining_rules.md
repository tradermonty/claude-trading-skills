# Cohort Mining Rules

## Purpose

Cohort summaries convert many 20% mover observations into evidence prompts. They should reduce hindsight bias, not create overfit rules.

## Minimum Evidence Rules

- Require `min_sample` before promoting any rule candidate. Default: 10 matured records.
- Treat samples below 30 as preliminary unless the pattern is very stable and explainable.
- Split by market regime before increasing risk based on a cohort.
- Review representative charts from both winners and failures.
- Prefer simple groupings before adding more filters.

## Default Cohort Dimensions

```text
direction,catalyst.label,technical_context.pattern_label,technical_context.close_quality
```

Useful alternate groupings:

```text
direction,technical_context.pattern_label,technical_context.extension_risk
catalyst.label,technical_context.close_quality,liquidity.volume_ratio_20d
direction,data_quality.flags,technical_context.pattern_label
```

## Rule Candidate Thresholds

A continuation-favorable cohort can become `candidate_for_review` when:

- Sample size is at or above `min_sample`
- Direction-adjusted win rate is at least 58%
- Median direction-adjusted return is at least +2%

A weak cohort can become `avoid_or_fade_study` when:

- Sample size is at or above `min_sample`
- Direction-adjusted win rate is 42% or lower
- Median direction-adjusted return is -2% or worse

## Overfitting Controls

- Do not add filters solely because they improved one backtest.
- Do not mine hundreds of tag combinations without recording the number of trials.
- Do not use future catalyst knowledge during historical classification.
- Do not count records with `PENDING` outcomes as matured.
- Do not mix current-universe-only and survivorship-complete backfills without a data-quality split.

## Promotion Path

1. `stockbee-20pct-study` produces a rule candidate.
2. Human reviews charts and data-quality notes.
3. `edge-hint-extractor` or `edge-candidate-agent` converts it into an explicit research ticket.
4. `backtest-expert` validates the hypothesis with realistic execution assumptions.
5. `monthly-performance-review` decides whether to accept, reject, or keep monitoring.
