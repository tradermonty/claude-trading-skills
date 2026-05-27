"""
Canonical artifact schemas for TraderMonty.

All structured outputs from skills and workflow steps must conform to one of
these models.  Each model extends ArtifactBase which provides:
  - Identity fields (artifact_id, schema_version, created_at, skill_id …)
  - Data gap tracking (data_gaps: list[DataGap])
  - Mandatory disclaimer (decision_support_only)
  - next_actions list
  - manual_review_required flag

Design choices
--------------
- Pydantic v2 models: runtime validation + JSON Schema export.
- Optional fields default to None so partial output is valid.
- Every model that contains trade-actionable content carries
  manual_review_required=True as its field default.
- Enums are defined as plain str subclasses so they serialise cleanly to JSON.

Adding a new schema
-------------------
1. Inherit from ArtifactBase.
2. Set ARTIFACT_TYPE as a class-level constant string.
3. Add the class name to __all__ at the bottom of this file.
4. Run `python schemas/export_json_schemas.py` to regenerate JSON Schema files.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Canonical disclaimer text — embed verbatim in every artifact
# ---------------------------------------------------------------------------
DISCLAIMER_TEXT = (
    "This artifact is produced by TraderMonty, a decision-support and "
    "trading-process toolkit. It is NOT financial advice, investment advisory, "
    "a trading signal, or a guarantee of profitability. All trading decisions, "
    "position sizing, risk management, and broker execution decisions remain "
    "solely the user's responsibility. Review all outputs manually before acting."
)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExposureRecommendation(str, Enum):
    NEW_ENTRY_ALLOWED = "NEW_ENTRY_ALLOWED"
    REDUCE_ONLY = "REDUCE_ONLY"
    CASH_PRIORITY = "CASH_PRIORITY"


class MarketRegimeType(str, Enum):
    CONCENTRATION = "CONCENTRATION"
    BROADENING = "BROADENING"
    CONTRACTION = "CONTRACTION"
    INFLATIONARY = "INFLATIONARY"
    TRANSITIONAL = "TRANSITIONAL"
    UNKNOWN = "UNKNOWN"


class HealthZone(str, Enum):
    STRONG = "STRONG"
    HEALTHY = "HEALTHY"
    NEUTRAL = "NEUTRAL"
    WEAKENING = "WEAKENING"
    CRITICAL = "CRITICAL"


class RiskZone(str, Enum):
    LOW = "LOW"
    CAUTION = "CAUTION"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


class SetupType(str, Enum):
    VCP = "VCP"
    CANSLIM = "CANSLIM"
    PEAD = "PEAD"
    EARNINGS_GAP = "EARNINGS_GAP"
    PARABOLIC_SHORT = "PARABOLIC_SHORT"
    BREAKOUT = "BREAKOUT"
    PAIR_LONG = "PAIR_LONG"
    PAIR_SHORT = "PAIR_SHORT"
    OPTIONS_COVERED_CALL = "OPTIONS_COVERED_CALL"
    OPTIONS_PROTECTIVE_PUT = "OPTIONS_PROTECTIVE_PUT"
    OPTIONS_SPREAD = "OPTIONS_SPREAD"
    DIVIDEND_PULLBACK = "DIVIDEND_PULLBACK"
    OTHER = "OTHER"


class ThesisLifecycle(str, Enum):
    IDEA = "IDEA"
    CANDIDATE = "CANDIDATE"
    PLANNED = "PLANNED"
    ENTERED = "ENTERED"
    MANAGED = "MANAGED"
    EXITED = "EXITED"
    POSTMORTEM_DONE = "POSTMORTEM_DONE"
    ARCHIVED = "ARCHIVED"


class ProcessQuality(str, Enum):
    GOOD = "GOOD"
    BAD = "BAD"


class OutcomeQuality(str, Enum):
    GOOD = "GOOD"
    BAD = "BAD"


class WorkflowStatus(str, Enum):
    STARTED = "STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_DECISION = "AWAITING_DECISION"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class ManualReviewStatus(str, Enum):
    """Lifecycle state of the human review gate for an artifact."""
    PENDING = "PENDING"       # Review not yet started (default)
    IN_REVIEW = "IN_REVIEW"   # Reviewer assigned; review in progress
    APPROVED = "APPROVED"     # Review complete — output approved for use
    REJECTED = "REJECTED"     # Review complete — output rejected / needs rework
    WAIVED = "WAIVED"         # Review explicitly waived (non-trade artifacts only)


class ReviewerRole(str, Enum):
    """Role of the reviewer who completed or waived the review."""
    RESEARCHER = "RESEARCHER"
    REVIEWER = "REVIEWER"
    RISK_APPROVER = "RISK_APPROVER"
    ADMIN = "ADMIN"


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class DataGap(BaseModel):
    """A single data gap record — emitted when expected data is absent or stale."""

    gap_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    severity: Severity
    description: str = Field(..., description="What data is missing or stale")
    affected_decision: str = Field(..., description="Which downstream decision this impairs")
    remediation: str = Field(..., description="How the user can resolve this gap")
    can_continue: bool = Field(
        ...,
        description="Whether the skill/workflow can produce useful output despite this gap",
    )
    source: Optional[str] = Field(None, description="Which upstream skill or API caused the gap")


class Disclaimer(BaseModel):
    text: str = Field(default=DISCLAIMER_TEXT)
    decision_support_only: bool = Field(default=True)


class ComponentScore(BaseModel):
    name: str
    score: Optional[float] = None
    weight: Optional[float] = None
    raw_value: Optional[Any] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Base model shared by all artifacts
# ---------------------------------------------------------------------------

class ArtifactBase(BaseModel):
    """Common fields required in every TraderMonty artifact."""

    schema_version: str = Field(default="1.0")
    artifact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    artifact_type: str = Field(..., description="Canonical artifact type identifier")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    skill_id: str = Field(..., description="ID of the skill that produced this artifact")
    workflow_id: Optional[str] = Field(
        None, description="Workflow run ID if produced within a workflow"
    )
    workflow_run_id: Optional[str] = Field(None)
    symbols: list[str] = Field(default_factory=list, description="Tickers/assets covered")
    data_sources_used: list[str] = Field(
        default_factory=list,
        description="APIs, CSVs, or other sources consumed",
    )
    data_gaps: list[DataGap] = Field(
        default_factory=list,
        description="All detected data gaps; empty list = no gaps detected",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Explicit assumptions made due to missing or inferred data",
    )
    confidence: Optional[str] = Field(
        None,
        description="HIGH / MEDIUM / LOW — reflects data completeness and signal quality",
    )
    manual_review_required: bool = Field(
        default=True,
        description="Whether human review is required before acting on this artifact",
    )
    manual_review_status: ManualReviewStatus = Field(
        default=ManualReviewStatus.PENDING,
        description=(
            "Review lifecycle: PENDING → IN_REVIEW → APPROVED / REJECTED. "
            "WAIVED is permitted only for non-trade artifacts (e.g., data quality reports). "
            "Promotion-blocking: outputs with status PENDING or IN_REVIEW must not be acted upon."
        ),
    )
    reviewer: Optional[str] = Field(
        None,
        description="Name or identifier of the human reviewer who completed or waived the review",
    )
    reviewed_at: Optional[str] = Field(
        None,
        description="ISO-8601 timestamp when the review was completed or waived",
    )
    review_notes: Optional[str] = Field(
        None,
        description="Reviewer's notes, decision rationale, or conditions attached to the approval",
    )
    reviewer_role: Optional[ReviewerRole] = Field(
        None,
        description="Role of the reviewer who completed or waived the review",
    )
    author_id: Optional[str] = Field(
        None,
        description="ID of the artifact author; used to prevent self-review",
    )
    dual_review_required: bool = Field(
        default=False,
        description="Whether a second independent reviewer is required",
    )
    secondary_reviewer: Optional[str] = Field(None)
    secondary_reviewer_role: Optional[ReviewerRole] = Field(None)
    secondary_reviewed_at: Optional[str] = Field(None)
    secondary_review_notes: Optional[str] = Field(None)
    next_actions: list[str] = Field(
        default_factory=list,
        description="Suggested next steps for the user",
    )
    disclaimer: Disclaimer = Field(default_factory=Disclaimer)

    @property
    def is_review_complete(self) -> bool:
        """True when human review has been explicitly APPROVED or WAIVED.

        An artifact is NOT promotion-ready unless this returns True.
        PENDING and IN_REVIEW both block promotion.
        REJECTED blocks promotion — rework and re-review required.
        """
        return self.manual_review_status in (
            ManualReviewStatus.APPROVED,
            ManualReviewStatus.WAIVED,
        )

    @model_validator(mode="after")
    def _set_artifact_type_on_subclass(self) -> "ArtifactBase":
        # Subclasses that define ARTIFACT_TYPE auto-populate artifact_type
        if hasattr(self.__class__, "ARTIFACT_TYPE") and not self.artifact_type:
            object.__setattr__(self, "artifact_type", self.__class__.ARTIFACT_TYPE)
        return self

    @model_validator(mode="after")
    def _enforce_critical_gap_confidence(self) -> "ArtifactBase":
        """CRITICAL data gaps must not be paired with HIGH or MEDIUM confidence.

        A CRITICAL gap means the skill explicitly declared it cannot produce useful
        output (can_continue=False).  Marking such an artifact HIGH or MEDIUM confidence
        is a contradiction that could lead to overconfident downstream decisions.

        Valid combinations:
          - CRITICAL gap  + confidence=None   → allowed (signal absent / unknown)
          - CRITICAL gap  + confidence="LOW"  → allowed (explicitly degraded)
          - CRITICAL gap  + confidence="HIGH" → FORBIDDEN (model_validator error)
          - CRITICAL gap  + confidence="MEDIUM" → FORBIDDEN
        """
        blocking_gaps = [
            g for g in self.data_gaps
            if g.severity == Severity.CRITICAL and not g.can_continue
        ]
        if blocking_gaps and self.confidence in ("HIGH", "MEDIUM"):
            raise ValueError(
                f"Artifact has {len(blocking_gaps)} CRITICAL data gap(s) with "
                f"can_continue=False but confidence='{self.confidence}'. "
                f"CRITICAL blocking gaps require confidence='LOW' or confidence=None. "
                f"Gap: {blocking_gaps[0].description!r}"
            )
        return self

    @model_validator(mode="after")
    def _enforce_no_self_review(self) -> "ArtifactBase":
        """Prevent artifact author from approving their own artifact.

        The author of an artifact must not be its reviewer unless status is WAIVED
        (which requires explicit justification in review_notes) or the reviewer
        is 'unspecified'.
        """
        if (
            self.author_id
            and self.reviewer
            and self.reviewer not in ("unspecified", "")
            and self.author_id == self.reviewer
            and self.manual_review_status == ManualReviewStatus.APPROVED
        ):
            raise ValueError(
                f"Self-review is not permitted: artifact author '{self.author_id}' "
                "cannot approve their own artifact. Use a different reviewer or "
                "set manual_review_status=WAIVED with explicit review_notes justification."
            )
        return self

    @model_validator(mode="after")
    def _enforce_dual_review(self) -> "ArtifactBase":
        """Enforce dual-review constraints when dual_review_required=True.

        When dual_review_required is set:
          1. secondary_reviewer must differ from the primary reviewer.
          2. secondary_reviewer must differ from the author_id.
          3. Waived reviews must have a non-empty review_notes justification.

        These checks fire at schema instantiation — no application code can
        bypass them without bypassing Pydantic validation.
        """
        if not self.dual_review_required:
            return self

        # Waiver must carry a justification
        if (
            self.manual_review_status == ManualReviewStatus.WAIVED
            and not (self.review_notes or "").strip()
        ):
            raise ValueError(
                "dual_review_required artifact has WAIVED status but no review_notes "
                "justification. All waivers must include a documented reason."
            )

        sec = self.secondary_reviewer
        if sec and sec not in ("unspecified", ""):
            # secondary must differ from primary reviewer
            if self.reviewer and self.reviewer not in ("unspecified", "") and sec == self.reviewer:
                raise ValueError(
                    f"Dual review invalid: secondary_reviewer '{sec}' is the same as "
                    f"reviewer '{self.reviewer}'. Two distinct reviewers are required."
                )
            # secondary must differ from author
            if self.author_id and sec == self.author_id:
                raise ValueError(
                    f"Dual review invalid: secondary_reviewer '{sec}' is the artifact "
                    f"author '{self.author_id}'. The author cannot serve as a reviewer."
                )

        return self

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Data quality artifacts
# ---------------------------------------------------------------------------

class DataQualityReport(ArtifactBase):
    """Aggregate data quality assessment for a report or document."""

    ARTIFACT_TYPE: ClassVar[str] = "data_quality_report"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    document_path: Optional[str] = None
    total_issues: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    checks_run: list[str] = Field(default_factory=list)
    passed_checks: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    can_publish: bool = False


# ---------------------------------------------------------------------------
# Market regime artifacts
# ---------------------------------------------------------------------------

class BreadthAssessment(ArtifactBase):
    """Output from market-breadth-analyzer or breadth-chart-analyst."""

    ARTIFACT_TYPE: ClassVar[str] = "breadth_assessment"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    composite_score: Optional[float] = Field(None, ge=0, le=100)
    zone: Optional[HealthZone] = None
    recommended_exposure_pct: Optional[float] = Field(None, ge=0, le=100)
    component_scores: list[ComponentScore] = Field(default_factory=list)
    score_trend: Optional[str] = Field(None, description="IMPROVING / DETERIORATING / STABLE")
    data_date: Optional[str] = None
    data_age_days: Optional[float] = None
    stale_data_threshold_days: int = 5


class UptrendAssessment(ArtifactBase):
    """Output from uptrend-analyzer."""

    ARTIFACT_TYPE: ClassVar[str] = "uptrend_assessment"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    composite_score: Optional[float] = Field(None, ge=0, le=100)
    zone: Optional[HealthZone] = None
    recommended_exposure_pct: Optional[float] = Field(None, ge=0, le=100)
    component_scores: list[ComponentScore] = Field(default_factory=list)
    sector_heatmap: dict[str, Any] = Field(default_factory=dict)
    active_warnings: list[str] = Field(default_factory=list)
    warning_penalty: float = 0.0
    data_date: Optional[str] = None


class MarketTopRiskReport(ArtifactBase):
    """Output from market-top-detector."""

    ARTIFACT_TYPE: ClassVar[str] = "market_top_risk_report"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    composite_score: Optional[float] = Field(None, ge=0, le=100)
    risk_zone: Optional[RiskZone] = None
    distribution_day_count: Optional[int] = None
    component_scores: list[ComponentScore] = Field(default_factory=list)
    correction_probability_pct: Optional[float] = None
    recommended_action: Optional[str] = None


class MacroRegimeReport(ArtifactBase):
    """Output from macro-regime-detector."""

    ARTIFACT_TYPE: ClassVar[str] = "macro_regime_report"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    regime_type: Optional[MarketRegimeType] = None
    regime_confidence: Optional[str] = None
    component_scores: list[ComponentScore] = Field(default_factory=list)
    transition_signals: list[str] = Field(default_factory=list)
    portfolio_posture: Optional[str] = None
    horizon_months: int = 18


class ExposureDecision(ArtifactBase):
    """Output from exposure-coach — the unified market posture decision."""

    ARTIFACT_TYPE: ClassVar[str] = "exposure_decision"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    ceiling_pct: Optional[float] = Field(None, ge=0, le=100)
    recommendation: Optional[ExposureRecommendation] = None
    confidence: Optional[str] = None
    bias: Optional[str] = Field(None, description="GROWTH / VALUE / NEUTRAL")
    participation: Optional[str] = Field(None, description="BROAD / NARROW / MIXED")
    rationale: Optional[str] = None
    component_scores: dict[str, Any] = Field(default_factory=dict)
    inputs_provided: list[str] = Field(default_factory=list)
    inputs_missing: list[str] = Field(default_factory=list)

    manual_review_required: bool = Field(
        default=True,
        description="Always true — exposure decisions require human confirmation",
    )


# ---------------------------------------------------------------------------
# Screening artifacts
# ---------------------------------------------------------------------------

class ScreenCandidate(ArtifactBase):
    """A single candidate from any screening skill."""

    ARTIFACT_TYPE: ClassVar[str] = "screen_candidate"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    ticker: str
    company_name: Optional[str] = None
    setup_type: Optional[SetupType] = None
    composite_score: Optional[float] = Field(None, ge=0, le=100)
    grade: Optional[str] = Field(None, description="A/B/C/D rating")
    execution_state: Optional[str] = None

    # Trade setup fields
    entry_trigger: Optional[str] = None
    invalidation: Optional[str] = None
    pivot_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    reward_risk: Optional[float] = None

    # Risk / sizing fields
    position_size_shares: Optional[int] = None
    risk_dollars: Optional[float] = None
    portfolio_heat_pct: Optional[float] = None

    # Contextual flags
    earnings_date: Optional[str] = None
    earnings_risk: Optional[str] = Field(None, description="NONE / LOW / MEDIUM / HIGH")
    regime_permission: Optional[str] = Field(
        None, description="ALLOWED / RESTRICTED / BLOCKED"
    )
    chart_review_status: Optional[str] = Field(
        None, description="PENDING / PASS / FAIL"
    )
    liquidity_adequate: Optional[bool] = None

    # Rejection
    rejected: bool = False
    rejection_reason: Optional[str] = None

    manual_review_required: bool = Field(
        default=True,
        description="Screener output is a watchlist candidate, not a signal",
    )


class TechnicalValidation(ArtifactBase):
    """Output from technical-analyst validating a candidate's chart setup."""

    ARTIFACT_TYPE: ClassVar[str] = "technical_validation"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    ticker: str
    timeframe: Optional[str] = Field(None, description="weekly / daily / intraday")
    setup_quality: Optional[str] = Field(None, description="TEXTBOOK / ACCEPTABLE / WEAK / FAIL")
    stage: Optional[str] = Field(None, description="Stage 1 / 2 / 3 / 4")
    base_type: Optional[str] = None
    key_levels: dict[str, float] = Field(default_factory=dict)
    scenario_bull: Optional[str] = None
    scenario_base: Optional[str] = None
    scenario_bear: Optional[str] = None
    chart_image_provided: bool = False
    manual_review_done: bool = False

    manual_review_required: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Trade planning artifacts
