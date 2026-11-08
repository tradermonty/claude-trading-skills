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
  commands. It writes `deps-nightly-smoke.json` and exits 0 on pass, 1 on
  failure, and 2 on incomplete coverage. The workflow step maps these to a
  promotion gate (see "Promotion gate" below).
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
2. Trigger one `workflow_dispatch` run; confirm no skill row is `fail`
   (`ok: false`) and the aggregate `outcome` is `pass` or `incomplete`, and
   review the incomplete list in the `packaged-deps-nightly-report` artifacts.
   Aggregate `pass` is not reachable until the incomplete skills are resolved
   (see "Promotion gate" below).
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

### Promotion gate

On the current tree 54 skills are eligible and 19 are incomplete: the 18 in
`PENDING_SMOKE_CONTRACTS` plus `portfolio-manager`, a recorded skip. The runner
therefore exits 2 every night, and aggregate `pass` cannot occur until that
list is closed.

The nightly step maps the runner exit code as follows:

| Runner exit | Step result | Why |
|---|---|---|
| 0 | green | Aggregate `pass` |
| 1 | red | A skill or the table failed; this is the gate |
| 2 | green with a `::warning::` annotation | Incomplete coverage only; the artifact holds the outcome |
| other nonzero | red | Unexpected runner crash |

So the gate for #349 is: no skill `fail`, aggregate `pass` or `incomplete`,
and the incomplete list reviewed. Because the step stays green on incomplete,
the green window and the eventual removal of `continue-on-error` are not
blocked by the pending list, but a green step is not proof of complete
coverage: read aggregate `outcome` and the per-skill rows in the uploaded
JSON. `scripts/tests/test_packaged_deps_nightly_workflow.py` pins this mapping.

Closing the incomplete list is tracked under #507, not #349. The
`portfolio-manager` skip reason is that `check_alpaca_connection.py` has no
offline CLI shape: it starts a live Alpaca connection probe immediately (see
`scripts/check_skill_deps.py`), so it cannot run in a clean room until a
synthetic-state CLI exists.

The nightly job still has `continue-on-error: true` under #349. Removing it is
#349's follow-up, not this change. This change does not establish a green
observation window. It does not unpack `.skill` archives; the existing
runner executes checkout scripts with isolated declared dependencies.

The remaining #507 work includes per-skill HTTP fault injection and redaction,
keyless optional-provider runs, synthetic personal-state CLI smokes, unified
smoke/sample coverage inventory, archive execution, calendar/intraday replays,
and sampled LLM checks. No scheduled or live run is claimed here.

## Python-specific public FINVIZ fallback (#671)

The declaration gate otherwise rejects environment markers. Its sole scoped
exception is theme-detector's optional
`finvizfinance>=1.5.0; python_version >= "3.10"` declaration. Upstream 1.5.0
requires Python>=3.10. This marker lets the existing Python3.9 clean-room install
retain requests-based Elite operation; public group acquisition is explicitly
unavailable there, including environments that retain an older scraper.
Other skills, specifiers, markers and required dependencies remain rejected.
The authority is `config/market-calendar-dependency.yaml`; regenerate with
`scripts/generate_market_calendar.py`. Tests exercise marker evaluation and
rejected near-matches, library absence, Python3.9 public refusal and Elite success.
