#!/usr/bin/env python3
"""
Theme Detector - Report Generator

Generates JSON and Markdown reports for detected market themes.
"""

import json
import os
from datetime import datetime
from typing import Optional


def generate_json_report(
    themes: list[dict], industry_rankings: dict, sector_uptrend: dict, metadata: dict
) -> dict:
    """Create the full JSON output structure.

    Args:
        themes: List of scored theme dicts from the classifier/scorer.
            Each theme has: name, direction, heat, maturity, stage,
            confidence, heat_breakdown, maturity_breakdown,
            representative_stocks, proxy_etfs, etc.
        industry_rankings: Dict with "top" and "bottom" lists of industries.
        sector_uptrend: Dict mapping sector name to uptrend data
            (ratio, ma_10, slope, trend, latest_date).
        metadata: Dict with run metadata (generated_at, data_sources, etc.)

    Returns:
        Complete JSON-serializable report dict.
    """
    bullish = [t for t in themes if t.get("direction") == "bullish"]
    bearish = [t for t in themes if t.get("direction") == "bearish"]

    # Sort by heat descending within each group
    bullish.sort(key=lambda t: t.get("heat", 0), reverse=True)
    bearish.sort(key=lambda t: t.get("heat", 0), reverse=True)

    # Data quality flags
    data_quality = _assess_data_quality(themes, industry_rankings, sector_uptrend, metadata)

    return {
        "report_type": "theme_detector",
        "generated_at": metadata.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "metadata": metadata,
        "summary": {
            "total_themes": len(themes),
            "bullish_count": len(bullish),
            "bearish_count": len(bearish),
            "top_bullish": bullish[0]["name"] if bullish else None,
            "top_bearish": bearish[0]["name"] if bearish else None,
        },
        "themes": {
            "all": themes,
            "bullish": bullish,
            "bearish": bearish,
        },
        "industry_rankings": industry_rankings,
        "sector_uptrend": sector_uptrend,
        "data_quality": data_quality,
    }


