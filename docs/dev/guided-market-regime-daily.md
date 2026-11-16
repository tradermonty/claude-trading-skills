# Guided fictional market-regime run

[日本語](guided-market-regime-daily.ja.md)

`scripts/run_market_regime_daily.py` guides the `market-regime-daily` workflow
through readiness, run-scoped artifact handoff, a human posture decision, and a
local journal handoff. This is an offline learning path using the committed
fictional component fixtures, evaluated at **2026-01-15T13:08:00+00:00**. It does
not describe today's market and is not a buy/sell signal.

## Start and decide

Use the repository's locked environment (`uv sync --locked --extra dev`). No
provider credentials are required. Run from the repository root:

```bash
uv run python scripts/run_market_regime_daily.py --run-dir reports/regime-demo
```

Choose a new directory for every run. Existing directories, including empty
ones, are refused. The runner validates the workflow and fixture contracts,
loads the required native scorer APIs, and snapshots the fixtures. It computes
breadth and uptrend reports, explicitly skips optional top-risk analysis, and
computes an Exposure Coach proposal from only that run's outputs. To include
top-risk analysis, add `--include-top-risk` when creating the run. That setting
cannot be changed on resume.

In an interactive terminal the command displays the proposal and asks for
`allow`, `restrict`, or `cash-priority`. Entering a posture explicitly records
your fictional decision. A blank answer pauses the run. With redirected input
or CI, the runner always pauses after displaying the proposal and returns 3:

```bash
uv run python scripts/run_market_regime_daily.py \
  --run-dir reports/regime-demo --status
uv run python scripts/run_market_regime_daily.py \
  --run-dir reports/regime-demo --resume --decision restrict
```

`--decision` is accepted only with `--resume` at `AWAITING_DECISION`. A proposal
does not record permission automatically. Completed runs reject further
decisions; `--resume` without a decision validates and displays the existing
completed outcome without rewriting artifacts or step timestamps.

## Decision diff (fictional two-day replay)

A decision diff answers one morning question: of the revisit conditions I wrote
down at my last decision, which ones changed, which did not, and which can not be
judged today? It is read-only evidence for the human gate and never decides a
posture. It exists only for the fictional fixtures, and it is off unless you ask
for it. Without the new options a run is what it was before, except for the
nested-directory refusal described under "Current limits".

Day 2 uses a second fictional fixture set,
`examples/workflows/market-regime-daily/guided-day-2/`, evaluated at
**2026-01-16T13:08:00+00:00**. It is not a replay variant and is not listed in
`replay-coverage.yaml`; the day-1 replay contract and goldens are untouched.

### Walk through two days

```bash
# Day 1: create with top-risk, then decide and record revisit conditions.
uv run python scripts/run_market_regime_daily.py \
  --run-dir reports/market-regime-daily/d1 --include-top-risk
uv run python scripts/run_market_regime_daily.py \
  --run-dir reports/market-regime-daily/d1 --resume --decision restrict \
  --revisit-conditions my-conditions.json

# Day 2: create against day 1, read the diff (exit 3), then decide.
uv run python scripts/run_market_regime_daily.py \
  --run-dir reports/market-regime-daily/d2 --fixture-set day-2 \
  --previous-run-dir reports/market-regime-daily/d1
uv run python scripts/run_market_regime_daily.py \
  --run-dir reports/market-regime-daily/d2 --resume --decision allow
```

`my-conditions.json` is a file you author, for example:

```json
{
  "schema_version": 1,
  "conditions": [
    {"id": "breadth-weakens", "label": "Breadth composite falls below 60",
     "metric": "breadth.composite_score", "comparator": "lt", "threshold": 60},
    {"id": "top-risk-rises", "label": "Top-risk composite reaches 50",
     "metric": "top_risk.composite_score", "comparator": "ge", "threshold": 50}
  ]
}
```

On the second day the runner prints a block headed `Decision diff (read-only; it
never records a decision)`: the previous decision, one
`[changed|unchanged|not_evaluable]` line per condition with its previous and
current value, and a list of things to confirm. The same data is saved in
`decision_diff.json`, and `--status` prints it again while the run is paused.