# ---------------------------------------------------------------------------

class PositionSizingPlan(ArtifactBase):
    """Output from position-sizer."""

    ARTIFACT_TYPE: ClassVar[str] = "position_sizing_plan"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    ticker: str
    method: str = Field(..., description="STOP_LOSS / ATR / KELLY")
    account_size: Optional[float] = None
    risk_pct: Optional[float] = None
    risk_dollars: Optional[float] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    atr: Optional[float] = None
    shares: Optional[int] = None
    position_value: Optional[float] = None
    portfolio_heat_pct: Optional[float] = None
    max_position_pct: Optional[float] = None
    sector: Optional[str] = None
    current_sector_exposure_pct: Optional[float] = None
    portfolio_constraints_met: Optional[bool] = None

    manual_review_required: bool = Field(default=True)


class TradePlan(ArtifactBase):
    """
    A complete, actionable trade plan for a single candidate.

    This is the terminal output of the trade-planning pipeline.
    It must not contain "buy now" language — it is a decision-support plan
    requiring manual human review and approval before any broker action.
    """

    ARTIFACT_TYPE: ClassVar[str] = "trade_plan"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    ticker: str
    company_name: Optional[str] = None
    setup_type: Optional[SetupType] = None
    plan_date: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).date().isoformat()
    )

    # Entry specification
    entry_trigger: str = Field(..., description="Specific condition required to enter")
    entry_price_target: Optional[float] = None
    order_type: Optional[str] = Field(None, description="STOP_LIMIT / LIMIT / MARKET_ON_OPEN")

    # Risk plan
    stop_price: float = Field(..., description="Hard stop loss price")
    target_price: Optional[float] = None
    reward_risk: Optional[float] = None
    invalidation: str = Field(
        ..., description="Condition that cancels the plan before entry"
    )

    # Position sizing
    shares: Optional[int] = None
    risk_dollars: Optional[float] = None
    portfolio_heat_pct: Optional[float] = None
    account_size: Optional[float] = None

    # Context gates
    earnings_date: Optional[str] = None
    earnings_risk: Optional[str] = None
    regime_permission: Optional[str] = None
    market_breadth_score: Optional[float] = None
    exposure_decision_id: Optional[str] = Field(
        None, description="artifact_id of the ExposureDecision that gated this plan"
    )

    # Manual review
    chart_review_status: str = Field(
        default="PENDING",
        description="PENDING / PASS / FAIL — must be PASS before acting",
    )
    manual_review_required: bool = Field(
        default=True,
        description=(
            "ALWAYS TRUE — this is a plan, not an execution instruction. "
            "All orders must be placed manually at the broker."
        ),
    )

    # Alpaca order template (optional, for reference only)
    alpaca_order_template: Optional[dict[str, Any]] = Field(
        None,
        description="Order template for manual entry at Alpaca — not auto-executed",
    )


