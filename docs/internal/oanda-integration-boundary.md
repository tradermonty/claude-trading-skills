# OANDA Integration Boundary Plan

**Date:** 2026-05-27
**Status:** Authoritative — enforced by design and pre-commit validation
**Owner:** TraderMonty maintainers

---

## Executive Summary

TraderMonty is a **decision-support and research toolkit only**.  
OANDA Trader (the separate `oanda-trader` repository) is the **execution system**.

These two systems must remain architecturally separated. TraderMonty hands off
structured research artifacts to OANDA Trader; it never touches the broker API,
never places orders, and never makes autonomous execution decisions.

---

## System Responsibilities

### TraderMonty (this repository)

| Responsibility | Permitted |
|---|---|
| Market research and screening | ✅ Yes |
| Technical analysis | ✅ Yes |
| Trade-idea artifacts (TradePlan, ThesisRecord) | ✅ Yes — with `manual_review_required=True` |
| Risk review artifacts | ✅ Yes |
| Manual review gate enforcement | ✅ Yes |
| Trade checklist generation | ✅ Yes |
| Decision-support workflow orchestration | ✅ Yes |
| Accessing broker APIs | ❌ **Never** |
| Placing, modifying, or cancelling orders | ❌ **Never** |
| Reading live account balances or positions from broker | ❌ **Never** |
| Autonomous execution triggered by artifact state | ❌ **Never** |
| Writing to OANDA Trader's state directory | ❌ **Never** |

### OANDA Trader (`oanda-trader` repository)

| Responsibility | Location |
|---|---|
| OANDA REST API client | OANDA Trader only |
| Risk engine (drawdown limits, position sizing enforcement) | OANDA Trader only |
| Order management (entry, SL, TP, modification, cancellation) | OANDA Trader only |
| Position reconciliation | OANDA Trader only |
| Live and paper mode management | OANDA Trader only |
| Execution logging and post-trade tracking | OANDA Trader only |

---

## Handoff Artifact Protocol

TraderMonty produces structured JSON artifacts that OANDA Trader MAY consume as
inputs for human-supervised trade execution. The handoff is always:

1. **One-directional**: TraderMonty → OANDA Trader (never the reverse for execution triggers)
2. **Human-gated**: A human operator must review and approve the TraderMonty artifact
   before any execution action is taken in OANDA Trader
3. **Explicit**: Artifacts are written to a designated handoff directory; OANDA Trader
   polls or reads on demand — TraderMonty never pushes directly into OANDA Trader

### Approved Handoff Artifacts

| Artifact Type | Pydantic Class | Required State Before Handoff |
|---|---|---|
| Trade plan | `TradePlan` | `manual_review_status = APPROVED`, `is_review_complete = True` |
| Research thesis | `ThesisRecord` | `manual_review_status = APPROVED` |
| Risk review | `RiskReview` | `manual_review_status = APPROVED` |
| Portfolio review | `PortfolioReview` | `manual_review_status = APPROVED` |
| Workflow run | `WorkflowRun` | `status = COMPLETED`, `manual_review_status = APPROVED` |

**Non-approved artifacts must never be passed to OANDA Trader.**  
A `TradePlan` with `manual_review_status = PENDING` or `REJECTED` is
not a valid handoff artifact — the execution system must reject it if
such an artifact is presented.

### Handoff Directory Convention

```
state/handoff/           ← TraderMonty writes APPROVED artifacts here
  trade-plans/           ← TradePlan JSON files
  theses/                ← ThesisRecord JSON files
  risk-reviews/          ← RiskReview JSON files
```

OANDA Trader reads from `state/handoff/` but never writes to it. TraderMonty
never reads the OANDA Trader state directory.

---

## What TraderMonty Must NEVER Output

The following outputs are categorically prohibited regardless of artifact type,
skill, or workflow. These are enforced by SK020 (SKILL.md validator) and FL001
(artifact file validator):

