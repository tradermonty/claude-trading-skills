# Validation Status and Reproduction Requirements

The component and zone thresholds in this beta skill are documented
heuristics. This repository does not currently include a pinned historical
dataset or a walk-forward harness capable of reproducing quantitative return,
win-rate, or drawdown claims. Accordingly, this skill makes no such claims and
its zone labels must not be treated as allocation or performance rules.

## What is verified in-repository

- Pure component calculations and boundary behavior are covered by unit tests.
- Offline bull, bear, degraded-data, and sparse-data snapshots exercise the
  same `run_analysis()` entry point used by live mode.
- Missing inputs fail closed: a composite classification requires at least four
  components representing at least 65% of original model weight.
- Report and package drift are checked by repository validation gates.

These tests establish deterministic software behavior. They do not establish
predictive power or investment performance.

## Required artifacts for historical validation

A future validation change must include all of the following in the repository:

1. A runnable harness that imports the shipped calculation code.
2. A data manifest with source URLs, retrieval timestamps, hashes, symbol map,
   delisting policy, and point-in-time universe construction.
3. A pinned or deterministically retrievable input snapshot that permits an
   offline rerun without silently substituting current constituents.
4. Explicit no-lookahead rules, missing-data treatment, transaction-cost
   assumptions, and non-overlapping or dependence-aware statistical summaries.
5. Machine-checked expected aggregates and documented commands to reproduce
   them.

Until those artifacts exist, `RISK_ON`, `NEUTRAL`, and `RISK_OFF` are descriptive
heuristic bands only. Any historical experiment performed outside this
repository is exploratory and must not be presented as verified evidence here.