# ---------------------------------------------------------------------------
# Trade memory artifacts
# ---------------------------------------------------------------------------

class TradeThesis(ArtifactBase):
    """A single trade or investment thesis tracked through its lifecycle."""

    ARTIFACT_TYPE: ClassVar[str] = "trade_thesis"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    thesis_id: str = Field(default_factory=lambda: f"th_{str(uuid.uuid4())[:8]}")
    ticker: str
    lifecycle_state: ThesisLifecycle = ThesisLifecycle.IDEA
    source_skill: Optional[str] = None

    # Thesis content
    setup_type: Optional[SetupType] = None
    thesis_summary: Optional[str] = None
    market_regime_at_entry: Optional[str] = None
    exposure_decision_id: Optional[str] = None

    # Plan
    entry_plan: Optional[str] = None
    entry_price_planned: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    reward_risk: Optional[float] = None
    shares_planned: Optional[int] = None
    risk_dollars_planned: Optional[float] = None

    # Actual execution (filled after entry)
    entry_price_actual: Optional[float] = None
    entry_date: Optional[str] = None
    shares_actual: Optional[int] = None

    # Exit (filled after close)
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    pnl_dollars: Optional[float] = None
    pnl_pct: Optional[float] = None
    mae_pct: Optional[float] = Field(None, description="Maximum Adverse Excursion %")
    mfe_pct: Optional[float] = Field(None, description="Maximum Favorable Excursion %")

    # Behavioral notes
    emotions_at_entry: Optional[str] = None
    rule_deviations: list[str] = Field(default_factory=list)
    exit_reason: Optional[str] = None

    # Review
    linked_report_paths: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)

    manual_review_required: bool = Field(default=True)


