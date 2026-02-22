#!/usr/bin/env python3
"""
Build Kanchi-style dividend review queue from normalized monitoring input.

This script is intentionally data-source agnostic:
- Upstream jobs fetch dividend/filing/fundamental data.
- This script only applies deterministic T1-T5 rules.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEVERITY_RANK = {"OK": 0, "WARN": 1, "REVIEW": 2}
INSTRUMENT_DENOMINATOR = {
    "stock": "fcf",
    "etf": "fcf",
    "reit": "ffo",
    "bdc": "nii",
}
T4_KEYWORDS = [
    "item 4.02",
    "non-reliance",
    "restatement",
    "material weakness",
    "sec investigation",
]


@dataclass
class TriggerFinding:
    trigger: str
    status: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


def to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def float_history(raw: Any) -> list[float]:
    if not isinstance(raw, list):
        return []
    out: list[float] = []
    for item in raw:
        value = to_float(item)
        if value is not None:
            out.append(value)
    return out


def rank(status: str) -> int:
    return SEVERITY_RANK.get(status, 0)


def t1_dividend_cut_or_suspension(holding: dict[str, Any]) -> TriggerFinding | None:
    dividend = holding.get("dividend", {})
    latest = to_float(dividend.get("latest_regular"))
    prior = to_float(dividend.get("prior_regular"))
    missing = bool(dividend.get("is_missing", False))

    if missing:
        return TriggerFinding(
            trigger="T1",
            status="REVIEW",
            reason="Dividend data missing; suspension or data integrity issue possible.",
            evidence={"latest_regular": latest, "prior_regular": prior, "is_missing": missing},
        )

    if latest is not None and latest <= 0:
        return TriggerFinding(
            trigger="T1",
            status="REVIEW",
            reason="Latest regular dividend is zero.",
            evidence={"latest_regular": latest, "prior_regular": prior},
        )

    if latest is not None and prior is not None and prior > 0 and latest < prior * 0.99:
        return TriggerFinding(
            trigger="T1",
            status="REVIEW",
            reason="Latest regular dividend is lower than prior regular dividend by more than 1%.",
            evidence={"latest_regular": latest, "prior_regular": prior},
        )

    return None


def t2_coverage_deterioration(holding: dict[str, Any]) -> TriggerFinding | None:
    instrument = str(holding.get("instrument_type", "stock")).lower()
    cashflow = holding.get("cashflow", {})
    denominator_key = INSTRUMENT_DENOMINATOR.get(instrument, "fcf")
    denominator = to_float(cashflow.get(denominator_key))
    dividends_paid = to_float(cashflow.get("dividends_paid"))
    ratio_history = float_history(cashflow.get("coverage_ratio_history"))

    evidence = {
        "instrument_type": instrument,
        "denominator_key": denominator_key,
        "denominator_value": denominator,
        "dividends_paid": dividends_paid,
        "coverage_ratio_history": ratio_history,
    }

    if denominator is not None and dividends_paid is not None:
        if denominator <= 0 and dividends_paid > 0:
            return TriggerFinding(
                trigger="T2",
                status="REVIEW",
                reason="Distribution is positive while denominator is non-positive.",
                evidence=evidence,
            )
    current_ratio: float | None = None
    if denominator is not None and dividends_paid is not None and denominator > 0:
        current_ratio = dividends_paid / denominator
        evidence["current_ratio"] = round(current_ratio, 4)

    if len(ratio_history) >= 2:
        last = ratio_history[-1]
        prev = ratio_history[-2]
        if last > 1.0 and prev > 1.0:
            return TriggerFinding(
                trigger="T2",
                status="REVIEW",
                reason="Coverage ratio above 1.0 for two consecutive periods.",
                evidence=evidence,
            )

    if current_ratio is not None and current_ratio > 1.0:
        # If the history likely excludes current period, still escalate if prior period is also > 1.0.
        if ratio_history and ratio_history[-1] > 1.0:
            return TriggerFinding(
                trigger="T2",
                status="REVIEW",
                reason="Coverage ratio above 1.0 for two consecutive periods.",
                evidence=evidence,
            )
        # Single-period breach can be noisy; classify as WARN unless sustained.
        return TriggerFinding(
            trigger="T2",
            status="WARN",
            reason="Current period payout coverage ratio exceeds 1.0.",
            evidence=evidence,
        )

    if len(ratio_history) >= 2:
        last = ratio_history[-1]
        prev = ratio_history[-2]
        if last > 0.8 and last > prev:
            return TriggerFinding(
                trigger="T2",
                status="WARN",
                reason="Coverage ratio is above 0.8 and still rising.",
                evidence=evidence,
            )

    return None


def strictly_increasing(values: list[float], lookback: int = 3) -> bool:
    if len(values) < lookback:
        return False
    window = values[-lookback:]
    return all(window[i] < window[i + 1] for i in range(len(window) - 1))


def t3_credit_stress_proxy(holding: dict[str, Any]) -> TriggerFinding | None:
    balance_sheet = holding.get("balance_sheet", {})
    capital = holding.get("capital_returns", {})
    cashflow = holding.get("cashflow", {})

    net_debt_history = float_history(balance_sheet.get("net_debt_history"))
    interest_coverage_history = float_history(balance_sheet.get("interest_coverage_history"))

    buybacks = to_float(capital.get("buybacks")) or 0.0
    dividends_paid = (
        to_float(capital.get("dividends_paid")) or to_float(cashflow.get("dividends_paid")) or 0.0
    )
    fcf = to_float(capital.get("fcf"))
    if fcf is None:
        fcf = to_float(cashflow.get("fcf"))

    debt_up = strictly_increasing(net_debt_history, lookback=3)
    icov_down = len(interest_coverage_history) >= 2 and (
        interest_coverage_history[-1] < interest_coverage_history[-2]
    )
    icov_weak = len(interest_coverage_history) >= 1 and interest_coverage_history[-1] < 2.5

    capital_stretch = False
    if fcf is not None and fcf > 0:
        capital_stretch = (buybacks + dividends_paid) > (fcf * 1.10)

    evidence = {
        "net_debt_history": net_debt_history,
        "interest_coverage_history": interest_coverage_history,
        "buybacks": buybacks,
        "dividends_paid": dividends_paid,
        "fcf": fcf,
        "debt_up_3p": debt_up,
        "icov_down": icov_down,
        "icov_weak": icov_weak,
        "capital_stretch": capital_stretch,
    }

    if debt_up and (icov_down or icov_weak or capital_stretch):
        return TriggerFinding(
            trigger="T3",
            status="REVIEW",
            reason="Debt trend worsens with weakening coverage or aggressive capital returns.",
            evidence=evidence,
        )

    if debt_up or (icov_down and icov_weak):
        return TriggerFinding(
            trigger="T3",
            status="WARN",
            reason="Early proxy credit stress detected.",
            evidence=evidence,
        )

    return None


def t4_governance_or_filing_alert(holding: dict[str, Any]) -> TriggerFinding | None:
    filings = holding.get("filings", {})
    text_parts: list[str] = []

    for key in ("recent_text", "latest_8k_text", "headlines"):
        value = filings.get(key)
        if isinstance(value, str):
            text_parts.append(value)
        elif isinstance(value, list):
            text_parts.extend(str(item) for item in value)

    full_text = " ".join(text_parts).lower()
    if not full_text:
        return None

    hits = [kw for kw in T4_KEYWORDS if kw in full_text]
    if hits:
        return TriggerFinding(
            trigger="T4",
            status="REVIEW",
            reason="Potential governance/accounting red-flag keywords found in filings text.",
            evidence={"keyword_hits": hits},
        )

    return None


def t5_structural_decline(holding: dict[str, Any]) -> TriggerFinding | None:
    ops = holding.get("operations", {})
    revenue_cagr_5y = to_float(ops.get("revenue_cagr_5y"))
    margin_trend = str(ops.get("margin_trend", "")).lower()
    guidance_trend = str(ops.get("guidance_trend", "")).lower()
    dividend_growth_stalled = bool(ops.get("dividend_growth_stalled", False))

    score = 0
    reasons: list[str] = []

    if revenue_cagr_5y is not None and revenue_cagr_5y < 0:
        score += 1
        reasons.append("revenue_cagr_5y<0")
    if margin_trend == "down":
        score += 1
        reasons.append("margin_trend=down")
    if guidance_trend == "down":
        score += 1
        reasons.append("guidance_trend=down")
    if dividend_growth_stalled:
        score += 1
        reasons.append("dividend_growth_stalled=true")

    evidence = {
        "score": score,
        "reasons": reasons,
        "revenue_cagr_5y": revenue_cagr_5y,
        "margin_trend": margin_trend,
        "guidance_trend": guidance_trend,
        "dividend_growth_stalled": dividend_growth_stalled,
    }

    if score >= 3:
        return TriggerFinding(
            trigger="T5",
            status="REVIEW",
            reason="Multiple structural decline factors are active.",
            evidence=evidence,
        )
    if score >= 2:
        return TriggerFinding(
            trigger="T5",
            status="WARN",
            reason="Structural decline score indicates rising business-model risk.",
            evidence=evidence,
        )

    return None


def evaluate_holding(holding: dict[str, Any]) -> dict[str, Any]:
    ticker = str(holding.get("ticker", "")).upper().strip()
    instrument_type = str(holding.get("instrument_type", "stock")).lower()

    findings: list[TriggerFinding] = []
    for evaluator in (
        t1_dividend_cut_or_suspension,
        t2_coverage_deterioration,
        t3_credit_stress_proxy,
        t4_governance_or_filing_alert,
        t5_structural_decline,
    ):
        finding = evaluator(holding)
        if finding:
            findings.append(finding)

    final_status = "OK"
    for finding in findings:
        if rank(finding.status) > rank(final_status):
            final_status = finding.status

    actions: list[str]
    if final_status == "REVIEW":
        actions = [
            "pause_buy_adds",
            "create_review_ticket",
            "human_read_full_disclosure",
        ]
    elif final_status == "WARN":
        actions = [
            "pause_buy_adds_optional",
            "append_next_earnings_checklist",
        ]
    else:
        actions = []

    return {
        "ticker": ticker,
        "instrument_type": instrument_type,
        "status": final_status,
        "actions": actions,
        "findings": [asdict(f) for f in findings],
    }


def render_markdown(report: dict[str, Any]) -> str:
    as_of = report.get("as_of", "unknown")
    lines = [
        f"# Dividend Review Queue (as_of: {as_of})",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- As of: `{report['as_of']}`",
        "",
        "## Summary",
        "",
        f"- OK: `{report['summary']['OK']}`",
        f"- WARN: `{report['summary']['WARN']}`",
        f"- REVIEW: `{report['summary']['REVIEW']}`",
        "",
        "## Queue",
        "",
        "| Ticker | Status | Triggers | Actions |",
        "|---|---|---|---|",
    ]

    for item in report["results"]:
        triggers = ",".join(f["trigger"] for f in item["findings"]) or "-"
        actions = ",".join(item["actions"]) or "-"
        lines.append(f"| {item['ticker']} | {item['status']} | {triggers} | {actions} |")

    lines.append("")
    lines.append("## Findings")
    lines.append("")

    for item in report["results"]:
        if not item["findings"]:
            continue
        lines.append(f"### {item['ticker']} ({item['status']})")
        for finding in item["findings"]:
            lines.append(f"- `{finding['trigger']}` `{finding['status']}`: {finding['reason']}")
        lines.append("")

    return "\n".join(lines)


def build_report(payload: dict[str, Any]) -> dict[str, Any]:
    as_of = payload.get("as_of")
    if not as_of:
        as_of = datetime.now(timezone.utc).date().isoformat()

    holdings = payload.get("holdings", [])
    if not isinstance(holdings, list):
        raise ValueError("Input JSON field 'holdings' must be a list.")

    results = [evaluate_holding(holding) for holding in holdings]

    summary = {"OK": 0, "WARN": 0, "REVIEW": 0}
    for row in results:
        summary[row["status"]] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "summary": summary,
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Kanchi dividend review queue.")
    parser.add_argument("--input", required=True, help="Path to normalized input JSON.")
    parser.add_argument("--output", required=True, help="Path to output JSON report.")
    parser.add_argument(
        "--markdown",
        help="Optional path to markdown report output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    payload = json.loads(input_path.read_text())
    report = build_report(payload)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")

    if args.markdown:
        markdown_path = Path(args.markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(report) + "\n")

    print(f"Wrote JSON report: {output_path}")
    if args.markdown:
        print(f"Wrote markdown report: {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