def generate_markdown_report(json_data: dict, top_n_detail: int = 3) -> str:
    """Generate a formatted Markdown report from JSON data.

    Args:
        json_data: Full JSON report dict from generate_json_report().
        top_n_detail: Number of top themes to show in detail sections
            (default 3, corresponds to --top CLI arg).

    Sections:
    1. Theme Dashboard (all themes table)
    2. Bullish Themes Detail (top N)
    3. Bearish Themes Detail (top N)
    4. All Themes Summary Table
    5. Industry Rankings (top/bottom 15)
    6. Sector Uptrend Ratios (3-point display)
    7. Methodology Notes + Data Quality Flags
    """
    lines = []
    themes_data = json_data.get("themes", {})
    all_themes = themes_data.get("all", [])
    bullish = themes_data.get("bullish", [])
    bearish = themes_data.get("bearish", [])
    summary = json_data.get("summary", {})

    # Header
    lines.append("# Theme Detector Report")
    lines.append("")
    lines.append(f"**Generated:** {json_data.get('generated_at', 'N/A')}")
    lines.append(
        f"**Themes Detected:** {summary.get('total_themes', 0)} "
        f"({summary.get('bullish_count', 0)} leading, "
        f"{summary.get('bearish_count', 0)} lagging)"
    )
    lines.append("")

    # Section 1: Theme Dashboard
    lines.append("---")
    lines.append("")
    lines.append("## 1. Theme Dashboard")
    lines.append("")

    if not all_themes:
        lines.append("**WARNING:** No themes detected. Check data sources.")
        lines.append("")
    else:
        lines.append("| Theme | Origin | Direction | Heat | Maturity | Stage | Confidence |")
        lines.append("|-------|--------|-----------|------|----------|-------|------------|")
        for t in all_themes:
            heat_bar = _heat_bar(t.get("heat", 0))
            origin = _origin_label(t.get("theme_origin", "seed"))
            lines.append(
                f"| {t.get('name', 'N/A')} "
                f"| {origin} "
                f"| {_direction_label(t.get('direction'))} "
                f"| {heat_bar} {t.get('heat', 0):.1f} "
                f"| {t.get('maturity', 0):.1f} "
                f"| {t.get('stage', 'N/A')} "
                f"| {t.get('confidence', 'N/A')} |"
            )
        lines.append("")

    # Section 2: Bullish Themes Detail
    lines.append("---")
    lines.append("")
    lines.append(f"## 2. Leading Themes (Top {top_n_detail})")
    lines.append("")
    _add_theme_details(lines, bullish[:top_n_detail])

    # Section 3: Bearish Themes Detail
    lines.append("---")
    lines.append("")
    lines.append(f"## 3. Lagging Themes (Top {top_n_detail})")
    lines.append("")
    _add_theme_details(lines, bearish[:top_n_detail])

    # Section 4: All Themes Summary Table
    lines.append("---")
    lines.append("")
    lines.append("## 4. All Themes Summary")
    lines.append("")
    if all_themes:
        lines.append("| # | Theme | Dir | Heat | Maturity | Stage | Industries |")
        lines.append("|---|-------|-----|------|----------|-------|------------|")
        for i, t in enumerate(all_themes, 1):
            industries = t.get("industries", [])
            ind_str = ", ".join(industries[:3])
            if len(industries) > 3:
                ind_str += f" (+{len(industries) - 3})"
            lines.append(
                f"| {i} "
                f"| {t.get('name', 'N/A')} "
                f"| {_direction_arrow(t.get('direction'))} "
                f"| {t.get('heat', 0):.1f} "
                f"| {t.get('maturity', 0):.1f} "
                f"| {t.get('stage', 'N/A')} "
                f"| {ind_str} |"
            )
        lines.append("")
    else:
        lines.append("No themes detected.")
        lines.append("")

    # Section 5: Industry Rankings
    lines.append("---")
    lines.append("")
    lines.append("## 5. Industry Rankings")
    lines.append("")
    rankings = json_data.get("industry_rankings", {})
    top = rankings.get("top", [])
    bottom = rankings.get("bottom", [])

    if top:
        lines.append("### Top 15 Industries")
        lines.append("")
        lines.append("| # | Industry | Perf 1W | Perf 1M | Perf 3M | Score |")
        lines.append("|---|----------|---------|---------|---------|-------|")
        for i, ind in enumerate(top[:15], 1):
            lines.append(
                f"| {i} "
                f"| {ind.get('name', 'N/A')} "
                f"| {_fmt_pct(ind.get('perf_1w'))} "
                f"| {_fmt_pct(ind.get('perf_1m'))} "
                f"| {_fmt_pct(ind.get('perf_3m'))} "
                f"| {ind.get('momentum_score', 0):.2f} |"
            )
        lines.append("")

    if bottom:
        lines.append("### Bottom 15 Industries")
        lines.append("")
        lines.append("| # | Industry | Perf 1W | Perf 1M | Perf 3M | Score |")
        lines.append("|---|----------|---------|---------|---------|-------|")
        for i, ind in enumerate(bottom[:15], 1):
            lines.append(
                f"| {i} "
                f"| {ind.get('name', 'N/A')} "
                f"| {_fmt_pct(ind.get('perf_1w'))} "
                f"| {_fmt_pct(ind.get('perf_1m'))} "
                f"| {_fmt_pct(ind.get('perf_3m'))} "
                f"| {ind.get('momentum_score', 0):.2f} |"
            )
        lines.append("")

    if not top and not bottom:
        lines.append("Industry ranking data unavailable.")
        lines.append("")

    # Section 6: Sector Uptrend Ratios
    lines.append("---")
    lines.append("")
    lines.append("## 6. Sector Uptrend Ratios")
    lines.append("")
    uptrend = json_data.get("sector_uptrend", {})
    if uptrend:
        lines.append("| Sector | Ratio | 10MA | Slope | Trend | Date |")
        lines.append("|--------|-------|------|-------|-------|------|")
        for sector_name, data in sorted(uptrend.items()):
            if not isinstance(data, dict):
                continue
            ratio_pct = f"{data['ratio'] * 100:.1f}%" if data.get("ratio") is not None else "N/A"
            ma_pct = f"{data['ma_10'] * 100:.1f}%" if data.get("ma_10") is not None else "N/A"
            slope_str = f"{data['slope']:+.4f}" if data.get("slope") is not None else "N/A"
            lines.append(
                f"| {sector_name} "
                f"| {ratio_pct} "
                f"| {ma_pct} "
                f"| {slope_str} "
                f"| {data.get('trend', 'N/A')} "
                f"| {data.get('latest_date', 'N/A')} |"
            )
        lines.append("")
    else:
        lines.append("Sector uptrend data unavailable.")
        lines.append("")

    # Section 7: Methodology + Data Quality
    lines.append("---")
    lines.append("")
    lines.append("## 7. Methodology & Data Quality")
    lines.append("")
    lines.append("### Methodology")
    lines.append("")
    lines.append("The Theme Detector identifies market themes by:")
    lines.append("")
    lines.append(
        "1. **Industry Ranking:** FINVIZ performance data ranked by "
        "multi-timeframe composite score (1W 10%, 1M 25%, 3M 35%, 6M 30%)"
    )
    lines.append(
        "2. **Theme Classification:** Industries grouped into "
        "thematic clusters (AI/Semiconductors, Energy Transition, etc.)"
    )
    lines.append(
        "3. **Heat Scoring:** Theme strength measured by performance "
        "momentum, volume confirmation, and breadth"
    )
    lines.append(
        "4. **Lifecycle Stage:** Theme maturity assessed via "
        "early/growth/mature/decline classification"
    )
    lines.append("5. **Uptrend Overlay:** Monty's sector uptrend ratios provide breadth context")
    lines.append("")
    lines.append(
        "**Note on Confidence:** Script output confidence is capped at "
        "Medium. Claude's WebSearch narrative confirmation can elevate "
        "confidence to High."
    )
    lines.append("")
    lines.append(
        "**Note on Direction:** Theme direction (LEAD/LAG) is based on "
        "**relative industry rank** (top-half vs bottom-half), not absolute "
        "price change. A LAG theme may still have positive returns — it "
        "indicates relative underperformance, not a short signal."
    )
    lines.append("")

    data_quality = json_data.get("data_quality", {})
    flags = data_quality.get("flags", [])
    if flags:
        lines.append("### Data Quality Flags")
        lines.append("")
        for flag in flags:
            lines.append(f"- {flag}")
        lines.append("")
    else:
        lines.append("### Data Quality")
        lines.append("")
        lines.append("All data sources returned valid results.")
        lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append(
        "**Disclaimer:** This analysis is for educational and "
        "informational purposes only. Not investment advice. "
        "Past patterns may not predict future outcomes."
    )
    lines.append("")

    return "\n".join(lines)


