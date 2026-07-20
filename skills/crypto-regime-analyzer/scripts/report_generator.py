#!/usr/bin/env python3
"""
Crypto Regime Analyzer - Report Generator

Generates JSON and Markdown reports for crypto regime analysis.
"""

import json

from scorer import COMPONENT_LABELS, COMPONENT_WEIGHTS


def generate_json_report(analysis: dict, output_file: str):
    """Save full analysis as JSON."""
    payload = json.dumps(analysis, indent=2, default=str, allow_nan=False)
    with open(output_file, "w") as f:
        f.write(payload)
    print(f"  JSON report saved to: {output_file}")


def _zone_bar(score: float) -> str:
    filled = int(round(score / 5))
    return "#" * filled + "-" * (20 - filled)


def generate_markdown_report(analysis: dict, output_file: str):
    """Generate the one-page Markdown regime report."""
    composite = analysis.get("composite", {})
    components = analysis.get("components", {})
    metadata = analysis.get("metadata", {})
    score = composite.get("score")

    lines = [
        "# Crypto Regime Report",
        "",
        f"**As of:** {metadata.get('as_of', 'unknown')}  ",
        f"**Universe:** top {metadata.get('universe_size', '?')} by market cap "
        "(stables and wrapped assets excluded)",
        "",
        "## Composite",
        "",
    ]
    if score is None:
        lines += [
            "**Zone: UNKNOWN**",
            "",
            composite.get("guidance", "Insufficient component coverage"),
            "",
        ]
    else:
        lines += [
            f"**Score: {score} / 100 — {composite.get('zone')}**",
            "",
            f"`[{_zone_bar(score)}]`",
            "",
            f"**Posture:** {composite.get('guidance')}",
            "",
            f"Components available: {composite.get('components_available')}"
            f"/{composite.get('components_total')}",
            "",
        ]

    lines += ["## Components", "", "| Component | Weight | Score | Signal |", "|---|---|---|---|"]
    for cid, label in COMPONENT_LABELS.items():
        comp = components.get(cid, {})
        weight = f"{COMPONENT_WEIGHTS[cid] * 100:.0f}%"
        if comp.get("data_available"):
            lines.append(f"| {label} | {weight} | {comp['score']} | {comp['signal']} |")
        else:
            lines.append(f"| {label} | {weight} | — | {comp.get('signal', 'not computed')} |")

    lines += [
        "",
        "## Notes",
        "",
        "- Score direction: 100 = risk-on health, 0 = critical risk-off.",
        "- Missing weights are redistributed only when at least four components",
        "  representing at least 65% of model weight remain; otherwise the zone is UNKNOWN.",
        "- This report describes market conditions; it is not investment advice",
        "  and issues no buy/sell instructions.",
        "",
    ]

    with open(output_file, "w") as f:
        f.write("\n".join(lines))
    print(f"  Markdown report saved to: {output_file}")


def print_summary(analysis: dict):
    """Console one-liner for workflow chaining."""
    composite = analysis.get("composite", {})
    score = composite.get("score")
    if score is None:
        print(f"CRYPTO REGIME: UNKNOWN — {composite.get('guidance', 'insufficient coverage')}")
        return
    print(
        f"CRYPTO REGIME: {composite.get('zone')} (score {score}/100) — {composite.get('guidance')}"
    )
