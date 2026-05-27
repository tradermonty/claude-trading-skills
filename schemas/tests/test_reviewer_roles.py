"""Tests for Phase 3 — ReviewerRole enum and identity fields on ArtifactBase."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from schemas.artifacts import (  # noqa: E402
    ArtifactBase,
    BacktestReport,
    BreadthAssessment,
    DataQualityReport,
    ExposureDecision,
    ManualReviewStatus,
    PortfolioReview,
    PostmortemReport,
    ReviewerRole,
    ScreenCandidate,
    TechnicalValidation,
    TradePlan,
    TradeThesis,
    WorkflowRun,
)


# ---------------------------------------------------------------------------
# ReviewerRole enum
# ---------------------------------------------------------------------------

class TestReviewerRoleEnum:
    def test_enum_has_four_values(self) -> None:
        values = {r.value for r in ReviewerRole}
        assert values == {"RESEARCHER", "REVIEWER", "RISK_APPROVER", "ADMIN"}

    def test_researcher_value(self) -> None:
        assert ReviewerRole.RESEARCHER.value == "RESEARCHER"

    def test_reviewer_value(self) -> None:
        assert ReviewerRole.REVIEWER.value == "REVIEWER"

    def test_risk_approver_value(self) -> None:
        assert ReviewerRole.RISK_APPROVER.value == "RISK_APPROVER"

    def test_admin_value(self) -> None:
        assert ReviewerRole.ADMIN.value == "ADMIN"

    def test_enum_is_str_subclass(self) -> None:
        assert isinstance(ReviewerRole.REVIEWER, str)

    def test_reviewer_role_in_all_exports(self) -> None:
        from schemas import artifacts
        assert "ReviewerRole" in artifacts.__all__


# ---------------------------------------------------------------------------
# ArtifactBase field defaults
# ---------------------------------------------------------------------------

def _make_base(**kwargs) -> ArtifactBase:
    defaults = dict(
        artifact_type="test_artifact",
        skill_id="test-skill",
    )
    defaults.update(kwargs)
    return ArtifactBase(**defaults)


class TestArtifactBaseFields:
    def test_reviewer_role_defaults_to_none(self) -> None:
        art = _make_base()
        assert art.reviewer_role is None

    def test_author_id_defaults_to_none(self) -> None:
        art = _make_base()
        assert art.author_id is None

    def test_dual_review_required_defaults_to_false(self) -> None:
        art = _make_base()
        assert art.dual_review_required is False

    def test_secondary_reviewer_defaults_to_none(self) -> None:
        art = _make_base()
        assert art.secondary_reviewer is None

    def test_secondary_reviewer_role_defaults_to_none(self) -> None:
        art = _make_base()
        assert art.secondary_reviewer_role is None

    def test_secondary_reviewed_at_defaults_to_none(self) -> None:
        art = _make_base()
        assert art.secondary_reviewed_at is None

    def test_secondary_review_notes_defaults_to_none(self) -> None:
        art = _make_base()
        assert art.secondary_review_notes is None

    def test_reviewer_role_can_be_set(self) -> None:
        art = _make_base(reviewer_role=ReviewerRole.RISK_APPROVER)
        assert art.reviewer_role == ReviewerRole.RISK_APPROVER

    def test_author_id_can_be_set(self) -> None:
        art = _make_base(author_id="alice")
        assert art.author_id == "alice"

    def test_dual_review_required_can_be_set(self) -> None:
        art = _make_base(dual_review_required=True)
        assert art.dual_review_required is True


# ---------------------------------------------------------------------------
# Self-review validation
# ---------------------------------------------------------------------------

class TestSelfReviewValidation:
    def test_self_review_raises_when_author_equals_reviewer_and_approved(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _make_base(
                author_id="alice",
                reviewer="alice",
                manual_review_status=ManualReviewStatus.APPROVED,
            )
        errors = exc_info.value.errors()
        assert any("Self-review" in str(e.get("msg", "")) for e in errors)

    def test_self_review_allowed_when_waived(self) -> None:
        # WAIVED status does not trigger the self-review block
        art = _make_base(
            author_id="alice",
            reviewer="alice",
            manual_review_status=ManualReviewStatus.WAIVED,
        )
        assert art.manual_review_status == ManualReviewStatus.WAIVED

    def test_self_review_allowed_when_reviewer_unspecified(self) -> None:
        art = _make_base(
            author_id="alice",
            reviewer="unspecified",
            manual_review_status=ManualReviewStatus.APPROVED,
        )
        assert art.reviewer == "unspecified"

    def test_self_review_allowed_when_reviewer_empty_string(self) -> None:
        art = _make_base(
            author_id="alice",
            reviewer="",
            manual_review_status=ManualReviewStatus.APPROVED,
        )
        assert art.reviewer == ""

    def test_self_review_allowed_when_author_id_none(self) -> None:
        art = _make_base(
            author_id=None,
            reviewer="alice",
            manual_review_status=ManualReviewStatus.APPROVED,
        )
        assert art.reviewer == "alice"

    def test_different_reviewer_is_allowed(self) -> None:
        art = _make_base(
            author_id="alice",
            reviewer="bob",
            manual_review_status=ManualReviewStatus.APPROVED,
        )
        assert art.reviewer == "bob"

    def test_self_review_allowed_when_status_pending(self) -> None:
        art = _make_base(
            author_id="alice",
            reviewer="alice",
            manual_review_status=ManualReviewStatus.PENDING,
        )
        assert art.author_id == "alice"

    def test_self_review_allowed_when_status_rejected(self) -> None:
        art = _make_base(
            author_id="alice",
            reviewer="alice",
            manual_review_status=ManualReviewStatus.REJECTED,
        )
        assert art.reviewer == "alice"


# ---------------------------------------------------------------------------
# Subclass artifacts inherit reviewer_role field
# ---------------------------------------------------------------------------

class TestSubclassFields:
    def _make_workflow_run(self, **kwargs) -> WorkflowRun:
        defaults = dict(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-workflow",
        )
        defaults.update(kwargs)
        return WorkflowRun(**defaults)

    def test_workflow_run_has_reviewer_role(self) -> None:
        run = self._make_workflow_run(reviewer_role=ReviewerRole.REVIEWER)
        assert run.reviewer_role == ReviewerRole.REVIEWER

    def test_breadth_assessment_has_reviewer_role(self) -> None:
        art = BreadthAssessment(skill_id="market-breadth-analyzer", artifact_type="breadth_assessment")
        assert art.reviewer_role is None
        art2 = BreadthAssessment(
            skill_id="market-breadth-analyzer",
            artifact_type="breadth_assessment",
            reviewer_role=ReviewerRole.ADMIN,
        )
        assert art2.reviewer_role == ReviewerRole.ADMIN

    def test_screen_candidate_has_reviewer_role(self) -> None:
        art = ScreenCandidate(skill_id="vcp-screener", artifact_type="screen_candidate", ticker="AAPL")
        assert art.reviewer_role is None

    def test_data_quality_report_has_author_id(self) -> None:
        art = DataQualityReport(
            skill_id="data-quality-checker",
            artifact_type="data_quality_report",
            author_id="researcher_1",
        )
        assert art.author_id == "researcher_1"

    def test_trade_thesis_has_dual_review_required(self) -> None:
        art = TradeThesis(
            skill_id="trader-memory-core",
            artifact_type="trade_thesis",
            ticker="AAPL",
            dual_review_required=True,
        )
        assert art.dual_review_required is True

    def test_portfolio_review_self_review_blocked(self) -> None:
        with pytest.raises(ValidationError):
            PortfolioReview(
                skill_id="portfolio-manager",
                artifact_type="portfolio_review",
                author_id="trader",
                reviewer="trader",
                manual_review_status=ManualReviewStatus.APPROVED,
            )


# ---------------------------------------------------------------------------
# Dual-review schema validator
# ---------------------------------------------------------------------------

class TestDualReviewValidator:
    """Tests for the _enforce_dual_review model_validator on ArtifactBase."""

    def test_dual_review_not_required_no_constraints(self) -> None:
        # dual_review_required=False — secondary_reviewer same as reviewer is fine
        art = _make_base(
            dual_review_required=False,
            reviewer="alice",
            secondary_reviewer="alice",
        )
        assert art.secondary_reviewer == "alice"

    def test_dual_review_secondary_same_as_primary_blocked(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _make_base(
                dual_review_required=True,
                reviewer="alice",
                secondary_reviewer="alice",
                author_id="bob",
            )
        assert any("Dual review invalid" in str(e.get("msg", "")) for e in exc_info.value.errors())

    def test_dual_review_secondary_is_author_blocked(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _make_base(
                dual_review_required=True,
                reviewer="alice",
                secondary_reviewer="bob",
                author_id="bob",
            )
        errors = exc_info.value.errors()
        assert any("author" in str(e.get("msg", "")).lower() for e in errors)

    def test_dual_review_valid_distinct_reviewers_passes(self) -> None:
        art = _make_base(
            dual_review_required=True,
            reviewer="alice",
            reviewer_role=ReviewerRole.REVIEWER,
            secondary_reviewer="carol",
            secondary_reviewer_role=ReviewerRole.RISK_APPROVER,
            author_id="bob",
        )
        assert art.secondary_reviewer == "carol"

    def test_dual_review_secondary_unspecified_allowed(self) -> None:
        # "unspecified" is treated as absent — validator doesn't fire
        art = _make_base(
            dual_review_required=True,
            reviewer="alice",
            secondary_reviewer="unspecified",
            author_id="bob",
        )
        assert art.secondary_reviewer == "unspecified"

    def test_dual_review_waiver_without_notes_blocked(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _make_base(
                dual_review_required=True,
                manual_review_status=ManualReviewStatus.WAIVED,
                reviewer="alice",
                review_notes=None,
            )
        errors = exc_info.value.errors()
        assert any("justification" in str(e.get("msg", "")).lower() for e in errors)

    def test_dual_review_waiver_with_notes_passes(self) -> None:
        art = _make_base(
            dual_review_required=True,
            manual_review_status=ManualReviewStatus.WAIVED,
            reviewer="alice",
            review_notes="Non-trade artifact approved for waiver by ADMIN",
        )
        assert art.manual_review_status == ManualReviewStatus.WAIVED

    def test_dual_review_secondary_none_is_fine_when_review_pending(self) -> None:
        # secondary not yet filled in — review still in progress
        art = _make_base(
            dual_review_required=True,
            manual_review_status=ManualReviewStatus.PENDING,
            secondary_reviewer=None,
        )
        assert art.dual_review_required is True