| Prohibited Content | Reason |
|---|---|
| "Place this trade automatically" | Violates decision-support boundary |
| "Auto-execute when signal fires" | Violates decision-support boundary |
| "Guaranteed profit / guaranteed return" | False financial claim |
| "Risk-free" trade or strategy | False financial claim |
| "Cannot lose" | False financial claim |
| "100% accurate" | False financial claim |
| Direct broker API credentials or tokens | Security — keep in OANDA Trader |
| Order IDs, position references, account numbers | Execution data — OANDA Trader only |

---

## Validation Enforcement

Three layers enforce this boundary:

### Layer 1 — Forbidden language in skill definitions (SK020)

`scripts/validate_skills_index.py` rejects any `SKILL.md` file containing
guaranteed-profit claims, risk-free claims, or auto-execution language.
This runs as a pre-commit hook and in CI.

### Layer 2 — Forbidden language in artifact files (FL001)

`scripts/validate_artifacts.py` scans all JSON artifact files for the same
forbidden phrases. An artifact file containing "place this trade automatically"
fails FL001 validation and must not be committed.

### Layer 3 — Manual review gate (Phase 1)

All trade-actionable artifacts (`TradePlan`, `ThesisRecord`, etc.) ship with
`manual_review_required=True` as their field default. The workflow runner's
`approve-review` command records reviewer identity, timestamp, and notes before
any run can be finalised. An artifact in `PENDING` or `IN_REVIEW` state must not
be promoted to OANDA Trader.

---

## Data Flow Diagram

```
┌───────────────────────────────────────────────────────┐
│                    TraderMonty                        │
│                                                       │
│  [Skills] → research artifacts → [Workflow Runner]    │
│              ↓                         ↓              │
│         [validate_artifacts.py]   [approve-review]    │
│              ↓                         ↓              │
│          APPROVED TradePlan → state/handoff/          │
└───────────────────────────────────────────────────────┘
                          │
                    HUMAN REVIEWS
                  (reads handoff dir)
                          │
                          ▼
┌───────────────────────────────────────────────────────┐
│                   OANDA Trader                        │
│                                                       │
│   Reads state/handoff/*.json  (read-only, no write)   │
│   Human confirms execution intent in OANDA Trader UI  │
│   OANDA REST API → order placement                    │
│   Risk engine enforces position limits                │
│   Post-trade reconciliation and logging               │
└───────────────────────────────────────────────────────┘
```

**Critical invariant**: No code path in TraderMonty may call OANDA Trader code,
import OANDA Trader modules, or write to OANDA Trader's state directory.

---

## When This Boundary Should Be Re-evaluated

This separation should be reviewed if:

- [ ] TraderMonty evolves into an autonomous trading agent (would require a full
  safety and compliance review; current architecture explicitly prevents this)
- [ ] A shared risk engine is desired between the two systems (keep as a library
  dependency, not a direct integration)
- [ ] Regulatory requirements mandate tighter audit trail integration

---

## Testing and Validation

The integration boundary is tested by:

1. **SK020 tests** (`scripts/tests/test_validate_skills_index.py`) — forbidden
   language in SKILL.md files detected and rejected as errors
2. **FL001 tests** (`scripts/tests/test_validate_artifacts.py`) — forbidden
   language in artifact JSON files detected
3. **Phase 1 manual review gate tests** (`scripts/tests/test_workflow_runner.py`)
   — AWAITING_REVIEW state blocks finalisation; unanswered gates block approval

No TraderMonty test may import or depend on code from `oanda-trader`. Any such
import is a boundary violation.

---

## References

- `schemas/artifacts.py` — `TradePlan`, `WorkflowRun` with `manual_review_required=True`
- `scripts/workflow_runner.py` — `approve-review` command; Phase 1 manual gate
- `scripts/validate_artifacts.py` — FL001 forbidden language validator
- `scripts/validate_skills_index.py` — SK020 skill-level forbidden language validator
- `docs/internal/package-signing-deferral.md` — package integrity model
- `docs/internal/hardening-mission-complete.md` — 15-phase first hardening pass
- Phase 8 of the TraderMonty Second Hardening Pass
