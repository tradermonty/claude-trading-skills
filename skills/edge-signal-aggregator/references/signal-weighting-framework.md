# Signal Weighting Framework

This document explains the rationale behind default signal weights, the scoring methodology, and guidance for customizing weights based on your trading style.

## Default Skill Weights

| Skill | Default Weight | Rationale |
|-------|----------------|-----------|
| edge-candidate-agent | 0.25 | Primary quantitative signal source with OHLCV anomaly detection |
| edge-concept-synthesizer | 0.20 | Synthesizes multiple inputs into coherent concepts |
| theme-detector | 0.15 | Identifies cross-sector thematic patterns |
| sector-analyst | 0.15 | Provides rotation and relative strength context |
| institutional-flow-tracker | 0.15 | Tracks smart money positioning via 13F filings |
| edge-hint-extractor | 0.10 | Supplementary hints that support other signals |

**Total: 1.00**

## Weight Rationale

### edge-candidate-agent (0.25)

Highest weight because:
- Quantitative, data-driven anomaly detection
- Produces actionable tickets with specific entry/exit levels
- Least susceptible to narrative bias
- Signals are time-stamped and verifiable

### edge-concept-synthesizer (0.20)

Second highest because:
- Integrates multiple upstream inputs
- Produces structured edge concepts with testable hypotheses
- Requires corroboration from multiple sources

### theme-detector, sector-analyst, institutional-flow-tracker (0.15 each)

Equal moderate weights because:
- Each provides a distinct analytical lens
- Themes capture narrative momentum
- Sectors capture rotational flows
- Institutional flow captures smart money
- None is inherently more reliable than others

### edge-hint-extractor (0.10)

Lowest weight because:
- Hints are suggestive, not definitive
- Often require validation from other skills
- Useful for idea generation, less for conviction

## Composite Score Calculation

The composite conviction score for an aggregated signal is calculated as:

```
composite_score = Σ (skill_weight × normalized_signal_score × agreement_bonus)
```

### Normalization

Raw scores from different skills are normalized to [0, 1]:
- For numeric scores: `(score - min) / (max - min)`
- For categorical grades: A=1.0, B=0.8, C=0.6, D=0.4, F=0.2
- Missing values: 0.0 (no contribution)

### Agreement Bonus

When multiple skills agree on the same signal:
- 2 skills agree: +10% to composite score
- 3+ skills agree: +20% to composite score
- Capped at 1.0 maximum

### Recency Adjustment

Recent signals receive a boost:
- Within 24 hours: ×1.0 (no adjustment)
- 1-3 days old: ×0.95
- 3-7 days old: ×0.90
- 7+ days old: ×0.85

## Deduplication Logic

### Similarity Detection

Two signals are considered duplicates if:
1. **Ticker overlap > 50%** -- More than half the tickers are the same
2. **Theme similarity > 0.8** -- Text similarity of descriptions (cosine or Jaccard)
3. **Direction match** -- Both LONG or both SHORT

### Merge Strategy

When duplicates are detected:
1. Keep the signal with the highest raw score as primary
2. Aggregate contributing skills from all duplicates
3. Boost composite score by 5% per merged duplicate (indicates consensus)
4. Log all merged signals for audit trail

## Contradiction Detection

### Definition

A contradiction exists when:
1. Same ticker or sector appears in multiple signals
2. Directions are opposite (LONG vs SHORT)
3. Time horizons overlap

### Severity Levels

| Level | Criteria | Action |
|-------|----------|--------|
| LOW | Different time horizons (e.g., short-term SHORT vs long-term LONG) | Log, no penalty |
| MEDIUM | Same horizon, different skills | Flag for review, -10% to both scores |
| HIGH | Same skill, opposite signals | Critical alert, exclude from ranking |

### Resolution Hints

The aggregator provides resolution hints:
- **Timeframe mismatch** -- Check if signals apply to different horizons
- **Sector vs stock** -- Sector bearish but specific stock bullish within sector
- **Flow vs price** -- Institutional buying but price declining (accumulation phase?)

## Customizing Weights

### For Momentum Traders

Increase weights for skills that capture short-term moves:
```yaml
weights:
  edge_candidate_agent: 0.30
  theme_detector: 0.25
  sector_analyst: 0.20
  edge_concept_synthesizer: 0.15
  institutional_flow_tracker: 0.05
  edge_hint_extractor: 0.05
```

### For Value/Position Traders

Increase weights for skills that capture longer-term positioning:
```yaml
weights:
  institutional_flow_tracker: 0.30
  edge_concept_synthesizer: 0.25
  edge_candidate_agent: 0.20
  sector_analyst: 0.15
  theme_detector: 0.05
  edge_hint_extractor: 0.05
```

### For Thematic Investors

Increase weights for narrative and theme detection:
```yaml
weights:
  theme_detector: 0.30
  edge_concept_synthesizer: 0.25
  sector_analyst: 0.20
  edge_candidate_agent: 0.15
  institutional_flow_tracker: 0.05
  edge_hint_extractor: 0.05
```

## Quality Indicators

### Signal Confidence Factors

Each aggregated signal includes a confidence breakdown:

| Factor | Weight | Description |
|--------|--------|-------------|
| multi_skill_agreement | 0.35 | How many skills corroborate the signal |
| signal_strength | 0.40 | Average normalized score across contributing skills |
| recency | 0.25 | Time decay adjustment |

### Minimum Thresholds

Recommended minimum conviction thresholds:

| Trading Style | Min Conviction | Rationale |
|---------------|----------------|-----------|
| Aggressive | 0.50 | More signals, higher risk |
| Moderate | 0.65 | Balanced approach |
| Conservative | 0.80 | Fewer, higher-quality signals |

## Limitations

1. **Garbage In, Garbage Out** -- Aggregation quality depends on upstream skill quality
2. **Weight Sensitivity** -- Small weight changes can shift rankings significantly
3. **No Fundamental Override** -- The aggregator doesn't validate fundamental thesis
4. **Temporal Lag** -- Some skills (institutional flow) have inherent reporting delays

## Best Practices

1. **Regular Weight Tuning** -- Review and adjust weights quarterly based on backtested performance
2. **Contradiction Review** -- Always manually review HIGH severity contradictions
3. **Provenance Audit** -- Periodically trace high-conviction signals back to source data
4. **Diverse Inputs** -- Run at least 3 upstream skills before aggregating for meaningful consensus
