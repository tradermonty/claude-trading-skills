"""Data models for IBD Distribution Day Monitor.

All OHLCV history is stored as a list[dict] in most-recent-first order
(history[0] = latest session). pandas is intentionally not used.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DistributionDayRule:
    """IBD-style Distribution Day detection rule."""

    min_decline_pct: float = -0.002
    expiration_sessions: int = 25
    invalidation_gain_pct: float = 0.05
    invalidation_price_source: str = "high"  # "high" | "close"


@dataclass
class RiskThresholds:
    """Configurable thresholds for NORMAL/CAUTION/HIGH/SEVERE classification."""

    caution_d25: int = 3
    high_d25: int = 5
    high_d15: int = 3
    high_d5: int = 2
    severe_d25: int = 6
    severe_d15: int = 4
    severe_ma_d25: int = 5  # SEVERE escalation when market_below_ma is True


@dataclass
class DDRecord:
    """A single Distribution Day record with enrichment fields."""

    date: str
    dd_index: int  # = age_sessions, index in effective_history
    age_sessions: int
    close: float
    pct_change: float
    volume: int
    prev_volume: int
    volume_change_pct: float
    # "previous_full_session" when an early-close session or the session after
    # it used the last full-length session as the volume reference (#892).
    volume_reference: str | None = None
    volume_reference_date: str | None = None
    # Filled by enrich_records:
    high_since: float | None = None
    invalidation_price: float | None = None
    invalidation_date: str | None = None
    invalidation_trigger_price: float | None = None
    invalidation_trigger_source: str | None = None
    expires_in_sessions: int | None = None
    status: str = "active"  # active | expired | invalidated
    removal_reason: str | None = None


@dataclass
class IndexResult:
    """Per-index analysis result."""

    symbol: str
    benchmark_name: str
    is_distribution_day_today: bool
    today: dict
    d5_count: int
    d15_count: int
    d25_count: int
    active_distribution_days: list[dict]
    removed_distribution_days: list[dict]
    risk_level: str
    cluster_state: dict
    trend_filters: dict
    explanation: str
    skipped_sessions: list[dict] = field(default_factory=list)


@dataclass
class PortfolioAction:
    """Recommended exposure action for the configured instrument."""

    instrument: str
    recommended_action: str
    current_exposure_pct: int
    target_exposure_pct: int
    exposure_delta_pct: int
    trailing_stop_pct: int
    alternative_action: str | None = None
    rationale: str = ""
