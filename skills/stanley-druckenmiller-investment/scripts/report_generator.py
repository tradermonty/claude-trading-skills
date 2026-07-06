#!/usr/bin/env python3
"""
Strategy Synthesizer - Report Generator

Generates JSON and Markdown reports for the Druckenmiller strategy analysis.

The Markdown output structure follows the specification defined in:
    assets/strategy_report_template.md
"""

import json


def generate_json_report(analysis: dict, output_file: str):
    """Save full analysis as JSON."""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"JSON report saved to: {output_file}")


def generate_markdown_report(analysis: dict, output_file: str):
    """Generate comprehensive Markdown report."""
    lines = []
    metadata = analysis.get("metadata", {})
    conviction = analysis.get("conviction", {})
    pattern = analysis.get("pattern", {})
    allocation = analysis.get("allocation", {})
    sizing = analysis.get("position_sizing", {})
    input_summary = analysis.get("input_summary", {})
    component_scores = conviction.get("component_scores", {})

    score = conviction.get("conviction_score", 0)
    zone = conviction.get("zone", "Unknown")
    zone_color = conviction.get("zone_color", "")

    # ================================================================
    # Header
    # ================================================================
    lines.append("# Druckenmiller Strategy Synthesizer Report")
    lines.append("")
    lines.append(f"**Generated:** {metadata.get('generated_at', 'N/A')}")
    lines.append(
        f"**Input Skills:** {metadata.get('skills_loaded', 0)} loaded "
        f"({metadata.get('required_count', 0)} required + "
        f"{metadata.get('optional_count', 0)} optional)"
    )
    lines.append("")

    # ================================================================
    # Section 1: Conviction Dashboard
    # ================================================================
    lines.append("---")
    lines.append("")
    lines.append("## 1. Conviction Dashboard")
    lines.append("")

    zone_emoji = _zone_emoji(zone_color)

    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Conviction Score** | {zone_emoji} **{score}/100** |")
    lines.append(f"| **Zone** | {zone} |")
    lines.append(f"| **Recommended Exposure** | {conviction.get('exposure_range', 'N/A')} |")
    strongest = conviction.get("strongest_component", {})
    weakest = conviction.get("weakest_component", {})
    lines.append(
        f"| **Strongest Component** | {strongest.get('label', 'N/A')} ({strongest.get('score', 0)}) |"
    )
    lines.append(
        f"| **Weakest Component** | {weakest.get('label', 'N/A')} ({weakest.get('score', 0)}) |"
    )
    lines.append("")

    lines.append(f"> **Guidance:** {conviction.get('guidance', '')}")
    lines.append("")

    # Actions
    actions = conviction.get("actions", [])
    if actions:
        lines.append("**Recommended Actions:**")
        lines.append("")
        for action in actions:
            lines.append(f"- {action}")
        lines.append("")

    # ================================================================
    # Section 2: Pattern Classification
    # ================================================================
    lines.append("---")
    lines.append("")
    lines.append("## 2. Pattern Classification")
    lines.append("")

    pattern_label = pattern.get("label", "Unknown")
    match_strength = pattern.get("match_strength", 0)
    lines.append(f"**Detected Pattern:** {pattern_label} (match: {match_strength}%)")
    lines.append("")
    lines.append(f"> {pattern.get('description', '')}")
    lines.append("")

    # All pattern scores
    all_scores = pattern.get("all_pattern_scores", {})
    if all_scores:
        lines.append("| Pattern | Match Score |")
        lines.append("|---------|-----------|")
        for p_name, p_score in sorted(all_scores.items(), key=lambda x: -x[1]):
            marker = " **DETECTED**" if p_name == pattern.get("pattern") else ""
            lines.append(f"| {p_name.replace('_', ' ').title()} | {p_score}{marker} |")
        lines.append("")

    # ================================================================
    # Section 3: Component Scores
    # ================================================================
    lines.append("---")
    lines.append("")
    lines.append("## 3. Component Scores (7 Components)")
    lines.append("")
    lines.append("| # | Component | Weight | Eff. Weight | Score | Weighted |")
    lines.append("|---|-----------|--------|-------------|-------|----------|")

    for i, (key, comp) in enumerate(component_scores.items(), 1):
        comp_score = comp.get("score", 0)
        weight = comp.get("weight", 0)
        eff_weight = comp.get("effective_weight", weight)
        available = comp.get("available", True)
        weighted = comp.get("weighted_contribution", 0)
        label = comp.get("label", key)
        if not available:
            label = f"{label} (N/A)"
        bar = _score_bar(comp_score)
        lines.append(
            f"| {i} | {label} | {weight * 100:.0f}% | {eff_weight * 100:.1f}% | {bar} {comp_score} | {weighted} |"
        )

    lines.append(f"| | **TOTAL** | **100%** | **100%** | | **{score}** |")
    lines.append("")

    # ================================================================
    # Section 4: Input Skills Summary
    # ================================================================
    lines.append("---")
    lines.append("")
    lines.append("## 4. Input Skills Summary")
    lines.append("")

    required_keys = [
        "market_breadth",
        "uptrend_analysis",
        "market_top",
        "macro_regime",
        "ftd_detector",
    ]
    optional_keys = ["vcp_screener", "theme_detector", "canslim_screener"]

    lines.append("### Required Skills")
    lines.append("")
    lines.append("| Skill | Score | Zone/State | Key Signal |")
    lines.append("|-------|-------|-----------|------------|")
    for key in required_keys:
        sig = input_summary.get(key, {})
        sig_score = sig.get("composite_score", sig.get("quality_score", "N/A"))
        zone_or_state = sig.get("zone", sig.get("state", "N/A"))
        key_signal = _format_key_signal(key, sig)
        lines.append(
            f"| {key.replace('_', ' ').title()} | {sig_score} | {zone_or_state} | {key_signal} |"
        )
    lines.append("")

    lines.append("### Optional Skills")
    lines.append("")
    lines.append("| Skill | Score | Key Signal |")
    lines.append("|-------|-------|------------|")
    for key in optional_keys:
        sig = input_summary.get(key, {})
        if sig:
            sig_score = sig.get("derived_score", "N/A")
            key_signal = _format_key_signal(key, sig)
            lines.append(f"| {key.replace('_', ' ').title()} | {sig_score} | {key_signal} |")
        else:
            lines.append(f"| {key.replace('_', ' ').title()} | -- | Not available |")
    lines.append("")

    # ================================================================
    # Section 5: Target Allocation
    # ================================================================
    lines.append("---")
    lines.append("")
    lines.append("## 5. Target Allocation")
    lines.append("")

    target = allocation.get("target", {})
    lines.append("| Asset Class | Allocation |")
    lines.append("|-------------|-----------|")
    for asset in ["equity", "bonds", "alternatives", "cash"]:
        pct = target.get(asset, 0)
        bar = _alloc_bar(pct)
        lines.append(f"| {asset.title()} | {bar} {pct}% |")
    lines.append("")

    # ================================================================
    # Section 6: Position Sizing & Risk
    # ================================================================
    lines.append("---")
    lines.append("")
    lines.append("## 6. Position Sizing & Risk")
    lines.append("")

    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| Max Single Position | {sizing.get('max_single_position', 'N/A')}% |")
    lines.append(f"| Daily Volatility Target | {sizing.get('daily_vol_target', 'N/A')}% |")
    lines.append(f"| Max Open Positions | {sizing.get('max_positions', 'N/A')} |")
    lines.append("")

    # ================================================================
    # Section 7: Druckenmiller Principle
    # ================================================================
    lines.append("---")
    lines.append("")
    lines.append("## 7. Druckenmiller Principle")
    lines.append("")

    principle = _select_principle(zone, pattern.get("pattern", ""))
    lines.append(f'> *"{principle["quote"]}"*')
    lines.append(">")
    lines.append("> — Stanley Druckenmiller")
    lines.append("")
    lines.append(f"**Application:** {principle['application']}")
    lines.append("")

    # ================================================================
    # Methodology
    # ================================================================
    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "This report synthesizes outputs from 8 upstream analysis skills "
        "(5 required + 3 optional) into a single conviction score using "
        "Stanley Druckenmiller's investment philosophy."
    )
    lines.append("")
    lines.append("**7 Components** (weighted 0-100):")
    lines.append("")
    lines.append("1. Market Structure (18%): Breadth + Uptrend health")
    lines.append("2. Distribution Risk (18%): Market Top risk (inverted)")
    lines.append("3. Bottom Confirmation (12%): FTD Detector re-entry signal")
    lines.append("4. Macro Alignment (18%): Macro Regime positioning")
    lines.append("5. Theme Quality (12%): Theme Detector momentum")
    lines.append("6. Setup Availability (10%): VCP + CANSLIM setups")
    lines.append("7. Signal Convergence (12%): Cross-skill agreement")
    lines.append("")
    lines.append(
        "**4 Patterns:** Policy Pivot Anticipation, Unsustainable Distortion, "
        "Extreme Sentiment Contrarian, Wait & Observe"
    )
    lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append(
        "**Disclaimer:** This analysis is for educational and informational purposes only. "
        "Not investment advice. Past performance does not guarantee future results. "
        "Conduct your own research and consult a financial advisor before making "
        "investment decisions."
    )
    lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Markdown report saved to: {output_file}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _zone_emoji(color: str) -> str:
    mapping = {
        "green": "🟢",
        "light_green": "🟢",
        "yellow": "🟡",
        "orange": "🟠",
        "red": "🔴",
    }
    return mapping.get(color, "⚪")


