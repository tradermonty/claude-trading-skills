"""WS-3: forward/recent corporate-action scanner (isolated, deterministic-testable).

Critical-review CR-2: the SOP core is a *deterministic* workflow. WebSearch
is non-deterministic and unavailable in some environments, so the event
layer is ISOLATED behind a small interface:

- The pure logic here (materiality gate, classification, pessimistic cap)
  never calls the network and is fully unit-testable.
- A scanner is INJECTED. `ManualEventScanner` reads a curated JSON events
  file (populated by Claude via WebSearch following SKILL.md Step 4b, with
  the source hierarchy IR > SEC > exchange > wire > portal). CI injects a
  fixture scanner -- real WebSearch is never called in tests.

Closes D3 (MKC-Unilever mega-merger missed: Step 4 was backward-only).

4th-review points folded in:
  #5  result in {FAILED-DEGRADED, SKIPPED, NO_EVENT_FOUND} AND Step-5
      timing TRIGGERED  ->  verdict cap HOLD-REVIEW + T1 BLOCKED
      (not merely a provenance stamp).
  #7  sector-specific materiality + rolling-24m cumulative M&A.
  #11 CLEAN_CONFIRMED (primary source checked) is stronger than
      NO_EVENT_FOUND (search only); the latter is treated pessimistically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from thresholds import (
    MNA_LEVERAGE_DELTA_EBITDA,
    MNA_SHARE_ISSUANCE_PCT,
    MNA_TX_VALUE_PCT_MCAP,
)

# event_scan_result enum (4th-review #11)
CLEAN_CONFIRMED = "CLEAN_CONFIRMED"
NO_EVENT_FOUND = "NO_EVENT_FOUND"
MAJOR_EVENT = "MAJOR_EVENT"
MINOR_EVENT_CAUTION = "MINOR_EVENT_CAUTION"
FAILED_DEGRADED = "FAILED-DEGRADED"
SKIPPED = "SKIPPED"

# Results that, on a TRIGGERED Step-5 name, must pessimistically cap.
_PESSIMISTIC_RESULTS = {FAILED_DEGRADED, SKIPPED, NO_EVENT_FOUND, MAJOR_EVENT}

# The complete valid enum. Anything else (e.g. a typo "FAILED_DEGRADED"
# instead of "FAILED-DEGRADED") is coerced to FAILED_DEGRADED — default-deny,
# never silently clean (6th-review Med1).
_VALID_RESULTS = {
    CLEAN_CONFIRMED,
    NO_EVENT_FOUND,
    MAJOR_EVENT,
    MINOR_EVENT_CAUTION,
    FAILED_DEGRADED,
    SKIPPED,
}


def _coerce_result(value: object) -> str:
    s = str(value).strip()
    return s if s in _VALID_RESULTS else FAILED_DEGRADED


_ROLLING_24M_TX_PCT_MCAP = 0.15


@dataclass
class ScanResult:
    ticker: str
    result: str
    pending_mna: bool = False
    completed_mna_within_4q: bool = False
    spinoff: bool = False
    dividend_policy_change: bool = False
    rating_action: bool = False
    sources: list[str] = field(default_factory=list)
    scanned_at: str | None = None
    reasons: list[str] = field(default_factory=list)


class EventScanner(Protocol):
    def scan(self, ticker: str, as_of: str) -> ScanResult: ...


def is_major_structural_event(deal: dict) -> tuple[bool, list[str]]:
    """Generic + sector-specific + rolling-cumulative materiality (v2.1 R-4, #7).

    `deal` keys (all optional): tx_value, market_cap, share_issuance_pct,
    leverage_delta_ebitda, control_change, listing_change, hq_change,
    structure (merger_of_equals|reverse_morris_trust|spinoff|large_asset_sale),
    policy_change (dividend|rating|leverage), sector, sector_metrics,
    rolling_24m_tx_value.
    """
    reasons: list[str] = []
    mcap = deal.get("market_cap") or 0
    tx = deal.get("tx_value") or 0

    if mcap and tx and tx / mcap > MNA_TX_VALUE_PCT_MCAP:
        reasons.append(f"tx_value_{round(tx / mcap * 100)}pct_mcap")
    if (deal.get("share_issuance_pct") or 0) > MNA_SHARE_ISSUANCE_PCT * 100:
        reasons.append("share_issuance_gt_10pct")
    if (deal.get("leverage_delta_ebitda") or 0) > MNA_LEVERAGE_DELTA_EBITDA:
        reasons.append("leverage_delta_gt_0.5x_ebitda")
    if deal.get("control_change") or deal.get("listing_change") or deal.get("hq_change"):
        reasons.append("control_or_listing_or_hq_change")
    if deal.get("structure") in (
        "merger_of_equals",
        "reverse_morris_trust",
        "spinoff",
        "large_asset_sale",
    ):
        reasons.append(f"structure_{deal['structure']}")
    if deal.get("policy_change") in ("dividend", "rating", "leverage"):
        reasons.append(f"policy_change_{deal['policy_change']}")

    # Sector-specific materiality (#7).
    sm = deal.get("sector_metrics") or {}
    sector = (deal.get("sector") or "").lower()
    if sector in ("bank", "banks", "financial", "financials", "financial services"):
        if (sm.get("acquired_assets_pct") or 0) > 10 or (sm.get("acquired_deposits_pct") or 0) > 10:
            reasons.append("bank_acquired_assets_or_deposits_gt_10pct")
        if sm.get("integration_charge_material"):
            reasons.append("bank_integration_charge_material")
    elif sector in ("utility", "utilities"):
        if (sm.get("acq_or_capex_pct_rate_base") or 0) > 10:
            reasons.append("utility_acq_capex_gt_10pct_rate_base")
        if sm.get("equity_issuance_required"):
            reasons.append("utility_equity_issuance_required")
        if sm.get("regulatory_approval_pending"):
            reasons.append("utility_regulatory_approval_pending")
    elif sector in ("insurer", "insurers", "insurance"):
        if sm.get("affects_statutory_or_reserves_or_combined_ratio"):
            reasons.append("insurer_capital_reserves_combined_ratio_impact")

    # Rolling 24-month cumulative M&A (#7).
    if mcap and (deal.get("rolling_24m_tx_value") or 0) / mcap > _ROLLING_24M_TX_PCT_MCAP:
        reasons.append("rolling_24m_tx_gt_15pct_mcap")

    return (bool(reasons), reasons)


def apply_event_cap(scan: ScanResult, *, step5_triggered: bool) -> dict:
    """Pessimistic cap (user decision + 4th-review #5).

    Returns {verdict_cap, t1_blocked, blockers, reasons}. verdict_cap is None
    when no cap applies (caller keeps the computed verdict).
    """
    blockers: list[str] = []
    reasons: list[str] = []

    # Default-deny: an unknown/typo result is coerced to FAILED-DEGRADED so
    # the pessimistic path runs instead of falling through to clean (Med1).
    result = _coerce_result(scan.result)

    if result == MAJOR_EVENT:
        blockers.append("major_structural_event")
        reasons.extend(scan.reasons or ["major_structural_event"])
        return {
            "verdict_cap": "HOLD-REVIEW",
            "t1_blocked": True,
            "blockers": blockers,
            "reasons": reasons,
        }

    if result in (FAILED_DEGRADED, SKIPPED):
        blockers.append("event_scan_failed_or_skipped")
        reasons.append(f"event_scan_{result}")
    elif result == NO_EVENT_FOUND:
        blockers.append("event_scan_primary_source_unconfirmed")
        reasons.append("no_event_found_primary_source_unchecked")
    elif result == MINOR_EVENT_CAUTION:
        return {
            "verdict_cap": None,
            "t1_blocked": False,
            "blockers": [],
            "reasons": ["minor_bolt_on_event_caution_note"],
        }
    else:  # exactly CLEAN_CONFIRMED (unknowns were coerced away above)
        return {"verdict_cap": None, "t1_blocked": False, "blockers": [], "reasons": []}

    # Weak/failed scans only HARD-cap when the name is actually entry-ready.
    if step5_triggered:
        return {
            "verdict_cap": "HOLD-REVIEW",
            "t1_blocked": True,
            "blockers": blockers,
            "reasons": reasons + ["pessimistic_cap_triggered_name"],
        }
    return {
        "verdict_cap": None,
        "t1_blocked": True,
        "blockers": blockers,
        "reasons": reasons,
    }


class ManualEventScanner:
    """Reads a curated events JSON: {ticker: {result, ...ScanResult fields}}.

    Populated by Claude per SKILL.md Step 4b (WebSearch + IR/SEC primary
    sources). Unknown tickers -> NO_EVENT_FOUND (pessimistic, not CLEAN).
    """

    def __init__(self, events_path: str | Path):
        self._events: dict = {}
        p = Path(events_path)
        if p.exists():
            data = json.loads(p.read_text())
            if isinstance(data, dict):
                self._events = data.get("events", data)

    def scan(self, ticker: str, as_of: str) -> ScanResult:
        rec = self._events.get(ticker.upper())
        if not isinstance(rec, dict):
            return ScanResult(
                ticker=ticker.upper(),
                result=NO_EVENT_FOUND,
                scanned_at=as_of,
                reasons=["ticker_not_in_events_file"],
            )
        return ScanResult(
            ticker=ticker.upper(),
            result=_coerce_result(rec.get("result", NO_EVENT_FOUND)),
            pending_mna=bool(rec.get("pending_mna", False)),
            completed_mna_within_4q=bool(rec.get("completed_mna_within_4q", False)),
            spinoff=bool(rec.get("spinoff", False)),
            dividend_policy_change=bool(rec.get("dividend_policy_change", False)),
            rating_action=bool(rec.get("rating_action", False)),
            sources=list(rec.get("sources", [])),
            scanned_at=str(rec.get("scanned_at", as_of)),
            reasons=list(rec.get("reasons", [])),
        )


class FixtureEventScanner:
    """Test/double scanner: constructed from an in-memory dict."""

    def __init__(self, events: dict[str, ScanResult]):
        self._events = events

    def scan(self, ticker: str, as_of: str) -> ScanResult:
        return self._events.get(
            ticker.upper(),
            ScanResult(ticker=ticker.upper(), result=NO_EVENT_FOUND, scanned_at=as_of),
        )
