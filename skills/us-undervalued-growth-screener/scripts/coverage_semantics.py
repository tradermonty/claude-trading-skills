"""Single source of truth for ranking-scope and coverage semantics.

Discovery (``run_pipeline``) and final evaluation (``evaluate_candidates``)
previously implemented the tri-state ranking scope twice, with subtly
different field access. Both now call into this module so the semantics
cannot drift when new acquisition modes (e.g. the v3.7 ``sharded_snapshot``)
are added.

The contract (rounds 6-8 of external review):

- ``final_marketwide``: estimate acquisition was attempted for EVERY
  listing-universe symbol (exact counts), the economic-scope completeness
  verdict agrees, and no enrichment queue is unresolved. Only then may an
  output be read as a market-wide ranking.
- ``final_scoped``: a bounded, explicitly audited subset was fully
  processed; conclusions bind only to that subset, never to the market.
- ``diagnostic``: fail-closed bucket — an unresolved queue, an empty
  universe, a missing/zero attempted count, or an attempted count that
  exceeds the universe (a configured LIMIT is not an attempt count).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

RANKING_SCOPES = ("final_marketwide", "final_scoped", "diagnostic")

_COVERAGE_COUNT_FIELDS = (
    "listing_universe_count",
    "economic_attempt_count",
    "economically_evaluable_count",
    "quality_probe_count",
    "deep_dive_count",
)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def classify_ranking_scope(
    *,
    economic_attempt_count: int,
    listing_universe_count: int,
    economic_scope_complete: bool,
    unresolved_queue_count: int,
) -> str:
    """Classify how far a run's conclusion may be generalized.

    Listing enumeration completeness never makes a market-wide ranking:
    only attempting economic (estimate) acquisition for EVERY listed symbol
    does. Empty or impossible work fails closed to ``diagnostic``.
    """
    if unresolved_queue_count > 0:
        return "diagnostic"
    if (
        listing_universe_count <= 0
        or economic_attempt_count <= 0
        or economic_attempt_count > listing_universe_count
    ):
        return "diagnostic"
    if economic_scope_complete and economic_attempt_count >= listing_universe_count:
        return "final_marketwide"
    return "final_scoped"


def build_coverage_block(
    *,
    ranking_scope: str,
    listing_universe_count: int,
    economic_attempt_count: int,
    economically_evaluable_count: int,
    quality_probe_count: int,
    deep_dive_count: int,
) -> dict[str, Any]:
    """Assemble the canonical per-stage coverage block (counts + percentages)."""

    def _pct(count: int) -> float:
        if listing_universe_count <= 0:
            return 0.0
        return round(count / listing_universe_count * 100.0, 6)

    return {
        "ranking_scope": ranking_scope,
        "listing_universe_count": listing_universe_count,
        "economic_attempt_count": economic_attempt_count,
        "economic_attempt_coverage_pct": _pct(economic_attempt_count),
        "economically_evaluable_count": economically_evaluable_count,
        "economically_evaluable_coverage_pct": _pct(economically_evaluable_count),
        "quality_probe_count": quality_probe_count,
        "quality_probe_coverage_pct": _pct(quality_probe_count),
        "deep_dive_count": deep_dive_count,
        "deep_dive_coverage_pct": _pct(deep_dive_count),
    }


def validate_coverage_block(block: Mapping[str, Any]) -> list[str]:
    """Return human-readable problems with a coverage block (empty = valid)."""
    problems: list[str] = []
    scope = block.get("ranking_scope")
    if scope not in RANKING_SCOPES:
        problems.append(f"ranking_scope {scope!r} is not one of {RANKING_SCOPES}")
    counts: dict[str, int] = {}
    for field in _COVERAGE_COUNT_FIELDS:
        value = _as_int(block.get(field))
        if value is None or value < 0:
            problems.append(f"{field} is missing or not a non-negative integer")
        else:
            counts[field] = value
    universe = counts.get("listing_universe_count")
    if universe is not None:
        for field in _COVERAGE_COUNT_FIELDS[1:]:
            value = counts.get(field)
            if value is not None and value > universe:
                problems.append(f"{field} ({value}) exceeds listing_universe_count ({universe})")
    attempted = counts.get("economic_attempt_count")
    evaluable = counts.get("economically_evaluable_count")
    if attempted is not None and evaluable is not None and evaluable > attempted:
        problems.append(
            f"economically_evaluable_count ({evaluable}) exceeds "
            f"economic_attempt_count ({attempted})"
        )
    return problems


def derive_ranking_scope_from_audit(
    audit: Mapping[str, Any], *, deep_dive_count: int
) -> dict[str, Any]:
    """Derive the coverage block from a run's screening audit.

    Copies discovery's ACTUAL ``economic_attempt_count`` — never the
    configured seed LIMIT, which can exceed a narrow universe and fabricate
    >100% coverage. Missing or impossible counts fail closed to
    ``diagnostic``.
    """
    audit = _as_mapping(audit)
    universe_total = _as_int(_as_mapping(audit.get("universe")).get("row_count")) or 0
    generation = _as_mapping(_as_mapping(audit.get("candidate_pool")).get("generation_audit"))
    bulk = _as_mapping(generation.get("bulk_estimate_audit"))
    covered = _as_int(bulk.get("covered_symbol_count")) or 0
    mode = str(generation.get("estimate_acquisition_mode") or "")
    if mode == "analyst_estimates_bulk" and covered:
        attempted: int | None = covered
    else:
        attempted = _as_int(generation.get("economic_attempt_count"))
    evaluable = _as_int(generation.get("economically_evaluable_count")) or 0
    probe_raw = _as_mapping(generation.get("quality_probe")).get("attempted")
    if isinstance(probe_raw, list):
        probe_count = len(probe_raw)
    else:
        probe_count = _as_int(probe_raw) or 0
    queue_count = _as_int(_as_mapping(audit.get("enrichment")).get("unresolved_count")) or 0

    snapshot_verification = _as_mapping(generation.get("snapshot_verification"))
    snapshot_digest = snapshot_verification.get("snapshot_verification_digest")
    verified_sharded_snapshot = bool(
        mode == "sharded_snapshot"
        and snapshot_verification.get("ready_for_screening") is True
        and isinstance(snapshot_digest, str)
        and len(snapshot_digest) == 64
        and snapshot_verification.get("classification_matches_universe") is True
        and _as_int(snapshot_verification.get("classified_total")) == universe_total
        and attempted == universe_total
    )

    if (
        queue_count > 0
        or universe_total <= 0
        or attempted is None
        or attempted <= 0
        or attempted > universe_total
        or (mode == "sharded_snapshot" and not verified_sharded_snapshot)
    ):
        scope = "diagnostic"
    elif (mode == "analyst_estimates_bulk" and covered >= universe_total) or (
        mode == "sharded_snapshot" and verified_sharded_snapshot
    ):
        scope = "final_marketwide"
    else:
        scope = "final_scoped"

    return build_coverage_block(
        ranking_scope=scope,
        listing_universe_count=universe_total,
        economic_attempt_count=attempted or 0,
        economically_evaluable_count=evaluable,
        quality_probe_count=probe_count,
        deep_dive_count=deep_dive_count,
    )
