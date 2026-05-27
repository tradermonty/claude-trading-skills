"""Tests for scripts/promotion_policy.py — promotion policy engine."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from promotion_policy import (  # noqa: E402
    PolicyCheck,
    evaluate_run,
    is_promotable,
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
)


def _make_run(**overrides) -> dict:
    """Return a minimal promotable run dict, optionally overriding fields."""
    base = {
        "status": "COMPLETED",
        "manual_review_status": "APPROVED",
        "manual_review_required": True,
        "reviewer": "alice",
        "operator": "bob",
        "author_id": "bob",
        "run_timestamp": "2026-01-15T12:00:00+00:00",
        "artifact_schema_versions": {"workflow_run": "1.0"},
        "skill_versions": {"vcp-screener": "1.0"},
        "steps": [
            {"step_number": 1, "name": "Step 1", "status": "DONE",
             "decision_gate_question": None, "decision_gate_answer": None},
        ],
        "data_gaps": [],
        "abort_reason": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# PP001 — All steps complete
# ---------------------------------------------------------------------------

class TestPP001AllStepsComplete:
    def test_passes_when_all_steps_done(self) -> None:
        run = _make_run(steps=[
            {"step_number": 1, "status": "DONE"},
            {"step_number": 2, "status": "SKIPPED"},
        ])
        check = _check_pp001_all_steps_complete(run)
        assert check.passed
        assert check.code == "PP001"

    def test_passes_with_empty_steps(self) -> None:
        run = _make_run(steps=[])
        check = _check_pp001_all_steps_complete(run)
        assert check.passed

    def test_blocked_when_step_pending(self) -> None:
        run = _make_run(steps=[
            {"step_number": 1, "status": "PENDING"},
        ])
        check = _check_pp001_all_steps_complete(run)
        assert not check.passed
        assert "step(s) are not DONE or SKIPPED" in check.message

    def test_blocked_when_step_running(self) -> None:
        run = _make_run(steps=[
            {"step_number": 1, "status": "RUNNING"},
        ])
        check = _check_pp001_all_steps_complete(run)
        assert not check.passed

    def test_blocked_when_step_failed(self) -> None:
        run = _make_run(steps=[
            {"step_number": 1, "status": "DONE"},
            {"step_number": 2, "status": "FAILED"},
        ])
        check = _check_pp001_all_steps_complete(run)
        assert not check.passed


# ---------------------------------------------------------------------------
# PP002 — Manual review complete
# ---------------------------------------------------------------------------

class TestPP002ManualReviewComplete:
    def test_passes_when_approved(self) -> None:
        run = _make_run(manual_review_status="APPROVED")
        check = _check_pp002_manual_review_complete(run)
        assert check.passed

    def test_passes_when_waived(self) -> None:
        run = _make_run(manual_review_status="WAIVED")
        check = _check_pp002_manual_review_complete(run)
        assert check.passed

    def test_blocked_when_pending(self) -> None:
        run = _make_run(manual_review_status="PENDING")
        check = _check_pp002_manual_review_complete(run)
        assert not check.passed
        assert "PENDING" in check.message

    def test_blocked_when_in_review(self) -> None:
        run = _make_run(manual_review_status="IN_REVIEW")
        check = _check_pp002_manual_review_complete(run)
        assert not check.passed

    def test_blocked_when_rejected(self) -> None:
        run = _make_run(manual_review_status="REJECTED")
        check = _check_pp002_manual_review_complete(run)
        assert not check.passed

    def test_passes_when_review_not_required(self) -> None:
        run = _make_run(manual_review_required=False, manual_review_status="PENDING")
        check = _check_pp002_manual_review_complete(run)
        assert check.passed


# ---------------------------------------------------------------------------
# PP003 — Reviewer identity
# ---------------------------------------------------------------------------

class TestPP003ReviewerIdentity:
    def test_passes_with_named_reviewer(self) -> None:
        run = _make_run(manual_review_status="APPROVED", reviewer="alice")
        check = _check_pp003_reviewer_identity(run)
        assert check.passed

    def test_blocked_when_reviewer_unspecified(self) -> None:
        run = _make_run(manual_review_status="APPROVED", reviewer="unspecified")
        check = _check_pp003_reviewer_identity(run)
        assert not check.passed
        assert "unspecified" in check.message

    def test_blocked_when_reviewer_empty(self) -> None:
        run = _make_run(manual_review_status="APPROVED", reviewer="")
        check = _check_pp003_reviewer_identity(run)
        assert not check.passed

    def test_blocked_when_reviewer_none(self) -> None:
        run = _make_run(manual_review_status="APPROVED", reviewer=None)
        check = _check_pp003_reviewer_identity(run)
        assert not check.passed

    def test_passes_when_review_not_yet_done(self) -> None:
        # If status is PENDING, PP003 doesn't apply
        run = _make_run(manual_review_status="PENDING", reviewer=None)
        check = _check_pp003_reviewer_identity(run)
        assert check.passed


# ---------------------------------------------------------------------------
# PP004 — Unanswered decision gates
# ---------------------------------------------------------------------------

class TestPP004DecisionGates:
    def test_passes_when_all_answered(self) -> None:
        run = _make_run(steps=[
            {"step_number": 1, "status": "DONE",
             "decision_gate_question": "Is market open?", "decision_gate_answer": "yes"},
        ])
        check = _check_pp004_no_unanswered_decision_gates(run)
        assert check.passed

    def test_passes_when_no_decision_gates(self) -> None:
        run = _make_run(steps=[
            {"step_number": 1, "status": "DONE",
             "decision_gate_question": None, "decision_gate_answer": None},
        ])
        check = _check_pp004_no_unanswered_decision_gates(run)
        assert check.passed

    def test_blocked_when_gate_done_but_no_answer(self) -> None:
        run = _make_run(steps=[
            {"step_number": 1, "status": "DONE",
             "decision_gate_question": "Go or no-go?", "decision_gate_answer": None},
        ])
        check = _check_pp004_no_unanswered_decision_gates(run)
        assert not check.passed
        assert "decision gate" in check.message.lower()

    def test_passes_when_gate_step_is_pending(self) -> None:
        # A gate in PENDING status is not yet "DONE with no answer"
        run = _make_run(steps=[
            {"step_number": 1, "status": "PENDING",
             "decision_gate_question": "Continue?", "decision_gate_answer": None},
        ])
        check = _check_pp004_no_unanswered_decision_gates(run)
        assert check.passed


# ---------------------------------------------------------------------------
# PP005 — No critical unresolved gaps
# ---------------------------------------------------------------------------

class TestPP005NoCriticalGaps:
    def test_passes_with_no_gaps(self) -> None:
        run = _make_run(data_gaps=[])
        check = _check_pp005_no_critical_unresolved_gaps(run)
        assert check.passed

    def test_passes_with_non_critical_gap(self) -> None:
        run = _make_run(data_gaps=[
            {"severity": "HIGH", "can_continue": False},
        ])
        check = _check_pp005_no_critical_unresolved_gaps(run)
        assert check.passed

    def test_passes_with_critical_continuable_gap(self) -> None:
        run = _make_run(data_gaps=[
            {"severity": "CRITICAL", "can_continue": True},
        ])
        check = _check_pp005_no_critical_unresolved_gaps(run)
        assert check.passed

    def test_blocked_when_critical_blocking_gap(self) -> None:
        run = _make_run(data_gaps=[
            {"severity": "CRITICAL", "can_continue": False},
        ])
        check = _check_pp005_no_critical_unresolved_gaps(run)
        assert not check.passed
        assert "CRITICAL" in check.message


# ---------------------------------------------------------------------------
# PP006 — Provenance captured
# ---------------------------------------------------------------------------

class TestPP006Provenance:
    def test_passes_with_all_fields(self) -> None:
        run = _make_run()
        check = _check_pp006_provenance_captured(run)
        assert check.passed

    def test_warning_when_run_timestamp_missing(self) -> None:
        run = _make_run(run_timestamp=None)
        check = _check_pp006_provenance_captured(run)
        assert not check.passed
        assert check.severity == "warning"
        assert "run_timestamp" in check.message

    def test_warning_when_schema_versions_missing(self) -> None:
        run = _make_run(artifact_schema_versions={})
        check = _check_pp006_provenance_captured(run)
        assert not check.passed
        assert check.severity == "warning"

    def test_warning_when_skill_versions_missing_with_steps(self) -> None:
        run = _make_run(skill_versions={}, steps=[{"step_number": 1}])
        check = _check_pp006_provenance_captured(run)
        assert not check.passed
        assert check.severity == "warning"

    def test_passes_when_no_steps_and_skill_versions_empty(self) -> None:
        run = _make_run(skill_versions={}, steps=[])
        check = _check_pp006_provenance_captured(run)
        assert check.passed


# ---------------------------------------------------------------------------
# PP007 — Workflow status COMPLETED
# ---------------------------------------------------------------------------

class TestPP007WorkflowStatus:
    def test_passes_when_completed(self) -> None:
        run = _make_run(status="COMPLETED")
        check = _check_pp007_workflow_status_completed(run)
        assert check.passed

    def test_blocked_when_in_progress(self) -> None:
        run = _make_run(status="IN_PROGRESS")
        check = _check_pp007_workflow_status_completed(run)
        assert not check.passed
        assert "IN_PROGRESS" in check.message

    def test_blocked_when_awaiting_review(self) -> None:
        run = _make_run(status="AWAITING_REVIEW")
        check = _check_pp007_workflow_status_completed(run)
        assert not check.passed

    def test_blocked_when_started(self) -> None:
        run = _make_run(status="STARTED")
        check = _check_pp007_workflow_status_completed(run)
        assert not check.passed


# ---------------------------------------------------------------------------
# PP008 — No self-review
# ---------------------------------------------------------------------------

class TestPP008NoSelfReview:
    def test_passes_when_different_reviewer(self) -> None:
        run = _make_run(author_id="alice", reviewer="bob", manual_review_status="APPROVED")
        check = _check_pp008_no_self_review(run)
        assert check.passed

    def test_blocked_when_self_review(self) -> None:
        run = _make_run(author_id="alice", reviewer="alice", manual_review_status="APPROVED")
        check = _check_pp008_no_self_review(run)
        assert not check.passed
        assert "Self-review" in check.message

    def test_passes_when_reviewer_unspecified(self) -> None:
        run = _make_run(author_id="alice", reviewer="unspecified", manual_review_status="APPROVED")
        check = _check_pp008_no_self_review(run)
        assert check.passed

    def test_passes_when_author_id_none(self) -> None:
        run = _make_run(author_id=None, reviewer="alice", manual_review_status="APPROVED")
        check = _check_pp008_no_self_review(run)
        assert check.passed

    def test_passes_when_review_not_approved(self) -> None:
        # Self-review of a PENDING run is not a violation
        run = _make_run(author_id="alice", reviewer="alice", manual_review_status="PENDING")
        check = _check_pp008_no_self_review(run)
        assert check.passed

    def test_uses_operator_as_fallback_for_author(self) -> None:
        run = _make_run(author_id=None, operator="alice", reviewer="alice",
                        manual_review_status="APPROVED")
        check = _check_pp008_no_self_review(run)
        assert not check.passed


# ---------------------------------------------------------------------------
# PP009 — Not abandoned
# ---------------------------------------------------------------------------

class TestPP009NotAbandoned:
    def test_passes_when_not_abandoned(self) -> None:
        run = _make_run(status="COMPLETED")
        check = _check_pp009_no_abandoned(run)
        assert check.passed

    def test_blocked_when_abandoned(self) -> None:
        run = _make_run(status="ABANDONED", abort_reason="User gave up")
        check = _check_pp009_no_abandoned(run)
        assert not check.passed
        assert "ABANDONED" in check.message

    def test_abandon_message_includes_reason(self) -> None:
        run = _make_run(status="ABANDONED", abort_reason="Data unavailable")
        check = _check_pp009_no_abandoned(run)
        assert "Data unavailable" in check.message


# ---------------------------------------------------------------------------
# evaluate_run and is_promotable
# ---------------------------------------------------------------------------

class TestEvaluateRunAndIsPromotable:
    def test_evaluate_run_returns_twelve_checks(self) -> None:
        run = _make_run()
        checks = evaluate_run(run)
        assert len(checks) == 12

    def test_is_promotable_all_pass(self) -> None:
        run = _make_run()
        assert is_promotable(run) is True

    def test_is_promotable_fails_on_one_error(self) -> None:
        run = _make_run(status="IN_PROGRESS")  # PP007 fails
        assert is_promotable(run) is False

    def test_is_promotable_true_when_only_warnings(self) -> None:
        # PP006 is a warning; it should not block promotion
        run = _make_run(run_timestamp=None)  # triggers PP006 warning
        # Fix all errors that might exist
        run["status"] = "COMPLETED"
        run["manual_review_status"] = "APPROVED"
        run["reviewer"] = "alice"
        run["steps"] = []
        checks = evaluate_run(run)
        errors = [c for c in checks if not c.passed and c.severity == "error"]
        warnings = [c for c in checks if not c.passed and c.severity == "warning"]
        # There should be at least a warning
        assert any(c.code == "PP006" for c in warnings)
        # is_promotable should only block on errors
        assert is_promotable(run) is True

    def test_is_promotable_false_on_abandoned(self) -> None:
        run = _make_run(status="ABANDONED")
        assert is_promotable(run) is False

    def test_is_promotable_false_on_self_review(self) -> None:
        run = _make_run(author_id="alice", reviewer="alice", operator="alice")
        assert is_promotable(run) is False

    def test_all_checks_return_policy_check_instances(self) -> None:
        run = _make_run()
        checks = evaluate_run(run)
        for check in checks:
            assert isinstance(check, PolicyCheck)
            assert check.code.startswith("PP")
            assert isinstance(check.passed, bool)
            assert isinstance(check.message, str)


# ---------------------------------------------------------------------------
# PP010 — Dual review: distinct secondary reviewer
# ---------------------------------------------------------------------------

class TestPP010DualReviewSecondaryReviewer:
    def test_passes_when_dual_review_not_required(self) -> None:
        run = _make_run(dual_review_required=False)
        check = _check_pp010_dual_review_secondary_reviewer(run)
        assert check.passed
        assert check.code == "PP010"

    def test_passes_when_dual_review_required_and_secondary_present(self) -> None:
        run = _make_run(
            dual_review_required=True,
            reviewer="alice",
            secondary_reviewer="carol",
            author_id="bob",
        )
        check = _check_pp010_dual_review_secondary_reviewer(run)
        assert check.passed

    def test_blocked_when_secondary_missing(self) -> None:
        run = _make_run(dual_review_required=True, reviewer="alice")
        check = _check_pp010_dual_review_secondary_reviewer(run)
        assert not check.passed
        assert "secondary reviewer" in check.message.lower()

    def test_blocked_when_secondary_is_unspecified(self) -> None:
        run = _make_run(dual_review_required=True, reviewer="alice", secondary_reviewer="unspecified")
        check = _check_pp010_dual_review_secondary_reviewer(run)
        assert not check.passed

    def test_blocked_when_secondary_same_as_primary(self) -> None:
        run = _make_run(
            dual_review_required=True,
            reviewer="alice",
            secondary_reviewer="alice",
            author_id="bob",
        )
        check = _check_pp010_dual_review_secondary_reviewer(run)
        assert not check.passed
        assert "same person" in check.message.lower()

    def test_blocked_when_secondary_is_author(self) -> None:
        run = _make_run(
            dual_review_required=True,
            reviewer="alice",
            secondary_reviewer="bob",
            author_id="bob",
        )
        check = _check_pp010_dual_review_secondary_reviewer(run)
        assert not check.passed
        assert "author" in check.message.lower()

    def test_deferred_when_primary_review_not_complete(self) -> None:
        run = _make_run(
            dual_review_required=True,
            manual_review_status="PENDING",
        )
        check = _check_pp010_dual_review_secondary_reviewer(run)
        # Should pass (deferred) — primary not done yet
        assert check.passed
        assert "deferred" in check.message.lower()

    def test_is_promotable_false_without_secondary(self) -> None:
        run = _make_run(dual_review_required=True, reviewer="alice", author_id="bob")
        assert is_promotable(run) is False

    def test_is_promotable_true_with_valid_dual_review_and_risk_approver(self) -> None:
        run = _make_run(
            dual_review_required=True,
            reviewer="alice",
            reviewer_role="REVIEWER",
            secondary_reviewer="carol",
            secondary_reviewer_role="RISK_APPROVER",
            author_id="bob",
        )
        assert is_promotable(run) is True


# ---------------------------------------------------------------------------
# PP011 — Dual review: at least one RISK_APPROVER
# ---------------------------------------------------------------------------

class TestPP011DualReviewRiskApprover:
    def test_passes_when_dual_review_not_required(self) -> None:
        run = _make_run(dual_review_required=False)
        check = _check_pp011_dual_review_risk_approver(run)
        assert check.passed

    def test_passes_when_primary_is_risk_approver(self) -> None:
        run = _make_run(
            dual_review_required=True,
            reviewer_role="RISK_APPROVER",
            secondary_reviewer="carol",
            secondary_reviewer_role="REVIEWER",
        )
        check = _check_pp011_dual_review_risk_approver(run)
        assert check.passed

    def test_passes_when_secondary_is_risk_approver(self) -> None:
        run = _make_run(
            dual_review_required=True,
            reviewer_role="REVIEWER",
            secondary_reviewer="carol",
            secondary_reviewer_role="RISK_APPROVER",
        )
        check = _check_pp011_dual_review_risk_approver(run)
        assert check.passed

    def test_blocked_when_no_risk_approver(self) -> None:
        run = _make_run(
            dual_review_required=True,
            reviewer_role="REVIEWER",
            secondary_reviewer="carol",
            secondary_reviewer_role="REVIEWER",
        )
        check = _check_pp011_dual_review_risk_approver(run)
        assert not check.passed
        assert "RISK_APPROVER" in check.message

    def test_blocked_when_roles_missing_entirely(self) -> None:
        run = _make_run(
            dual_review_required=True,
            secondary_reviewer="carol",
        )
        check = _check_pp011_dual_review_risk_approver(run)
        assert not check.passed

    def test_deferred_when_review_pending(self) -> None:
        run = _make_run(dual_review_required=True, manual_review_status="PENDING")
        check = _check_pp011_dual_review_risk_approver(run)
        assert check.passed  # deferred


# ---------------------------------------------------------------------------
# PP012 — Waiver justification
# ---------------------------------------------------------------------------

class TestPP012WaiverJustification:
    def test_passes_when_not_waived(self) -> None:
        run = _make_run(manual_review_status="APPROVED")
        check = _check_pp012_waiver_justification(run)
        assert check.passed

    def test_passes_when_waived_with_notes(self) -> None:
        run = _make_run(
            manual_review_status="WAIVED",
            reviewer="alice",
            review_notes="Non-trade artifact; waiver approved by ADMIN.",
        )
        check = _check_pp012_waiver_justification(run)
        assert check.passed

    def test_blocked_when_waived_without_notes(self) -> None:
        run = _make_run(manual_review_status="WAIVED", reviewer="alice", review_notes=None)
        check = _check_pp012_waiver_justification(run)
        assert not check.passed
        assert "justification" in check.message.lower()

    def test_blocked_when_waived_with_empty_notes(self) -> None:
        run = _make_run(manual_review_status="WAIVED", reviewer="alice", review_notes="   ")
        check = _check_pp012_waiver_justification(run)
        assert not check.passed

    def test_is_promotable_false_waived_without_notes(self) -> None:
        run = _make_run(manual_review_status="WAIVED", reviewer="alice", review_notes="")
        assert is_promotable(run) is False
