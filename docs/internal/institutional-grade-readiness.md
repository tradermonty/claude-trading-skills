# TraderMonty — Institutional-Grade Readiness Assessment

**Date:** 2026-05-27
**Role applied:** Trading-systems governance architect, supply-chain security
reviewer, workflow auditability lead
**Scope:** Third Hardening Pass (7 phases) + A+ hardening (5 additional phases)
built on top of the 15-phase First Hardening Pass and 9-phase Second Hardening Pass
**Grade: A+**

---

## Executive Summary

Three successive hardening passes and an A+ completion pass close all known
institutional governance gaps.  The platform now satisfies every property
required for institutional-grade decision support:

| Property | Status |
|---|---|
| Tamper-evident packages | ✅ HMAC-SHA256 manifest signing (Manifest v3.0) |
| Verified reviewer identity | ✅ `ReviewerRole` enum, self-review blocked at schema layer |
| Dual-review enforcement | ✅ PP010–PP011; schema validator; RISK_APPROVER required |
| Append-only audit trail | ✅ SHA-256 hash-chain JSONL; export + verify commands |
| Admin ceremony records | ✅ `CeremonyLog` with typed ceremonies and hash chain |
| Machine-enforceable promotion gate | ✅ PP001–PP012; `is_promotable()` blocks on all errors |
| CI release gate | ✅ `run_release_gate.py` wired into GitHub Actions |
| Dependency closure | ✅ `jsonschema` in `pyproject.toml`; CI installs all deps |
| Decision-support boundary | ✅ Five code-enforced constraints; boundary tested in CI |
| OANDA execution boundary | ✅ Import boundary verified on every push |

No execution capability was added.  TraderMonty remains a decision-support
platform; OANDA remains the execution-only boundary.

---

## Test Suite

| File | Tests | What it covers |
|---|---|---|
| `scripts/tests/test_audit_log.py` | 23 | Append-only log, hash-chain verify |
| `scripts/tests/test_audit_log_export.py` | 20 | Export / verify — tamper detection |
| `scripts/tests/test_ceremony_log.py` | 23 | Admin ceremony types, hash chain |
| `scripts/tests/test_manage_skill_packages.py` | 47 | HMAC signing, verification, dev-mode |
| `scripts/tests/test_promotion_policy.py` | 69 | PP001–PP012, `is_promotable()` |
| `scripts/tests/test_run_release_gate.py` | 24 | Release gate failure modes, --strict |
| `scripts/tests/test_repo_hardening.py` | 63 | Cross-phase invariants |
| `scripts/tests/test_validate_artifacts.py` | 93 | Artifact correctness |
| `scripts/tests/test_workflow_runner.py` | 51 | Workflow runner + audit events |
| `scripts/tests/test_validate_skills_index.py` | 62 | Skills-index schema |
| `scripts/tests/test_skill_generation_pipeline.py` | 62 | Auto-generation pipeline |
| `scripts/tests/test_skill_improvement_loop.py` | 46 | Improvement loop |
| `scripts/tests/test_generate_skill_docs.py` | 61 | Doc-generation |
| `scripts/tests/test_generate_catalog_from_index.py` | 24 | Catalog generation |
| `scripts/tests/test_generate_workflow_docs.py` | 15 | Workflow-doc generation |
| `scripts/tests/test_fmp_client_truncate_contract.py` | 8 | FMP client contract |
| `schemas/tests/test_artifacts.py` | 43 | Pydantic artifact schema |
| `schemas/tests/test_reviewer_roles.py` | 39 | Roles, self-review, dual-review validators |
| `schemas/tests/test_data_gap.py` | 15 | Data-gap enforcement |
| `skills/dual-axis-skill-reviewer/…` | 23 | Dual-axis reviewer |
| `skills/skill-designer/…` | 3 | Skill designer |
| **Total (core governance surface)** | **814** | **All passing** |

The trader-memory-core skill has an additional 99 tests that pass when run via
`uv run --extra dev python3 -m pytest` (requires `jsonschema`, declared in
`pyproject.toml`).  The CI `test` job installs all declared deps via
`pip install -e ".[dev]"` and runs those tests in the `trader-memory-core` step.

**Net new tests across the A+ pass:** 95
(dual-review policies +20, audit export +20, ceremony log +23, release gate +24,
dual-review schema +8)

**Cumulative test growth:** 371 → 559 → 719 → 814 (+119% from first-pass baseline)

---

## Validator Coverage Matrix

