# Packaged-Dependency Smoke Contracts (issue #349)

Context: #330 requires every executable skill to declare its runtime
dependencies in `skills/<id>/requirements.txt`. The nightly
`.github/workflows/packaged-deps-nightly.yml` smoke-tests those declarations in
clean-room venvs. Issue #349 promotes that pipeline from report-only toward
fail-closed.

## Structure

- `scripts/check_skill_deps.py` declares `SMOKE_CONTRACTS` (per skill, one or
  more `SmokeContract` entries) and `PENDING_SMOKE_CONTRACTS` (wave-2
  backlog). Every third-party-required executable skill must be in one of the
  two sets — `scripts/tests/test_smoke_contracts.py` enforces the partition.
- The module is intentionally free of `subprocess`/network imports (guarded by
  `test_check_module_has_no_network_surface`), so the nightly runner can import
  the table without pyyaml or any project venv.
- `scripts/smoke_contracts_runner.py` executes the table: fresh venv per skill,
  declared-requirements-only install, reverse import probes, contract
  commands. It writes `deps-nightly-smoke.json` and exits **nonzero on any
  failure** — this exit-code fix is what makes the checklist item 4 flip
  meaningful.
- `--root` allows running the same runner against an alternate checkout.

## Contract semantics

- `script` must be repo-relative inside `skills/<id>/scripts/`.
- `args`/`expect_exit`/`expect_out`: the clean-room command, expected exit
  code, and required output substrings (the fixture expectation).
- `fixture`: optional repo-relative file backing the expectation; verified
  present by validation and recorded in the evidence.
- Skip entries (empty `script`) require `skip_reason`; they are recorded as
  skipped in the evidence instead of executed.
- Wave-1 contracts were dry-run on the 2026-10-03 worktree; evidence links in
  the #349 PR.

## Rollout (maintainer sequencing from #349)

1. This PR (contracts + runner + exit codes) keeps
   `continue-on-error: true` — report-only promotion trial.
2. Trigger one `workflow_dispatch` run; confirm every contract row is `ok`
   in the `packaged-deps-nightly-report` artifacts.
3. After the 2-week green window completes (effective green from 2026-09-27,
   so ≥ 2026-10-10/11) a follow-up PR removes `continue-on-error: true` and
   renames the job to fail-closed. The nightly `report` step stays exit-0:
   declaration enforcement already fails `ci.yml` via `run_check`; the report
   is evidence, not a gate.

## Adding a contract (wave 2)

1. Dry-run the candidate command on a clean venv
   (`uv venv && uv pip install -r skills/<id>/requirements.txt`).
2. Add the `SmokeContract` entry with a distinctive `expect_out` token.
3. If coverage would move a skill out of `PENDING_SMOKE_CONTRACTS`, remove it
   from there in the same change — the partition test fails otherwise.