def _score_bar(score: float) -> str:
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


def _alloc_bar(pct: float) -> str:
    filled = int(pct / 10)
    empty = 10 - filled
    return "█" * filled + "░" * empty


def _format_key_signal(skill: str, sig: dict) -> str:
    """Format a one-line key signal per skill."""
    if skill == "market_breadth":
        return f"Zone: {sig.get('zone', 'N/A')}"
    elif skill == "uptrend_analysis":
        return f"Zone: {sig.get('zone', 'N/A')}"
    elif skill == "market_top":
        return f"Risk: {sig.get('zone', 'N/A')}"
    elif skill == "macro_regime":
        return f"Regime: {sig.get('regime', 'N/A')} ({sig.get('confidence', 'N/A')})"
    elif skill == "ftd_detector":
        return f"State: {sig.get('state', 'N/A')}, Quality: {sig.get('quality_score', 0)}"
    elif skill == "vcp_screener":
        return f"Textbook: {sig.get('textbook_count', 0)}, Strong: {sig.get('strong_count', 0)}"
    elif skill == "theme_detector":
        return f"Hot: {sig.get('hot_count', 0)}, Exhausting: {sig.get('exhaustion_count', 0)}"
    elif skill == "canslim_screener":
        return (
            f"M Score: {sig.get('m_score', 'N/A')}, Exceptional: {sig.get('exceptional_count', 0)}"
        )
    return "N/A"


