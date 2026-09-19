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
measured 35,429 out of 48,073 (73.698%). The temporary repository effective
floor is therefore the lower cross-platform baseline rounded down to 72%, with
a 75% target. Per-skill floors follow the same cross-platform rule. All current
waivers expire on 2026-10-31 and link to Issue #293.

### Burn-down schedule

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
