# CI test and executable-code coverage policy

`config/ci-test-policy.yaml` is the single source of truth for the dynamic
pytest matrix, temporary allowed failures, and coverage floors. The CI runner
rejects unknown fields, unsafe paths or dependency strings, stale skill IDs,
expired exceptions, and policy/artifact mismatches.

## Test-presence gate

Every skill with executable `skills/<id>/scripts/**/*.py` code must have at
least one canonical `test_*.py` file in `scripts/tests/` or `tests/`.
Files under a `tests/` directory and `__init__.py` are not executables.
This applies to production, beta, experimental, and deprecated skills so that a
status change cannot make an untested executable disappear from CI. An empty
test directory does not satisfy the gate.

Script-free production skills must declare `knowledge_only: true` in
`skills-index.yaml`. The marker is invalid for non-production skills and for a
skill that contains executable Python scripts at any depth under `scripts/`.

## Coverage measurement

Coverage percentages include executable code and exclude all files matching
`*/tests/*`:

- Core risk, financial-math, and state-management skills have an 85% target:
  `position-sizer`, `futures-position-sizer`, `trader-memory-core`, and
  `drawdown-circuit-breaker`.
- Every other executable skill has a 70% target, regardless of status.
- The repository aggregate includes every executable skill plus code under the
  root `scripts/` directory and has a 75% target.

The aggregate step publishes `per-skill-coverage.json`,
`per-skill-coverage.md`, the raw per-row coverage JSON, and the combined
repository coverage JSON. It writes the reports before returning a failure for
any floor violation, so failed CI still preserves actionable evidence.

## Ratchet and waiver rules

Coverage that is already at target has no waiver and may not regress below the
target. A below-target baseline may temporarily declare an effective floor,
but every waiver must include all of the following in versioned config:

- the final target and a lower current floor;
- an ISO `expires_on` date;
- a linked GitHub issue number;
- a non-empty reason.

The loader fails closed after the expiry date. Lowering a floor or extending an
expiry requires fresh measured evidence and explicit review; it is not routine
CI maintenance. Once a skill reaches its target, remove its waiver instead of
resetting the baseline.

The historical 2026-08-10 baseline uses executable code only. Across the then-current 69
executable skills plus root repository scripts, Linux CI measured 35,031
covered statements out of 48,073 (72.870%); local Python 3.9 validation
measured 35,429 out of 48,073 (73.698%). At that baseline the temporary
repository effective floor was the lower cross-platform baseline rounded down
to 72%, with a 75% target; that aggregate waiver has since been retired (see
below). Per-skill floors follow the same cross-platform rule.

### Status as of 2026-10-10

All waivers originally expired on 2026-10-31, and the loader fails closed after
the expiry date, so every `ci_test_matrix.py` command would have failed from
2026-11-01. They were handled on measured evidence from three successful main
CI runs (Ubuntu/Python 3.10): 38043262308, 37331242157 and 37257679899.

- The aggregate waiver is retired (`aggregate_coverage.waiver: null`). The
  repository aggregate measured 77.60%, 78.18% and 78.22% in those runs, at or
  above the 75% target each time, so the effective floor is the target.
  PR-head Coverage run: recorded in the pull request. The waiver removal is
  valid only if that run also reports at least 75% with `effective_floor` 75.
- The 14 remaining per-skill waivers are re-dated to 2027-01-31 and keep
  Issue #293. Their per-skill percentages were identical in all three runs.
  No floor is lowered, and `ibd-distribution-day-monitor` is ratcheted from 38
  to 44 (measured 44.42%).

| Skill | CI actual | Floor |
|---|---:|---:|
| `breadth-chart-analyst` | 25.76% | 25 |
| `canslim-screener` | 48.56% | 48 |
| `dividend-growth-pullback-screener` | 39.24% | 39 |
| `downtrend-duration-analyzer` | 46.24% | 46 |
| `edge-candidate-agent` | 40.48% | 40 |
| `edge-strategy-designer` | 47.59% | 47 |
| `ibd-distribution-day-monitor` | 44.42% | 44 |
| `pair-trade-screener` | 56.54% | 56 |
| `skill-designer` | 47.46% | 47 |
| `stockbee-episodic-pivot-analyzer` | 59.82% | 59 |
| `stockbee-exhaustion-hammer-screener` | 59.88% | 59 |
| `stockbee-momentum-burst-screener` | 57.23% | 57 |
| `stockbee-setup-fluency-trainer` | 53.95% | 53 |
| `value-dividend-screener` | 35.07% | 34 |

