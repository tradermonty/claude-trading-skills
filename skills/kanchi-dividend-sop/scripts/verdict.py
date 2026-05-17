"""WS-5: actionable verdict tier + provenance synthesis.

Pure, offline. Synthesizes the final tier from the WS-1 Step-1 decision,
the WS-2 payout-safety verdict, the WS-3 event cap and the aggregated
pre-order blockers. Replaces the binary signal with the reviewer-validated
actionable tier so the SOP yields a usable shortlist (Customer Issue-1),
not "always 0 PASS".

Tier (best -> worst): CLEAN-PASS, PASS-CAUTION, CONDITIONAL-PASS,
HOLD-REVIEW, STEP1-RECHECK, FAIL.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from thresholds import VERDICTS  # tuple, authoritative enum

_RANK = {v: i for i, v in enumerate(VERDICTS)}  # 0 = best (CLEAN-PASS)


@dataclass
class FinalVerdict:
    verdict: str
    t1_blocked: bool
    reasons: list[str] = field(default_factory=list)


def synthesize_verdict(
    *,
    step1_verdict: str | None,
    safety_verdict: str | None,
    event_verdict_cap: str | None,
    event_t1_blocked: bool = False,
    pre_order_blockers: list[str] | None = None,
) -> FinalVerdict:
    blockers = pre_order_blockers or []
    reasons: list[str] = []

    # Hard FAILs first (irrecoverable).
    if step1_verdict == "FAIL":
        return FinalVerdict("FAIL", True, ["step1_fail"])
    if safety_verdict == "FAIL":
        return FinalVerdict("FAIL", True, ["payout_safety_fail"])

    # Step-1 data-freshness recheck dominates (cannot assert PASS yet).
    if step1_verdict in ("STEP1-RECHECK", "ASSUMPTION-REQUIRED"):
        return FinalVerdict("STEP1-RECHECK", True, ["step1_recheck"])

    # Event / safety HOLD-REVIEW caps.
    if event_verdict_cap == "HOLD-REVIEW":
        reasons.append("event_cap_hold_review")
        return FinalVerdict("HOLD-REVIEW", True, reasons)
    if safety_verdict == "HOLD-REVIEW":
        reasons.append("payout_safety_hold_review")
        return FinalVerdict("HOLD-REVIEW", True, reasons)

    # Dividend freeze: income cash-cow only if safety is clean & unblocked.
    if step1_verdict == "HOLD-REVIEW":  # WS-1 emits this for freeze
        if safety_verdict == "PASS" and not blockers:
            return FinalVerdict(
                "CONDITIONAL-PASS",
                event_t1_blocked,
                ["dividend_freeze_income_cash_cow"],
            )
        return FinalVerdict("HOLD-REVIEW", True, ["dividend_freeze_unconfirmed_safety"])

    # Step-1 passed on regular yield. Blend safety + blockers.
    if safety_verdict == "CAUTION" or blockers:
        if blockers:
            reasons.append("open_pre_order_blockers")
        if safety_verdict == "CAUTION":
            reasons.append("payout_safety_caution")
        return FinalVerdict("PASS-CAUTION", event_t1_blocked, reasons)

    if safety_verdict in (None, "PASS") and not blockers:
        return FinalVerdict("CLEAN-PASS", event_t1_blocked, ["step1_pass_safety_pass"])

    return FinalVerdict("PASS-CAUTION", event_t1_blocked, ["residual_caution"])


def worst(verdicts: list[str]) -> str:
    """Return the worst (highest-rank) verdict in a list."""
    return max(verdicts, key=lambda v: _RANK.get(v, 0)) if verdicts else "STEP1-RECHECK"


def build_run_context(
    *,
    profile: str | None,
    yield_floor_pct: float | None,
    safety_bias: str | None,
    universe_source: str | None,
    excluded_asset_types: list[str] | None,
) -> dict:
    """Top-level run_context (4th-review #13) so a 3%-run Step-1 result is
    never silently reused inside a 4%-run."""
    return {
        "profile": profile,
        "yield_floor_pct": yield_floor_pct,
        "safety_bias": safety_bias,
        "universe_source": universe_source,
        "excluded_asset_types": excluded_asset_types or [],
    }


def evidence_ref(
    claim: str,
    *,
    source_type: str,
    source_url: str | None = None,
    checked_at: str | None = None,
    raw_value=None,
    normalized_value=None,
    confidence: str = "medium",
) -> dict:
    """One evidence record for the provenance block (4th-review #8)."""
    return {
        "claim": claim,
        "source_type": source_type,
        "source_url": source_url,
        "checked_at": checked_at,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "confidence": confidence,
    }
