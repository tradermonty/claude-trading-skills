# Scoring System

The initial implementation uses deterministic scores. Scores are research triage aids, not trade signals.

## Continuation Quality Score

`continuation_quality_score` ranges from 0 to 100.

| Component | Intent |
|---|---|
| Catalyst quality | Durable revaluation catalysts score higher than no-news pops |
| Liquidity | Higher dollar volume improves execution realism and institutional relevance |
| Volume shock | Volume expansion indicates unusual attention and participation |
| Close quality | Strong closes receive higher continuation score for upside events |
| Setup context | Base breakout and gap-and-go patterns score higher than weak or failed moves |
| 52-week context | Upside events near 52-week highs receive additional score |
| Data quality | Missing history, missing volume, and split-like moves reduce confidence |
| Extension risk | Extreme prior extension reduces quality score |

## Reversal Risk Score

`reversal_risk_score` ranges from 0 to 100.

Risk increases when:

- Catalyst is `NO_CLEAR_NEWS`, `LOW_FLOAT_SPECULATION`, or `CAPITAL_STRUCTURE`
- The event is extremely extended
- Upside event closes weakly
- Dollar volume is below the liquidity floor
- Data quality flags are present

## Study Priority Score

`study_priority_score` ranks which events deserve manual review. A high-priority event is not necessarily a trade; it may be a high-quality example, a dangerous failure, or a useful negative case.

## Suggested Human Ratings

| Condition | Human-facing label |
|---|---|
| Quality >= 75 and catalyst is durable | `A_REVALUATION_OR_HIGH_QUALITY_EVENT` |
| Quality >= 60 | `B_MOMENTUM_EVENT` |
| Reversal risk >= 65 | `D_LOW_QUALITY_OR_REVERSAL_RISK` |
| Otherwise | `C_STUDY_ONLY` |

## Handoff Flags

| Flag | Meaning |
|---|---|
| `stockbee_episodic_pivot` | Event resembles a Day 1 EP / gap-and-go / base breakout candidate |
| `pead_screener` | Earnings or guidance catalyst may warrant PEAD-style research |
| `theme_detector` | Theme or high-priority event may deserve cluster review |
| `edge_candidate_agent` | Event is strong enough to export as an edge research prompt |
| `parabolic_short_watch` | Reversal-risk profile is high enough for study-only exhaustion review |
