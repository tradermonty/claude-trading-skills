#!/usr/bin/env python3
"""
VCP Screener Report Generator

Generates JSON and Markdown reports for VCP screening results.

Outputs:
- JSON: Structured data for programmatic use
- Markdown: Human-readable ranked list with VCP pattern details
"""

import json
from datetime import datetime
from typing import Dict, List, Optional


def generate_json_report(results: List[Dict], metadata: Dict, output_file: str,
                         all_results: Optional[List[Dict]] = None):
    """Generate JSON report with screening results.

    Args:
        results: Top results to include in report detail
        metadata: Screening metadata
        output_file: Output file path
        all_results: Full candidate list for summary stats (defaults to results)
    """
    report = {
        "metadata": metadata,
        "results": results,
        "summary": _generate_summary(all_results if all_results is not None else results),
    }

    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"  JSON report saved to: {output_file}")


def generate_markdown_report(results: List[Dict], metadata: Dict, output_file: str,
                             all_results: Optional[List[Dict]] = None):
    """Generate Markdown report with VCP screening results.

    Args:
        results: Top results to include in report detail
        metadata: Screening metadata
        output_file: Output file path
        all_results: Full candidate list for summary stats (defaults to results)
    """
    lines = []

    # Header
    lines.append("# VCP Screener Report - Minervini Volatility Contraction Pattern")
    lines.append(f"**Generated:** {metadata.get('generated_at', 'N/A')}")
    lines.append(f"**Universe:** {metadata.get('universe_description', 'S&P 500')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Screening funnel
    funnel = metadata.get("funnel", {})
    lines.append("## Screening Funnel")
    lines.append("")
    lines.append(f"| Stage | Count |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Universe | {funnel.get('universe', 'N/A')} |")
    lines.append(f"| Pre-filter passed | {funnel.get('pre_filter_passed', 'N/A')} |")
    lines.append(f"| Trend Template passed | {funnel.get('trend_template_passed', 'N/A')} |")
    lines.append(f"| VCP candidates | {funnel.get('vcp_candidates', len(results))} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Top candidates (results already truncated to --top by caller)
    top_n = len(results)
    lines.append(f"## Top {top_n} VCP Candidates")
    lines.append("")

    for i, stock in enumerate(results, 1):
        lines.extend(_format_stock_entry(i, stock))

    # Summary statistics
    lines.append("---")
    lines.append("")
    lines.append("## Summary Statistics")
    summary_source = all_results if all_results is not None else results
    summary = _generate_summary(summary_source)
    lines.append(f"- **Total VCP Candidates:** {summary['total']}")
    lines.append(f"- **Textbook VCP (90+):** {summary['textbook']}")
    lines.append(f"- **Strong VCP (80-89):** {summary['strong']}")
    lines.append(f"- **Good VCP (70-79):** {summary['good']}")
    lines.append(f"- **Developing (60-69):** {summary['developing']}")
    lines.append(f"- **Weak/No VCP (<60):** {summary['weak']}")
    lines.append("")

    # Sector distribution
    sectors = {}
    for stock in results:
        s = stock.get("sector", "Unknown")
        sectors[s] = sectors.get(s, 0) + 1

    if sectors:
        lines.append("### Sector Distribution")
        lines.append("")
        lines.append("| Sector | Count |")
        lines.append("|--------|-------|")
        for sector, count in sorted(sectors.items(), key=lambda x: -x[1]):
            lines.append(f"| {sector} | {count} |")
        lines.append("")

    # API usage
    api_stats = metadata.get("api_stats", {})
    if api_stats:
        lines.append("### API Usage")
        lines.append(f"- **API Calls Made:** {api_stats.get('api_calls_made', 'N/A')}")
        lines.append(f"- **Cache Entries:** {api_stats.get('cache_entries', 'N/A')}")
        lines.append("")

    # Methodology
    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("This screener implements Mark Minervini's Volatility Contraction Pattern (VCP):")
    lines.append("")
    lines.append("1. **Trend Template** (25%) - 7-point Stage 2 uptrend filter")
    lines.append("2. **Contraction Quality** (25%) - VCP pattern with successive tighter corrections")
    lines.append("3. **Volume Pattern** (20%) - Volume dry-up near pivot point")
    lines.append("4. **Pivot Proximity** (15%) - Distance from breakout level")
    lines.append("5. **Relative Strength** (15%) - Minervini-weighted RS vs S&P 500")
    lines.append("")
    lines.append("For detailed methodology, see `references/vcp_methodology.md`.")
    lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append("**Disclaimer:** This screener is for educational and informational purposes only. "
                "Not investment advice. Always conduct your own research and consult a financial "
                "advisor before making investment decisions. Past patterns do not guarantee future results.")
    lines.append("")

    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))

    print(f"  Markdown report saved to: {output_file}")


