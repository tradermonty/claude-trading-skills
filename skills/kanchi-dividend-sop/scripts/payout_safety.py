"""WS-2: sector-aware payout-safety triad (GAAP / Adjusted / FCF).

Pure, dependency-free, offline-testable. Closes defect D2 (MKC payout
understated because a single GAAP-TTM proxy was inflated by a non-cash
acquisition remeasurement gain) and the over-strict utility -FCF problem.

Key rules (improvement-plan v2.1 R-3 + 4th-review):
- FCF payout is meaningless for banks and structurally negative for
  regulated utilities -> sector dispatch, NOT one uniform triad.
- Adjusted EPS is not in FMP; `adjusted_eps_source` is recorded and
  UNAVAILABLE -> verdict capped HOLD-REVIEW (fail-safe), never silent PASS.
- A merger completed within COMPLETED_MNA_LOOKBACK_QUARTERS presumes GAAP
  EPS is distorted -> force the adjusted path or HOLD-REVIEW
  (FITB/Comerica Q1-2026 GAAP EPS $0.15 is the golden case).
- Emits machine-checkable pre_order_blocker codes for WS-6 (4th-review #6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from thresholds import (
    ADJ_EPS_PAYOUT_CAUTION,
    ADJ_EPS_PAYOUT_MAX,
    FCF_PAYOUT_HIGH_RISK,
    FCF_PAYOUT_MAX,
    GAAP_ADJ_DIVERGENCE,
)

_CONSUMER_SECTORS = {
    "consumer",
    "consumer defensive",
    "consumer staples",
    "consumer cyclical",
    "industrials",
    "industrial",
    "communication",
    "communication services",
    "technology",
    "healthcare",
    "energy",
    "materials",
    "basic materials",
    "real estate",  # treated as consumer-style triad unless flagged a REIT upstream
}
_BANK_SECTORS = {"bank", "banks", "financial", "financials", "financial services"}
_UTILITY_SECTORS = {"utility", "utilities"}
_INSURER_SECTORS = {"insurance", "insurer", "insurers"}


def _sector_kind(sector: str | None) -> str:
    s = (sector or "").strip().lower()
    if s in _BANK_SECTORS:
        return "bank"
    if s in _UTILITY_SECTORS:
        return "utility"
    if s in _INSURER_SECTORS:
        return "insurer"
    return "consumer"


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


@dataclass
class SafetyAssessment:
    sector_kind: str
    safety_verdict: str  # PASS | CAUTION | FAIL | HOLD-REVIEW
    gaap_eps_payout: float | None = None
    adjusted_eps_payout: float | None = None
    fcf_payout: float | None = None
    adjusted_eps_source: str = "UNAVAILABLE"  # FMP | MANUAL | UNAVAILABLE
    gaap_adj_divergence: float | None = None
    one_off_flag: bool = False
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def assess_payout_safety(
    *,
    sector: str | None,
    annual_dividend: float | None,
    gaap_eps: float | None = None,
    adjusted_eps: float | None = None,
    adjusted_eps_source: str = "UNAVAILABLE",
    fcf_per_share: float | None = None,
    completed_merger_within_4q: bool = False,
    bank_metrics: dict | None = None,
    utility_metrics: dict | None = None,
    insurer_metrics: dict | None = None,
) -> SafetyAssessment:
    kind = _sector_kind(sector)
    reasons: list[str] = []
    blockers: list[str] = []

    gaap_payout = _ratio(annual_dividend, gaap_eps)
    adj_payout = _ratio(annual_dividend, adjusted_eps)
    fcf_payout = _ratio(annual_dividend, fcf_per_share)

    # --- GAAP vs Adjusted divergence -> one-off flag (D2) ---
    one_off = False
    divergence = None
    if gaap_eps is not None and adjusted_eps not in (None, 0):
        divergence = abs(gaap_eps - adjusted_eps) / abs(adjusted_eps)
        if divergence > GAAP_ADJ_DIVERGENCE:
            one_off = True
            reasons.append(f"gaap_adj_divergence_{round(divergence * 100)}pct")
            blockers.append("gaap_adjusted_divergence_gt_25pct")

    # --- completed-merger linkage: GAAP presumed distorted (FITB/Comerica) ---
    if completed_merger_within_4q:
        reasons.append("completed_merger_within_4q_gaap_distorted")
        if adjusted_eps is None:
            blockers.append("adjusted_eps_unavailable")
            return SafetyAssessment(
                sector_kind=kind,
                safety_verdict="HOLD-REVIEW",
                gaap_eps_payout=_round(gaap_payout),
                adjusted_eps_payout=None,
                fcf_payout=_round(fcf_payout),
                adjusted_eps_source=adjusted_eps_source,
                gaap_adj_divergence=_round(divergence, 4),
                one_off_flag=True,
                reasons=reasons + ["use_adjusted_eps_after_merger"],
                blockers=blockers,
            )
        one_off = True

    # --- adjusted EPS availability is the safety anchor for income names ---
    if adjusted_eps is None or adjusted_eps_source == "UNAVAILABLE":
        blockers.append("adjusted_eps_unavailable")
        reasons.append("adjusted_eps_unavailable_failsafe_hold")

    if kind == "bank":
        verdict = _assess_bank(bank_metrics or {}, gaap_payout, reasons, blockers)
    elif kind == "utility":
        verdict = _assess_utility(utility_metrics or {}, gaap_payout, reasons, blockers)
    elif kind == "insurer":
        verdict = _assess_insurer(insurer_metrics or {}, gaap_payout, reasons, blockers)
    else:
        verdict = _assess_consumer(adj_payout, fcf_payout, adjusted_eps, reasons, blockers)

    # Fail-safe: never PASS while the adjusted-EPS anchor is missing.
    if "adjusted_eps_unavailable" in blockers and verdict in ("PASS", "CAUTION"):
        verdict = "HOLD-REVIEW"

    return SafetyAssessment(
        sector_kind=kind,
        safety_verdict=verdict,
        gaap_eps_payout=_round(gaap_payout),
        adjusted_eps_payout=_round(adj_payout),
        fcf_payout=_round(fcf_payout),
        adjusted_eps_source=adjusted_eps_source,
        gaap_adj_divergence=_round(divergence, 4),
        one_off_flag=one_off,
        reasons=reasons,
        blockers=sorted(set(blockers)),
    )


def _round(value: float | None, ndigits: int = 4) -> float | None:
    return round(value, ndigits) if value is not None else None


def _assess_consumer(adj_payout, fcf_payout, adjusted_eps, reasons, blockers) -> str:
    # Primary: adjusted-EPS payout + FCF payout.
    if fcf_payout is not None and fcf_payout > FCF_PAYOUT_HIGH_RISK:
        reasons.append("fcf_payout_above_100pct")
        return "FAIL"
    if adj_payout is not None and adj_payout > ADJ_EPS_PAYOUT_MAX:
        reasons.append("adj_eps_payout_above_85pct")
        return "FAIL"
    caution = False
    if adj_payout is not None and adj_payout > ADJ_EPS_PAYOUT_CAUTION:
        reasons.append("adj_eps_payout_caution_band")
        caution = True
    if fcf_payout is not None and fcf_payout > FCF_PAYOUT_MAX:
        reasons.append("fcf_payout_above_80pct")
        caution = True
    if adjusted_eps is None:
        return "HOLD-REVIEW"
    return "CAUTION" if caution else "PASS"


def _assess_bank(m: dict, eps_payout, reasons, blockers) -> str:
    # FCF payout is meaningless for banks; use EPS payout + credit + capital.
    npl_trend = str(m.get("npl_trend", "")).lower()
    nco_trend = str(m.get("nco_trend", "")).lower()
    cet1 = m.get("cet1")
    cre_concentration = m.get("cre_concentration")
    verdict = "PASS"
    if cet1 is None:
        blockers.append("bank_capital_unavailable")
        verdict = "CAUTION"
    if cre_concentration is None:
        blockers.append("bank_cre_concentration_unavailable")
        verdict = "CAUTION"
    if npl_trend == "deteriorating" or nco_trend == "deteriorating":
        reasons.append("bank_npl_nco_deteriorating")
        blockers.append("bank_npl_nco_deteriorating")
        verdict = "CAUTION"
    if eps_payout is not None and eps_payout > ADJ_EPS_PAYOUT_MAX:
        reasons.append("bank_eps_payout_high")
        verdict = "FAIL"
    return verdict


def _assess_utility(m: dict, eps_payout, reasons, blockers) -> str:
    # Regulated utilities run structurally negative FCF (rate-base capex);
    # judge on FFO/debt + allowed ROE + rate-case + equity issuance instead.
    ffo_debt = m.get("ffo_to_debt")
    rate_case = str(m.get("rate_case_status", "")).lower()
    equity_issuance = str(m.get("equity_issuance_risk", "")).lower()
    verdict = "PASS"
    if ffo_debt is None:
        blockers.append("utility_ffo_debt_unavailable")
        verdict = "CAUTION"
    if rate_case in ("adverse", "pending_adverse"):
        reasons.append("utility_rate_case_adverse")
        blockers.append("utility_rate_case_adverse")
        verdict = "HOLD-REVIEW"
    if equity_issuance in ("high", "dilutive"):
        reasons.append("utility_equity_issuance_risk")
        if verdict == "PASS":
            verdict = "CAUTION"
    if eps_payout is not None and eps_payout > 1.0:
        reasons.append("utility_eps_payout_above_100pct")
        verdict = "FAIL"
    return verdict


def _assess_insurer(m: dict, eps_payout, reasons, blockers) -> str:
    combined_ratio = m.get("combined_ratio")
    reserve_dev = str(m.get("reserve_development", "")).lower()
    statutory = str(m.get("statutory_capital", "")).lower()
    verdict = "PASS"
    if combined_ratio is None:
        blockers.append("insurer_combined_ratio_unavailable")
        verdict = "CAUTION"
    if reserve_dev == "adverse":
        reasons.append("insurer_reserve_development_adverse")
        blockers.append("insurer_reserve_development_adverse")
        verdict = "HOLD-REVIEW"
    if combined_ratio is not None and combined_ratio > 1.0:
        reasons.append("insurer_combined_ratio_above_100")
        if verdict == "PASS":
            verdict = "CAUTION"
    if statutory == "weak":
        reasons.append("insurer_statutory_capital_weak")
        verdict = "HOLD-REVIEW"
    return verdict