def _select_principle(zone: str, pattern: str) -> dict:
    """Select a relevant Druckenmiller quote for the current situation."""
    if zone == "Maximum Conviction":
        return {
            "quote": "The way to build long-term returns is through preservation of "
            "capital and home runs. When you have tremendous conviction on a "
            "trade, you have to go for the jugular.",
            "application": "All signals aligned. This is the moment to concentrate "
            "positions and size up aggressively.",
        }
    elif pattern == "extreme_sentiment_contrarian":
        return {
            "quote": "I've made most of my money in bear markets. The biggest "
            "opportunities come when everyone is running for the exits.",
            "application": "FTD confirmed after extreme pessimism. Consider aggressive "
            "re-entry as the bottom forms.",
        }
    elif pattern == "unsustainable_distortion":
        return {
            "quote": "It's not whether you're right or wrong that's important, "
            "but how much money you make when you're right and how much "
            "you lose when you're wrong.",
            "application": "Distribution signals mounting. Reduce exposure, tighten "
            "stops, and preserve capital for the next opportunity.",
        }
    elif zone == "Capital Preservation":
        return {
            "quote": "The first thing I heard when I got in the business was bulls "
            "make money, bears make money, and pigs get slaughtered. "
            "I'm here to tell you I was a pig.",
            "application": "Conditions are hostile. Sit on the sidelines and wait. "
            "The best trade is sometimes no trade.",
        }
    elif pattern == "policy_pivot_anticipation":
        return {
            "quote": "Earnings don't move the overall market; it's the Federal "
            "Reserve Board... focus on the central banks, and focus on "
            "the movement of liquidity.",
            "application": "Macro regime is transitioning. Position ahead of the "
            "policy pivot for asymmetric upside.",
        }
    else:
        return {
            "quote": "Don't invest in the present; invest in what you think the "
            "world will look like in 18 months.",
            "application": "Signals are mixed. Maintain discipline, stay patient, "
            "and wait for a clearer setup.",
        }