class JournalEntry(ArtifactBase):
    """A single journal session entry, typically produced at end of workflow run."""

    ARTIFACT_TYPE: ClassVar[str] = "journal_entry"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    entry_date: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).date().isoformat()
    )
    workflow_id: Optional[str] = None
    thesis_ids: list[str] = Field(default_factory=list)
    market_regime_summary: Optional[str] = None
    exposure_decision_summary: Optional[str] = None
    candidates_reviewed: int = 0
    candidates_passed: int = 0
    trades_entered: int = 0
    trades_exited: int = 0
    process_notes: Optional[str] = None
    emotion_notes: Optional[str] = None
    rule_deviations: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    rule_changes_proposed: list[str] = Field(default_factory=list)


class PostmortemReport(ArtifactBase):
    """
    Postmortem for a closed trade.

    Classifies outcome using the 2×2 process/outcome matrix:
      - Good process / Good outcome  → reinforce process
      - Good process / Bad outcome   → accept randomness; check market regime
      - Bad process / Good outcome   → do NOT reinforce; correct process
      - Bad process / Bad outcome    → fix process first
    """

    ARTIFACT_TYPE: ClassVar[str] = "postmortem_report"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    thesis_id: str
    ticker: str
    process_quality: Optional[ProcessQuality] = None
    outcome_quality: Optional[OutcomeQuality] = None
    classification: Optional[str] = Field(
        None,
        description=(
            "GOOD_PROCESS_GOOD_OUTCOME / GOOD_PROCESS_BAD_OUTCOME / "
            "BAD_PROCESS_GOOD_OUTCOME / BAD_PROCESS_BAD_OUTCOME"
        ),
    )
    root_cause: Optional[str] = None
    thesis_quality_issues: list[str] = Field(default_factory=list)
    execution_issues: list[str] = Field(default_factory=list)
    market_environment_factors: list[str] = Field(default_factory=list)
    randomness_factors: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    rule_changes_proposed: list[str] = Field(default_factory=list)
    pnl_dollars: Optional[float] = None
    pnl_pct: Optional[float] = None
    mae_pct: Optional[float] = None
    mfe_pct: Optional[float] = None

    manual_review_required: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Strategy research artifacts