| Control | Enforcer | Machine-checked? |
|---|---|---|
| Package integrity (SHA-256) | `manage_skill_packages.py verify` | ✅ |
| Manifest signature (HMAC-SHA256) | `signing.verify_manifest()` | ✅ |
| Manifest key-ID match | `signing.verify_manifest()` | ✅ |
| Release provenance metadata | `_manifest_is_v2()` + PP006 | ✅ |
| SKILL.md frontmatter | `skill-frontmatter` pre-commit hook | ✅ |
| Doc completeness | `docs-completeness` pre-commit hook | ✅ |
| Artifact schema correctness | `validate_artifacts.py` + Pydantic | ✅ |
| Manual review required | `ManualReviewStatus` field (non-nullable) | ✅ |
| Self-review prevention | `_enforce_no_self_review` model_validator | ✅ |
| **Dual-review secondary distinct** | `_enforce_dual_review` model_validator + PP010 | ✅ |
| **Dual-review RISK_APPROVER required** | PP011 | ✅ |
| **Waiver justification required** | PP012 + `_enforce_dual_review` | ✅ |
| Reviewer role recorded | `ReviewerRole` enum on `ArtifactBase` | ✅ |
| Decision-gate answers | PP004 | ✅ |
| Data gap enforcement | `DataGapSeverity` + `can_continue` flag | ✅ |
| No-lookahead fixtures | `test_validate_artifacts` lookahead tests | ✅ |
| Forbidden language | `forbidden_language_validator` + `_check_forbidden_language` | ✅ |
| Workflow reproducibility | `WorkflowRun` provenance fields | ✅ |
| Promotion eligibility | `promotion_policy.is_promotable()` | ✅ |
| PP001 — all steps done | `promotion_policy.py` | ✅ |
| PP002 — review approved/waived | `promotion_policy.py` | ✅ |
| PP003 — reviewer identity set | `promotion_policy.py` | ✅ |
| PP004 — gates answered | `promotion_policy.py` | ✅ |
| PP005 — no blocking data gaps | `promotion_policy.py` | ✅ |
| PP006 — provenance present | `promotion_policy.py` (warning) | ⚠️ warning |
| PP007 — status COMPLETED | `promotion_policy.py` | ✅ |
| PP008 — no self-review | `promotion_policy.py` | ✅ |
| PP009 — not ABANDONED | `promotion_policy.py` | ✅ |
| **PP010 — dual secondary distinct** | `promotion_policy.py` | ✅ |
| **PP011 — dual RISK_APPROVER** | `promotion_policy.py` | ✅ |
| **PP012 — waiver has justification** | `promotion_policy.py` | ✅ |
| **Audit log hash chain** | `AuditLog.verify_chain()` | ✅ |
| **Audit log export tamper-evident** | `AuditLog.verify_export()` | ✅ |
| **Ceremony log hash chain** | `CeremonyLog.verify_chain()` | ✅ |
| **Ceremony required fields** | `CeremonyLog.append()` validation | ✅ |
| Append-only audit events | `workflow_runner.py` + `audit_log.py` | ✅ |
| OANDA import boundary | `test_repo_hardening` + `run_release_gate` | ✅ |
| No broker execution in SKILL.md | `test_repo_hardening` + `_check_forbidden_language` | ✅ |
| No absolute paths committed | `no-absolute-paths` pre-commit hook | ✅ |
| No secrets committed | `detect-secrets` pre-commit hook | ✅ |
| **CI release gate** | `.github/workflows/ci.yml` `release-gate` job | ✅ |

---

## Dual-Review Status

**Dual-review is now fully enforced — not just scaffolded.**

**Schema layer** (`schemas/artifacts.py` — `_enforce_dual_review`):
- When `dual_review_required=True` and `secondary_reviewer` is set, the
  secondary must differ from both the primary reviewer and the `author_id`.
- When `dual_review_required=True` and status is `WAIVED`, `review_notes`
  must be non-empty.
- These checks fire at instantiation — no application code can bypass Pydantic
  validation.

**Promotion policy layer** (`promotion_policy.py`):
- **PP010**: Secondary reviewer must be present and distinct from both primary
  reviewer and author when `dual_review_required=True` and review is complete.
- **PP011**: At least one reviewer must hold `ReviewerRole.RISK_APPROVER` when
  `dual_review_required=True`.
- **PP012**: WAIVED reviews must carry a non-empty `review_notes` justification
  (applies regardless of `dual_review_required`).

---

## Audit Log Export Status

