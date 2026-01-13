#!/usr/bin/env python3
"""
CANSLIM Report Generator - Phase 3 (Full CANSLIM)

Generates JSON and Markdown reports for CANSLIM screening results.

Outputs:
- JSON: Structured data for programmatic use
- Markdown: Human-readable ranked list with component breakdowns
"""

import json
from datetime import datetime
from typing import Dict, List


def generate_json_report(results: List[Dict], metadata: Dict, output_file: str):
    """
    Generate JSON report with screening results

    Args:
        results: List of analyzed stocks with scores
        metadata: Screening metadata (date, parameters, etc.)
        output_file: Output file path
    """
    report = {
        "metadata": metadata,
        "results": results,
        "summary": generate_summary_stats(results)
    }

    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"✓ JSON report saved to: {output_file}")


def generate_markdown_report(results: List[Dict], metadata: Dict, output_file: str):
    """
    Generate Markdown report with screening results

    Args:
        results: List of analyzed stocks with scores
        metadata: Screening metadata
        output_file: Output file path
    """
    lines = []

    # Header
    lines.append("# CANSLIM Stock Screener Report - Phase 3 (Full CANSLIM)")
    lines.append(f"**Generated:** {metadata['generated_at']}")

    # Extract components from metadata
    components = metadata.get('components_included', ['C', 'A', 'N', 'S', 'I', 'M'])
    components_str = ', '.join(components)
    lines.append(f"**Phase:** {metadata['phase']} (Components: {components_str})")
    lines.append(f"**Stocks Analyzed:** {metadata['candidates_analyzed']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Market condition summary
    if 'market_condition' in metadata:
        market = metadata['market_condition']
        lines.append("## Market Condition Summary")
        lines.append(f"- **Trend:** {market.get('trend', 'unknown')}")
        lines.append(f"- **M Score:** {market.get('M_score', 'N/A')}/100")

        if market.get('warning'):
            lines.append(f"- **⚠️ Warning:** {market['warning']}")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Top candidates
    lines.append(f"## Top {min(len(results), 20)} CANSLIM Candidates")
    lines.append("")

    for i, stock in enumerate(results[:20], 1):
        lines.extend(format_stock_entry(i, stock))

    # Summary statistics
    lines.append("---")
    lines.append("")
    lines.append("## Summary Statistics")
    summary = generate_summary_stats(results)
    lines.append(f"- **Total Stocks Screened:** {summary['total_stocks']}")
    lines.append(f"- **Exceptional (90+):** {summary['exceptional']} stocks")
    lines.append(f"- **Strong (80-89):** {summary['strong']} stocks")
    lines.append(f"- **Above Average (70-79):** {summary['above_average']} stocks")
    lines.append(f"- **Average (60-69):** {summary['average']} stocks")
    lines.append(f"- **Below Average (<60):** {summary['below_average']} stocks")
    lines.append("")

    # Methodology note
    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("This Phase 3 implementation includes all 7 CANSLIM components (100% coverage):")
    lines.append("")
    lines.append("- **C** (Current Earnings) - 15% weight: Quarterly EPS growth YoY")
    lines.append("- **A** (Annual Growth) - 20% weight: 3-year EPS CAGR")
    lines.append("- **N** (Newness) - 15% weight: Price position vs 52-week high")
    lines.append("- **S** (Supply/Demand) - 15% weight: Volume accumulation/distribution")
    lines.append("- **L** (Leadership) - 20% weight: Relative Strength vs S&P 500 (52-week)")
    lines.append("- **I** (Institutional) - 10% weight: Institutional holder analysis")
    lines.append("- **M** (Market Direction) - 5% weight: S&P 500 trend")
    lines.append("")
    lines.append("Component weights follow William O'Neil's original CANSLIM methodology,")
    lines.append("with L (Leadership/RS Rank) as the most weighted component alongside A (Annual Growth).")
    lines.append("")
    lines.append("For detailed methodology, see `references/canslim_methodology.md`.")
    lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append("**Disclaimer:** This screener is for educational and informational purposes only. "
                "Not investment advice. Conduct your own research and consult a financial advisor "
                "before making investment decisions.")
    lines.append("")

    # Write to file
    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))

    print(f"✓ Markdown report saved to: {output_file}")


