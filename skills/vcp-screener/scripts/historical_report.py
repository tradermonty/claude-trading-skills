#!/usr/bin/env python3
"""Historical VCP report writers — JSON + Markdown timeline for a single ticker.

Schema is intentionally distinct from the cross-sectional ``report_generator.py``
output: that one is "ranked list at a single point in time", this one is
"timeline of detections with forward-outcome stats per detection".
"""

import json
from typing import Optional


def generate_historical_json_report(
    symbol: str,
    detections: list[dict],
    metadata: dict,
    output_file: str,
) -> None:
    """Write a structured JSON timeline of historical VCP detections."""
    report = {
        "schema_version": "1.0",
        "symbol": symbol,
        "metadata": metadata,
        "summary": _summarize(detections),
        "detections": detections,
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  JSON report saved to: {output_file}")


def generate_historical_markdown_report(
    symbol: str,
    detections: list[dict],
    metadata: dict,
    output_file: str,
) -> None:
    """Write a human-readable timeline of historical VCP detections."""
    lines: list[str] = []

    lines.append(f"# VCP History — {symbol}")
    lines.append(f"**Generated:** {metadata.get('generated_at', 'N/A')}")
    if metadata.get("history_range"):
        lines.append(f"**History range:** {metadata['history_range']}")
    lines.append(
        f"**Sweep:** stride={metadata.get('stride_days', '?')}d, "
        f"lookback={metadata.get('lookback_days', '?')}d, "
        f"outcome_window={metadata.get('outcome_days', '?')}d"
    )
    lines.append("")
    lines.append("> **Note**: `marketCap` and absolute RS percentile reflect the "
                 "ticker in isolation, not against the live screening universe. "
                 "Use this report for pattern study, not portfolio sizing.")
    lines.append("")
    lines.append("---")
    lines.append("")

    summary = _summarize(detections)
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Detections | {summary['total']} |")
    lines.append(f"| Breakouts | {summary['breakouts']} |")
    lines.append(f"| Stop hits | {summary['stop_hits']} |")
    lines.append(f"| Timeouts | {summary['timeouts']} |")
    lines.append(
        f"| Hit rate (breakouts / resolved) | {summary['hit_rate_pct']}% |"
    )
    lines.append(
        f"| Avg max gain (breakouts only) | {summary['avg_max_gain_breakout_pct']}% |"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    if not detections:
        lines.append("_No VCP detections found in the scanned history._")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  Markdown report saved to: {output_file}")
        return

    lines.append("## Detection Timeline")
    lines.append("")
    lines.append(
        "| As-of date | Score | Rating | State | Pattern | Pivot | Stop | Outcome | Days | Max gain | Max loss |"
    )
    lines.append(
        "|------------|-------|--------|-------|---------|-------|------|---------|------|----------|----------|"
    )
    for det in detections:
        outcome = det.get("forward_outcome", {}) or {}
        vcp = det.get("vcp_pattern", {}) or {}
        contractions = vcp.get("contractions") or []
        stop = contractions[-1].get("low_price") if contractions else None
        lines.append(
            "| {as_of} | {score} | {rating} | {state} | {pat} | {pivot} | {stop} | {outcome} | {days} | {gain} | {loss} |".format(
                as_of=det.get("as_of_date", "?"),
                score=_fmt(det.get("composite_score"), "{:.1f}"),
                rating=det.get("rating", "-"),
                state=det.get("execution_state", "-"),
                pat=det.get("pattern_type", "-"),
                pivot=_fmt(vcp.get("pivot_price"), "${:.2f}"),
                stop=_fmt(stop, "${:.2f}"),
                outcome=outcome.get("outcome_type", "-"),
                days=_fmt(outcome.get("days_to_outcome"), "{}"),
                gain=_fmt(outcome.get("max_gain_pct"), "{:+.1f}%"),
                loss=_fmt(outcome.get("max_loss_pct"), "{:+.1f}%"),
            )
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-detection detail")
    lines.append("")
    for i, det in enumerate(detections, start=1):
        vcp = det.get("vcp_pattern", {}) or {}
        outcome = det.get("forward_outcome", {}) or {}
        contractions = vcp.get("contractions") or []
        lines.append(f"### {i}. {det.get('as_of_date', '?')} — {det.get('rating', '-')}")
        lines.append("")
        lines.append(
            f"- **Composite score:** {_fmt(det.get('composite_score'), '{:.1f}')}  "
            f"({det.get('pattern_type', '-')}, state: {det.get('execution_state', '-')})"
        )
        lines.append(
            f"- **Pivot:** {_fmt(vcp.get('pivot_price'), '${:.2f}')}  ·  "
            f"**# contractions:** {vcp.get('num_contractions', '-')}  ·  "
            f"**duration:** {vcp.get('pattern_duration_days', '-')} bars"
        )
        if contractions:
            lines.append("- **Contractions:**")
            for c in contractions:
                lines.append(
                    f"  - {c.get('label', '?')}: "
                    f"{c.get('high_date', '?')} ${c.get('high_price', '?')} → "
                    f"{c.get('low_date', '?')} ${c.get('low_price', '?')}  "
                    f"({_fmt(c.get('depth_pct'), '{:.1f}%')}, "
                    f"{c.get('duration_days', '?')}d)"
                )
        lines.append(
            f"- **Forward outcome ({outcome.get('bars_evaluated', '?')} bars):** "
            f"{outcome.get('outcome_type', '-')} "
            f"in {_fmt(outcome.get('days_to_outcome'), '{} days')}  ·  "
            f"max gain {_fmt(outcome.get('max_gain_pct'), '{:+.1f}%')}  ·  "
            f"max loss {_fmt(outcome.get('max_loss_pct'), '{:+.1f}%')}"
        )
        lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Markdown report saved to: {output_file}")


def _fmt(val, template: str) -> str:
    if val is None:
        return "-"
    try:
        return template.format(val)
    except (TypeError, ValueError):
        return str(val)


def _summarize(detections: list[dict]) -> dict:
    total = len(detections)
    counts = {"breakout": 0, "stop_hit": 0, "timeout": 0, "insufficient_data": 0}
    gain_sum = 0.0
    gain_count = 0
    for det in detections:
        oc = (det.get("forward_outcome") or {}).get("outcome_type")
        if oc in counts:
            counts[oc] += 1
        if oc == "breakout":
            g = (det.get("forward_outcome") or {}).get("max_gain_pct")
            if g is not None:
                gain_sum += g
                gain_count += 1
    resolved = counts["breakout"] + counts["stop_hit"]
    hit_rate = round(counts["breakout"] / resolved * 100, 1) if resolved else None
    avg_gain = round(gain_sum / gain_count, 1) if gain_count else None
    return {
        "total": total,
        "breakouts": counts["breakout"],
        "stop_hits": counts["stop_hit"],
        "timeouts": counts["timeout"],
        "insufficient_data": counts["insufficient_data"],
        "hit_rate_pct": hit_rate,
        "avg_max_gain_breakout_pct": avg_gain,
    }