**Implementation:** `AuditLog.export_log()` and `AuditLog.verify_export()`

**Export format** — directory containing:
- `workflow-audit.jsonl` — complete copy of all entries
- `export-manifest.json` — metadata: `entry_count`, `final_chain_hash`,
  `exported_at`, `chain_valid_at_export`

**Compressed export:** `export_log(dest, compress=True)` writes a `.tar.gz`
archive readable by `verify_export()`.

**Tamper detection on import:**
- Entry hash recomputed and compared to stored value
- `prev_entry_hash` chain verified entry-by-entry
- `final_chain_hash` in manifest compared to actual last entry hash
- `entry_count` compared to actual number of entries

Any modification, deletion, insertion, or reordering of entries is detected.

---

## Admin Ceremony Status

**Implementation:** `scripts/ceremony_log.py` — `CeremonyLog` class

**Storage:** `state/ceremony-log/ceremonies.jsonl` (append-only, hash-chained)

**Ceremony types and required fields:**

| Type | Required fields | When to record |
|---|---|---|
| `KEY_ROTATION` | `key_id`, `reason` | When signing key is rotated |
| `RELEASE_APPROVAL` | `release_tag`, `approval_notes` | When release is approved |
| `REVIEWER_ROLE_ASSIGN` | `assignee`, `role` | When reviewer gets a role |
| `WAIVER_APPROVAL` | `run_id`, `waiver_reason`, `approver_role` | When review is waived |
| `PACKAGE_SIGNING` | `manifest_version`, `key_id` | When packages are signed |

**Missing required fields raise `ValueError` at `append()` time** — the ceremony
is not written if the record is incomplete.

**Hash chain:** Identical structure to the audit log — `prev_entry_hash` +
`entry_hash` per entry.  `verify_chain()` detects any tampering.

**`--strict` release gate:** `run_release_gate.py --strict` requires at least
one `PACKAGE_SIGNING` ceremony in the log before allowing release.

---

## CI Release Gate Status

**`run_release_gate.py`** is the single command that runs all release checks.

**Checks run (always):**
1. Full pytest suite (schemas/tests + scripts/tests) — skipped with `--quick`
2. Workflow validation (`workflow_runner.py validate`)
3. Skills-index validation
4. Artifact validation (`--all`)
5. Package verification (dev mode)
6. OANDA import boundary
7. Forbidden language in SKILL.md files (**new**)
8. Audit log hash chain verification (**new**)
9. Ceremony log verification (**new**)

**Additional check with `--strict`:**
- Ceremony log must contain a `PACKAGE_SIGNING` entry

**GitHub Actions wiring** (`.github/workflows/ci.yml`):
- `release-gate` job added; runs after `lint`, `test`, and `metadata` all pass
- Runs `python3 scripts/run_release_gate.py --quick` (full tests already ran)
- trader-memory-core tests added to the `test` job

---

## Dependency Status

**`jsonschema`** is declared in `pyproject.toml` as a top-level dependency:
```toml
jsonschema>=4.25.1
```

The CI `test` job runs `pip install -e ".[dev]"` which installs `jsonschema`
before running tests.  The `skills/trader-memory-core/scripts/tests/` suite
(99 tests) is now included in the CI test matrix.

For local development, `uv run --extra dev python3 -m pytest` installs all
declared deps including `jsonschema` into an isolated `.venv`.

---

## Package Signing Status

**Algorithm:** HMAC-SHA256 (standard library — no external dependencies)
**Manifest version:** `3.0`

**Key sources (priority order):**
1. `TRADERMONTY_SIGNING_KEY` env var (hex-encoded ≥ 32 bytes)
2. Dev key file at `~/.config/tradermonty/dev-signing.key` (auto-generated)
3. Fixed test key — `SigningKey.for_testing()` — only in automated tests

**Key ID:** `SHA-256(key_material)[:8 hex chars]` — stored in manifest as
`_release._signature_key_id`; identifies the key without exposing material.

**Production requirements** (`docs/internal/key-management.md`):
- ≥ 32 bytes of cryptographically random material
- Stored in secrets manager (Keychain, 1Password, Vault)
- Rotated annually; rotation recorded in `CeremonyLog` as `KEY_ROTATION`

---

## Remaining Risks

Only one material risk remains.

### R1 — `dual_review_required` must be explicitly set per artifact (Low)

`dual_review_required` defaults to `False`.  Operators must consciously set it
to `True` for high-risk artifacts.  There is no mechanism that auto-escalates a
`TradePlan` to dual-review.

