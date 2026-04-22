#!/usr/bin/env python3
"""Classify the macro regime and compute the 0-100 risk-on score from FRED data.

Reads the JSON emitted by fetch_fred_data.py and emits a new JSON with:
  - regime (one of GOLDILOCKS / REFLATION / STAGFLATION / SLOWDOWN / RECESSION / RECOVERY)
  - regime_confidence (0-1)
  - risk_on_score (0-100)
  - exposure_scale (0.0-1.0)  -> consumed by exposure-coach
  - per-indicator z-scores and signals
  - narrative

Usage:
    python3 compute_regime.py --input macro_raw.json --output macro_regime.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REGIMES = ["GOLDILOCKS", "REFLATION", "STAGFLATION", "SLOWDOWN", "RECESSION", "RECOVERY"]


def _series(data: dict[str, Any], sid: str) -> list[dict[str, Any]]:
    return data.get("series", {}).get(sid, {}).get("observations", [])


def _latest_value(data: dict[str, Any], sid: str) -> float | None:
    obs = _series(data, sid)
    return obs[-1]["value"] if obs else None


def _values(data: dict[str, Any], sid: str) -> list[float]:
    return [o["value"] for o in _series(data, sid)]


def _rolling_mean(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def _z_score(values: list[float]) -> float | None:
    """Standard z-score of the latest value vs the full series history."""
    if len(values) < 12:
        return None
    mean = statistics.mean(values)
    stdev = statistics.pstdev(values) or 1.0
    return (values[-1] - mean) / stdev


def _yoy_change(data: dict[str, Any], sid: str, freq_points: int) -> float | None:
    """YoY % change. freq_points is how many observations back = 1 year."""
    obs = _series(data, sid)
    if len(obs) < freq_points + 1:
        return None
    latest = obs[-1]["value"]
    yoy = obs[-1 - freq_points]["value"]
    if yoy == 0:
        return None
    return (latest / yoy - 1) * 100


def compute_growth_score(data: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Return (growth_score in [-2, 2], detail dict)."""
    components: dict[str, Any] = {}

    # PAYEMS 3-month annualized growth
    payems = _values(data, "PAYEMS")
    if len(payems) >= 4:
        recent = payems[-1]
        three_ago = payems[-4]
        mom_ann = ((recent / three_ago) ** 4 - 1) * 100 if three_ago > 0 else 0
        components["payems_3m_ann_growth_pct"] = round(mom_ann, 2)
    else:
        mom_ann = 0

    # INDPRO 6-month change
    indpro = _values(data, "INDPRO")
    if len(indpro) >= 7:
        indpro_6m = (indpro[-1] / indpro[-7] - 1) * 100
        components["indpro_6m_change_pct"] = round(indpro_6m, 2)
    else:
        indpro_6m = 0

    # UNRATE: Sahm rule proxy - 3-month average vs 12-month low
    unrate = _values(data, "UNRATE")
    sahm = 0.0
    if len(unrate) >= 13:
        three_m_avg = sum(unrate[-3:]) / 3
        twelve_m_min = min(unrate[-13:-1])
        sahm = three_m_avg - twelve_m_min
        components["sahm_proxy_pp"] = round(sahm, 2)

    # ICSA: z-score of 4-week moving average (inverted: high = bad)
    icsa = _values(data, "ICSA")
    icsa_z = 0.0
    if len(icsa) >= 52:
        ma4 = [sum(icsa[i - 4 : i]) / 4 for i in range(4, len(icsa) + 1)]
        if len(ma4) >= 12:
            mean = statistics.mean(ma4[-52:]) if len(ma4) >= 52 else statistics.mean(ma4)
            stdev = statistics.pstdev(ma4[-52:]) or 1.0
            icsa_z = (ma4[-1] - mean) / stdev
            components["icsa_4w_zscore"] = round(icsa_z, 2)

    # Normalize to [-2, 2]
    # PAYEMS: healthy >2%, weak <0%; map ~[0, 3] to [0, 2]
    p_norm = max(-2.0, min(2.0, (mom_ann - 1.0) * 1.0))
    # INDPRO 6M: healthy >1%, weak <-1%; map to [-2, 2]
    i_norm = max(-2.0, min(2.0, indpro_6m * 1.0))
    # SAHM: 0 is neutral, 0.5+ is recession; invert so negative = bad
    s_norm = max(-2.0, min(2.0, -4.0 * sahm))
    # ICSA z: positive z = bad for growth (claims rising)
    c_norm = max(-2.0, min(2.0, -icsa_z))

    score = (p_norm + i_norm + s_norm + c_norm) / 4
    components["growth_score"] = round(score, 3)
    components["subscores"] = {
        "payems": round(p_norm, 3),
        "indpro": round(i_norm, 3),
        "sahm": round(s_norm, 3),
        "icsa": round(c_norm, 3),
    }
    return score, components


