#!/usr/bin/env python3
"""
Uptrend Analyzer - Report Generator

Generates JSON and Markdown reports for uptrend breadth analysis.
"""

import json
from typing import Dict


def generate_json_report(analysis: Dict, output_file: str):
    """Save full analysis as JSON"""
    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"JSON report saved to: {output_file}")


def generate_markdown_report(analysis: Dict, output_file: str):
    """Generate comprehensive Markdown report"""
    lines = []
    composite = analysis.get("composite", {})
    components = analysis.get("components", {})
    metadata = analysis.get("metadata", {})

    score = composite.get("composite_score", 0)
    zone = composite.get("zone", "Unknown")
    exposure = composite.get("exposure_guidance", "N/A")

    # Header
    lines.append("# Uptrend Analyzer Report")
    lines.append("")
    lines.append(f"**Generated:** {metadata.get('generated_at', 'N/A')}")
    lines.append(f"**Data Source:** Monty's Uptrend Ratio Dashboard (GitHub CSV)")
    lines.append(f"**API Key Required:** No")
    lines.append("")

    # Overall Assessment
    lines.append("---")
    lines.append("")
    lines.append("## Overall Assessment")
    lines.append("")
    zone_emoji = _zone_emoji(composite.get("zone_color", ""))
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Composite Score** | **{score}/100** |")
    lines.append(f"| **Zone** | {zone_emoji} {zone} |")
    lines.append(f"| **Exposure Guidance** | {exposure} |")
    lines.append(f"| **Strongest Component** | {composite.get('strongest_component', {}).get('label', 'N/A')} "
                 f"({composite.get('strongest_component', {}).get('score', 0)}/100) |")
    lines.append(f"| **Weakest Component** | {composite.get('weakest_component', {}).get('label', 'N/A')} "
                 f"({composite.get('weakest_component', {}).get('score', 0)}/100) |")
    dq = composite.get("data_quality", {})
    if dq:
        lines.append(f"| **Data Quality** | {dq.get('label', 'N/A')} |")
    lines.append("")

    # Guidance
    lines.append(f"> **Guidance:** {composite.get('guidance', '')}")
    lines.append("")

    # Current Market Snapshot
    breadth = components.get("market_breadth", {})
    if breadth.get("data_available"):
        lines.append("---")
        lines.append("")
        lines.append("## Current Market Snapshot")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Uptrend Ratio | {breadth.get('ratio_pct', 'N/A')}% |")
        lines.append(f"| 10-Day MA | {breadth.get('ma_10_pct', 'N/A')}% |")
        lines.append(f"| Trend | {breadth.get('trend', 'N/A')} |")
        lines.append(f"| Slope | {_format_slope(breadth.get('slope'))} |")
        lines.append(f"| Distance from 37% (Overbought) | {_format_distance(breadth.get('distance_from_upper'))} |")
        lines.append(f"| Distance from 9.7% (Oversold) | {_format_distance(breadth.get('distance_from_lower'))} |")
        lines.append(f"| Date | {breadth.get('date', 'N/A')} |")
        lines.append("")

    # Component Scores Table
    lines.append("---")
    lines.append("")
    lines.append("## Component Scores")
    lines.append("")
    lines.append("| # | Component | Weight | Score | Contribution | Signal |")
    lines.append("|---|-----------|--------|-------|--------------|--------|")

    component_order = [
        "market_breadth", "sector_participation", "sector_rotation",
        "momentum", "historical_context",
    ]

    for i, key in enumerate(component_order, 1):
        comp = composite.get("component_scores", {}).get(key, {})
        detail = components.get(key, {})
        signal = detail.get("signal", "N/A")
        score_val = comp.get("score", 0)
        weight_pct = f"{comp.get('weight', 0)*100:.0f}%"
        contribution = comp.get("weighted_contribution", 0)
        bar = _score_bar(score_val)

        lines.append(f"| {i} | **{comp.get('label', key)}** | {weight_pct} | "
                     f"{bar} {score_val} | {contribution:.1f} | {signal} |")

    lines.append("")

    # Component Details
    lines.append("---")
    lines.append("")
    lines.append("## Component Details")
    lines.append("")

    # 1. Market Breadth
    lines.append("### 1. Market Breadth (Overall)")
    lines.append("")
    if breadth.get("data_available"):
        lines.append(f"- **Uptrend Ratio:** {breadth.get('ratio_pct', 'N/A')}%")
        lines.append(f"- **10-Day MA:** {breadth.get('ma_10_pct', 'N/A')}%")
        lines.append(f"- **Trend:** {breadth.get('trend', 'N/A')}")
        lines.append(f"- **Slope:** {_format_slope(breadth.get('slope'))}")
        lines.append(f"- **Trend Adjustment:** {breadth.get('trend_adjustment', 0):+d}")
    else:
        lines.append("- Data unavailable")
    lines.append("")

    # 2. Sector Participation
    participation = components.get("sector_participation", {})
    lines.append("### 2. Sector Participation")
    lines.append("")
    if participation.get("data_available"):
        lines.append(f"- **Uptrending Sectors:** {participation.get('uptrend_count', 0)}"
                     f"/{participation.get('total_sectors', 0)}")
        lines.append(f"- **Count Score:** {participation.get('count_score', 0)}/100")
        lines.append(f"- **Spread:** {participation.get('spread_pct', 'N/A')}% "
                     f"(score: {participation.get('spread_score', 0)}/100)")
        lines.append(f"- **Overbought ({'>'}37%):** {participation.get('overbought_count', 0)} "
                     f"sectors ({', '.join(participation.get('overbought_sectors', []))})")
        lines.append(f"- **Oversold ({'<'}9.7%):** {participation.get('oversold_count', 0)} "
                     f"sectors ({', '.join(participation.get('oversold_sectors', []))})")
    else:
        lines.append("- Data unavailable")
    lines.append("")

    # 3. Sector Rotation
    rotation = components.get("sector_rotation", {})
    lines.append("### 3. Sector Rotation")
    lines.append("")
    if rotation.get("data_available"):
        lines.append(f"- **Cyclical Avg:** {rotation.get('cyclical_avg_pct', 'N/A')}%")
        lines.append(f"- **Defensive Avg:** {rotation.get('defensive_avg_pct', 'N/A')}%")
        lines.append(f"- **Commodity Avg:** {rotation.get('commodity_avg_pct', 'N/A')}%")
        lines.append(f"- **Cyclical-Defensive Gap:** {rotation.get('difference_pct', 'N/A')}pp")
        if rotation.get("late_cycle_flag"):
            lines.append(f"- **Late Cycle Warning:** YES (commodity penalty: {rotation.get('commodity_penalty', 0)})")

        # Group detail tables
        for group_name, group_key in [("Cyclical", "cyclical_details"),
                                       ("Defensive", "defensive_details"),
                                       ("Commodity", "commodity_details")]:
            details = rotation.get(group_key, [])
            if details:
                lines.append(f"\n**{group_name} Sectors:**")
                lines.append("")
                lines.append("| Sector | Ratio | Trend | Slope |")
                lines.append("|--------|-------|-------|-------|")
                for d in details:
                    lines.append(f"| {d.get('sector', '')} | "
                                 f"{d.get('ratio_pct', 'N/A')}% | "
                                 f"{d.get('trend', 'N/A')} | "
                                 f"{_format_slope(d.get('slope'))} |")
                lines.append("")
    else:
        lines.append("- Data unavailable")
    lines.append("")

    # 4. Momentum
    momentum = components.get("momentum", {})
    lines.append("### 4. Momentum")
    lines.append("")
    if momentum.get("data_available"):
        lines.append(f"- **Current Slope:** {_format_slope(momentum.get('slope'))} "
                     f"(score: {momentum.get('slope_score', 0)}/100)")
        lines.append(f"- **Acceleration:** {momentum.get('acceleration', 'N/A')} "
                     f"({momentum.get('acceleration_label', 'N/A')}, "
                     f"score: {momentum.get('acceleration_score', 0)}/100)")
        lines.append(f"- **Sector Slope Breadth:** "
                     f"{momentum.get('sector_positive_slope_count', 0)}"
                     f"/{momentum.get('sector_total', 0)} positive "
                     f"(score: {momentum.get('sector_slope_breadth_score', 0)}/100)")
    else:
        lines.append("- Data unavailable")
    lines.append("")

    # 5. Historical Context
    historical = components.get("historical_context", {})
    lines.append("### 5. Historical Context")
    lines.append("")
    if historical.get("data_available"):
        lines.append(f"- **Current Ratio:** {historical.get('current_ratio_pct', 'N/A')}%")
        lines.append(f"- **Percentile Rank:** {historical.get('percentile', 'N/A')}th")
        lines.append(f"- **Historical Range:** "
                     f"{historical.get('historical_min_pct', 'N/A')}% - "
                     f"{historical.get('historical_max_pct', 'N/A')}%")
        lines.append(f"- **Historical Median:** {historical.get('historical_median_pct', 'N/A')}%")
        lines.append(f"- **30-Day Avg:** {historical.get('avg_30d_pct', 'N/A')}%")
        lines.append(f"- **90-Day Avg:** {historical.get('avg_90d_pct', 'N/A')}%")
        lines.append(f"- **Data Points:** {historical.get('data_points', 0)} "
                     f"({historical.get('date_range', 'N/A')})")
    else:
        lines.append("- Data unavailable")
    lines.append("")

    # Sector Heatmap Table
    sector_details = components.get("sector_participation", {}).get("sector_details", [])
    if sector_details:
        lines.append("---")
        lines.append("")
        lines.append("## Sector Heatmap")
        lines.append("")
        lines.append("| Rank | Sector | Ratio | 10MA | Trend | Slope | Status |")
        lines.append("|------|--------|-------|------|-------|-------|--------|")
        for i, s in enumerate(sector_details, 1):
            lines.append(f"| {i} | {s.get('sector', '')} | "
                         f"{s.get('ratio_pct', 'N/A')}% | "
                         f"{round(s['ma_10'] * 100, 1) if s.get('ma_10') is not None else 'N/A'}% | "
                         f"{s.get('trend', '')} | "
                         f"{_format_slope(s.get('slope'))} | "
                         f"{s.get('status', '')} |")
        lines.append("")

    # Recommended Actions
    lines.append("---")
    lines.append("")
    lines.append("## Recommended Actions")
    lines.append("")
    lines.append(f"**Zone:** {zone}")
    lines.append(f"**Exposure Guidance:** {exposure}")
    lines.append("")
    for action in composite.get("actions", []):
        lines.append(f"- {action}")
    lines.append("")

    # Active Warnings (overlay adjustments)
    active_warnings = composite.get("active_warnings", [])
    if active_warnings:
        lines.append("### Active Warnings")
        lines.append("")
        for warning in active_warnings:
            lines.append(f"**{warning.get('label', 'WARNING')}**")
            lines.append(f"> {warning.get('description', '')}")
            lines.append("")
            for action in warning.get("actions", []):
                lines.append(f"- {action}")
            lines.append("")

    # Methodology
    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("This analysis uses Monty's Uptrend Ratio Dashboard data to assess market breadth health.")
    lines.append("The dashboard tracks ~2,800 US stocks across 11 sectors, measuring the percentage in uptrends.")
    lines.append("")
    lines.append("**5-Component Scoring System (0-100, higher = healthier):**")
    lines.append("")
    lines.append("1. **Market Breadth (30%):** Overall uptrend ratio level and trend direction")
    lines.append("2. **Sector Participation (25%):** Number of uptrending sectors and spread uniformity")
    lines.append("3. **Sector Rotation (15%):** Cyclical vs Defensive vs Commodity balance")
    lines.append("4. **Momentum (20%):** Slope direction, acceleration, and sector slope breadth")
    lines.append("5. **Historical Context (10%):** Percentile rank in historical distribution")
    lines.append("")
    lines.append("**Key Thresholds (Monty's Dashboard):** Overbought = 37%, Oversold = 9.7%")
    lines.append("")
    lines.append("For detailed methodology, see `references/uptrend_methodology.md`.")
    lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append("**Disclaimer:** This analysis is for educational and informational purposes only. "
                 "Not investment advice. Past patterns may not predict future outcomes. "
                 "Conduct your own research and consult a financial advisor before making "
                 "investment decisions.")
    lines.append("")

    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))

    print(f"Markdown report saved to: {output_file}")


def _zone_emoji(color: str) -> str:
    mapping = {
        "green": "🟢",
        "light_green": "🟢",
        "yellow": "🟡",
        "orange": "🟠",
        "red": "🔴",
    }
    return mapping.get(color, "⚪")


def _score_bar(score: int) -> str:
    """Simple text bar for score visualization"""
    if score >= 80:
        return "████"
    elif score >= 60:
        return "███░"
    elif score >= 40:
        return "██░░"
    elif score >= 20:
        return "█░░░"
    else:
        return "░░░░"


def _format_slope(value) -> str:
    """Format slope value with 4 decimal places."""
    if value is None:
        return "N/A"
    return f"{value:+.4f}"


def _format_distance(value) -> str:
    """Format distance value as percentage points."""
    if value is None:
        return "N/A"
    pct = round(value * 100, 1)
    return f"{pct:+.1f}pp"
