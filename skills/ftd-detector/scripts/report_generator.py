#!/usr/bin/env python3
"""
FTD Detector - Report Generator

Generates JSON and Markdown reports for FTD detection analysis.
"""

import json
import math

# Headline for a run whose combined state is unavailable (issue #655)
DATA_GAP_STATE_LABEL = "State unavailable (data gap)"


def generate_json_report(analysis: dict, output_file: str):
    """Save full analysis as JSON."""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"  JSON report saved to: {output_file}")


def generate_markdown_report(analysis: dict, output_file: str):
    """Generate comprehensive Markdown report."""
    lines = []
    metadata = analysis.get("metadata", {})
    ms = analysis.get("market_state", {})
    sp500 = analysis.get("sp500", {})
    nasdaq = analysis.get("nasdaq", {})
    quality = analysis.get("quality_score", {})
    post_dist = analysis.get("post_ftd_distribution", {})
    inv = analysis.get("ftd_invalidation", {})
    pt = analysis.get("power_trend", {})

    combined_state = ms.get("combined_state", "UNKNOWN")
    total_score = quality.get("total_score", 0)
    signal = quality.get("signal", "N/A")
    # Issue #655: the quality score is Unavailable (int 0) when its inputs had a gap
    quality_gap = bool(quality.get("data_gap"))
    # Under a data gap the combined state is reported as NO_SIGNAL = unavailable
    state_gap = quality_gap or bool(analysis.get("data_gap")) or bool(ms.get("data_gap"))
    data_quality_line = _data_quality_line(analysis)

    # Header
    lines.append("# FTD Detector Report")
    lines.append("")
    lines.append(f"**Generated:** {metadata.get('generated_at', 'N/A')}")
    prices = metadata.get("index_prices", {})
    if prices.get("sp500"):
        lines.append(f"**S&P 500:** ${prices['sp500']:.2f}")
    if prices.get("qqq"):
        lines.append(f"**QQQ:** ${prices['qqq']:.2f}")
    lines.append("")

    # ── Market Timing Status ─────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Market Timing Status")
    lines.append("")

    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    if state_gap:
        # Never the green/normal "No Signal (Uptrend)" label for a gapped run
        lines.append(f"| **Current State** | ⚠️ **{DATA_GAP_STATE_LABEL}** |")
    else:
        state_emoji = _state_emoji(combined_state)
        lines.append(f"| **Current State** | {state_emoji} **{_state_label(combined_state)}** |")
    lines.append(f"| **Quality Score** | **{total_score}/100** |")
    lines.append(f"| **Signal** | {signal} |")
    lines.append(f"| **Exposure Guidance** | {quality.get('exposure_range', 'N/A')} |")
    if ms.get("dual_confirmation"):
        lines.append("| **Dual Confirmation** | YES (S&P 500 + NASDAQ) |")
    elif ms.get("ftd_index"):
        lines.append(f"| **FTD Index** | {ms['ftd_index']} |")
    lines.append("")

    lines.append(f"> **Guidance:** {quality.get('guidance', 'N/A')}")
    lines.append("")
    if data_quality_line:
        lines.append(data_quality_line)
        lines.append("")

    # ── Index Status Table ────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Index Status")
    lines.append("")
    lines.append("| Index | State | Current | High | Correction | Swing Low |")
    lines.append("|-------|-------|---------|------|------------|-----------|")

    for label, data in [("S&P 500", sp500), ("NASDAQ/QQQ", nasdaq)]:
        state = data.get("state", "N/A")
        current = f"${data['current_price']:.2f}" if data.get("current_price") else "N/A"
        high = f"${data['lookback_high']:.2f}" if data.get("lookback_high") else "N/A"
        corr = (
            f"{data['correction_depth_pct']:.1f}%"
            if data.get("correction_depth_pct") is not None
            else "N/A"
        )
        swing = data.get("swing_low", {})
        sl_str = f"{swing.get('date', 'N/A')} (${swing.get('price', 0):.2f})" if swing else "None"
        lines.append(f"| {label} | {state} | {current} | {high} | {corr} | {sl_str} |")

    lines.append("")

    # ── Rally Attempt Details ─────────────────────────────────────────────
    has_rally = False
    for _label, data in [("S&P 500", sp500), ("NASDAQ/QQQ", nasdaq)]:
        rally = data.get("rally_attempt", {})
        if rally and rally.get("day1_date"):
            has_rally = True

    if has_rally:
        lines.append("---")
        lines.append("")
        lines.append("## Rally Attempt Details")
        lines.append("")

        for label, data in [("S&P 500", sp500), ("NASDAQ/QQQ", nasdaq)]:
            rally = data.get("rally_attempt", {})
            swing = data.get("swing_low", {})
            if not rally or not rally.get("day1_date"):
                continue

            lines.append(f"### {label}")
            lines.append("")
            lines.append(
                f"- **Swing Low:** {swing.get('date', 'N/A')} "
                f"(${swing.get('price', 0):.2f}, {swing.get('decline_pct', 0):.1f}% decline)"
            )
            lines.append(f"- **Rally Day 1:** {rally.get('day1_date', 'N/A')}")
            lines.append(f"- **Current Day Count:** {rally.get('current_day_count', 0)}")

            if rally.get("invalidated"):
                lines.append(f"- **INVALIDATED:** {rally.get('invalidation_reason', 'N/A')}")
            lines.append("")

    # ── FTD Signal ────────────────────────────────────────────────────────
    sp_ftd = sp500.get("ftd", {})
    nq_ftd = nasdaq.get("ftd", {})
    has_ftd = (sp_ftd and sp_ftd.get("ftd_detected")) or (nq_ftd and nq_ftd.get("ftd_detected"))

    if has_ftd:
        lines.append("---")
        lines.append("")
        lines.append("## FTD Signal")
        lines.append("")

        for label, ftd_data in [("S&P 500", sp_ftd), ("NASDAQ/QQQ", nq_ftd)]:
            if not ftd_data or not ftd_data.get("ftd_detected"):
                continue

            lines.append(f"### {label} FTD")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| **FTD Date** | {ftd_data.get('ftd_date', 'N/A')} |")
            lines.append(f"| **Day Number** | Day {ftd_data.get('ftd_day_number', 'N/A')} |")
            lines.append(
                f"| **Price Gain** | +{ftd_data.get('gain_pct', 0):.2f}% "
                f"({ftd_data.get('gain_tier', 'N/A')}) |"
            )
            vol_above = ftd_data.get("volume_above_avg")
            if vol_above is not None:
                vol_str = "Above 50-day avg" if vol_above else "Below 50-day avg"
            else:
                vol_str = "N/A"
            lines.append(f"| **Volume** | {vol_str} |")
            lines.append("")

    # ── Quality Score Breakdown ───────────────────────────────────────────
    if quality.get("breakdown"):
        lines.append("---")
        lines.append("")
        lines.append("## Quality Score Breakdown")
        lines.append("")
        lines.append(f"**Total: {total_score}/100**")
        lines.append("")
        lines.append("| Factor | Detail |")
        lines.append("|--------|--------|")

        for key, detail in quality.get("breakdown", {}).items():
            lines.append(f"| {key.replace('_', ' ').title()} | {detail} |")
        lines.append("")

    # ── Post-FTD Health ───────────────────────────────────────────────────
    if post_dist or inv or pt:
        lines.append("---")
        lines.append("")
        lines.append("## Post-FTD Health")
        lines.append("")

        if post_dist and post_dist.get("data_gap"):
            lines.append(
                "- **Distribution Days Since FTD:** "
                f"Unavailable ({post_dist.get('reason', 'data gap')})"
            )
        elif post_dist:
            dist_count = post_dist.get("distribution_count", 0)
            monitored = post_dist.get("days_monitored", 0)
            lines.append(
                f"- **Distribution Days Since FTD:** {dist_count} (in {monitored} days monitored)"
            )
            for d in post_dist.get("details", []):
                lines.append(
                    f"  - Day {d['day']}: {d['date']} "
                    f"({d['change_pct']:+.2f}%, vol {d['volume_change_pct']:+.1f}%)"
                )

        if inv:
            if inv.get("invalidated"):
                lines.append(
                    f"- **FTD INVALIDATED** on {inv.get('invalidation_date')} "
                    f"(Day {inv.get('days_after_ftd')}, close "
                    f"{_money(inv.get('invalidation_close'))} "
                    f"below FTD low {_money(inv.get('ftd_low'))})"
                )
            elif "invalidated" in inv and inv["invalidated"] is None:
                lines.append(f"- **FTD Valid:** Unavailable ({inv.get('reason', 'data gap')})")
            else:
                lines.append(
                    f"- **FTD Valid:** {inv.get('days_since_ftd', 0)} days since FTD "
                    f"(FTD low: {_money(inv.get('ftd_low'))})"
                )

        if pt and "power_trend" in pt and pt["power_trend"] is None:
            lines.append(f"- **Power Trend:** Unavailable ({pt.get('reason', 'data gap')})")
        elif pt:
            pt_status = "YES" if pt.get("power_trend") else "No"
            lines.append(
                f"- **Power Trend:** {pt_status} ({pt.get('conditions_met', 0)}/3 conditions)"
            )
            if pt.get("ema_21") is not None:
                lines.append(
                    f"  - 21 EMA: ${pt['ema_21']:.2f} "
                    f"({'>' if pt.get('ema_above_sma') else '<'} 50 SMA: ${pt.get('sma_50', 0):.2f})"
                )
                lines.append(f"  - 50 SMA Rising: {'Yes' if pt.get('sma_50_rising') else 'No'}")
                lines.append(
                    f"  - Price above 21 EMA: {'Yes' if pt.get('price_above_21ema') else 'No'}"
                )

        lines.append("")

    # ── Action Guidance ───────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Action Guidance")
    lines.append("")

    exposure = quality.get("exposure_range", "N/A")
    lines.append(f"**Recommended Exposure:** {exposure}")
    lines.append("")

    if state_gap:
        # Checked first: a gapped signal must never read as a buy or "normal" market
        lines.append(
            "- Data gap: confirmation unavailable — do not increase exposure on this signal"
        )
        lines.append(f"- Reason: {quality.get('reason', 'missing or invalid price data')}")
        lines.append("- Stay at defensive exposure until a clean data run confirms the state")
        lines.append("- Re-run once the data provider has backfilled the missing bars")
    elif combined_state == "FTD_CONFIRMED" and total_score >= 80:
        lines.append("- Aggressively increase equity exposure")
        lines.append("- Buy leading stocks breaking out of proper bases")
        lines.append("- Use FTD day's low as stop-loss reference")
        lines.append("- Monitor for distribution days (early distribution = caution)")
    elif combined_state == "FTD_CONFIRMED" and total_score >= 60:
        lines.append("- Gradually increase exposure with each successful breakout")
        lines.append("- Start with half positions, add on confirmation")
        lines.append("- Use FTD day's low as invalidation level")
        lines.append("- Watch for distribution within 3 days (bearish)")
    elif combined_state == "FTD_CONFIRMED":
        lines.append("- Cautious exposure increase with tight stops")
        lines.append("- Only buy highest-quality setups")
        lines.append("- Small position sizes (25-50% of normal)")
        lines.append("- Be prepared for FTD failure")
    elif combined_state == "FTD_WINDOW":
        lines.append("- WATCH MODE: FTD window is open (Day 4-10)")
        lines.append("- Prepare buy lists of leading stocks in bases")
        lines.append("- Do not buy ahead of FTD confirmation")
        lines.append("- Monitor daily for qualifying FTD day")
    elif combined_state == "RALLY_ATTEMPT":
        lines.append("- Rally attempt in progress (Day 1-3)")
        lines.append("- Too early to act - wait for Day 4+")
        lines.append("- Prepare watchlists, research leaders")
        lines.append("- Monitor for rally failure (close below swing low)")
    elif combined_state == "CORRECTION":
        lines.append("- Market in correction, no rally attempt yet")
        lines.append("- Stay defensive, preserve capital")
        lines.append("- Build watchlists of relative strength leaders")
        lines.append("- Wait for first up day to start rally count")
    elif combined_state == "FTD_INVALIDATED":
        lines.append("- FTD has been invalidated - signal failed")
        lines.append("- Reduce exposure back to defensive levels")
        lines.append("- Wait for new swing low and fresh rally attempt")
        lines.append("- Do not try to anticipate next FTD")
    elif combined_state == "RALLY_FAILED":
        lines.append("- Rally attempt failed (broke below swing low)")
        lines.append("- Remain in cash/defensive")
        lines.append("- New swing low may form - reset cycle")
        lines.append("- Patience is key; do not force entries")
    else:
        lines.append("- No correction detected - normal market conditions")
        lines.append("- FTD monitoring not applicable in uptrend")
        lines.append("- Focus on individual stock setups")
        lines.append("- Use Market Top Detector for defensive signals")

    lines.append("")

    # ── Key Watch Levels ──────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Key Watch Levels")
    lines.append("")

    for label, data in [("S&P 500", sp500), ("NASDAQ/QQQ", nasdaq)]:
        swing = data.get("swing_low", {})
        ftd_data = data.get("ftd", {})

        if not swing and not ftd_data:
            continue

        lines.append(f"**{label}:**")
        if swing:
            lines.append(f"- Swing Low: ${swing.get('price', 0):.2f} ({swing.get('date', 'N/A')})")
        if ftd_data and ftd_data.get("ftd_detected"):
            lines.append(f"- FTD Day: {ftd_data.get('ftd_date', 'N/A')}")
            if ftd_data.get("ftd_low"):
                lines.append(f"- FTD Day Low (invalidation level): ${ftd_data['ftd_low']:.2f}")
        if data.get("lookback_high"):
            lines.append(f"- Lookback High: ${data['lookback_high']:.2f}")
        lines.append("")

    # ── Methodology ───────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "This analysis uses William O'Neil's Follow-Through Day (FTD) methodology "
        "to confirm market bottoms:"
    )
    lines.append("")
    lines.append("1. **Swing Low Detection:** 3%+ decline from recent high with 3+ down days")
    lines.append("2. **Rally Attempt:** Day 1 (first up close), Day 2-3 must hold Day 1 low")
    lines.append("3. **FTD (Day 4-10):** 1.25%+ gain on volume higher than previous day")
    lines.append(
        "4. **Quality Score:** Multi-factor 0-100 score (day timing, gain size, "
        "volume, dual-index, post-FTD health)"
    )
    lines.append(
        "5. **Post-FTD Monitoring:** Distribution day tracking, invalidation check, "
        "Power Trend confirmation"
    )
    lines.append("")
    lines.append(
        "Dual-index tracking (S&P 500 + NASDAQ) provides stronger confirmation "
        "than single-index analysis."
    )
    lines.append("")
    lines.append("For detailed methodology, see `references/ftd_methodology.md`.")
    lines.append("")

    # ── Disclaimer ────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append(
        "**Disclaimer:** This analysis is for educational and informational purposes only. "
        "Not investment advice. Follow-Through Days have approximately a 25% success rate "
        "historically. Always use proper risk management and position sizing. "
        "Consult a financial advisor before making investment decisions."
    )
    lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  Markdown report saved to: {output_file}")