# ---------------------------------------------------------------------------

class BacktestSpec(ArtifactBase):
    """
    Specification for a backtest — filled BEFORE running the backtest.

    All fields in the 'Research Quality Checklist' section are required before
    a backtest result can be considered valid.
    """

    ARTIFACT_TYPE: ClassVar[str] = "backtest_spec"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    strategy_name: str
    strategy_description: Optional[str] = None
    universe: str = Field(..., description="e.g. 'S&P 500' / 'NASDAQ 100' / custom list")
    in_sample_start: Optional[str] = None
    in_sample_end: Optional[str] = None
    out_of_sample_start: Optional[str] = None
    out_of_sample_end: Optional[str] = None

    # Cost assumptions (REQUIRED — cannot be None in a valid spec)
    transaction_cost_bps: Optional[float] = Field(
        None, description="Round-trip transaction cost in basis points (required)"
    )
    slippage_bps: Optional[float] = Field(
        None, description="Slippage assumption in basis points (required)"
    )
    min_avg_volume_shares: Optional[int] = Field(
        None, description="Minimum average daily volume liquidity filter"
    )

    # Research quality checklist
    no_lookahead_confirmed: bool = Field(
        default=False,
        description=(
            "Confirmed that all signals use only data available at signal time. "
            "Must be True before a backtest is considered valid."
        ),
    )
    survivorship_bias_acknowledged: bool = Field(
        default=False,
        description=(
            "Confirmed awareness that universe may exclude delisted stocks. "
            "Must be True before a backtest is considered valid."
        ),
    )
    min_trades_required: int = Field(
        default=30,
        description="Minimum number of trades required for statistical significance",
    )
    walk_forward_planned: bool = False
    regime_segmentation_planned: bool = False
    parameter_stability_planned: bool = False

    paper_only_until_validated: bool = Field(
        default=True,
        description=(
            "ALWAYS TRUE until out-of-sample test passes. "
            "Strategy must not be used live before out-of-sample validation."
        ),
    )


