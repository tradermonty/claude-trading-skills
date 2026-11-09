# Maintenance Runbook (Developer / Maintainer Operations)

This is the operational ledger for **maintaining** this repository: regenerating
derived artifacts, clearing drift-gate failures, and understanding the
self-maintenance `launchd` agents. It is **not** a general contribution guide —
it assumes you are a maintainer working on `main`.

`<repo>` below = the repository root. Never hard-code an absolute
`/Users/...` path anywhere in the repo (the `no-absolute-paths` pre-commit hook
blocks it); use `<repo>` / `$PROJECT_DIR` / `$HOME` placeholders.

Related references (this runbook links rather than duplicates):

- [`skill-automation.md`](skill-automation.md) ([日本語](skill-automation.ja.md))
  → maintainer quickstart, manual commands, scheduling, and the mode-by-mode
  side-effect boundary for the self-improvement and generation pipelines.
- `CLAUDE.md` → *Pre-commit Hooks*, *Creating a New Skill*, *Creating
  Documentation Site Pages*, *Skill Self-Improvement Loop*, and *Skill
  Auto-Generation Pipeline* implementation details and test commands.
- `docs/README.md` → *Skill Doc Ownership* (the `generated:` marker), page
  templates.
- `docs/dev/metadata-and-workflow-schema.md` → the `skills-index.yaml` /
  `workflows/*.yaml` schema and validator error codes.
- `workflows/README.md`, `skillsets/README.md` → manifest schemas.

---

## 1. Environment setup

```bash
uv sync --extra dev --extra ci                       # runtime + dev deps + ci deps (PIL, statsmodels, ...)
pre-commit install && pre-commit install --hook-type pre-push
```

The `ci` extra is required for a full root run: with only `--extra dev`, root
collection fails on missing imports such as `PIL` and `statsmodels`. This
matches `.github/workflows/ci.yml`.

Run tests:

```bash
uv run --extra dev --extra ci pytest -q              # full suite
uv run --extra dev pytest <path>                     # a subset (dev extra is enough for most skills)
bash scripts/run_all_tests.sh                        # per-skill isolation = the pre-push gate
```

For skills that are primarily instructions, references, image-input workflows,
or agent orchestration, use
[`knowledge-skill-test-contract.md`](knowledge-skill-test-contract.md) as the
minimum test contract instead of skipping tests.

A fresh `git worktree` has its own venv — run `uv sync --extra dev --extra ci`
in it before a full `uv run --extra dev --extra ci pytest -q`, or collection
fails with import errors.

---

## 2. Generators / validators / drift gates

All commands run from `<repo>` root. Every generator has a `--check` mode
(used by the matching pre-commit hook + CI step) that exits non-zero on drift
without writing.

### Generators (write derived artifacts)

| Generator | Regenerate | Inputs → Outputs | pre-commit hook / CI step |
|---|---|---|---|
| `scripts/generate_catalog_from_index.py` | `python3 scripts/generate_catalog_from_index.py` | `skills-index.yaml` → catalog blocks in `README.md`, `README.ja.md`, `CLAUDE.md` (between `<!-- skills-index:* -->` sentinels) | `catalog-drift` / "README catalog drift check" |
| `scripts/generate_skill_docs.py` | `python3 scripts/generate_skill_docs.py` (missing only) · `--skill <name>` · `--overwrite` (generator-owned only) · `--force` (override protection — never in CI) | `skills/*/SKILL.md` + `references/` + `scripts/*.py` + `CLAUDE.md` + `skill-packages/*.skill` → `docs/{en,ja}/skills/*.md` (+ index) | `skill-docs-drift` / "Skill docs drift check" |
| `scripts/generate_skillset_docs.py` | `python3 scripts/generate_skillset_docs.py` (`--lang en\|ja\|all`, default `all`) | `skillsets/*.yaml` → `docs/{en,ja}/skillsets.md` | `skillset-docs-drift` / "Skillset docs drift check" |
| `scripts/generate_workflow_docs.py` | `python3 scripts/generate_workflow_docs.py` (`--lang en\|ja\|all`, default `all`) | `workflows/*.yaml` → `docs/{en,ja}/workflows.md`; JA requires complete `*_ja` prose and never falls back to EN | `workflow-docs-drift` / "Workflow docs drift check" |
| `skills/trading-skills-navigator/scripts/build_snapshot.py` | `python3 skills/trading-skills-navigator/scripts/build_snapshot.py` | `skills-index.yaml` + `workflows/*.yaml` + `skillsets/*.yaml` → `skills/trading-skills-navigator/assets/metadata_snapshot.json` | `snapshot-check` / "Navigator snapshot drift check" |