The chain depends on you passing `--revisit-conditions` at every decision. The
day-2 decision above omits it, so day 2 records `revisit_conditions: null` and a
day-3 run that names day 2 as its previous run has no conditions to classify; it
shows only a "no revisit conditions" item to confirm. To keep the chain going,
pass a conditions file with each decision.

### Command-line rules

| Option | Accepted when | Notes |
|---|---|---|
| `--fixture-set {day-1,day-2}` | creating a run | Default is day 1. Fixed for the life of the run. |
| `--previous-run-dir PATH` | creating a run | Names the previous run explicitly. |
| `--previous-runs-root ROOT` | creating a run | Picks the most recent completed run under ROOT. Mutually exclusive with `--previous-run-dir`. |
| `--revisit-conditions FILE` | `--resume --decision` at the gate | Records conditions with the decision. |

Giving `--fixture-set`, `--previous-run-dir` or `--previous-runs-root` together
with `--resume` or `--status`, giving both previous-run options, or giving
`--revisit-conditions` without `--decision` exits with code 2. The exit codes of
all other outcomes are unchanged. The interactive posture prompt is unchanged
too: to record conditions, pause with a blank answer and resume with flags. A
posture entered at the prompt records `revisit_conditions: null`.

### Choosing the previous run

- **Explicit** (`--previous-run-dir`): the directory is classified as given.
  It is refused only if its evaluation time is later than today's; an equal time
  is allowed.
- **Root** (`--previous-runs-root`): only the root's immediate child directories
  are considered, with no recursion and never by file modification time. The
  root must not be a symlink. A child counts when its manifest has
  `workflow_id` `market-regime-daily`, status `COMPLETED`, a timezone-aware
  `evaluation_at` not later than today's, and a timezone-aware gate
  `decision_at`. Symlinked children and plain files are skipped. A child whose
  manifest is missing, oversized or unparsable is counted in
  `skipped_unreadable`. The greatest `(evaluation_at, decision_at)` wins; an exact
  tie gives `ambiguous`. A root that does not exist and a root with no
  qualifying run both give `not_found` with different messages. More than 500
  child directories (files are not counted) gives `unavailable`; use a dedicated
  root such as `reports/market-regime-daily/`.
- **No fallback.** The one selected run is fully verified. If it fails, that
  status is reported and the run continues as a first run. An older run is never
  substituted, so a superseded decision is never shown as "previous". Use
  `--previous-run-dir` to choose an older run on purpose.

The result is frozen once, at creation, into `inputs/previous_run.json` with the
selection counts and no paths. Resume and `--status` never read the previous
directory again, so it can be moved or deleted afterwards. Classification is
read-only: it never takes or removes the previous run's lock and writes nothing
there.

| Status | Meaning |
|---|---|
| `loaded` | Verified, completed, earlier or equal in time. Its conditions are classified. |
| `not_found` | The path or root is absent, or no qualifying run exists. |
| `unavailable` | Symlink in the path, not a directory, locked, unreadable, a lock or change appeared while reading, or too many root children. |
| `invalid` | No readable manifest, unknown fixture set, or any unexpected failure. |
| `other_workflow` | The manifest belongs to a different workflow. |
| `incomplete` | No recorded decision yet. |
| `source_changed` | Runner, workflow, fixture or native sources changed since that run. |
| `integrity_mismatch` | The previous run no longer verifies. |
| `not_earlier` | The previous run is later than today's evaluation time. |
| `ambiguous` | Several root candidates tie for most recent. |

Any status other than `loaded` is a first run: `first_run: true`, no conditions,
a fixed message, and a "first run" item to confirm. Messages are fixed strings;
the runner never echoes file content.

### What a decision records

When `--previous-run-dir`, `--previous-runs-root` or `--revisit-conditions` is
used, the decision gate stores an extended record and the journal becomes
`schema_version: 2`. It keeps every version-1 field and adds four:

- `decision`: the posture, as before.
- `revisit_conditions`: your conditions, each with `value_at_decision` and
  `holds_at_decision`. `null` means none were given; `[]` means you explicitly
  recorded that nothing would change your mind.
- `data_as_of`: the evaluation time and the `as_of` of every input that ran.
- `unevaluated`: inputs not evaluated, either an optional step you did not select
  (`optional_step_not_selected`) or an exposure input this workflow never
  provides (`not_provided_by_this_workflow`).

