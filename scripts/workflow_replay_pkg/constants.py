"""Repository paths and fixed constants shared across the replay harness."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


DEFAULT_COVERAGE = REPO_ROOT / "examples" / "workflows" / "replay-coverage.yaml"


SPEC_SCHEMA = REPO_ROOT / "examples" / "workflows" / "replay-spec.schema.json"


MANUAL_LESSONS_SCHEMA = REPO_ROOT / "examples" / "workflows" / "manual-lessons.schema.json"


TWENTY_PCT_LESSONS_SCHEMA = REPO_ROOT / "examples" / "workflows" / "twenty-pct-lessons.schema.json"


CORE_PORTFOLIO_SCHEMA = (
    REPO_ROOT / "examples" / "workflows" / "core-portfolio-weekly" / "replay-contract.schema.json"
)


KANCHI_REPLAY_SCHEMA = (
    REPO_ROOT / "examples" / "workflows" / "kanchi-dividend-weekly" / "replay-contract.schema.json"
)


EP_ANALYZE_SCHEMA = (
    REPO_ROOT / "examples" / "workflows" / "stockbee-ep-daily" / "replay-contract.schema.json"
)


MULTI_ASSET_REPLAY_SCHEMA = (
    REPO_ROOT
    / "examples"
    / "workflows"
    / "multi-asset-opportunity-daily"
    / "replay-contract.schema.json"
)


KANCHI_ACTIONABLE_VERDICTS = frozenset({"CLEAN-PASS", "PASS-CAUTION", "CONDITIONAL-PASS"})


KANCHI_FORBIDDEN_REVIEW_TOKENS = frozenset(
    {"sell", "liquidat", "trim", "exit", "reduce", "close", "redeem"}
)


VARIANTS = ("required-only", "full-path")


# Coverage 12/12 leaves no workflow deferred. This frozen baseline prevents a
# newly introduced workflow from being waved through as another deferral.
FROZEN_DEFERRED_WORKFLOWS = frozenset()


MARKET_COMPONENT_CONFIG = {
    "breadth": {
        "input": "market_breadth_components",
        "artifact": "market_breadth_report",
        "skill": "market-breadth-analyzer",
        "components": frozenset(
            {
                "breadth_level_trend",
                "ma_crossover",
                "cycle_position",
                "bearish_signal",
                "historical_percentile",
                "divergence",
            }
        ),
        "warning_flags": frozenset(),
    },
    "uptrend": {
        "input": "market_uptrend_components",
        "artifact": "uptrend_report",
        "skill": "uptrend-analyzer",
        "components": frozenset(
            {
                "market_breadth",
                "sector_participation",
                "sector_rotation",
                "momentum",
                "historical_context",
            }
        ),
        "warning_flags": frozenset({"late_cycle", "high_spread", "divergence"}),
    },
    "top_risk": {
        "input": "market_top_risk_components",
        "artifact": "top_risk_report",
        "skill": "market-top-detector",
        "components": frozenset(
            {
                "distribution_days",
                "leading_stocks",
                "defensive_rotation",
                "breadth_divergence",
                "index_technical",
                "sentiment",
            }
        ),
        "warning_flags": frozenset(),
    },
}


TIMESTAMP_FIELDS = frozenset(
    {"generated_at", "created_at", "updated_at", "last_outcome_update_at", "recorded_at"}
)


SENSITIVE_ENV_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "PROXY")


DIGEST_ALLOWLIST_KEYS = frozenset(
    {
        "setup_fluency_summary",
        "rule_candidates",
        "twenty_pct_cohort_summary",
        "edge_hints_yaml",
        "closed_thesis_record",
        "realized_returns",
        "native_postmortem_record",
        "coach_report",
        "coach_report_sha256",
        "postmortem_findings",
        "backtest_validation",
    }
)


RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