def save_reports(json_data: dict, markdown: str, output_dir: str) -> dict[str, str]:
    """Save JSON and Markdown report files.

    Args:
        json_data: Full JSON report dict
        markdown: Formatted markdown string
        output_dir: Directory to save reports

    Returns:
        Dict with "json" and "markdown" keys containing file paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_path = os.path.join(output_dir, f"theme_detector_{timestamp}.json")
    md_path = os.path.join(output_dir, f"theme_detector_{timestamp}.md")

    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2, default=str)

    with open(md_path, "w") as f:
        f.write(markdown)

    return {"json": json_path, "markdown": md_path}


# --- Private helpers ---


def _assess_data_quality(
    themes: list[dict], industry_rankings: dict, sector_uptrend: dict, metadata: dict
) -> dict:
    """Assess data quality and return flags.

    Checks FINVIZ connectivity, uptrend data freshness, and scanner
    backend statistics (FMP failure rate, yfinance fallback usage).
    """
    flags = []

    if not themes:
        flags.append("No themes detected - check FINVIZ connectivity")

    top = industry_rankings.get("top", [])
    bottom = industry_rankings.get("bottom", [])
    if not top and not bottom:
        flags.append("Industry rankings unavailable - FINVIZ data may be missing")

    if not sector_uptrend:
        flags.append("Sector uptrend data unavailable - GitHub CSV fetch may have failed")
    else:
        # Check for stale data
        for sector, data in sector_uptrend.items():
            if isinstance(data, dict) and data.get("latest_date"):
                try:
                    latest = datetime.strptime(data["latest_date"], "%Y-%m-%d")
                    age = (datetime.now() - latest).days
                    if age > 3:
                        flags.append(f"Uptrend data for {sector} is {age} days old")
                        break  # One warning is enough
                except (ValueError, TypeError):
                    pass

    sources = metadata.get("data_sources", {})
    if sources.get("finviz_error"):
        flags.append(f"FINVIZ error: {sources['finviz_error']}")
    if sources.get("uptrend_error"):
        flags.append(f"Uptrend error: {sources['uptrend_error']}")

    # Scanner backend statistics (support both flat and nested formats)
    scanner = sources.get("scanner_backend", {})
    for ctx_label, ctx_key in [("Stock", "stock"), ("ETF", "etf")]:
        ctx_stats = scanner.get(ctx_key, {})
        ctx_fmp_calls = ctx_stats.get("fmp_calls", 0)
        ctx_fmp_failures = ctx_stats.get("fmp_failures", 0)
        if ctx_fmp_calls > 0 and ctx_fmp_failures / ctx_fmp_calls > 0.2:
            pct = ctx_fmp_failures / ctx_fmp_calls
            flags.append(
                f"FMP API ({ctx_label}): {ctx_fmp_failures}/{ctx_fmp_calls} "
                f"calls failed ({pct:.0%})"
            )
            # FMP uses dual-endpoint fallback (stable → v3); a ~50% failure
            # rate typically means one endpoint is consistently unavailable
            # while the other succeeds. Actual data loss is lower than the
            # failure count suggests.
            if pct >= 0.4:
                flags.append(
                    f"  Note: FMP uses dual-endpoint fallback; "
                    f"~{pct:.0%} failure rate likely reflects one endpoint "
                    f"being unavailable, not {pct:.0%} data loss"
                )

    # Flat fallback for backward compat (if nested not available)
    fmp_calls = scanner.get("fmp_calls", 0)
    fmp_failures = scanner.get("fmp_failures", 0)
    if fmp_calls > 0 and fmp_failures / fmp_calls > 0.2 and "stock" not in scanner:
        pct = fmp_failures / fmp_calls
        flags.append(f"FMP API: {fmp_failures}/{fmp_calls} calls failed ({pct:.0%})")

    yf_fallbacks = scanner.get("yf_fallbacks", 0)
    if yf_fallbacks > 0:
        flags.append(f"yfinance fallback used {yf_fallbacks} time(s) for missing FMP data")

    return {
        "status": "warning" if flags else "ok",
        "flags": flags,
    }


def _heat_bar(heat: float) -> str:
    """Create a text bar for heat visualization (0-100 scale)."""
    if heat >= 80.0:
        return "████"
    elif heat >= 60.0:
        return "███░"
    elif heat >= 40.0:
        return "██░░"
    elif heat >= 20.0:
        return "█░░░"
    else:
        return "░░░░"


_ORIGIN_LABELS = {"seed": "Seed", "vertical": "Vertical", "discovered": "*NEW*"}


def _origin_label(origin: Optional[str]) -> str:
    """Format theme origin for display."""
    return _ORIGIN_LABELS.get(origin or "seed", "Seed")


def _direction_label(direction: Optional[str]) -> str:
    """Format direction for display.

    Uses LEAD/LAG instead of BULL/BEAR because direction is determined
    by relative rank (top-half vs bottom-half of industries), not by
    absolute price change. A 'LAG' theme may still have positive returns.
    """
    if direction == "bullish":
        return "LEAD"
    elif direction == "bearish":
        return "LAG"
    return "N/A"


def _direction_arrow(direction: Optional[str]) -> str:
    """Format direction as arrow."""
    if direction == "bullish":
        return "^"
    elif direction == "bearish":
        return "v"
    return "-"


def _fmt_pct(value: Optional[float]) -> str:
    """Format a percent value as percentage string (no conversion)."""
    if value is None:
        return "N/A"
    return f"{value:+.1f}%"


def _heat_subscore_interpretation(key: str, value: float) -> str:
    """Provide a brief interpretation of a heat sub-score value."""
    if value >= 75:
        strength = "strong"
    elif value >= 50:
        strength = "moderate"
    elif value >= 25:
        strength = "weak"
    else:
        strength = "very weak"

    descriptions = {
        "momentum_strength": f"{strength} theme momentum",
        "volume_intensity": f"{strength} volume confirmation",
        "uptrend_signal": f"{strength} breadth alignment",
        "breadth_signal": f"{strength} directional consensus",
    }
    return descriptions.get(key, strength)


_SOURCE_LABELS = {
    "finviz_elite": "Fe",
    "finviz_public": "Fp",
    "etf_holdings": "E",
    "static": "S",
}


def _format_stock_list(theme_data: dict) -> str:
    """Format stock list with optional source labels.

    When stock_details is present and contains non-static sources,
    appends [Fe]/[Fp]/[E]/[S] labels. Otherwise plain comma-joined tickers.
    """
    details = theme_data.get("stock_details", [])
    tickers = theme_data.get("representative_stocks", [])

    if not details:
        return ", ".join(tickers) if tickers else "N/A"

    parts = []
    for d in details:
        label = _SOURCE_LABELS.get(d.get("source", ""), "?")
        parts.append(f"{d['symbol']}[{label}]")
    return ", ".join(parts) if parts else "N/A"


def _add_theme_details(lines: list[str], themes: list[dict]) -> None:
    """Add detailed theme sections to the report lines."""
    if not themes:
        lines.append("No themes in this category.")
        lines.append("")
        return

    for t in themes:
        lines.append(f"### {t.get('name', 'Unknown Theme')}")
        lines.append("")
        # Show origin line for discovered themes (seed/vertical are self-evident)
        t_origin = t.get("theme_origin", "seed")
        if t_origin == "discovered":
            name_conf = t.get("name_confidence", "medium")
            lines.append(f"- **Origin:** Discovered (name confidence: {name_conf})")
        lines.append(f"- **Direction:** {_direction_label(t.get('direction'))}")
        lines.append(f"- **Heat:** {t.get('heat', 0):.1f}/100 ({t.get('heat_label', 'N/A')})")
        lines.append(f"- **Maturity:** {t.get('maturity', 0):.1f}/100")
        lines.append(f"- **Stage:** {t.get('stage', 'N/A')}")
        lines.append(f"- **Confidence:** {t.get('confidence', 'N/A')}")
        lines.append("")

        # Heat breakdown with interpretive labels
        heat_bd = t.get("heat_breakdown", {})
        if heat_bd:
            lines.append("**Heat Breakdown:**")
            lines.append("")
            for key, val in heat_bd.items():
                label = key.replace("_", " ").title()
                if isinstance(val, float):
                    interp = _heat_subscore_interpretation(key, val)
                    lines.append(f"- {label}: {val:.2f} ({interp})")
                else:
                    lines.append(f"- {label}: {val}")
            lines.append("")

        # Maturity breakdown
        mat_bd = t.get("maturity_breakdown", {})
        if mat_bd:
            lines.append("**Maturity Breakdown:**")
            lines.append("")
            if t.get("lifecycle_data_quality") == "insufficient":
                lines.append(
                    "- *Note: Maturity based on defaults (no stock "
                    "metrics available). Values may not reflect "
                    "actual lifecycle stage.*"
                )
            for key, val in mat_bd.items():
                label = key.replace("_", " ").title()
                if isinstance(val, float):
                    lines.append(f"- {label}: {val:.2f}")
                else:
                    lines.append(f"- {label}: {val}")
            lines.append("")

        # Representative stocks
        lines.append(f"**Representative Stocks:** {_format_stock_list(t)}")
        lines.append("")

        # Proxy ETFs
        etfs = t.get("proxy_etfs", [])
        if etfs:
            lines.append(f"**Proxy ETFs:** {', '.join(etfs)}")
            lines.append("")