def _money(value) -> str:
    """Format a price, rendering a missing or non-finite value as N/A (never None)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return "$N/A"
    return f"${value:.2f}"


def _data_quality_line(analysis: dict) -> str:
    """One-line data-quality note, or "" on a clean run (keeps clean Markdown unchanged)."""
    data_quality = analysis.get("data_quality") or {}
    parts = []
    for label, key in (("S&P 500", "sp500"), ("NASDAQ", "nasdaq")):
        index = analysis.get(key) or {}
        dq = data_quality.get(key) or index.get("data_quality") or {}
        notes = []
        if index.get("data_gap") and index.get("error"):
            notes.append(index["error"])
        elif dq.get("bad_bars"):
            notes.append(
                f"{dq['bad_bars']} bad bar(s) in the {dq.get('window_sessions')}-session window "
                f"(latest bad: {dq.get('latest_bad')})"
            )
        if dq.get("power_trend_bad_bars"):
            notes.append(
                f"{dq['power_trend_bad_bars']} bad close(s) in the power-trend input "
                "(power trend unavailable)"
            )
        if notes:
            parts.append(f"{label}: " + "; ".join(notes))
    if not parts and not analysis.get("data_gap"):
        return ""
    if analysis.get("data_gap") and not parts:
        reason = (analysis.get("quality_score") or {}).get("reason")
        parts.append(reason or "missing or invalid price data")
    return "> **Data quality:** " + " | ".join(parts)


def _state_emoji(state: str) -> str:
    mapping = {
        "NO_SIGNAL": "⚪",
        "CORRECTION": "🔴",
        "RALLY_ATTEMPT": "🟡",
        "FTD_WINDOW": "🟡",
        "FTD_CONFIRMED": "🟢",
        "RALLY_FAILED": "🔴",
        "FTD_INVALIDATED": "🔴",
    }
    return mapping.get(state, "⚪")


def _state_label(state: str) -> str:
    mapping = {
        "NO_SIGNAL": "No Signal (Uptrend)",
        "CORRECTION": "Correction",
        "RALLY_ATTEMPT": "Rally Attempt (Day 1-3)",
        "FTD_WINDOW": "FTD Window (Day 4-10)",
        "FTD_CONFIRMED": "FTD Confirmed",
        "RALLY_FAILED": "Rally Failed",
        "FTD_INVALIDATED": "FTD Invalidated",
    }
    return mapping.get(state, state)
