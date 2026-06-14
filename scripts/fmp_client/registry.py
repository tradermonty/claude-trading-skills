"""Single source of truth for the vendored ``fmp_client.py`` generator (Issue #115).

Each row declares which optional features a skill's emitted client includes. The
generator (``scripts/generate_fmp_client.py``) renders
``scripts/fmp_client/core_template.py.tmpl`` plus the listed extension blocks into
``skills/<skill>/scripts/fmp_client.py`` and copies
``scripts/fmp_client/compat_v3_to_stable.py.tmpl`` verbatim to
``skills/<skill>/scripts/_fmp_compat.py``.

The canonical core is the evolved vcp-screener client (``_last_error`` /
``_warn_fallback`` / ``shape_issue`` diagnostics). Family A's quote surface and
family B's API-budget surface are toggled by the ``has_quote`` / ``budget`` flags
so a single core serves both families.
"""

from __future__ import annotations

from dataclasses import dataclass

# Module-docstring "Features:" lines shared by every family-B client.
_FAMILY_B_FEATURES = (
    "- API call budget enforcement",
    "- Batch company profile support",
    "- Earnings calendar and historical price fetching",
)


@dataclass(frozen=True)
class SkillConfig:
    """Per-skill knobs that drive the generated ``fmp_client.py``."""

    skill: str  # skill directory name under skills/
    title: str  # module-docstring title line
    family: str  # "A" | "B"
    has_quote: bool  # family A: quote endpoint + get_quote/get_batch_quotes
    budget: bool  # family B: ApiCallBudgetExceeded + max_api_calls=200
    hist_days: int  # get_historical_prices default `days`
    hist_return_list: bool  # earnings: unwrap to list[dict] (else dict)
    has_compat: bool  # vendor _fmp_compat.py and import v3_to_stable
    feature_lines: tuple[str, ...]  # extra "- ..." module-docstring feature bullets
    class_constants: tuple[tuple[str, str], ...]  # (name, literal) class attributes
    extensions: tuple[str, ...]  # extension module names appended to the FMPClient body


# PR1a scope: family B only. Family A rows land in PR1b (same generator).
SKILLS: dict[str, SkillConfig] = {
    "pead-screener": SkillConfig(
        skill="pead-screener",
        title="FMP API Client for PEAD Screener",
        family="B",
        has_quote=False,
        budget=True,
        hist_days=90,
        hist_return_list=False,
        has_compat=True,
        feature_lines=_FAMILY_B_FEATURES,
        class_constants=(),
        extensions=("family_b_profiles",),
    ),
    "earnings-trade-analyzer": SkillConfig(
        skill="earnings-trade-analyzer",
        title="FMP API Client for Earnings Trade Analyzer",
        family="B",
        has_quote=False,
        budget=True,
        hist_days=250,
        hist_return_list=True,
        has_compat=True,
        feature_lines=_FAMILY_B_FEATURES,
        class_constants=(
            (
                "US_EXCHANGES",
                '["NYSE", "NASDAQ", "AMEX", "NYSEArca", "BATS", "NMS", "NGM", "NCM"]',
            ),
        ),
        extensions=("family_b_profiles",),
    ),
    "ibd-distribution-day-monitor": SkillConfig(
        skill="ibd-distribution-day-monitor",
        title="FMP API Client for IBD Distribution Day Monitor",
        family="B",
        has_quote=False,
        budget=True,
        hist_days=90,
        hist_return_list=False,
        has_compat=True,
        feature_lines=_FAMILY_B_FEATURES,
        class_constants=(),
        extensions=("family_b_profiles",),
    ),
}