The journal also carries `decision_diff`, the manifest record of the diff file or
`null`. Runs made without the new options keep the version-1 journal.

### Conditions and metrics

Each condition has exactly `id`, `label`, `metric`, `comparator` and
`threshold`. The whole `id` must match `[a-z0-9][a-z0-9-]{0,63}`, with no
trailing newline, and must be unique. `label` is 1 to 200 printable characters.
There are at most 20 conditions and the file is at most 64 KiB. NaN, Infinity and duplicate JSON keys are rejected, and every error
is a fixed message that does not echo the file.

| Metric | Comparators | Threshold |
|---|---|---|
| `breadth.composite_score`, `uptrend.composite_score`, `top_risk.composite_score` | `lt`, `le`, `gt`, `ge` | finite number, not a boolean |
| `exposure.recommendation` | `eq`, `ne` | `CASH_PRIORITY`, `REDUCE_ONLY` or `NEW_ENTRY_ALLOWED` |

Values always come from the run's own verified artifacts. A skipped step
records no baseline (`value_at_decision: null`), which is allowed. Component and
numeric exposure metrics are follow-up work. Recording a condition that already
holds prints a warning, and the next diff lists it as
`condition_already_met_at_decision`.

### How conditions are classified

`changed` means the condition's truth value flipped between the previous
decision and today. A threshold crossed in either direction is `changed`; a
value that moved without flipping it is `unchanged`. `unchanged` is reached only
after every check below has passed. The first failing check gives
`not_evaluable` with that reason:

1. `no_baseline_value`: nothing was recorded at the previous decision.
2. `input_missing_today`: today has no value, for example the optional top-risk
   step was not selected (detail `optional_step_not_selected`).
3. `input_as_of_unknown`: an `as_of` is missing on either side.
4. `input_not_refreshed`: today's `as_of` is not strictly newer than the
   previous one. This is the stale rule: an unrefreshed input is never "no
   change".
5. `input_stale`: the input is older than its `max_age_days` at today's
   evaluation time.
6. `input_set_changed`: for `exposure.recommendation`, a different set of inputs
   fed the composite.
7. `invalid_value`: a non-finite value or a type mismatch.

Missing or stale data is never `unchanged`; the tests enforce that contract.

## Evidence and boundaries

The run directory holds:

- `manifest.json`: UUID run ID, readiness, fixed evaluation time, wall-clock
  execution timestamps, source hashes, input snapshots, step states, consumed
  artifact hashes, and the explicit decision.
- `inputs/*.json`: fictional fixture snapshots bound to the run ID.
- `01_*.json` through `03_*.json`: native component-score analyses. Step 3 has
  no output in the default path and is marked `SKIPPED`, never passed.
- `04_exposure_proposal.json`: native Exposure Coach calculation, including
  strict breadth/uptrend provenance and its fixed-time freshness check.
- `journal.json`: the decision and proposal hash, with
  `destination: trader-memory-core` and `delivery: handoff_only`. It is schema 2
  with the extra fields above when the decision diff options were used.
- `inputs/previous_run.json` and `decision_diff.json`: present only when a
  previous run was requested. The first is the frozen evidence about the previous
  run; the second is the read-only diff, recomputed and compared on every resume.
  A diff or snapshot that does not belong to the run, or that differs from its
  recomputation, blocks resume.

**The journal is not delivered to trader-memory-core.** The runner does not
read or modify real thesis/journal state, portfolios, accounts, or dotenv files.
It does not inspect or record credentials. Native scorers consume complete,
fictional component scores; provider fetches, individual component calculators,
live API behavior, and broker actions are outside this path. The runner calls
the native Exposure Coach Python API; it does not execute that skill's CLI.

Before handoff and resume, the runner checks fixed paths, step dependencies,
schemas, source hashes, input/output bytes, and run IDs. It recomputes saved
results with native APIs for validation, without repeating completed step
publication. It refuses changed/missing artifacts and source revisions rather
than adopting files from another run. Hashes detect corruption and unintended
edits; this local manifest is not a signed or tamper-proof audit record.

The current implementation shares the market fixture validation and scorer
helpers in `workflow_replay.py` and its `workflow_replay_pkg` package; the
source fingerprint covers both. Changes to those helpers, the runner, workflow,
fixtures, or relevant native skill scripts require a new run directory. The
existing deterministic replays remain the independent numeric baseline.