class BacktestReport(ArtifactBase):
    """
    Results of a completed backtest.

    A BacktestReport is ONLY valid if the accompanying BacktestSpec has:
      - no_lookahead_confirmed = True
      - survivorship_bias_acknowledged = True
      - transaction_cost_bps is not None
      - slippage_bps is not None
      - out_of_sample_start is not None
    """

    ARTIFACT_TYPE: ClassVar[str] = "backtest_report"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    spec_artifact_id: Optional[str] = Field(
        None, description="artifact_id of the BacktestSpec used"
    )
    strategy_name: str

    # Performance metrics
    total_trades: Optional[int] = None
    win_rate_pct: Optional[float] = None
    avg_win_pct: Optional[float] = None
    avg_loss_pct: Optional[float] = None
    profit_factor: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    cagr_pct: Optional[float] = None

    # In-sample vs out-of-sample
    in_sample_metrics: dict[str, Any] = Field(default_factory=dict)
    out_of_sample_metrics: dict[str, Any] = Field(default_factory=dict)
    out_of_sample_degradation_pct: Optional[float] = Field(
        None, description="% degradation from in-sample to out-of-sample (positive = degraded)"
    )

    # Regime breakdown
    regime_breakdown: dict[str, Any] = Field(default_factory=dict)

    # Quality flags
    overfitting_warnings: list[str] = Field(default_factory=list)
    false_discovery_risk: Optional[str] = Field(
        None, description="LOW / MEDIUM / HIGH — how many configs were tested"
    )
    validation_status: str = Field(
        default="UNVALIDATED",
        description="UNVALIDATED / IN_SAMPLE_ONLY / OUT_OF_SAMPLE_PASSED / OUT_OF_SAMPLE_FAILED",
    )
    paper_trade_required: bool = Field(
        default=True,
        description="Paper trade required before live use",
    )

    manual_review_required: bool = Field(default=True)

    @model_validator(mode="after")
    def _enforce_spec_linkage_for_validated_reports(self) -> "BacktestReport":
        """A BacktestReport that claims validated status MUST reference its BacktestSpec.

        Without a spec_artifact_id, there is no way to verify that the backtest
        was run with no-lookahead confirmed, defined cost assumptions, or an
        out-of-sample period — all of which are preconditions for any status other
        than UNVALIDATED.
        """
        _requires_spec = {"IN_SAMPLE_ONLY", "OUT_OF_SAMPLE_PASSED", "OUT_OF_SAMPLE_FAILED"}
        if self.validation_status in _requires_spec and not self.spec_artifact_id:
            raise ValueError(
                f"BacktestReport.validation_status='{self.validation_status}' requires "
                f"spec_artifact_id to be set. A validated backtest must reference its "
                f"BacktestSpec so that no_lookahead_confirmed and cost assumptions can "
                f"be audited."
            )
        return self


