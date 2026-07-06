#!/usr/bin/env python3
"""
PEAD Screener Report Generator

Generates JSON and Markdown reports for PEAD screening results.
Groups results by stage: BREAKOUT first, then SIGNAL_READY, MONITORING, EXPIRED.

Outputs:
- JSON: Structured data for programmatic use
- Markdown: Human-readable report with stage-grouped results
"""

import json

# Stage display order (highest priority first)
STAGE_ORDER = ["BREAKOUT", "SIGNAL_READY", "MONITORING", "EXPIRED"]

STAGE_DESCRIPTIONS = {
    "BREAKOUT": "Price has broken above the red candle high on a green weekly candle",
    "SIGNAL_READY": "Red candle pullback identified, awaiting breakout",
    "MONITORING": "Post-earnings gap-up, no red candle yet",
    "EXPIRED": "Beyond the monitoring window",
}


def generate_json_report(
    results: list[dict],
    metadata: dict,
    output_file: str,
) -> None:
    """Generate JSON report with PEAD screening results.

    Args:
        results: All screening results
        metadata: Screening metadata
        output_file: Output file path
    """
    # Group and sort by stage
    sorted_results = _sort_by_stage(results)

    # Generate summary
    summary = _generate_summary(results)

    report = {
        "metadata": metadata,
        "results": sorted_results,
        "summary": summary,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"  JSON report saved to: {output_file}")