## Interruption and recovery

Every step checkpoints `RUNNING` before execution and checkpoints its output
hash and completion afterward. Completed checkpoints resume without rewriting
their artifacts. Failed or interrupted `RUNNING` steps are never retried or
promoted automatically; preserve that directory and start a fresh run. A crash
during journal publication similarly requires a fresh run.

A `.lock` file prevents concurrent writers. `--status` briefly acquires the
same lock while validating; it does not update the manifest. A normal exit or
Python interruption removes its own lock. SIGKILL or power loss can leave one
behind. The runner never deletes an existing lock:

1. Read the PID in the exact run's `.lock` file and inspect it with `ps -p PID
   -o pid=,command=`. PID reuse is possible: verify the command and run directory.
2. If the owning process is still running, let it finish. Do not remove its lock.
3. Only after establishing that no process owns this run, remove that exact
   `.lock` file manually. Preserve all JSON artifacts and the manifest.
4. Run `--status`. If any step is `RUNNING`/`FAILED`, a hash differs, or the
   manifest is incomplete, keep the evidence and use a new directory. Do not
   edit status fields, hashes, or delete outputs to force resume.

Manifest replacement uses a flushed temporary file followed by atomic rename.
An abandoned `.tmp` file is refused rather than reused. Symlinks in run paths
are refused. Recovery is intentionally conservative.

Exit codes: **0** completed; **3** awaiting a decision; **1** failed/blocked
readiness, integrity, lock, or execution; **2** invalid arguments or missing
runtime dependencies. The decision diff adds no exit code: an unusable previous
run is a first run and still exits 3 at the gate, and invalid revisit conditions
exit 1 and leave the run paused. An integrity failure prints `BLOCKED` and
preserves the previous manifest for diagnosis; it does not rewrite its status to
claim an execution occurred. Dependency setup failures happen before a new run is
allocated.

## Current limits

- Fictional fixtures only. No provider, broker, or real trader-memory state.
- The previous run is named with `--previous-run-dir`, or chosen by recorded
  times from one dedicated root with `--previous-runs-root`; nothing else is
  scanned.
- Any edit to the runner, helpers, workflow or fixtures between two days gives
  `source_changed`, and the next day is a first run. Showing an older record
  by hash alone is future work.
- No interactive prompt for revisit conditions; use the flag.
- The record is not delivered to trader-memory-core (Issue #513).
- `as_of` follows the fixture convention until the real-data convention of
  Issue #297 exists.
- Snapshot and diff hashes detect edits and corruption; they are not tamper-proof.
  A downgrade that removes the decision record, rewrites a version-1 journal and
  re-hashes it is undetectable for a run that never used a previous run.
- A run directory can no longer be created inside a directory that has a
  `manifest.json` in any ancestor. This is a new refusal that applies with or
  without the new options, because writing a run inside another run would
  corrupt its evidence.

## Measurement plan (maintainer routine)

The aim is to learn whether the diff shortens the morning decision without
hiding changes.

- **Metric A, time to decision.** From each manifest, `steps[3].decision_at`
  minus `created_at`, for example
  `jq -r '[.created_at, .steps[3].decision_at] | @tsv' reports/<run>/manifest.json`.
  This includes any time the run sat paused, so also note active minutes by hand.
- **Metric B, missed re-checks.** After each decision, count the items you still
  had to re-check that the diff did not flag. Split them into B1, items marked
  `unchanged` that had in fact changed, which is a contract bug with a target of
  0 and gets an issue if it ever happens, and B2, changes that no condition
  covered, which is a condition-authoring gap.
- **Log.** Keep a private local CSV under the gitignored `reports/` with date,
  run_id, minutes, the changed, unchanged and not_evaluable counts, B1, B2 and a
  note. Nothing is committed.
- **Window.** In this slice, exercise the procedure only on the two-day fictional
  replay. Real measurement covers 20 consecutive runs once the Issue #513
  real-data path exists, against a baseline of 5 runs without a previous run.

Issue #513 remains open for delivery to the journal destination and any future
live-data or additional-workflow support. This runner alone does not authorize
or implement those extensions.
