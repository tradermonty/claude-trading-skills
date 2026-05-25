# Trade Performance Coach Review Framework

## Purpose

This framework turns recorded trade evidence into process-improvement feedback.
It evaluates the quality of the trader's decision process, not whether the trade
made money.

A clean-process loss can be acceptable. A profitable rule violation can still be
a serious process problem.

## Five-Axis Review Model

| Axis | Question | Typical Evidence | Output |
|---|---|---|---|
| Thesis Quality | Was the original idea clear, falsifiable, and aligned with the setup? | trade thesis, invalidation, catalyst, setup notes | root-cause finding |
| Process Adherence | Did actual behavior follow the plan and workflow? | entry timing, setup confirmation, thesis record, stop plan | process findings |
| Risk Discipline | Did actual risk follow predefined limits? | planned R, actual R, portfolio heat, weekly loss, correlations | risk manager notes |
| Execution Quality | Were entry, stop, adds/trims, and exits consistent with plan? | execution log, partial close, stop changes | execution assessment |
| Behavior Pattern | Did the journal suggest repeated behavior patterns? | journal text, timing, rule deviations | behavior tags + questions |

## Root-Cause Categories

Use one primary root cause and optional secondary causes:

- `thesis_quality`
- `execution`
- `risk_sizing`
- `market_environment`
- `rule_violation`
- `randomness`
- `unknown`

Classification guidance:

- If the plan was followed and the setup was valid, but the market simply moved
  against the trade, prefer `randomness` or `market_environment`.
- If the trade was taken without the required setup confirmation, prefer
  `execution` or `rule_violation`.
- If the actual risk exceeded the user-defined plan, prefer `risk_sizing`.
- If the user's note shows the trade was taken to make back a prior loss, prefer
  `rule_violation` with a possible `revenge_trade` behavior tag.

## Verdicts

| Verdict | Use When |
|---|---|
| `OK` | The record is complete enough, no material process/risk issue appears, and no behavior pattern is detected. |
| `WARN` | Minor issue, incomplete evidence, or soft process concern. |
| `REVIEW_REQUIRED` | Meaningful process/risk/execution issue, but not a hard rule violation. |
| `RULE_VIOLATION` | Explicit rule breach: risk limit, stop discipline, regime gate, or unplanned add/trim. |
| `COOL_DOWN` | Repeated violations, revenge pattern, drawdown escalation, or multiple critical findings. |

## Scoring

Scores are advisory, not scientific. They help the user compare reviews over
time.

Start at 100 and subtract:

- info finding: 0-5
- warning finding: 10-20
- critical finding: 25-40
- missing critical record: 10-20

Recommended score fields:

```yaml
process_score: 0-100
risk_score: 0-100
execution_score: 0-100
review_quality_score: 0-100
```

`review_quality_score` reflects evidence completeness. Do not over-interpret
behavior tags when review quality is low.

## Next-Session Operating Rules

Each review should produce concrete, temporary operating rules. Good rules are:

- observable
- time-boxed
- tied to evidence
- simple enough to follow before the next trade

Examples:

- "For the next two trades, max planned risk is 0.5R."
- "No entry without a pre-entry thesis record and invalidation point."
- "If two rule violations occur in one week, switch to review-only mode."
- "A missed entry may be added to the watchlist, but not chased above the planned trigger."

## Evidence Standard

Every warning or tag should cite evidence:

- field value (`actual.risk_r = 1.8` vs `max_risk_per_trade_r = 1.0`)
- journal phrase
- missing required record
- explicit flag (`stop_moved = true`)

Avoid unsupported claims. If evidence is unclear, say so.
