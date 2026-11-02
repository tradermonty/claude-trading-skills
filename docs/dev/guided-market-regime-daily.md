# Guided fictional market-regime run

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
  `destination: trader-memory-core` and `delivery: handoff_only`.

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
helpers in `workflow_replay.py`. Changes to those helpers, the runner, workflow,
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
runtime dependencies. An integrity failure prints `BLOCKED` and preserves the
previous manifest for diagnosis; it does not rewrite its status to claim an
execution occurred. Dependency setup failures happen before a new run is
allocated.

Issue #513 remains open for delivery to the journal destination and any future
live-data or additional-workflow support. This runner alone does not authorize
or implement those extensions.