class StrategyReview(ArtifactBase):
    """Output from edge-strategy-reviewer."""

    ARTIFACT_TYPE: ClassVar[str] = "strategy_review"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    draft_id: Optional[str] = None
    strategy_name: Optional[str] = None
    verdict: Optional[str] = Field(None, description="PASS / REVISE / REJECT")

    # Scoring categories
    completeness_score: Optional[float] = Field(None, ge=0, le=100)
    evidence_quality_score: Optional[float] = Field(None, ge=0, le=100)
    risk_controls_score: Optional[float] = Field(None, ge=0, le=100)
    operationality_score: Optional[float] = Field(None, ge=0, le=100)
    testability_score: Optional[float] = Field(None, ge=0, le=100)
    research_quality_score: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description=(
            "Checks: no-lookahead confirmed, out-of-sample plan, "
            "survivorship bias acknowledged, min sample size defined"
        ),
    )
    composite_score: Optional[float] = Field(None, ge=0, le=100)

    overfitting_flags: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)

    manual_review_required: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Portfolio artifacts
# ---------------------------------------------------------------------------

class AllocationEntry(BaseModel):
    label: str
    value_dollars: Optional[float] = None
    pct_of_portfolio: Optional[float] = None


class PortfolioReview(ArtifactBase):
    """Output from portfolio-manager or core-portfolio-weekly workflow."""

    ARTIFACT_TYPE: ClassVar[str] = "portfolio_review"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    review_date: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).date().isoformat()
    )
    total_value_dollars: Optional[float] = None
    cash_pct: Optional[float] = None

    # Concentration checks
    allocation_by_asset_class: list[AllocationEntry] = Field(default_factory=list)
    allocation_by_sector: list[AllocationEntry] = Field(default_factory=list)
    largest_single_position_pct: Optional[float] = None
    largest_single_position_ticker: Optional[str] = None
    currency_exposure: dict[str, float] = Field(default_factory=dict)

    # Risk flags
    sector_over_target: list[str] = Field(default_factory=list)
    single_name_over_target: list[str] = Field(default_factory=list)
    dividend_risk_flags: list[str] = Field(default_factory=list)

    # Actions
    rebalance_candidates: list[str] = Field(default_factory=list)
    do_nothing_rationale: Optional[str] = Field(
        None,
        description=(
            "If no rebalancing is warranted, explain why. "
            "Do-nothing is always a valid option."
        ),
    )

    # Disclaimer
    tax_disclaimer: str = Field(
        default=(
            "Tax implications noted herein are informational only and do not "
            "constitute tax advice. Consult a qualified tax professional."
        )
    )
    not_financial_advice: str = Field(
        default=(
            "This review is for informational and decision-support purposes only. "
            "It is NOT financial advice. All investment decisions remain the user's responsibility."
        )
    )
    manual_review_required: bool = Field(default=True)


class DividendReview(ArtifactBase):
    """Output from kanchi-dividend-review-monitor."""

    ARTIFACT_TYPE: ClassVar[str] = "dividend_review"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    ticker: str
    company_name: Optional[str] = None
    anomaly_flags: list[str] = Field(default_factory=list)
    t1_dividend_cut_risk: Optional[str] = None
    t2_payout_sustainability: Optional[str] = None
    t3_earnings_trend: Optional[str] = None
    t4_balance_sheet_risk: Optional[str] = None
    t5_sector_regime: Optional[str] = None
    review_queue_status: Optional[str] = Field(
        None, description="OK / MONITOR / REVIEW / URGENT"
    )
    additional_buy_deferred: bool = Field(
        default=False,
        description="True if T1-T5 anomalies prevent additional buys",
    )
    manual_review_required: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Scenario / macro artifacts
# ---------------------------------------------------------------------------

class ScenarioEntry(BaseModel):
    name: str = Field(..., description="Base / Bull / Bear")
    probability_pct: Optional[float] = None
    description: Optional[str] = None
    key_driver: Optional[str] = None
    sector_impacts: list[str] = Field(default_factory=list)
    stock_impacts: list[str] = Field(default_factory=list)