`value-dividend-screener` stays at 34 because a floor of 35 would leave 0.07
points of headroom and block almost any edit to that skill.

### Expiry warnings

`ci_test_matrix.py` reports every dated exception (aggregate waiver, coverage
waivers, allowed failures) that is close to expiry. Warnings never change an
exit code.

- `urgent`: 7 days or fewer remain. Day 0 is the last valid day, because the
  loader accepts `expires_on == today`.
- `warning`: 8 to 14 days remain.
- `matrix` prints the warnings to stderr, so the Discover step log shows them
  while stdout stays pure JSON. `aggregate` prints them to stderr too, as
  GitHub `::warning` annotations when `GITHUB_ACTIONS=true`, and records every
  row under `exception_expiry` in `per-skill-coverage.json` plus an "Exception
  expiry" section in `per-skill-coverage.md`.

### Renewal rule

Extending a waiver is allowed only when all of the following hold:

- The CI coverage artifact of at least one main run supports it, and at least
  two runs if the change claims the numbers are deterministic.
- No floor decreases.
- The new floor is `floor(actual)`, unless that would leave under 0.1 points
  of headroom, in which case keep the current floor.
- One extension adds at most one quarter.
- The linked issue stays on the waiver.

### Burn-down schedule (historical, 2026-08-11 plan)

This schedule is kept for history. The remaining 14 waivers were not burned
down by 2026-10-31 and were re-dated on evidence as described above.

The 2026-08-11 local planning snapshot measured 27 waived skills and estimated
2,709 additional covered executable lines to reach every tier target. That
estimate is for workload planning only: Ubuntu/Python 3.10 CI at each pull
request head is authoritative because platform-specific imports and branches
can change both the numerator and denominator. Root CI now runs Python 3.10;
the dated Python 3.9 measurements above remain historical evidence.

| Week ending | Skills | Planning lift (covered lines) |
|---|---|---:|
| 2026-08-16 | `us-market-bubble-detector`, `economic-calendar-fetcher`, `pead-screener` | 46 |
| 2026-08-23 | `breadth-chart-analyst`, `position-sizer`, `market-breadth-analyzer` | 446 |
| 2026-08-30 | `edge-candidate-agent`, `canslim-screener`, `earnings-trade-analyzer` | 666 |
| 2026-09-06 | `ibd-distribution-day-monitor`, `value-dividend-screener`, `institutional-flow-tracker` | 505 |
| 2026-09-13 | `dividend-growth-pullback-screener`, `signal-postmortem`, `ftd-detector` | 349 |
| 2026-09-20 | `stockbee-setup-fluency-trainer`, `pair-trade-screener`, `stockbee-momentum-burst-screener` | 258 |
| 2026-09-27 | `stockbee-exhaustion-hammer-screener`, `earnings-calendar`, `stockbee-episodic-pivot-analyzer` | 230 |
| 2026-10-04 | `skill-idea-miner`, `downtrend-duration-analyzer`, `edge-strategy-designer` | 156 |
| 2026-10-11 | `strategy-pivot-designer`, `skill-designer`, `stockbee-20pct-study` | 53 |

This completes the planned per-skill work by 2026-10-11 and leaves October
12-31 for Ubuntu/Python 3.10 variance, full-matrix reruns, and removal of any
remaining waiver before expiry. The aggregate planning snapshot was 72.963%,
about 983 covered lines below 75%; the cumulative schedule crosses that local
estimate by 2026-08-30. Capture the exact CI aggregate at every pull request
head and remove the aggregate waiver no later than 2026-09-06 once the
authoritative report reaches 75%.

Each batch must add behavioral happy-path, boundary, error-path, and relevant
fail-closed assertions. Do not improve the percentage with `# pragma: no
cover`, coverage omit/source changes, file relocation, generated-code
exclusions, test-only production execution, or production-line deletion whose
sole purpose is denominator reduction. Local preflight must reach at least
71.0% for a 70% skill (or 86.0% for an 85% core skill); the waiver is removed
only after the exact Ubuntu/Python 3.10 CI command reports at least the policy
target at the pull request head. If platform results differ, keep the waiver
and add behavioral tests.

`allowed_failures` are separate from coverage waivers. They permit a matrix row
to be non-blocking only when the entry has its own future expiry, linked issue,
and reason. There are currently no allowed-failure rows; `theme-detector` is a
blocking suite.
