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
  failure or incomplete coverage** — this exit-code fix is what makes the checklist item 4 flip
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
2. Trigger one `workflow_dispatch` run; confirm the aggregate `outcome` is `pass` and every skill row is `ok: true`
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

## Evidence outcomes (issue #507 partial implementation)

The runner distinguishes execution success from incomplete coverage. Its JSON
contains `skills`, aggregate `outcome`, and `summary` counts of skill outcomes:

| Outcome | Skill `ok` | Exit code | Meaning |
|---|---|---|---|
| `pass` | `true` | 0 | Every eligible skill installed, imported, and executed every declared contract successfully |
| `fail` | `false` | 1 | Table/manifest validation, setup, import, command, or assertion failed |
| `incomplete` | `null` | 2 | Pending, empty, or skipped contracts; or no eligible skills |

A skill with both executed and skipped contracts is `incomplete` with
`contracts_status: partial`. Other incomplete statuses are `pending_wave2`,
`missing` (empty contract list), and `skipped`. Errors take precedence over
incomplete coverage, both within a skill and in the aggregate. A setup failure
has `contracts_status: not_run`, an empty `contracts` list, and outcome `fail`.

Malformed requirements are a table failure before any subprocess runs, even
when another skill could pass. Table failures include `table_problems`,
`skills: []`, aggregate `outcome: fail`, and zero summary counts because no
skill was executed. An empty eligible inventory likewise has zero counts but
aggregate `outcome: incomplete`. Only skills with required third-party
requirements are eligible; these counts do not cover all repository skills.

Incomplete coverage prints GitHub `::warning::` annotations and never prints
the all-passed message. Consumers must check `outcome == "pass"` or
`ok is True`; `ok: null` is unverified, not successful evidence. Existing
consumers that only inspect the old boolean field must adopt these semantics.

The nightly job still has `continue-on-error: true` under #349. GitHub's job
conclusion may remain green despite a nonzero runner exit; inspect annotations
and the uploaded JSON. This change does not promote the job or establish a
green observation window. It does not unpack `.skill` archives; the existing
runner executes checkout scripts with isolated declared dependencies.

The remaining #507 work includes per-skill HTTP fault injection and redaction,
keyless optional-provider runs, synthetic personal-state CLI smokes, unified
smoke/sample coverage inventory, archive execution, calendar/intraday replays,
and sampled LLM checks. No scheduled or live run is claimed here.