class ScenarioAnalysis(ArtifactBase):
    """Output from scenario-analyzer."""

    ARTIFACT_TYPE: ClassVar[str] = "scenario_analysis"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    headline: str
    horizon_months: int = 18
    scenarios: list[ScenarioEntry] = Field(default_factory=list)
    primary_sector_impacts: dict[str, str] = Field(default_factory=dict)
    secondary_sector_impacts: dict[str, str] = Field(default_factory=dict)
    tertiary_sector_impacts: dict[str, str] = Field(default_factory=dict)
    positive_stock_candidates: list[str] = Field(default_factory=list)
    negative_stock_candidates: list[str] = Field(default_factory=list)
    second_opinion_summary: Optional[str] = None
    analysis_language: str = Field(default="ja")

    manual_review_required: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Workflow run artifact
# ---------------------------------------------------------------------------

class WorkflowStepRecord(BaseModel):
    step_number: int
    name: str
    skill_id: str
    status: str = Field(default="PENDING", description="PENDING / RUNNING / DONE / SKIPPED / FAILED")
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    artifact_ids_produced: list[str] = Field(default_factory=list)
    input_artifact_ids: list[str] = Field(
        default_factory=list,
        description="artifact_ids consumed as inputs by this step",
    )
    output_artifact_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="SHA-256 hashes of artifacts produced by this step: {artifact_id: sha256}",
    )
    decision_gate_question: Optional[str] = None
    decision_gate_answer: Optional[str] = None
    notes: Optional[str] = None


class WorkflowRun(ArtifactBase):
    """
    Record of a single workflow execution session.

    Saved to state/workflow-runs/<run_id>.json by the workflow runner.
    Never contains trade execution instructions.
    """

    ARTIFACT_TYPE: ClassVar[str] = "workflow_run"
    artifact_type: str = Field(default=ARTIFACT_TYPE)

    workflow_id: str
    workflow_display_name: Optional[str] = None
    workflow_version: Optional[str] = Field(
        None,
        description="Manifest version of the workflow at run-start time (from manifest 'version' field)",
    )
    run_id: str = Field(default_factory=lambda: f"run_{str(uuid.uuid4())[:12]}")
    run_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 UTC timestamp when the run was created (alias for started_at; "
                    "always populated for reproducibility audit trails)",
    )
    operator: Optional[str] = Field(
        None,
        description="Name or identifier of the operator who started the run",
    )
    status: WorkflowStatus = WorkflowStatus.STARTED
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: Optional[str] = None
    estimated_minutes: Optional[int] = None

    # --- Provenance / reproducibility fields (Phase 7) ---
    skill_versions: dict[str, str] = Field(
        default_factory=dict,
        description="Snapshot of skill versions at run-start time: {skill_id: version}",
    )
    artifact_schema_versions: dict[str, str] = Field(
        default_factory=dict,
        description="Snapshot of artifact schema versions at run-start time: "
                    "{artifact_type: schema_version}",
    )
    input_artifact_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="SHA-256 hashes of key input artifacts: {artifact_id: sha256}",
    )
    output_artifact_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="SHA-256 hashes of key output artifacts: {artifact_id: sha256}",
    )

    steps: list[WorkflowStepRecord] = Field(default_factory=list)
    artifact_ids: list[str] = Field(
        default_factory=list,
        description="artifact_ids of all artifacts produced during this run",
    )
    decision_gate_log: list[dict[str, str]] = Field(
        default_factory=list,
        description="Log of all decision gate answers",
    )
    manual_review_items_completed: list[str] = Field(default_factory=list)
    journal_entry_id: Optional[str] = None
    abort_reason: Optional[str] = None

    manual_review_required: bool = Field(
        default=True,
        description="Workflow runs require human review at each decision gate",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Enums
    "Severity",
    "ExposureRecommendation",
    "MarketRegimeType",
    "HealthZone",
    "RiskZone",
    "SetupType",
    "ThesisLifecycle",
    "ProcessQuality",
    "OutcomeQuality",
    "WorkflowStatus",
    "ManualReviewStatus",
    "ReviewerRole",
    # Sub-models
    "DataGap",
    "Disclaimer",
    "ComponentScore",
    "AllocationEntry",
    "ScenarioEntry",
    "WorkflowStepRecord",
    # Artifacts
    "ArtifactBase",
    "DataQualityReport",
    "BreadthAssessment",
    "UptrendAssessment",
    "MarketTopRiskReport",
    "MacroRegimeReport",
    "ExposureDecision",
    "ScreenCandidate",
    "TechnicalValidation",
    "PositionSizingPlan",
    "TradePlan",
    "TradeThesis",
    "JournalEntry",
    "PostmortemReport",
    "BacktestSpec",
    "BacktestReport",
    "StrategyReview",
    "PortfolioReview",
    "DividendReview",
    "ScenarioAnalysis",
    "WorkflowRun",
    # Constants
    "DISCLAIMER_TEXT",
]