> `generate_skill_docs.py` has **no `--lang`** flag — it emits EN + JA
> together. `generate_skillset_docs.py` / `generate_workflow_docs.py` **do**
> take `--lang` (default `all`).

### Validators (no output; exit non-zero on violation)

| Validator | Command | Scope |
|---|---|---|
| `scripts/validate_skills_index.py` | `python3 scripts/validate_skills_index.py [--strict-workflows] [--strict-metadata]` | `skills-index.yaml` ↔ `skills/` bijection, enums, workflow artifact flow. Default = warn on best-effort fields; `--strict-metadata` requires `timeframe`/`difficulty`/`inputs`/`outputs`; `--strict-workflows` errors on workflow issues, including incomplete Japanese prose (`WF014`). |
| `scripts/validate_skillsets.py` | `python3 scripts/validate_skillsets.py` | `skillsets/*.yaml` manifests (SK001–SK013) + `related_workflows` coherence. Always strict. |
| `scripts/check_provider_contracts.py` | `python3 scripts/check_provider_contracts.py check` (offline, CI) · `canary` (live, weekly, report-only: `--provider fmp` via `.github/workflows/fmp-contract-canary.yml` needs `FMP_API_KEY`; `--provider trader-monty` via `.github/workflows/public-csv-contract-canary.yml` needs no key) | `config/provider-contracts/{fmp,trader-monty}/*.v*.json` structure + fixtures vs. `skills-index.yaml` owners (`check`); live response vs. contract, redacting any key (`canary`). See [`docs/dev/provider-contracts.md`](provider-contracts.md). |

### Skill-doc ownership (the `generated:` marker)

Per-page frontmatter `generated: true` = generator-owned (drift-checked,
`--overwrite` may rewrite); `generated: false` **or absent**, **or** any skill
in the `HAND_WRITTEN` frozenset = hand-maintained & protected (`--overwrite`
refuses it; `--force` is the only override and is never used in CI/pre-commit;
`--check` only verifies existence + marker validity, never content). Full
contract: `docs/README.md` → *Skill Doc Ownership*.

---

## 3. "I edited X → regenerate Y → verify Z"

| You edited | Regenerate | Verify |
|---|---|---|
| `skills-index.yaml` | `generate_catalog_from_index.py`, `build_snapshot.py` | `validate_skills_index.py --strict-workflows --strict-metadata`; `catalog-drift`, `snapshot-check` |
| `skills/<s>/SKILL.md` (or its `references/`, `scripts/`) | `generate_skill_docs.py --skill <s>` (only if its page is `generated: true`) | `generate_skill_docs.py --check`; `docs-completeness` |
| `workflows/*.yaml` | `generate_workflow_docs.py`, `build_snapshot.py` | `validate_skills_index.py --strict-workflows` (including JA completeness); `workflow-docs-drift`, `snapshot-check` |
| `skillsets/*.yaml` | `generate_skillset_docs.py`, `build_snapshot.py` | `validate_skillsets.py`; `skillset-docs-drift`, `snapshot-check` |
| Added a **new skill** | follow `CLAUDE.md` → *Creating a New Skill* (mandatory checklist: docs, index entry, catalog, README, API matrix) | `validate_skills_index.py --strict-metadata` + `pre-commit run --all-files` |

Fastest catch-all before pushing: `pre-commit run --all-files` (runs every
drift `--check`) then `bash scripts/run_all_tests.sh`.