def format_stock_entry(rank: int, stock: Dict) -> List[str]:
    """
    Format a single stock entry for Markdown report

    Args:
        rank: Stock rank (1-20)
        stock: Stock data dict

    Returns:
        List of formatted lines
    """
    lines = []

    # Header with rank and rating emoji
    rating_emoji = get_rating_emoji(stock['composite_score'])
    lines.append(f"### {rank}. {stock['symbol']} - {stock['company_name']} {rating_emoji}")

    # Basic info
    lines.append(f"**Price:** ${stock.get('price', 'N/A'):.2f} | "
                f"**Market Cap:** ${stock.get('market_cap', 0)/1e9:.1f}B | "
                f"**Sector:** {stock.get('sector', 'N/A')}")

    # Composite score
    lines.append(f"**Composite Score:** {stock['composite_score']:.1f}/100 ({stock['rating']})")
    lines.append("")

    # Component breakdown table
    lines.append("#### Component Breakdown")
    lines.append("")
    lines.append("| Component | Score | Details |")
    lines.append("|-----------|-------|---------|")

    # C component
    c_details = stock.get('c_component', {})
    c_score = c_details.get('score', 0)
    c_eps = c_details.get('latest_qtr_eps_growth', 'N/A')
    c_rev = c_details.get('latest_qtr_revenue_growth', 'N/A')
    c_eps_str = f"{c_eps:+.1f}%" if isinstance(c_eps, (int, float)) else str(c_eps)
    c_rev_str = f"{c_rev:+.1f}%" if isinstance(c_rev, (int, float)) else str(c_rev)
    lines.append(f"| 🅲 Current Earnings | {c_score}/100 | "
                f"EPS: {c_eps_str}, Revenue: {c_rev_str} |")

    # A component
    a_details = stock.get('a_component', {})
    a_score = a_details.get('score', 0)
    a_cagr = a_details.get('eps_cagr_3yr', 'N/A')
    a_stability = a_details.get('stability', 'unknown')
    a_cagr_str = f"{a_cagr:.1f}%" if isinstance(a_cagr, (int, float)) else str(a_cagr)
    lines.append(f"| 🅰 Annual Growth | {a_score}/100 | "
                f"3yr CAGR: {a_cagr_str}, {a_stability} |")

    # N component
    n_details = stock.get('n_component', {})
    n_score = n_details.get('score', 0)
    n_distance = n_details.get('distance_from_high_pct', 'N/A')
    n_breakout = "✓ Breakout" if n_details.get('breakout_detected') else ""
    n_distance_str = f"{n_distance:+.1f}%" if isinstance(n_distance, (int, float)) else str(n_distance)
    lines.append(f"| 🅽 Newness | {n_score}/100 | "
                f"{n_distance_str} from 52wk high {n_breakout} |")

    # S component
    s_details = stock.get('s_component', {})
    s_score = s_details.get('score', 0)
    s_ratio = s_details.get('up_down_ratio', 'N/A')
    s_accumulation = "✓ Accumulation" if s_details.get('accumulation_detected') else ""
    s_ratio_str = f"{s_ratio:.2f}" if isinstance(s_ratio, (int, float)) else str(s_ratio)
    lines.append(f"| 🅂 Supply/Demand | {s_score}/100 | "
                f"Up/Down Volume Ratio: {s_ratio_str} {s_accumulation} |")

    # L component (Phase 3 - Leadership / Relative Strength)
    l_details = stock.get('l_component', {})
    l_score = l_details.get('score', 0)
    l_stock_perf = l_details.get('stock_52w_performance', 'N/A')
    l_relative = l_details.get('relative_performance', 'N/A')
    l_rs_rank = l_details.get('rs_rank_estimate', 'N/A')
    l_stock_perf_str = f"{l_stock_perf:+.1f}%" if isinstance(l_stock_perf, (int, float)) else str(l_stock_perf)
    l_relative_str = f"{l_relative:+.1f}% vs S&P" if isinstance(l_relative, (int, float)) else str(l_relative)
    l_rs_str = f"RS: {l_rs_rank}" if isinstance(l_rs_rank, (int, float)) else ""
    lines.append(f"| 🅻 Leadership | {l_score}/100 | "
                f"52wk: {l_stock_perf_str} ({l_relative_str}) {l_rs_str} |")

    # I component
    i_details = stock.get('i_component', {})
    i_score = i_details.get('score', 0)
    i_holders = i_details.get('num_holders', 'N/A')
    i_ownership = i_details.get('ownership_pct', 'N/A')
    i_ownership_str = f"{i_ownership:.1f}%" if isinstance(i_ownership, (int, float)) else str(i_ownership)
    i_superinvestor = "⭐ Superinvestor" if i_details.get('superinvestor_present') else ""
    lines.append(f"| 🅸 Institutional | {i_score}/100 | "
                f"{i_holders} holders, {i_ownership_str} ownership {i_superinvestor} |")

    # M component
    m_details = stock.get('m_component', {})
    m_score = m_details.get('score', 0)
    m_trend = m_details.get('trend', 'unknown')
    lines.append(f"| 🅼 Market Direction | {m_score}/100 | {m_trend.replace('_', ' ').title()} |")

    lines.append("")

    # Interpretation
    lines.append("#### Interpretation")
    lines.append(f"**Rating:** {stock['rating']} - {stock['rating_description']}")
    lines.append("")
    lines.append(f"**Guidance:** {stock['guidance']}")
    lines.append("")

    # Weakest component
    lines.append(f"**Weakest Component:** {stock['weakest_component']} "
                f"({stock['weakest_score']}/100)")

    # Warnings
    warnings = []
    if c_details.get('quality_warning'):
        warnings.append(f"⚠️ {c_details['quality_warning']}")
    if a_details.get('quality_warning'):
        warnings.append(f"⚠️ {a_details['quality_warning']}")
    if s_details.get('quality_warning'):
        warnings.append(f"⚠️ {s_details['quality_warning']}")
    if l_details.get('quality_warning'):
        warnings.append(f"⚠️ {l_details['quality_warning']}")
    if i_details.get('quality_warning'):
        warnings.append(f"⚠️ {i_details['quality_warning']}")
    if m_details.get('warning'):
        warnings.append(f"⚠️ {m_details['warning']}")

    if warnings:
        lines.append("")
        lines.append("**Warnings:**")
        for warning in warnings:
            lines.append(f"- {warning}")

    lines.append("")
    lines.append("---")
    lines.append("")

    return lines


