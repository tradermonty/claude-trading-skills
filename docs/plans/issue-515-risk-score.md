# Issue 515: risk score interpretation and validation preparation

Refs #515. Partial implementation; keep the Issue open. No measured point-in-time
calibration dataset/results are supplied, so the full acceptance criteria remain unmet.

## Selection and scope

Live queue: #571/#572/#573 CLEAN, 89 passing checks each, one scheduled-only link
check skipped, no requested changes or inline review comments. No file overlap.
Skipped #332/#495/#496/#298/#297 because existing branches/worktrees already exist.
Skipped #497 and #507 because their proposed CI/client edits overlap open PRs.
Considered #512; selected #515 as a narrower risk-interpretation change.

Replace probability claims with heuristic score labels and explicit JSON/report/CLI
interpretation. Preserve score weights and risk-budget policies. Reject analogue
matches for incomplete/invalid evidence or weighted RMS >15; expose nearest candidate
only as a diagnostic. Specify a reproducible point-in-time dataset/evaluation protocol.
Regenerate the skill package and affected generated documentation/metadata.

## Plan review

Round 1: independent sub-agent identified fallback numeric components could match
without actual evidence. Fixed plan to pass availability flags; invalid inputs yield
null match/distance/nearest and empty comparisons. Review approved corrected plan.
Also cover unrounded threshold boundaries and all output representations.

## Validation

Run skill pytest, scoped Ruff, package checks, catalog/docs/index/workflow/skillset
and navigator snapshot checks, pre-commit and diff checks. No live financial calls.
Implementation review results and actual validation are recorded in the PR.

## Implementation review

Three rounds. Round 1 found contradictory calibration claims in bundled references;
round 2 found remaining outcome-likelihood descriptions in the illustrative band
examples. Corrected all claims and rebuilt the package. Round 3 approved with no
unresolved material findings. Full skill suite: 229 passed; targeted additions: 11
passed. Scoped Ruff passes. Standard generated/metadata checks pass after removing
an unrelated duplicate Stockbee catalog row produced by the docs generator.