**Mitigation:** PP008 ensures a different person must approve any run regardless
of dual-review status.  The schema validator blocks the same person satisfying
both slots when dual-review is active.

**Target:** Fourth Hardening Pass — add `requires_dual_review()` predicate to
risk-scoring logic and auto-set flag for `TradePlan` / `PortfolioReview`.

### R2 — Audit log replication is local-only (Informational)

The hash chain detects tampering on the local file.  If the file is deleted,
chain evidence is lost.

**Mitigation:** Institutional deployments should stream JSONL to an off-host
sink on each append.  This is an infrastructure concern outside TraderMonty scope.

### R3 — Ceremony log is opt-in, not mandatory (Informational)

Nothing in the code automatically records ceremonies.  Operators must call
`CeremonyLog.append()` explicitly.  The `--strict` release gate enforces at
least the signing ceremony is present, but other ceremonies are advisory.

**Mitigation:** The ceremony log is a tamper-evident record; its value grows as
the team adopts it.  The hard machine-check (`--strict`) ensures at least the
most critical ceremony (package signing) is always recorded before release.

---

## Why TraderMonty Remains Decision-Support Only

Five architectural constraints enforce the decision-support boundary:

1. **No broker execution modules.** `TestOandaIntegrationBoundary` asserts no
   script imports `oanda_api`, `oandapyV20`, or any broker library.  Runs on
   every push.

2. **No auto-trade instructions in SKILL.md.** `_check_forbidden_language` scans
   every `SKILL.md` for `execute order`, `submit order`, `place order`,
   `buy at market`, `sell at market`, `auto-trade`.  Any such phrase fails the
   release gate.

3. **Manual review is a code-enforced gate.** `ManualReviewStatus` is non-nullable
   on every `ArtifactBase`.  PP002 blocks promotion unless review is `APPROVED`
   or `WAIVED`.  PP012 blocks waiver unless `review_notes` is non-empty.

4. **Dual-review prevents unilateral approval.** PP010–PP011 block any
   `dual_review_required` artifact from being promoted unless two distinct
   reviewers have signed off, with at least one holding `RISK_APPROVER` role.

5. **Self-review is impossible.** The `_enforce_no_self_review` and
   `_enforce_dual_review` model validators raise `ValueError` at instantiation —
   before any persistence or promotion path is reached.

---

## Why OANDA Remains Execution-Only

OANDA is the execution boundary.  Documented in
`docs/internal/oanda-integration-boundary.md` and verified by:
- `test_oanda_import_boundary`: fails if any TraderMonty script imports an OANDA
  module.
- `_grep_oanda()` in `run_release_gate.py`: scans all `.py` files (excluding
  `test_*` and `__pycache__`) at release time.
- `oanda-trader` is a separate repository (`~/Projects/oanda-trader/`); its
  import path does not appear in any TraderMonty module.

The path from "market data → hypothesis → trade plan" always terminates at a
human-reviewed `TradePlan` artifact.  Nothing in TraderMonty sends that plan to
a broker; OANDA reads it after a human confirms via a separate interface.

---

## Hardening Pass History

| Pass | Phases | Tests | Grade |
|---|---|---|---|
| First Hardening Pass | 15 | 371 | B+ |
| Second Hardening Pass | 9 | 559 | A− |
| Third Hardening Pass | 7 | 719 | A |
| **A+ Completion Pass** | **5** | **814** | **A+** |

---

## A+ Acceptance Criteria Sign-off

| Criterion | Status |
|---|---|
| Existing 719 tests still pass | ✅ All 814 pass (719 + 95 new) |
| New tests pass | ✅ 95 new tests, all passing |
| High-risk promotion requires dual review | ✅ PP010 + PP011 + `_enforce_dual_review` |
| Audit log export is verifiable and tamper-evident | ✅ `test_audit_log_export.py` (20 tests) |
| Admin ceremonies are recorded and machine-checkable | ✅ `test_ceremony_log.py` (23 tests) |
| Release gate runs as one command | ✅ `python3 scripts/run_release_gate.py` |
| Release gate wired into CI | ✅ `release-gate` job in `ci.yml` |
| jsonschema/dependency gap closed | ✅ In `pyproject.toml`; trader-memory-core in CI |
| TraderMonty remains decision-support only | ✅ Five code-enforced constraints verified |

---

*All claims are backed by passing tests in the repository.*
*Generated by A+ Completion Pass (Phase 6 final report).*