def get_rating_emoji(score: float) -> str:
    """Get emoji for rating"""
    if score >= 90:
        return "⭐⭐⭐"  # Exceptional+
    elif score >= 80:
        return "⭐⭐"   # Exceptional
    elif score >= 70:
        return "⭐"     # Strong
    elif score >= 60:
        return "✓"     # Above Average
    else:
        return ""


def generate_summary_stats(results: List[Dict]) -> Dict:
    """
    Generate summary statistics for results

    Args:
        results: List of analyzed stocks

    Returns:
        Dict with summary statistics
    """
    total = len(results)

    exceptional = sum(1 for s in results if s['composite_score'] >= 90)
    strong = sum(1 for s in results if 80 <= s['composite_score'] < 90)
    above_avg = sum(1 for s in results if 70 <= s['composite_score'] < 80)
    average = sum(1 for s in results if 60 <= s['composite_score'] < 70)
    below_avg = sum(1 for s in results if s['composite_score'] < 60)

    return {
        "total_stocks": total,
        "exceptional": exceptional,
        "strong": strong,
        "above_average": above_avg,
        "average": average,
        "below_average": below_avg
    }


# Example usage
if __name__ == "__main__":
    print("Testing Report Generator...\n")

    # Sample data
    sample_results = [
        {
            "symbol": "NVDA",
            "company_name": "NVIDIA Corporation",
            "price": 495.50,
            "market_cap": 1220000000000,
            "sector": "Technology",
            "composite_score": 97.2,
            "rating": "Exceptional+",
            "rating_description": "Rare multi-bagger setup",
            "guidance": "Immediate buy, aggressive sizing",
            "weakest_component": "A",
            "weakest_score": 95,
            "c_component": {
                "score": 100,
                "latest_qtr_eps_growth": 429,
                "latest_qtr_revenue_growth": 101
            },
            "a_component": {
                "score": 95,
                "eps_cagr_3yr": 76,
                "stability": "stable"
            },
            "n_component": {
                "score": 98,
                "distance_from_high_pct": -0.5,
                "breakout_detected": True
            },
            "m_component": {
                "score": 100,
                "trend": "strong_uptrend"
            }
        },
        {
            "symbol": "META",
            "company_name": "Meta Platforms Inc",
            "price": 389.50,
            "market_cap": 1000000000000,
            "sector": "Technology",
            "composite_score": 82.8,
            "rating": "Exceptional",
            "rating_description": "Outstanding fundamentals",
            "guidance": "Strong buy, standard sizing",
            "weakest_component": "A",
            "weakest_score": 78,
            "c_component": {
                "score": 85,
                "latest_qtr_eps_growth": 164,
                "latest_qtr_revenue_growth": 23
            },
            "a_component": {
                "score": 78,
                "eps_cagr_3yr": 28,
                "stability": "stable"
            },
            "n_component": {
                "score": 88,
                "distance_from_high_pct": -5.0,
                "breakout_detected": False
            },
            "m_component": {
                "score": 80,
                "trend": "uptrend"
            }
        }
    ]

    sample_metadata = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "phase": "1 (MVP)",
        "components_included": ["C", "A", "N", "M"],
        "candidates_analyzed": 40,
        "market_condition": {
            "trend": "uptrend",
            "M_score": 80,
            "warning": None
        }
    }

    # Generate reports
    json_file = "test_canslim_report.json"
    md_file = "test_canslim_report.md"

    generate_json_report(sample_results, sample_metadata, json_file)
    generate_markdown_report(sample_results, sample_metadata, md_file)

    print("\n✓ Test reports generated successfully")
    print(f"  JSON: {json_file}")
    print(f"  Markdown: {md_file}")