---

## 4. Pre-commit / pre-push / CI topology

**Commit stage** (`.pre-commit-config.yaml`): hygiene
(`trailing-whitespace`, `end-of-file-fixer`, `check-yaml/toml`,
`check-merge-conflict`, `check-added-large-files`, `ruff`, `ruff-format`,
`codespell`, `detect-secrets`), local guards (`no-absolute-paths`,
`skill-frontmatter`, `docs-completeness`), then validators + drift gates
(`validate-skills-index`, `validate-skillsets`, `workflow-docs-drift`,
`skillset-docs-drift`, `skill-docs-drift`, `catalog-drift`, `snapshot-check`).

**Pre-push stage**: `validate-skills-index-strict`
(`--strict-workflows --strict-metadata`) + `pytest-pre-push`
(`scripts/run_all_tests.sh`).

**CI** (`.github/workflows/ci.yml`): `Lint`, `Test`, `Security`, and
`Metadata + Workflow checks` (runs the validators + every drift `--check`).

**Known test skips** (`scripts/run_all_tests.sh` `KNOWN_SKIP`): `theme-detector`
(pre-existing failures) and `canslim-screener` (needs optional `bs4`). CI runs
`theme-detector` as a non-blocking `continue-on-error` step; it does not run a
`canslim-screener` test step today. A green local maintenance run reports
`46/46 passed, 2 skipped`.

### Clearing a failing gate

- **A `*-drift` hook failed** → you changed a source but not its derived
  artifact (or hand-edited a generated file). Run the matching generator from
  §2, `git add` the result, re-commit. Never edit a generated file or the
  content between `<!-- skills-index:* -->` sentinels by hand.
- **`ruff-format` "files were modified"** → it reformatted; `git add -A` and
  re-run (`pre-commit run --all-files`). Standard, not an error.
- **`no-absolute-paths` failed** → replace the `/Users/...` literal with
  `<repo>` / `$PROJECT_DIR` / `$HOME`, or `# noqa: absolute-path` if it is a
  regex/test fixture.
- **`docs-completeness` failed** → a `skills/*/SKILL.md` lacks an EN or JA
  page; run `generate_skill_docs.py --skill <name>`.
- **PR / issue creation fails with `must be a collaborator`** → the active
  `gh` account is wrong; see §6.

---

## 5. Scheduled self-maintenance jobs

Four shipped `launchd` **templates** under `launchd/` automate repo
self-maintenance. They are templates (paths use a `$PROJECT_DIR` placeholder);
whether they are loaded is **local machine state**, so verify with `launchctl`
rather than assuming.

| Plist (`launchd/`) | Label | Schedule | Entry |
|---|---|---|---|
| `com.trade-analysis.skill-improvement.plist` | `com.trade-analysis.skill-improvement` | daily 05:00 | `scripts/run_skill_improvement.sh` → `run_skill_improvement_loop.py` |
| `com.trade-analysis.skill-generation-daily.plist` | `com.trade-analysis.skill-generation-daily` | daily 07:00 | `scripts/run_skill_generation.sh` (daily) → `run_skill_generation_pipeline.py` |
| `com.trade-analysis.skill-generation-weekly.plist` | `com.trade-analysis.skill-generation-weekly` | Saturday 06:00 | `scripts/run_skill_generation.sh` (weekly: mine + score) |
| `com.trade-analysis.skill-heartbeat.plist` | `com.trade-analysis.skill-heartbeat` | daily 08:00 | `scripts/run_skill_heartbeat.sh` (independent success watchdog) |

Install all four maintenance templates from the repository root with one command:

```bash
python3 scripts/install_launchd.py
```

