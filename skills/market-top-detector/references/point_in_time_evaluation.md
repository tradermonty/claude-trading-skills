# Point-in-time evaluation protocol v1

Status: specification only; no dataset or measured calibration results are supplied.
The existing four historical component vectors are illustrative retrospective
estimates and must never be substituted for archived observations.

## Frozen estimand and score

Before collecting outcomes, freeze a manifest with protocol version `market-top-pit-v1`,
score version `market-top-risk-v1`, code commit, configuration hash, provider versions,
universe-selection rules, missing-data policy and calendar version. Preserve the
current weights, correlation discount and availability-based redistribution in the
score implementation. Record all six raw components, availability flags, adjusted
components, effective weights and final score. Do not pool different availability
masks or score versions when reporting band frequencies.

Define the primary event as an S&P 500 closing-price loss of at least 10% relative
to the as-of close at any of the next 40 trading-session closes. This operational
correction event does not identify a literal local market top. Freeze this endpoint;
other horizons (10/20 sessions) and thresholds (15/20%) are secondary and reported
separately, without replacing a disappointing primary result.

## Versioned dataset specification

Store immutable UTF-8 JSONL observations and a JSON manifest with file SHA-256 hashes.
One observation per Friday session close (last session of a holiday week); sample
all eligible weeks, including ordinary/non-event periods, without top-based selection.
Each row contains:

- `schema_version`: `market-top-pit-v1`; unique `observation_id`, `as_of` (UTC),
  exchange session date, score version, code commit and configuration hash.
- `inputs`: immutable artifact URI and SHA-256 for every input; source, vintage,
  publication time, retrieval time, original timezone and maximum observation time.
  Every observation/publication must be no later than `as_of`. Retrieval after
  `as_of` is acceptable only for a verifiable archived vintage available then.
- Point-in-time basket membership and selection evidence (including delisted names);
  six raw scores and availability flags, adjustments, effective weights and final score.
- `split`: development or holdout; `label_status`: pending, complete or excluded;
  forward 40 session dates/closes, as-of close, minimum forward return and event boolean.
  Outcome data lives separately from scoring inputs and is never read by scoring.
- Exclusion reason for unverifiable vintage, missing calendar/prices, unavailable
  required inputs or incomplete horizon. Never encode excluded/pending as non-events.

No historical live `--as-of` run is valid evidence: the current CLI rejects it because
live quotes are not archived point-in-time quotes. A future offline replay must read
only hashed archived inputs and reproduce component/score outputs before evaluation.

## Chronological evaluation and leakage controls

Pre-register a date range and split: development 2000-01-01 through 2015-12-31;
holdout 2016-01-01 through 2025-12-31. Purge development observations whose 40-session
outcome crosses the holdout boundary. If these dates cannot be reconstructed from
verifiable vintages, report infeasible and pre-register a new untouched prospective
holdout; do not manufacture history. These periods are protocol choices, not results.
Fit any thresholds solely on development data, freeze hashes before opening holdout
outcomes, and evaluate the holdout once. Record previous exposure to holdout data;
if already used for tuning it cannot be described as untouched.

## Reproducibility and reporting contract

A future evaluator must validate input hashes/timestamps, reconstruct scores from
archived inputs, label complete horizons, enforce split/purge rules, then emit a
versioned JSON metrics artifact plus a human report. Fixed inputs and code must
produce identical rows/metrics; missing vintages stop that observation with a reason.

Use fixed score bands [0,20], (20,40], (40,60], (60,80], (80,100]. For each split,
availability mask and band, report n, events, non-events, empirical event rate and
95% Wilson interval. These are observed frequencies, not a new probability model.
At a predeclared score >60 alert threshold report TP/FP/FN/TN, false alarms (FP),
misses (FN), precision, recall and coverage; undefined denominators yield null.
Report pending/excluded counts and reasons separately. Since weekly 40-session
outcomes overlap, Wilson intervals are descriptive only: also report uncertainty
using a moving-block bootstrap (52-week blocks, 2,000 replicates, fixed seed 515),
flag insufficient blocks/samples, and publish split-level counts. Never imply
independent trials. Publish non-event and event examples with provenance.

A trained probability mapping requires a separate version, development-only fitting
and untouched holdout calibration metrics. Until those measured results exist, retain
`calibrated_probability: false`. The 15-point analogue tolerance is heuristic and
cannot be tuned against these illustrative historical vectors to claim validation.
