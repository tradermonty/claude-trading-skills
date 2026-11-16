# Security Review Checklist (`security_review` axis)

This checklist backs the `security_review` axis of the production verification block.
It is the lightweight, skill-specific review required by
[`production-verification.md`](production-verification.md): a value of `passed`
is an AND claim across the five security-relevant dimensions of the axis
(*input/output*, *credential*, *dependency*, *path*, *data-exposure*).

## Rules

- `passed` requires that every item in each of the five dimensions below is
  satisfied by skill-specific, auditable evidence. A green repository-wide scan
  (detect-secrets, supply-chain audit, CI `security` job) is **not** by itself
  sufficient (`production-verification.md` states this explicitly).
- Mechanical checks in `scripts/backfill_security_review.py` are advisory
  signals. They cannot replace a recorded per-skill review. A skill is only a
  `passed` candidate when it is clean on the mechanical checks **and** is
  explicitly reviewer-confirmed (the collector's confirmation flag starts empty).
- Every `passed` record must name the reviewer, the assessment date, the
  assessed commit, and the exact files reviewed. These are recorded in the
  baseline override `rationale` and `evidence` fields (see
  `scripts/tests/test_production_verification_baseline.py` for the accepted
  shape).
- A skill that fails any item, or whose applicability cannot be cleared, stays
  `not_verified` with the specific gap recorded in the baseline override
  `rationale`.

## Dimensions and items

### 1. Credential

- API keys, secrets, and tokens are read from environment variables (for
  example `FMP_API_KEY`, `FINVIZ_API_KEY`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`)
  or command-line flags, never hard-coded as literal values in committed files.
- Placeholder strings such as `export FMP_API_KEY='your-key'` in help text are
  acceptable; a non-placeholder committed value is a fail.
- Secrets are excluded from committed repositories (`.gitignore`, `.mcp.json`,
  `.envrc`); no personal information or absolute user paths are committed.

### 2. Data exposure

- The skill does not print or log a resolved credential value to stdout,
  stderr, any log file, or any output artifact.
- Diagnostics that mention a credential reuse the shared redaction helpers
  (for example the `_redact_key` fragment in the generated FMP client) so a
  leaked value is masked rather than emitted verbatim.

### 3. Path

- The skill does not invoke a shell (`shell=True`, `os.system`, or a string
  command list) with attacker- or input-influenced arguments.
- Subprocess calls and file paths derived from external input are validated or
  constrained before use.

### 4. Input/output and network

- Network calls set an explicit timeout; no call can hang indefinitely on an
  unresponsive provider.
- Non-2xx responses, empty/missing fields, and malformed payloads are handled
  fail-closed (rejected or surfaced as an error, never silently treated as a
  valid zero/success).

### 5. Dependency

- The skill ships a `skills/<id>/requirements.txt` that passes
  `python3 scripts/check_skill_deps.py check` (issue #330): no undeclared
  imports, no stale entries, and no optional entry without a fallback path plus
  absence test.
- The declared dependencies are consistent with the repository supply-chain
  audit (`docs/dev/supply-chain-security.md`).

## Recording evidence

A `security_review: passed` entry is added as a per-skill override in
`docs/dev/production-verification-baseline.yaml` (and mirrored in the skill's
`verification.security_review` value in `skills-index.yaml`). The override
carries:

- a `rationale` describing, per skill, what was reviewed and the fail-closed /
  credential / timeout / path facts that were verified;
- an `evidence` list with non-empty entries such as the review date, the
  assessed commit, the reviewer, and the exact file or command inspected.

Keep evidence current as in `production-verification.md` "Keeping evidence
current": when a skill's credential handling, network code, dependencies, or
paths change, re-run this checklist and update the record, or reset the axis to
`not_verified`.