The stdlib installer replaces `$HOME` and `$PROJECT_DIR` structurally, creates
`logs/`, and writes the rendered plists to `~/Library/LaunchAgents`. It validates
all four templates and existing destinations before writing anything. An
identical installed plist is retained; a differing/customized plist is refused.
Plain `cp` leaves literal placeholders and is not a supported installation.
Use `--output-dir <temporary-directory>` to inspect rendered files without
loading jobs (this also creates the repository's log directory).

Activate all four schedules explicitly:

```bash
python3 scripts/install_launchd.py --load
```

`--load` bootstraps into the current user's GUI domain on macOS; it does not
stop/restart existing services or run scoring immediately. It requires a logged-in
GUI session. Rendering is idempotent, but bootstrapping an already loaded service
fails with update guidance. Some earlier services may have loaded before a later
bootstrap failure; inspect `launchctl print` for each exact label.

For an existing installation, first check that no maintenance job is running,
then unload the exact four maintenance services before rerunning `--load`:

```bash
for job in skill-improvement skill-generation-daily skill-generation-weekly skill-heartbeat; do
  launchctl bootout "gui/$(id -u)/com.trade-analysis.$job"
done
```

A service not yet loaded can report an error. If the installer refuses an
existing customized plist, move only that file to a backup outside
`~/Library/LaunchAgents`, rerun the installer, and reapply intended local settings.
Keep webhook URLs private. Never delete logs/state to fix installation conflicts.
The installer does not automatically unload agents or overwrite customizations.

For a concise explanation of what each mode reads and writes, including why
`--dry-run` is not filesystem-read-only, see the
[Skill Automation Quickstart](skill-automation.md) ([日本語](skill-automation.ja.md)).
Implementation architecture, quality-gate rollback, and tests remain in
`CLAUDE.md` → *Skill Self-Improvement Loop* and *Skill Auto-Generation
Pipeline*. State / logs:

- Improvement: `logs/.skill_improvement.lock`,
  `logs/.skill_improvement_state.json`, `logs/skill_improvement.log`,
  `reports/skill-improvement-log/<date>_summary.md`.
- Generation: `logs/.skill_generation.lock`,
  `logs/.skill_generation_state.json`, `logs/.skill_generation_backlog.yaml`,
  `logs/skill_generation.log`, `reports/skill-generation-log/<date>_*.md`.

> `examples/daily-market-dashboard/launchd/com.trading.daily-dashboard.plist`
> is **not** repo maintenance — it is the user's personal example trading-app
> routine. Keep it out of maintenance reasoning.

### The improvement loop runs in its own checkout

`scripts/run_skill_improvement.sh` does **not** run the loop against your
working tree. The loop's git-safety precondition aborts on a dirty tree or a
non-`main` branch, so a maintainer's ordinary editing day would block it —
that is what stalled it for 48 days between 2026-06-13 and 2026-07-31.

The launcher instead maintains a dedicated checkout at
`~/.local/share/claude-trading-skills-bot`, overridable with
`SKILL_LOOP_CHECKOUT`. On every run it clones if absent, then
`fetch` → `checkout -B main origin/main` → `reset --hard` → `clean -fd`.
`clean` deliberately omits `-x` so gitignored paths survive, and `logs/` and
`reports/` are symlinked back to the primary repo so round-robin state,
run logs, and daily summaries stay in one place.

The isolation fix on 2026-07-31 was followed by a second stall, observed from
2026-08-01 through the 2026-11-07 audit (#652). Git's directory-only `logs/`
and `reports/` ignore patterns did not cover the symlinks created by the wrapper;
the safety check rejected them as untracked. Root-only `/logs` and `/reports`
ignore entries now cover both directories and symlinks without relaxing source
safety. Deployment and a subsequent real scheduled score must still be verified
on the maintainer machine; local fixtures are not evidence of operational recovery.

Consequences worth knowing:

- Edit freely in your working tree; the 05:00 run is unaffected.
- The loop always reviews `origin/main`, never your uncommitted work.
- `logs/.skill_improvement.lock` is shared between both checkouts, so a manual
  run and the scheduled run cannot collide.
- To reset the automation checkout, delete the directory — the next run
  re-clones it.

Never place work-in-progress directories under `skills/`. The safety check
blocks on **any** untracked path, so a staging folder there stops the loop
every night. Use the gitignored `.staging/` at the repo root instead.

### When a scheduled job "didn't do anything"

Inspect, don't assume:

```bash
launchctl list | grep -E 'skill-improvement|skill-generation'   # is it loaded?
tail -n 100 <repo>/logs/skill_generation.log                    # detailed run log
tail -n 100 <repo>/logs/launchd_skill_generation_daily_error.log # launchd stderr
sed -n '1,40p' <repo>/logs/.skill_generation_state.json          # last run + outcome
```

Common outcomes and where they come from (grep the `*.log`):

- **Lock held / stale** → another run in progress, or a stale
  `logs/.skill_*.lock` (PID-based; a dead PID is auto-reclaimed). Remove only
  if you have confirmed no live process.
- **`Not on main branch` / `Working tree has non-safe dirty files`** → the
  git-safety precondition aborted the run (by design). Clean the tree / switch
  to `main`.
- **`design_failed` / `review_failed` / `pr_failed`** (in
  `.skill_generation_state.json` / backlog) → generation pipeline outcomes;
  `review_failed` is terminal (content quality), the others retry once.
- **Quality-gate rollback** (improvement loop) → re-scored skill did not
  improve; the change was reverted by design.
- **PR not opened** → almost always the `gh` account (see §6); check the log
  tail for `must be a collaborator`.

---

## 6. The `gh` account gotcha

PR / issue creation on `tradermonty/claude-trading-skills` requires the
**`tradermonty`** `gh` account to be active. If more than one account is logged
in, the active one is global `gh` state and may be any of them at session
start. Before any `gh pr create` / `gh issue` / scheduled job that opens a PR:

```bash
gh auth switch --hostname github.com --user tradermonty
gh auth status | grep -A1 'Active account: true'
```

With a non-collaborator account active, PR creation fails with
`GraphQL: must be a collaborator (createPullRequest)`. Reverting afterward is
optional (local preference only).

---

## 7. Releasing skill-package archives

`skill-packages/*.skill` are regenerated after a skill directory changes:

```bash
python3 scripts/package_skills.py --skill <skill-name>
```

The packager excludes `tests/`, `__pycache__/`, Python bytecode, and `.DS_Store`
files from distributable archives. The `skill-docs-drift` hook's `files:`
includes `skill-packages/*.skill`, so a stale archive that feeds a
generator-owned page surfaces as drift. Repackage, `git add` the `.skill`, and
re-run `pre-commit run --all-files`.

## Automation failure notifications and heartbeat

Both `scripts/run_skill_improvement.sh` and `scripts/run_skill_generation.sh`
notify on a nonzero exit when `SKILL_LOOP_NOTIFY` is configured. Those immediate
failure notifications remain opt-in. Notifications contain only the job name, exit code, and a prompt
to read local logs; command output and exception text are never sent.

- Set `SKILL_LOOP_NOTIFY=macos` for a local macOS notification (`osascript`).
- Set `SKILL_LOOP_NOTIFY=webhook` and `SKILL_LOOP_WEBHOOK_URL` to an HTTPS
  endpoint accepting JSON `{"text": "..."}`. Redirects and URL credentials are
  rejected. Keep the URL in a local, ignored environment file or launchd
  environment, never in a committed plist or shell command history.
- These settings must reach the wrapper, for example via the existing trusted
  `.envrc`/direnv setup or the installed LaunchAgent's local environment.
  Setup failures before `.envrc` is loaded require the variables to be inherited.

Notification is best effort: one request with a five-second socket timeout,
no retry, or a five-second macOS subprocess timeout. An unavailable Python
interpreter prevents delivery and produces a fixed stderr warning instead.
Notifier errors never replace the original job exit code. A killed process or
unloaded LaunchAgent cannot send its own failure notification.

Check all three job heartbeats offline:

```bash
python3 scripts/job_monitor.py --check-heartbeat --project-root .
```

Exit 0 means all success timestamps are fresh; exit 1 reports missing, invalid,
future, or stale timestamps. Thresholds are 48 hours for improvement and daily
generation, and 14 days for weekly generation. This command reads only the two
existing `logs/.skill_*_state.json` files and does not notify or modify anything.
Use the primary repository whose logs the improvement checkout shares, or pass
its path with `--project-root`. After upgrading, jobs without a recorded success
warn until their first healthy run; old `last_run` values are not evidence of
success.

State records UTC `last_success_at` (an ISO timestamp for improvement, a mapping
with independent `daily` and `weekly` timestamps for generation). A completed
daily check with no eligible ideas or an already open PR is healthy. Dry runs,
lock skips, and failures do not refresh it. A failed improvement attempt returns
nonzero even when scoring and the summary succeeded. Success is recorded after
normal cleanup; it does not prove that a PR was merged or deployed.

The fourth template schedules `run_skill_heartbeat.sh` independently at 08:00
local time. It runs `job_monitor.py --notify-heartbeat`, checks the same success
thresholds, and defaults to a local macOS notification without opt-in. Each
unhealthy job produces one generic notification per watchdog invocation; healthy
jobs do not notify. Missing, invalid and future timestamps also notify. Delivery
failure remains best effort and never turns stale health into a successful exit.
The ordinary `--check-heartbeat` command above stays silent and read-only.

For an explicit opt-out, set `SKILL_LOOP_NOTIFY=off` in the installed heartbeat
plist's `EnvironmentVariables`, then unload/reload that exact watchdog service.
`macos` and `webhook` remain supported. The watchdog does not source `.envrc`, so
webhook settings must reach its process through its private local LaunchAgent
environment. It does not modify success state or start the monitored jobs.
Do not put webhook secrets into committed templates. Local macOS delivery depends
on OS notification permissions and the GUI session. A sleeping/offline machine or
an unloaded watchdog cannot deliver a notification; verification requires checking
its own `launchctl print`/logs as well. No agents are installed by merely checking
out this change; activate them with the installer only when ready.


## Smoke evidence layers (issue #507)

| Layer | Current evidence / remaining work |
|---|---|
| PR CI | Offline dependency declarations, table/runner regression tests, provider fixtures, and workflow replay; not proof of every CLI failure path |
| Nightly | Packaged dependency runner records `pass`, `fail`, or `incomplete`; job remains report-only under #349. Keyless optional-provider coverage and actual archive execution remain follow-ups |
| Weekly sample | #506 tracks the separate live happy-path sample; it cannot establish fallback, personal-state, or failure-path coverage |
| Monthly LLM sample | Instruction-only and model-driven checks remain planned under #507; they need separate runtime/cost authorization |

Read the nightly artifact's aggregate `outcome` and per-skill rows, not only the
GitHub conclusion. Exit 2 and `ok: null` mean incomplete coverage; warnings
identify pending/skip cases. The nightly step stays green on exit 2 with a
warning annotation and fails on exit 1 or any other nonzero code, which
overrides incomplete coverage. Today exit 2 is expected every night because
19 skills are incomplete, so a green step is not evidence of complete smoke
success.
See [packaged smoke outcomes](packaged-deps-smoke.md#evidence-outcomes-issue-507-partial-implementation)
for the schema and remaining acceptance gaps. Issue #507 remains open until
its full set of layers and coverage requirements is met.

## API metadata contract maintenance

After changing a skill's credentials or API modes, update its `integrations`
in `skills-index.yaml`, run `python3 scripts/check_api_requirements.py`, and
regenerate with `python3 scripts/generate_catalog_from_index.py`. This also
regenerates the required EN/JA README API-guidance blocks linking to the canonical
matrices and individual guides. `--check` rejects edits or missing guidance
sentinels, in addition to index-derived catalog drift. It also regenerates
website category provider badges and API matrix cells while keeping
localized descriptions/non-provider badges. Update any workflow profile and
regenerate workflow docs and Navigator snapshot/package when inputs change.
See [API declaration coverage and limits](metadata-and-workflow-schema.md#api-declarations-versus-credential-reads-653).
