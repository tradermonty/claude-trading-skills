# Maintenance Runbook (Developer / Maintainer Operations)

This is the operational ledger for **maintaining** this repository: regenerating
derived artifacts, clearing drift-gate failures, and understanding the
self-maintenance `launchd` agents. It is **not** a general contribution guide —
it assumes you are a maintainer working on `main`.

`<repo>` below = the repository root. Never hard-code an absolute
`/Users/...` path anywhere in the repo (the `no-absolute-paths` pre-commit hook
blocks it); use `<repo>` / `$PROJECT_DIR` / `$HOME` placeholders.

Related references (this runbook links rather than duplicates):

- `CLAUDE.md` → *Pre-commit Hooks*, *Creating a New Skill*, *Creating
  Documentation Site Pages*, *Skill Self-Improvement Loop*, *Skill
  Auto-Generation Pipeline*.
- `docs/README.md` → *Skill Doc Ownership* (the `generated:` marker), page
  templates.
- `docs/dev/metadata-and-workflow-schema.md` → the `skills-index.yaml` /
  `workflows/*.yaml` schema and validator error codes.
- `workflows/README.md`, `skillsets/README.md` → manifest schemas.

---

## 1. Environment setup

```bash
uv sync --extra dev                                  # runtime + dev deps (pytest, jsonschema, pre-commit, ruff, ...)
pre-commit install && pre-commit install --hook-type pre-push
```

Run tests:

```bash
uv run pytest -q                                     # full suite
uv run --extra dev pytest <path>                     # a subset
bash scripts/run_all_tests.sh                        # per-skill isolation = the pre-push gate
```

A fresh `git worktree` has its own venv — run `uv sync --extra dev` in it
before `uv run pytest`, or collection fails with import errors.

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
| `scripts/generate_workflow_docs.py` | `python3 scripts/generate_workflow_docs.py` (`--lang en\|ja\|all`, default `all`) | `workflows/*.yaml` → `docs/{en,ja}/workflows.md` | `workflow-docs-drift` / "Workflow docs drift check" |
| `skills/trading-skills-navigator/scripts/build_snapshot.py` | `python3 skills/trading-skills-navigator/scripts/build_snapshot.py` | `skills-index.yaml` + `workflows/*.yaml` + `skillsets/*.yaml` → `skills/trading-skills-navigator/assets/metadata_snapshot.json` | `snapshot-check` / "Navigator snapshot drift check" |

> `generate_skill_docs.py` has **no `--lang`** flag — it emits EN + JA
> together. `generate_skillset_docs.py` / `generate_workflow_docs.py` **do**
> take `--lang` (default `all`).

### Validators (no output; exit non-zero on violation)

| Validator | Command | Scope |
|---|---|---|
| `scripts/validate_skills_index.py` | `python3 scripts/validate_skills_index.py [--strict-workflows] [--strict-metadata]` | `skills-index.yaml` ↔ `skills/` bijection, enums, workflow artifact flow. Default = warn on best-effort fields; `--strict-metadata` requires `timeframe`/`difficulty`/`inputs`/`outputs`; `--strict-workflows` errors on workflow issues. |
| `scripts/validate_skillsets.py` | `python3 scripts/validate_skillsets.py` | `skillsets/*.yaml` manifests (SK001–SK013) + `related_workflows` coherence. Always strict. |

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
| `workflows/*.yaml` | `generate_workflow_docs.py`, `build_snapshot.py` | `validate_skills_index.py --strict-workflows`; `workflow-docs-drift`, `snapshot-check` |
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

Three shipped `launchd` **templates** under `launchd/` automate repo
self-maintenance. They are templates (paths use a `$PROJECT_DIR` placeholder);
whether they are loaded is **local machine state**, so verify with `launchctl`
rather than assuming.

| Plist (`launchd/`) | Label | Schedule | Entry |
|---|---|---|---|
| `com.trade-analysis.skill-improvement.plist` | `com.trade-analysis.skill-improvement` | daily 05:00 | `scripts/run_skill_improvement.sh` → `run_skill_improvement_loop.py` |
| `com.trade-analysis.skill-generation-daily.plist` | `com.trade-analysis.skill-generation-daily` | daily 07:00 | `scripts/run_skill_generation.sh` (daily) → `run_skill_generation_pipeline.py` |
| `com.trade-analysis.skill-generation-weekly.plist` | `com.trade-analysis.skill-generation-weekly` | Saturday 06:00 | `scripts/run_skill_generation.sh` (weekly: mine + score) |

What they do, lock files, git-safety preconditions (clean tree / on `main` /
`pull --ff-only`), quality-gate rollback, and PR creation are documented in
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
**`tradermonty`** `gh` account to be active. Both `tradermonty` and
`takusaotome` are logged in; the active one is global `gh` state and may be
either at session start. Before any `gh pr create` / `gh issue` / scheduled
job that opens a PR:

```bash
gh auth switch --hostname github.com --user tradermonty
gh auth status | grep -A1 'Active account: true'
```

With the wrong account, PR creation fails with
`GraphQL: must be a collaborator (createPullRequest)` (`takusaotome` is not a
collaborator). Reverting afterward is optional (local preference only).

---

## 7. Releasing skill-package archives

`skill-packages/*.skill` are regenerated with the skill-creator packager after
a skill directory changes (see prior PRs for the exact invocation). The
`skill-docs-drift` hook's `files:` includes `skill-packages/*.skill`, so a
stale archive that feeds a generator-owned page surfaces as drift. Repackage,
`git add` the `.skill`, re-run `pre-commit run --all-files`.
