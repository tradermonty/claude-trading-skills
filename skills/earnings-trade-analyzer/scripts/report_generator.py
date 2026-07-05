#!/usr/bin/env python3
"""
Report Generator for Earnings Trade Analyzer

Generates JSON and Markdown reports from scored earnings trade results.
JSON output uses schema_version "1.0" for pead-screener compatibility.
"""

import json
import os
from datetime import datetime


def _format_market_cap(market_cap):
    """Format market cap in human-readable format."""
    if not market_cap or market_cap == 0:
        return "N/A"
    if market_cap >= 1e12:
        return f"${market_cap / 1e12:.1f}T"
    elif market_cap >= 1e9:
        return f"${market_cap / 1e9:.1f}B"
    elif market_cap >= 1e6:
        return f"${market_cap / 1e6:.0f}M"
    else:
        return f"${market_cap:,.0f}"


def _generate_summary(results: list[dict]) -> dict:
    """Generate summary statistics from results.

    Args:
        results: List of scored stock result dicts

    Returns:
        Summary dict with counts by grade.
    """
    summary = {
        "total": len(results),
        "grade_a": 0,
        "grade_b": 0,
        "grade_c": 0,
        "grade_d": 0,
    }

    for r in results:
        grade = r.get("grade", "D")
        if grade == "A":
            summary["grade_a"] += 1
        elif grade == "B":
            summary["grade_b"] += 1
        elif grade == "C":
            summary["grade_c"] += 1
        else:
            summary["grade_d"] += 1

    return summary