def compute_inflation_score(data: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Return (inflation_score in [-2, 2], detail dict). Positive = high/rising."""
    components: dict[str, Any] = {}

    # Core CPI YoY (proxy for core PCE)
    cpilfe_yoy = _yoy_change(data, "CPILFESL", 12)
    if cpilfe_yoy is None:
        cpilfe_yoy = 2.0
    components["core_cpi_yoy_pct"] = round(cpilfe_yoy, 2)

    # PCE YoY
    pce_yoy = _yoy_change(data, "PCEPI", 12)
    if pce_yoy is None:
        pce_yoy = 2.0
    components["pce_yoy_pct"] = round(pce_yoy, 2)

    # 5Y breakeven (market expectations)
    t5yie = _latest_value(data, "T5YIE")
    if t5yie is None:
        t5yie = 2.0
    components["t5yie_pct"] = round(t5yie, 2)

    # Acceleration check: 3M annualized core CPI vs 12M YoY
    cpilfe = _values(data, "CPILFESL")
    accel = 0.0
    if len(cpilfe) >= 4:
        three_m = ((cpilfe[-1] / cpilfe[-4]) ** 4 - 1) * 100 if cpilfe[-4] > 0 else 0
        accel = three_m - cpilfe_yoy
        components["core_cpi_3m_ann_vs_yoy_pp"] = round(accel, 2)

    # Normalize around 2% target. Above 3% is inflationary, below 1.5% is
    # disinflationary. Acceleration adds direction.
    core_avg = (cpilfe_yoy + pce_yoy) / 2
    level = max(-2.0, min(2.0, (core_avg - 2.0)))  # 4% -> +2, 0% -> -2
    expectations = max(-1.0, min(1.0, (t5yie - 2.0)))  # breakevens tilt
    direction = max(-1.0, min(1.0, accel * 0.5))

    score = (level * 0.6) + (expectations * 0.2) + (direction * 0.2)
    score = max(-2.0, min(2.0, score))
    components["inflation_score"] = round(score, 3)
    return score, components


def compute_financial_conditions(data: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Return (component detail, nfci_contribution to risk_on)."""
    detail: dict[str, Any] = {}

    nfci = _latest_value(data, "NFCI")
    if nfci is not None:
        detail["nfci"] = round(nfci, 3)
        # NFCI: -0.5 = very loose, +1 = crisis. Negative is risk-on.
        detail["nfci_signal"] = (
            "very_loose"
            if nfci < -0.5
            else "loose"
            if nfci < 0
            else "tightening"
            if nfci < 0.5
            else "tight"
        )

    hy_oas = _latest_value(data, "BAMLH0A0HYM2")
    if hy_oas is not None:
        detail["hy_oas_pct"] = round(hy_oas, 2)
        detail["hy_oas_signal"] = (
            "very_tight"
            if hy_oas < 3
            else "tight"
            if hy_oas < 4
            else "normal"
            if hy_oas < 6
            else "stressed"
        )

    ig_oas = _latest_value(data, "BAMLC0A0CM")
    if ig_oas is not None:
        detail["ig_oas_pct"] = round(ig_oas, 2)

    # Normalize for composite: NFCI negative is good, HY tight is good
    nfci_norm = nfci if nfci is not None else 0.0
    hy_norm = (hy_oas - 4.0) / 2.0 if hy_oas is not None else 0.0  # 4% = 0, 6% = +1

    fc_contribution = -nfci_norm * 20 - max(0, hy_norm) * 10
    return detail, fc_contribution


def compute_yield_curve(data: dict[str, Any]) -> tuple[dict[str, Any], float]:
    detail: dict[str, Any] = {}
    t10y3m = _latest_value(data, "T10Y3M")
    t10y2y = _latest_value(data, "T10Y2Y")

    if t10y3m is not None:
        detail["t10y3m"] = round(t10y3m, 3)
        detail["t10y3m_signal"] = (
            "steep"
            if t10y3m > 1.0
            else "normal"
            if t10y3m > 0.25
            else "flat"
            if t10y3m > 0
            else "inverted"
        )
    if t10y2y is not None:
        detail["t10y2y"] = round(t10y2y, 3)

    # Use the worse of the two. Negative = inverted = bad.
    curve = min(t10y3m or 0, t10y2y or 0)
    detail["worst_curve"] = round(curve, 3)

    # Contribution: steeper = more risk-on. Map [-1, +2] to [-15, +15].
    contribution = max(-15.0, min(15.0, curve * 10))
    return detail, contribution


def compute_liquidity(data: dict[str, Any]) -> tuple[dict[str, Any], float]:
    detail: dict[str, Any] = {}

    m2_yoy = _yoy_change(data, "M2SL", 12)
    if m2_yoy is not None:
        detail["m2_yoy_pct"] = round(m2_yoy, 2)

    rrp = _latest_value(data, "RRPONTSYD")
    if rrp is not None:
        detail["rrp_billions"] = round(rrp, 1)

    m2_score = 0.0
    if m2_yoy is not None:
        # healthy M2 growth ~6-8%, contraction is bad
        m2_score = max(-5.0, min(5.0, m2_yoy - 2.0))

    return detail, m2_score


def classify_regime(
    growth_score: float,
    inflation_score: float,
    nfci: float | None,
    prior_growth: float | None,
) -> tuple[str, float]:
    """Apply the rules from economic_regime_framework.md. Return (regime, confidence)."""
    nfci = nfci if nfci is not None else 0.0

    # Recession
    if growth_score <= -1.0 and nfci >= 1.0:
        confidence = min(1.0, abs(growth_score) * 0.3 + nfci * 0.3)
        return "RECESSION", round(confidence, 2)

    # Recovery
    if prior_growth is not None and prior_growth <= -0.5 and growth_score > 0:
        return "RECOVERY", 0.7

    # Stagflation
    if growth_score < 0 and inflation_score > 0.5:
        confidence = min(1.0, abs(growth_score) * 0.3 + inflation_score * 0.3)
        return "STAGFLATION", round(confidence, 2)

    # Goldilocks
    if growth_score > 0 and inflation_score < 0:
        confidence = min(1.0, growth_score * 0.3 + abs(inflation_score) * 0.3 + 0.3)
        return "GOLDILOCKS", round(confidence, 2)

    # Reflation
    if growth_score > 0 and inflation_score > 0:
        confidence = min(1.0, growth_score * 0.3 + 0.3)
        return "REFLATION", round(confidence, 2)

    # Slowdown (default)
    confidence = 0.5
    return "SLOWDOWN", confidence


def compute_risk_on_score(
    growth_score: float,
    inflation_score: float,
    fc_contribution: float,
    curve_contribution: float,
    liquidity_contribution: float,
) -> int:
    """Bound the composite to [0, 100]."""
    base = 50.0
    base += 25 * growth_score  # -50 to +50
    base += -15 * max(0, inflation_score - 1)  # penalize high inflation only
    base += fc_contribution  # -20 to +20
    base += curve_contribution  # -15 to +15
    base += liquidity_contribution  # -5 to +5
    return max(0, min(100, int(round(base))))


def score_to_exposure_scale(risk_on_score: int) -> float:
    if risk_on_score >= 85:
        return 1.00
    if risk_on_score >= 70:
        return 0.85
    if risk_on_score >= 55:
        return 0.70
    if risk_on_score >= 40:
        return 0.50
    if risk_on_score >= 25:
        return 0.30
    return 0.10


def build_narrative(
    regime: str,
    risk_on_score: int,
    growth_detail: dict[str, Any],
    inflation_detail: dict[str, Any],
    fc_detail: dict[str, Any],
    curve_detail: dict[str, Any],
) -> str:
    pieces = []
    pieces.append(f"Regime: {regime}, risk-on score {risk_on_score}/100.")

    gs = growth_detail.get("growth_score", 0)
    if gs > 0.5:
        pieces.append("Growth solid (labor + industrial production expanding).")
    elif gs < -0.5:
        pieces.append("Growth deteriorating (Sahm proxy and claims flashing).")
    else:
        pieces.append("Growth mixed/flat.")

    inf = inflation_detail.get("inflation_score", 0)
    core = inflation_detail.get("core_cpi_yoy_pct", 2.0)
    if inf > 0.5:
        pieces.append(f"Inflation sticky/rising (core CPI YoY {core}%).")
    elif inf < -0.3:
        pieces.append(f"Disinflation continues (core CPI YoY {core}%).")
    else:
        pieces.append(f"Inflation near target (core CPI YoY {core}%).")

    nfci = fc_detail.get("nfci", 0)
    if nfci is not None:
        if nfci < 0:
            pieces.append(f"Financial conditions loose (NFCI {nfci}).")
        else:
            pieces.append(f"Financial conditions tight (NFCI {nfci}).")

    curve = curve_detail.get("t10y3m")
    if curve is not None:
        if curve < 0:
            pieces.append(f"Yield curve inverted (T10Y3M {curve}pp).")
        elif curve < 0.25:
            pieces.append(f"Yield curve flat (T10Y3M {curve}pp).")

    return " ".join(pieces)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input", type=Path, required=True, help="macro_raw JSON from fetch_fred_data.py"
    )
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--previous",
        type=Path,
        default=None,
        help="previous macro_regime JSON for recovery detection",
    )
    args = ap.parse_args()

    with args.input.open() as f:
        data = json.load(f)

    prior_growth = None
    if args.previous and args.previous.exists():
        try:
            with args.previous.open() as f:
                prev = json.load(f)
            prior_growth = prev.get("axes", {}).get("growth_score")
        except Exception:
            pass

    growth_score, growth_detail = compute_growth_score(data)
    inflation_score, inflation_detail = compute_inflation_score(data)
    fc_detail, fc_contrib = compute_financial_conditions(data)
    curve_detail, curve_contrib = compute_yield_curve(data)
    liq_detail, liq_contrib = compute_liquidity(data)

    regime, confidence = classify_regime(
        growth_score, inflation_score, fc_detail.get("nfci"), prior_growth
    )
    risk_on = compute_risk_on_score(
        growth_score, inflation_score, fc_contrib, curve_contrib, liq_contrib
    )
    exposure_scale = score_to_exposure_scale(risk_on)

    out = {
        "as_of": data.get("as_of", dt.date.today().isoformat()),
        "regime": regime,
        "regime_confidence": confidence,
        "risk_on_score": risk_on,
        "exposure_scale": exposure_scale,
        "axes": {
            "growth_score": round(growth_score, 3),
            "inflation_score": round(inflation_score, 3),
        },
        "indicators": {
            "growth": growth_detail,
            "inflation": inflation_detail,
            "financial_conditions": fc_detail,
            "yield_curve": curve_detail,
            "liquidity": liq_detail,
        },
        "narrative": build_narrative(
            regime, risk_on, growth_detail, inflation_detail, fc_detail, curve_detail
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        json.dump(out, f, indent=2)

    print(f"Regime: {regime} (confidence {confidence})", file=sys.stderr)
    print(f"Risk-on score: {risk_on}/100", file=sys.stderr)
    print(f"Exposure scale: {exposure_scale:.2f}", file=sys.stderr)
    print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
