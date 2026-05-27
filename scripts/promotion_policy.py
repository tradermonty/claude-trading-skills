"""Promotion policy engine for TraderMonty workflow artifacts.

A workflow run or artifact CANNOT be promoted unless all policy checks pass.
Policy checks are machine-executable and return structured results.

Usage:
    from promotion_policy import PromotionPolicy, evaluate_run
    checks = evaluate_run(run_json_dict, manifest_json_dict=None)
    if all(c.passed for c in checks):
        print("Promotion approved")
    else:
        for c in checks:
            if not c.passed:
                print(f"  BLOCKED [{c.code}] {c.message}")
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PolicyCheck:
    code: str
    passed: bool
    message: str
    severity: str = "error"  # "error" | "warning"


def _check_pp001_all_steps_complete(run: dict) -> PolicyCheck:
    steps = run.get("steps", [])
    incomplete = [s for s in steps if s.get("status") not in ("DONE", "SKIPPED")]
    if incomplete:
        return PolicyCheck(
            "PP001", False,
            f"{len(incomplete)} step(s) are not DONE or SKIPPED: "
            + ", ".join(f"Step {s['step_number']}" for s in incomplete),
        )
    return PolicyCheck("PP001", True, "All steps complete")


def _check_pp002_manual_review_complete(run: dict) -> PolicyCheck:
    review = run.get("manual_review_status", "PENDING")
    if run.get("manual_review_required", True):
        if review not in ("APPROVED", "WAIVED"):
            return PolicyCheck(
                "PP002", False,
                f"Manual review is {review} — must be APPROVED or WAIVED before promotion",
            )
    return PolicyCheck("PP002", True, f"Manual review: {review}")


def _check_pp003_reviewer_identity(run: dict) -> PolicyCheck:
    review = run.get("manual_review_status", "PENDING")
    if review in ("APPROVED", "WAIVED"):
        reviewer = run.get("reviewer", "")
        if not reviewer or reviewer == "unspecified":
            return PolicyCheck(
                "PP003", False,
                "Reviewer identity is missing or 'unspecified' — "
                "review must be attributed to a named reviewer",
            )
    return PolicyCheck("PP003", True, "Reviewer identity recorded")


def _check_pp004_no_unanswered_decision_gates(run: dict) -> PolicyCheck:
    unanswered = [
        s for s in run.get("steps", [])
        if s.get("decision_gate_question") and not s.get("decision_gate_answer")
        and s.get("status") == "DONE"
    ]
    if unanswered:
        return PolicyCheck(
            "PP004", False,
            f"{len(unanswered)} decision gate(s) are marked DONE but have no answer recorded",
        )
    return PolicyCheck("PP004", True, "All decision gates answered")


def _check_pp005_no_critical_unresolved_gaps(run: dict) -> PolicyCheck:
    # Check run-level data_gaps (if any artifact gaps were propagated)
    gaps = run.get("data_gaps", [])
    blocking = [
        g for g in gaps
        if g.get("severity") == "CRITICAL" and not g.get("can_continue", True)
    ]
    if blocking:
        return PolicyCheck(
            "PP005", False,
            f"{len(blocking)} CRITICAL data gap(s) are unresolved and block promotion",
        )
    return PolicyCheck("PP005", True, "No blocking critical data gaps")


def _check_pp006_provenance_captured(run: dict) -> PolicyCheck:
    missing = []
    if not run.get("run_timestamp"):
        missing.append("run_timestamp")
    if not run.get("artifact_schema_versions"):
        missing.append("artifact_schema_versions")
    if not run.get("skill_versions") and run.get("steps"):
        missing.append("skill_versions")
    if missing:
        return PolicyCheck(
            "PP006", False,
            f"Provenance fields missing: {', '.join(missing)} — run `start` to capture them",
            severity="warning",
        )
    return PolicyCheck("PP006", True, "Provenance captured")


def _check_pp007_workflow_status_completed(run: dict) -> PolicyCheck:
    status = run.get("status", "")
    if status != "COMPLETED":
        return PolicyCheck(
            "PP007", False,
            f"Workflow run status is '{status}' — must be COMPLETED before promotion",
        )
    return PolicyCheck("PP007", True, "Status: COMPLETED")


def _check_pp008_no_self_review(run: dict) -> PolicyCheck:
    author = run.get("author_id") or run.get("operator", "")
    reviewer = run.get("reviewer", "")
    review_status = run.get("manual_review_status", "PENDING")
    if (
        author
        and reviewer
        and reviewer not in ("unspecified", "")
        and author == reviewer
        and review_status == "APPROVED"
    ):
        return PolicyCheck(
            "PP008", False,
            f"Self-review detected: operator '{author}' approved their own run. "
            "Use a different reviewer.",
        )
    return PolicyCheck("PP008", True, "No self-review detected")


def _check_pp009_no_abandoned(run: dict) -> PolicyCheck:
    if run.get("status") == "ABANDONED":
        return PolicyCheck(
            "PP009", False,
            f"Run is ABANDONED (reason: {run.get('abort_reason', 'unknown')}) — cannot promote",
        )
    return PolicyCheck("PP009", True, "Run is not abandoned")


def _check_pp010_dual_review_secondary_reviewer(run: dict) -> PolicyCheck:
    """PP010: When dual_review_required, a distinct secondary reviewer must be recorded."""
    if not run.get("dual_review_required", False):
        return PolicyCheck("PP010", True, "Dual review not required")

    review_status = run.get("manual_review_status", "PENDING")
    if review_status not in ("APPROVED", "WAIVED"):
        # Primary review not complete — can't enforce secondary yet
        return PolicyCheck("PP010", True, "Dual review check deferred — primary review not complete")

    secondary = run.get("secondary_reviewer", "") or ""
    if not secondary or secondary == "unspecified":
        return PolicyCheck(
            "PP010", False,
            "Dual review is required but no secondary reviewer is recorded. "
            "A second independent reviewer must sign off before promotion.",
        )

    primary = run.get("reviewer", "") or ""
    author = run.get("author_id") or run.get("operator", "") or ""

    if primary and secondary == primary:
        return PolicyCheck(
            "PP010", False,
            f"Dual review invalid: primary and secondary reviewer are the same person "
            f"'{secondary}'. Two distinct reviewers are required.",
        )
    if author and secondary == author:
        return PolicyCheck(
            "PP010", False,
            f"Dual review invalid: secondary reviewer '{secondary}' is the artifact author. "
            "The author cannot serve as a reviewer.",
        )

    return PolicyCheck(
        "PP010", True,
        f"Dual review recorded: primary={primary!r}, secondary={secondary!r}",
    )


def _check_pp011_dual_review_risk_approver(run: dict) -> PolicyCheck:
    """PP011: When dual_review_required, at least one reviewer must hold RISK_APPROVER role."""
    if not run.get("dual_review_required", False):
        return PolicyCheck("PP011", True, "Dual review not required")

    review_status = run.get("manual_review_status", "PENDING")
    if review_status not in ("APPROVED", "WAIVED"):
        return PolicyCheck("PP011", True, "Dual review risk-approver check deferred")

    primary_role = run.get("reviewer_role", "") or ""
    secondary_role = run.get("secondary_reviewer_role", "") or ""

    has_risk_approver = (
        primary_role == "RISK_APPROVER" or secondary_role == "RISK_APPROVER"
    )
    if not has_risk_approver:
        return PolicyCheck(
            "PP011", False,
            f"Dual review requires at least one RISK_APPROVER. "
            f"Got primary_role={primary_role!r}, secondary_role={secondary_role!r}. "
            "Assign a reviewer with ReviewerRole.RISK_APPROVER.",
        )

    return PolicyCheck(
        "PP011", True,
        "Dual review includes a RISK_APPROVER",
    )


def _check_pp012_waiver_justification(run: dict) -> PolicyCheck:
    """PP012: A WAIVED review must record a non-empty justification in review_notes."""
    if run.get("manual_review_status") != "WAIVED":
        return PolicyCheck("PP012", True, "Review not waived — no justification required")

    notes = run.get("review_notes", "") or ""
    if not notes.strip():
        return PolicyCheck(
            "PP012", False,
            "Review is WAIVED but review_notes is empty. "
            "All waivers must include a documented justification.",
        )

    return PolicyCheck("PP012", True, "Waiver justification recorded")


ALL_CHECKS = [
    _check_pp001_all_steps_complete,
    _check_pp002_manual_review_complete,
    _check_pp003_reviewer_identity,
    _check_pp004_no_unanswered_decision_gates,
    _check_pp005_no_critical_unresolved_gaps,
    _check_pp006_provenance_captured,
    _check_pp007_workflow_status_completed,
    _check_pp008_no_self_review,
    _check_pp009_no_abandoned,
    _check_pp010_dual_review_secondary_reviewer,
    _check_pp011_dual_review_risk_approver,
    _check_pp012_waiver_justification,
]


def evaluate_run(run: dict) -> list[PolicyCheck]:
    """Evaluate all promotion policy checks for a workflow run dict."""
    return [check(run) for check in ALL_CHECKS]


def is_promotable(run: dict) -> bool:
    """Return True only if all error-severity checks pass."""
    return all(
        c.passed for c in evaluate_run(run) if c.severity == "error"
    )