def generate_json_report(
    results: list[dict],
    metadata: dict,
    output_path: str,
    all_results: list[dict] = None,
) -> str:
    """Generate JSON report with schema_version "1.0".

    Args:
        results: List of top scored results to include
        metadata: Metadata dict (generated_at, lookback_days, etc.)
        output_path: Path to write JSON file
        all_results: All results for summary counts (defaults to results)

    Returns:
        Path to the generated JSON file.
    """
    if all_results is None:
        all_results = results

    summary = _generate_summary(all_results)

    # Build sector distribution
    sector_distribution = {}
    for r in all_results:
        sector = r.get("sector", "Unknown")
        sector_distribution[sector] = sector_distribution.get(sector, 0) + 1

    report = {
        "schema_version": "1.0",
        "metadata": metadata,
        "results": [
            {
                "symbol": r.get("symbol"),
                "company_name": r.get("company_name"),
                "earnings_date": r.get("earnings_date"),
                "earnings_timing": r.get("earnings_timing"),
                "gap_pct": r.get("gap_pct"),
                "composite_score": r.get("composite_score"),
                "grade": r.get("grade"),
                "current_price": r.get("current_price"),
                "market_cap": r.get("market_cap"),
                "sector": r.get("sector"),
                "components": r.get("components", {}),
            }
            for r in results
        ],
        "summary": summary,
        "sector_distribution": sector_distribution,
    }

    os.makedirs(
        os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return output_path


def generate_markdown_report(
    results: list[dict],
    metadata: dict,
    output_path: str,
    all_results: list[dict] = None,
) -> str:
    """Generate Markdown report with tables.

    Args:
        results: List of top scored results to include
        metadata: Metadata dict
        output_path: Path to write Markdown file
        all_results: All results for summary counts (defaults to results)

    Returns:
        Path to the generated Markdown file.
    """
    if all_results is None:
        all_results = results

    summary = _generate_summary(all_results)
    now = metadata.get("generated_at", datetime.now().isoformat())
    lookback_days = metadata.get("lookback_days", "N/A")

    lines = []
    lines.append("# Earnings Trade Analyzer Report")
    lines.append("")
    lines.append(f"**Generated:** {now}")
    lines.append(f"**Lookback:** {lookback_days} days")
    lines.append(f"**Total Screened:** {summary['total']}")
    lines.append("")

    # Show top count if limited
    if len(results) < len(all_results):
        lines.append(f"*Showing top {len(results)} of {len(all_results)} candidates*")
        lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append("| Grade | Count |")
    lines.append("|-------|-------|")
    lines.append(f"| A (85+) | {summary['grade_a']} |")
    lines.append(f"| B (70-84) | {summary['grade_b']} |")
    lines.append(f"| C (55-69) | {summary['grade_c']} |")
    lines.append(f"| D (<55) | {summary['grade_d']} |")
    lines.append(f"| **Total** | **{summary['total']}** |")
    lines.append("")

    # Results table
    lines.append("## Top Results")
    lines.append("")
    lines.append(
        "| Rank | Symbol | Grade | Score | Gap% | Trend% | Vol Ratio | MA200 | MA50 | Mkt Cap |"
    )
    lines.append(
        "|------|--------|-------|-------|------|--------|-----------|-------|------|---------|"
    )

    for i, r in enumerate(results, 1):
        symbol = r.get("symbol", "???")
        grade = r.get("grade", "D")
        score = r.get("composite_score", 0)
        gap_pct = r.get("gap_pct", 0)
        components = r.get("components", {})

        trend_pct = components.get("pre_earnings_trend", {}).get("return_20d_pct", 0)
        vol_ratio = components.get("volume_trend", {}).get("vol_ratio_20_60", 0)
        ma200_dist = components.get("ma200_position", {}).get("distance_pct", 0)
        ma50_dist = components.get("ma50_position", {}).get("distance_pct", 0)
        market_cap = r.get("market_cap", 0)

        lines.append(
            f"| {i} | **{symbol}** | {grade} | {score:.1f} | "
            f"{gap_pct:+.1f}% | {trend_pct:+.1f}% | {vol_ratio:.2f}x | "
            f"{ma200_dist:+.1f}% | {ma50_dist:+.1f}% | {_format_market_cap(market_cap)} |"
        )

    lines.append("")

    # Detailed cards for Grade A and B
    grade_ab = [r for r in results if r.get("grade") in ("A", "B")]
    if grade_ab:
        lines.append("## Grade A & B Details")
        lines.append("")

        for r in grade_ab:
            symbol = r.get("symbol", "???")
            company = r.get("company_name", symbol)
            grade = r.get("grade", "?")
            score = r.get("composite_score", 0)
            gap_pct = r.get("gap_pct", 0)
            earnings_date = r.get("earnings_date", "N/A")
            timing = r.get("earnings_timing", "unknown")
            sector = r.get("sector", "N/A")
            guidance = r.get("guidance", "")
            weakest = r.get("weakest_component", "N/A")
            strongest = r.get("strongest_component", "N/A")
            components = r.get("components", {})

            lines.append(f"### {symbol} - {company} (Grade {grade}, Score {score:.1f})")
            lines.append("")
            lines.append(f"- **Earnings Date:** {earnings_date} ({timing.upper()})")
            lines.append(f"- **Gap:** {gap_pct:+.1f}%")
            lines.append(f"- **Sector:** {sector}")
            lines.append(f"- **Strongest Factor:** {strongest}")
            lines.append(f"- **Weakest Factor:** {weakest}")
            lines.append(f"- **Guidance:** {guidance}")
            lines.append("")

            # Component scores
            lines.append("| Component | Score | Weight | Weighted |")
            lines.append("|-----------|-------|--------|----------|")
            breakdown = r.get("component_breakdown", {})
            for comp_name, comp_data in breakdown.items():
                lines.append(
                    f"| {comp_name} | {comp_data['score']:.0f} | "
                    f"{comp_data['weight']:.0%} | {comp_data['weighted_score']:.1f} |"
                )
            lines.append("")

    # Sector distribution
    sector_distribution = {}
    for r in all_results:
        sector = r.get("sector", "Unknown")
        sector_distribution[sector] = sector_distribution.get(sector, 0) + 1

    if sector_distribution:
        lines.append("## Sector Distribution")
        lines.append("")
        lines.append("| Sector | Count |")
        lines.append("|--------|-------|")
        for sector, count in sorted(sector_distribution.items(), key=lambda x: -x[1]):
            lines.append(f"| {sector} | {count} |")
        lines.append("")

    # Methodology reference
    lines.append("---")
    lines.append("")
    lines.append("*Scoring methodology reference: see `references/scoring_methodology.md`*")
    lines.append("")

    os.makedirs(
        os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path