def generate_markdown_report(
    results: list[dict],
    metadata: dict,
    output_file: str,
) -> None:
    """Generate Markdown report with PEAD screening results.

    Args:
        results: All screening results
        metadata: Screening metadata
        output_file: Output file path
    """
    lines = []

    # Header
    lines.append("# PEAD Screener Report - Post-Earnings Announcement Drift")
    lines.append(f"**Generated:** {metadata.get('generated_at', 'N/A')}")
    mode = metadata.get("mode", "A")
    mode_desc = "FMP Earnings Calendar" if mode == "A" else "Earnings Trade Analyzer JSON"
    lines.append(f"**Mode:** {mode} ({mode_desc})")
    lines.append(f"**Lookback:** {metadata.get('lookback_days', 'N/A')} days")
    lines.append(f"**Watch Window:** {metadata.get('watch_weeks', 'N/A')} weeks")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary
    summary = _generate_summary(results)
    lines.append("## Summary")
    lines.append("")
    lines.append("| Stage | Count |")
    lines.append("|-------|-------|")
    lines.append(f"| Total Screened | {summary['total_screened']} |")
    lines.append(f"| BREAKOUT | {summary['breakout']} |")
    lines.append(f"| SIGNAL_READY | {summary['signal_ready']} |")
    lines.append(f"| MONITORING | {summary['monitoring']} |")
    lines.append(f"| EXPIRED | {summary['expired']} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Group results by stage
    stage_groups = {}
    for stage in STAGE_ORDER:
        stage_groups[stage] = [r for r in results if r.get("stage") == stage]

    # Render each stage section
    for stage in STAGE_ORDER:
        group = stage_groups.get(stage, [])
        # Sort by composite score within each stage
        group.sort(key=lambda x: x.get("composite_score", 0), reverse=True)

        stage_desc = STAGE_DESCRIPTIONS.get(stage, "")
        count_label = f"{len(group)} stock{'s' if len(group) != 1 else ''}"
        lines.append(f"## {stage} ({count_label})")
        lines.append(f"*{stage_desc}*")
        lines.append("")

        if group:
            for i, stock in enumerate(group, 1):
                lines.extend(_format_stock_entry(i, stock))
        else:
            lines.append("No stocks in this stage.")
            lines.append("")

        lines.append("---")
        lines.append("")

    # API usage
    api_stats = metadata.get("api_stats", {})
    if api_stats:
        lines.append("## API Usage")
        lines.append(f"- **API Calls Made:** {api_stats.get('api_calls_made', 'N/A')}")
        lines.append(f"- **Budget Remaining:** {api_stats.get('budget_remaining', 'N/A')}")
        lines.append(f"- **Cache Entries:** {api_stats.get('cache_entries', 'N/A')}")
        lines.append("")

    # Methodology
    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("This screener identifies Post-Earnings Announcement Drift (PEAD) setups:")
    lines.append("")
    lines.append("1. **Setup Quality** (30%) - Earnings gap quality and weekly pattern formation")
    lines.append(
        "2. **Breakout Strength** (25%) - Price breakout above red candle high with volume"
    )
    lines.append("3. **Liquidity** (25%) - ADV20, average volume, and price thresholds")
    lines.append("4. **Risk/Reward** (20%) - Entry/stop/target risk-reward ratio")
    lines.append("")
    lines.append(
        "For detailed methodology, see the PEAD strategy reference in the pead-screener skill directory."
    )
    lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append(
        "**Disclaimer:** This screener is for educational and informational purposes only. "
        "Not investment advice. Always conduct your own research and consult a financial "
        "advisor before making investment decisions. Past patterns do not guarantee future results."
    )
    lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  Markdown report saved to: {output_file}")


def _format_stock_entry(rank: int, stock: dict) -> list[str]:
    """Format a single stock entry for the Markdown report."""
    lines = []

    # Header with rating indicator
    rating = stock.get("rating", "N/A")
    indicator = _rating_indicator(stock.get("composite_score", 0))
    symbol = stock.get("symbol", "???")
    stage = stock.get("stage", "UNKNOWN")
    lines.append(f"### {rank}. {symbol} {indicator}")

    # Basic info
    price = stock.get("current_price", 0) or 0
    earnings_date = stock.get("earnings_date", "N/A")
    gap_pct = stock.get("gap_pct", 0) or 0
    timing = stock.get("earnings_timing", "N/A")
    weeks = stock.get("weeks_since_earnings", 0)
    lines.append(
        f"**Price:** ${price:.2f} | **Earnings:** {earnings_date} ({timing}) | "
        f"**Gap:** {gap_pct:+.1f}% | **Weeks Since:** {weeks}"
    )

    # Composite score
    lines.append(f"**PEAD Score:** {stock.get('composite_score', 0):.1f}/100 ({rating})")
    lines.append("")

    # Component breakdown table
    components = stock.get("components", {})
    if components:
        lines.append("| Component | Score | Weight | Weighted |")
        lines.append("|-----------|-------|--------|----------|")
        for key, comp in components.items():
            label = comp.get("label", key)
            score = comp.get("score", 0)
            weight = comp.get("weight", 0)
            weighted = comp.get("weighted", 0)
            lines.append(f"| {label} | {score:.0f} | {weight:.0%} | {weighted:.1f} |")
        lines.append("")

    # Red candle info
    red_candle = stock.get("red_candle")
    if red_candle:
        rc_high = red_candle.get("high", 0)
        rc_low = red_candle.get("low", 0)
        rc_week = red_candle.get("week_start", "N/A")
        lines.append(
            f"**Red Candle:** Week of {rc_week} | High: ${rc_high:.2f} | Low: ${rc_low:.2f}"
        )
    else:
        lines.append("**Red Candle:** Not yet formed")

    # Trade setup
    lines.append("")
    lines.append("**Trade Setup:**")

    if stage == "BREAKOUT":
        entry = stock.get("entry_price", price)
        stop = stock.get("stop_price", 0)
        target = stock.get("target_price", 0)
        rr = stock.get("risk_reward_ratio", 0)
        breakout_pct = stock.get("breakout_pct", 0)
        lines.append(f"- Entry: ${entry:.2f} (breakout +{breakout_pct:.1f}% above red candle high)")
        lines.append(f"- Stop: ${stop:.2f} (red candle low)")
        lines.append(f"- Target: ${target:.2f} (2R)")
        lines.append(f"- Risk/Reward: {rr:.1f}:1")
    elif stage == "SIGNAL_READY":
        if red_candle:
            lines.append(f"- Trigger: Close above ${red_candle['high']:.2f} on green weekly candle")
            lines.append(f"- Stop (if triggered): ${red_candle['low']:.2f}")
        lines.append("- Action: Set alert at red candle high")
    elif stage == "MONITORING":
        lines.append("- Action: Monitor for red candle formation")
    else:
        lines.append("- Action: Remove from watchlist (expired)")

    guidance = stock.get("guidance", "N/A")
    lines.append(f"- Guidance: {guidance}")
    lines.append("")
    lines.append("---")
    lines.append("")

    return lines


def _rating_indicator(score: float) -> str:
    """Get indicator for rating."""
    if score >= 85:
        return "[STRONG]"
    elif score >= 70:
        return "[GOOD]"
    elif score >= 55:
        return "[DEVELOPING]"
    else:
        return ""


def _sort_by_stage(results: list[dict]) -> list[dict]:
    """Sort results by stage priority, then by composite score within each stage."""
    stage_priority = {stage: i for i, stage in enumerate(STAGE_ORDER)}

    def sort_key(r):
        stage = r.get("stage", "EXPIRED")
        priority = stage_priority.get(stage, len(STAGE_ORDER))
        score = r.get("composite_score", 0)
        return (priority, -score)

    return sorted(results, key=sort_key)


def _generate_summary(results: list[dict]) -> dict:
    """Generate summary statistics from results."""
    total = len(results)
    breakout = sum(1 for r in results if r.get("stage") == "BREAKOUT")
    signal_ready = sum(1 for r in results if r.get("stage") == "SIGNAL_READY")
    monitoring = sum(1 for r in results if r.get("stage") == "MONITORING")
    expired = sum(1 for r in results if r.get("stage") == "EXPIRED")

    return {
        "total_screened": total,
        "breakout": breakout,
        "signal_ready": signal_ready,
        "monitoring": monitoring,
        "expired": expired,
    }