def _format_stock_entry(rank: int, stock: Dict) -> List[str]:
    """Format a single stock entry for the Markdown report."""
    lines = []

    # Header with rating indicator
    rating = stock.get("rating", "N/A")
    indicator = _rating_indicator(stock.get("composite_score", 0))
    lines.append(f"### {rank}. {stock['symbol']} - {stock.get('company_name', 'N/A')} {indicator}")

    # Basic info
    price = stock.get("price", 0) or 0
    mcap = stock.get("market_cap", 0) or 0
    mcap_str = f"${mcap/1e9:.1f}B" if mcap >= 1e9 else (f"${mcap/1e6:.0f}M" if mcap > 0 else "N/A")
    lines.append(f"**Price:** ${price:.2f} | **Market Cap:** {mcap_str} | "
                f"**Sector:** {stock.get('sector', 'N/A')}")

    # Composite score
    lines.append(f"**VCP Score:** {stock.get('composite_score', 0):.1f}/100 ({rating})")
    lines.append("")

    # Component breakdown table
    lines.append("| Component | Score | Details |")
    lines.append("|-----------|-------|---------|")

    # Trend Template
    tt = stock.get("trend_template", {})
    tt_score = tt.get("score", 0)
    tt_pass = f"{tt.get('criteria_passed', 0)}/7 criteria"
    lines.append(f"| Trend Template | {tt_score:.0f}/100 | {tt_pass} |")

    # Contraction Quality
    vcp = stock.get("vcp_pattern", {})
    vcp_score = vcp.get("score", 0)
    num_c = vcp.get("num_contractions", 0)
    contractions = vcp.get("contractions", [])
    depths = ", ".join([f"{c['label']}={c['depth_pct']:.1f}%" for c in contractions[:4]])
    lines.append(f"| Contraction Quality | {vcp_score:.0f}/100 | {num_c} contractions: {depths} |")

    # Volume Pattern
    vol = stock.get("volume_pattern", {})
    vol_score = vol.get("score", 0)
    dry_up = vol.get("dry_up_ratio")
    dry_up_str = f"Dry-up: {dry_up:.2f}" if dry_up is not None else "N/A"
    lines.append(f"| Volume Pattern | {vol_score:.0f}/100 | {dry_up_str} |")

    # Pivot Proximity
    piv = stock.get("pivot_proximity", {})
    piv_score = piv.get("score", 0)
    dist = piv.get("distance_from_pivot_pct")
    status = piv.get("trade_status", "N/A")
    dist_str = f"{dist:+.1f}% from pivot" if dist is not None else "N/A"
    lines.append(f"| Pivot Proximity | {piv_score:.0f}/100 | {dist_str} ({status}) |")

    # Relative Strength
    rs = stock.get("relative_strength", {})
    rs_score = rs.get("score", 0)
    rs_rank = rs.get("rs_rank_estimate", "N/A")
    weighted_rs = rs.get("weighted_rs")
    rs_str = f"RS Rank ~{rs_rank}" + (f", Weighted RS: {weighted_rs:+.1f}%" if weighted_rs is not None else "")
    lines.append(f"| Relative Strength | {rs_score:.0f}/100 | {rs_str} |")

    lines.append("")

    # Trade setup
    pivot_price = vcp.get("pivot_price")
    stop_loss = piv.get("stop_loss_price")
    risk_pct = piv.get("risk_pct")

    lines.append("**Trade Setup:**")
    lines.append(f"- Pivot: ${pivot_price:.2f}" if pivot_price else "- Pivot: N/A")
    lines.append(f"- Stop-loss: ${stop_loss:.2f}" if stop_loss else "- Stop-loss: N/A")
    lines.append(f"- Risk: {risk_pct:.1f}%" if risk_pct is not None else "- Risk: N/A")
    lines.append(f"- Guidance: {stock.get('guidance', 'N/A')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    return lines


def _rating_indicator(score: float) -> str:
    """Get indicator for rating."""
    if score >= 90:
        return "[TEXTBOOK]"
    elif score >= 80:
        return "[STRONG]"
    elif score >= 70:
        return "[GOOD]"
    elif score >= 60:
        return "[DEVELOPING]"
    else:
        return ""


def _generate_summary(results: List[Dict]) -> Dict:
    """Generate summary statistics."""
    total = len(results)
    textbook = sum(1 for s in results if s.get("composite_score", 0) >= 90)
    strong = sum(1 for s in results if 80 <= s.get("composite_score", 0) < 90)
    good = sum(1 for s in results if 70 <= s.get("composite_score", 0) < 80)
    developing = sum(1 for s in results if 60 <= s.get("composite_score", 0) < 70)
    weak = sum(1 for s in results if s.get("composite_score", 0) < 60)

    return {
        "total": total,
        "textbook": textbook,
        "strong": strong,
        "good": good,
        "developing": developing,
        "weak": weak,
    }
