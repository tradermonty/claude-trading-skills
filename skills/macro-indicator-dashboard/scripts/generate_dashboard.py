#!/usr/bin/env python3
"""Render the macro-indicator-dashboard JSON into a human-readable Markdown report.

Usage:
    python3 generate_dashboard.py --input macro_regime.json --output-dir reports/
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


REGIME_EMOJI = {
    "GOLDILOCKS": "[++]",
    "REFLATION": "[+]",
    "RECOVERY": "[+]",
    "SLOWDOWN": "[~]",
    "STAGFLATION": "[-]",
    "RECESSION": "[--]",
}


def render(data: dict[str, Any]) -> str:
    out: list[str] = []
    as_of = data.get("as_of", "")
    regime = data.get("regime", "UNKNOWN")
    confidence = data.get("regime_confidence", 0)
    risk_on = data.get("risk_on_score", 0)
    exposure_scale = data.get("exposure_scale", 0.5)
    narrative = data.get("narrative", "")

    out.append(f"# Macro Indicator Dashboard")
    out.append(f"**As of:** {as_of}")
    out.append("")
    out.append(f"## {REGIME_EMOJI.get(regime, '')} Regime: **{regime}**  (confidence {confidence})")
    out.append("")
    out.append(f"- **Risk-on score:** **{risk_on}/100**")
    out.append(f"- **Exposure scale (consumed by exposure-coach):** **{exposure_scale:.2f}**")
    out.append("")
    out.append("### Narrative")
    out.append(narrative)
    out.append("")

    axes = data.get("axes", {})
    out.append("## Two-Axis Snapshot")
    out.append("")
    out.append(f"- Growth score: `{axes.get('growth_score', 0):+.2f}` (range -2 to +2)")
    out.append(f"- Inflation score: `{axes.get('inflation_score', 0):+.2f}` (range -2 to +2)")
    out.append("")

    ind = data.get("indicators", {})

    # Growth detail
    g = ind.get("growth", {})
    out.append("## Growth Indicators")
    out.append("")
    out.append("| Indicator | Value | Notes |")
    out.append("|-----------|-------|-------|")
    if "payems_3m_ann_growth_pct" in g:
        out.append(f"| Nonfarm Payrolls 3M annualized | {g['payems_3m_ann_growth_pct']:+.2f}% | >2% healthy |")
    if "indpro_6m_change_pct" in g:
        out.append(f"| Industrial Production 6M change | {g['indpro_6m_change_pct']:+.2f}% | >0 expansion |")
    if "sahm_proxy_pp" in g:
        out.append(f"| Sahm Rule proxy (UR 3M avg vs 12M low) | {g['sahm_proxy_pp']:+.2f}pp | >=0.5pp = recession signal |")
    if "icsa_4w_zscore" in g:
        out.append(f"| Initial Claims 4W z-score | {g['icsa_4w_zscore']:+.2f} | >1.5 elevated |")
    out.append("")

    # Inflation detail
    inf = ind.get("inflation", {})
    out.append("## Inflation Indicators")
    out.append("")
    out.append("| Indicator | Value | Notes |")
    out.append("|-----------|-------|-------|")
    if "core_cpi_yoy_pct" in inf:
        out.append(f"| Core CPI YoY | {inf['core_cpi_yoy_pct']:.2f}% | Target ~2% |")
    if "pce_yoy_pct" in inf:
        out.append(f"| Headline PCE YoY | {inf['pce_yoy_pct']:.2f}% | Fed target 2% |")
    if "t5yie_pct" in inf:
        out.append(f"| 5Y Breakeven (market) | {inf['t5yie_pct']:.2f}% | Anchored ~2% |")
    if "core_cpi_3m_ann_vs_yoy_pp" in inf:
        accel = inf["core_cpi_3m_ann_vs_yoy_pp"]
        direction = "accelerating" if accel > 0 else "decelerating"
        out.append(f"| Core CPI 3M ann vs YoY | {accel:+.2f}pp | {direction} |")
    out.append("")

    # Financial conditions
    fc = ind.get("financial_conditions", {})
    out.append("## Financial Conditions")
    out.append("")
    out.append("| Indicator | Value | Signal |")
    out.append("|-----------|-------|--------|")
    if "nfci" in fc:
        out.append(f"| Chicago Fed NFCI | {fc['nfci']:+.2f} | {fc.get('nfci_signal', '')} |")
    if "hy_oas_pct" in fc:
        out.append(f"| HY Credit OAS | {fc['hy_oas_pct']:.2f}% | {fc.get('hy_oas_signal', '')} |")
    if "ig_oas_pct" in fc:
        out.append(f"| IG Credit OAS | {fc['ig_oas_pct']:.2f}% |  |")
    out.append("")

    # Yield curve
    yc = ind.get("yield_curve", {})
    out.append("## Yield Curve")
    out.append("")
    out.append("| Spread | Value | Signal |")
    out.append("|--------|-------|--------|")
    if "t10y3m" in yc:
        out.append(f"| 10Y - 3M | {yc['t10y3m']:+.2f}pp | {yc.get('t10y3m_signal', '')} |")
    if "t10y2y" in yc:
        out.append(f"| 10Y - 2Y | {yc['t10y2y']:+.2f}pp |  |")
    out.append("")

    # Liquidity
    liq = ind.get("liquidity", {})
    out.append("## Liquidity")
    out.append("")
    out.append("| Indicator | Value |")
    out.append("|-----------|-------|")
    if "m2_yoy_pct" in liq:
        out.append(f"| M2 YoY | {liq['m2_yoy_pct']:+.2f}% |")
    if "rrp_billions" in liq:
        out.append(f"| Overnight Reverse Repo | ${liq['rrp_billions']:.1f}B |")
    out.append("")

    out.append("---")
    out.append("")
    out.append("## How the orchestrator uses this")
    out.append("")
    out.append(f"- `exposure_scale = {exposure_scale:.2f}` is multiplied with exposure-coach's")
    out.append("  ceiling and the bubble-detector's phase cap. The trade-loop-orchestrator")
    out.append("  takes the **minimum** of the three to set the maximum equity exposure.")
    out.append(f"- `risk_on_score = {risk_on}/100` is logged for postmortem and trend tracking.")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, default=Path("reports"))
    args = ap.parse_args()

    with args.input.open() as f:
        data = json.load(f)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    as_of = data.get("as_of", date.today().isoformat())
    out_path = args.output_dir / f"macro_dashboard_{as_of}.md"
    with out_path.open("w") as f:
        f.write(render(data))

    print(f"Wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
