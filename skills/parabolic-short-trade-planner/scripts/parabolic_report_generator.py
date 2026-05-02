"""Phase 1 output: JSON + Markdown.

Pure functions only — no FMP calls, no I/O. ``screen_parabolic.py`` is
responsible for fetching data, building the per-candidate dicts, and
calling :func:`build_json_report` / :func:`build_markdown_report` to render
output. Keeping the renderer pure means the schema contract is tested
against in-memory fixtures without any network dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"
SKILL_NAME = "parabolic-short-trade-planner"
PHASE = "screen"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def render_candidate(
    *,
    ticker: str,
    composite_result: dict,
    component_scores_raw: dict,
    raw_metrics: dict,
    state_caps: list[str],
    warnings: list[str],
    key_levels: dict,
    invalidation_checks_passed: bool,
    earnings_within_days: int | None,
    market_cap_usd: float | None,
) -> dict:
    """Build one candidate dict in the v1.0 schema shape.

    ``components`` is rendered as **weighted** sub-scores so the values sum
    to the composite ``score``. The ``component_breakdown`` from the scorer
    is the source of truth.
    """
    components_weighted = {
        name: bd["weighted_score"] for name, bd in composite_result["component_breakdown"].items()
    }
    earnings_within_2d = earnings_within_days is not None and earnings_within_days <= 2
    return {
        "ticker": ticker,
        "rank": composite_result["grade"],
        "score": composite_result["score"],
        "state_caps": list(state_caps),
        "warnings": list(warnings),
        "components": components_weighted,
        "components_raw": component_scores_raw,
        "metrics": raw_metrics,
        "key_levels": key_levels,
        "invalidation_checks_passed": invalidation_checks_passed,
        "earnings_within_2d": earnings_within_2d,
        "market_cap_usd": market_cap_usd,
    }


def build_json_report(
    *,
    candidates: list[dict],
    mode: str,
    universe: str,
    as_of: str,
    data_source: str = "FMP",
    data_latency_sec: int = 0,
    generated_at: str | None = None,
) -> dict:
    """Top-level JSON report. ``candidates`` is a list of dicts shaped by
    :func:`render_candidate`."""
    a_count = sum(1 for c in candidates if c.get("rank") == "A")
    return {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "phase": PHASE,
        "generated_at": generated_at or _now_iso(),
        "as_of": as_of,
        "data_source": data_source,
        "data_latency_sec": data_latency_sec,
        "mode": mode,
        "universe": universe,
        "candidates_total": len(candidates),
        "candidates_a_rank": a_count,
        "candidates": candidates,
    }


def build_markdown_report(report: dict) -> str:
    """Render the JSON report as a Markdown watchlist."""
    lines: list[str] = []
    lines.append(f"# Parabolic Short Watchlist — {report['as_of']}")
    lines.append("")
    lines.append(f"- Mode: `{report['mode']}`")
    lines.append(f"- Universe: `{report['universe']}`")
    lines.append(
        f"- Candidates: {report['candidates_total']} (A-rank: {report['candidates_a_rank']})"
    )
    lines.append(f"- Data source: {report['data_source']}")
    lines.append(f"- Generated at: {report['generated_at']}")
    lines.append("")
    if not report["candidates"]:
        lines.append("_No candidates met the screening thresholds._")
        return "\n".join(lines) + "\n"

    by_grade: dict[str, list[dict]] = {}
    for c in report["candidates"]:
        by_grade.setdefault(c["rank"], []).append(c)

    for grade in ("A", "B", "C", "D"):
        bucket = by_grade.get(grade, [])
        if not bucket:
            continue
        lines.append(f"## {grade}-rank ({len(bucket)})")
        lines.append("")
        for c in bucket:
            lines.append(f"### {c['ticker']} — score {c['score']}")
            metrics = c.get("metrics", {})
            r5 = metrics.get("return_5d_pct")
            ext20 = metrics.get("ext_20dma_pct")
            vol = metrics.get("volume_ratio_20d")
            atr = metrics.get("atr_14")
            r5_str = f"{r5:+.1f}%" if isinstance(r5, (int, float)) else "n/a"
            ext_str = f"{ext20:+.1f}%" if isinstance(ext20, (int, float)) else "n/a"
            vol_str = f"{vol:.1f}x" if isinstance(vol, (int, float)) else "n/a"
            atr_str = f"{atr:.2f}" if isinstance(atr, (int, float)) else "n/a"
            lines.append(
                f"- Return 5d: {r5_str} · 20DMA ext: {ext_str} · "
                f"Vol/20d: {vol_str} · ATR(14): {atr_str}"
            )
            kl = c.get("key_levels", {})
            kl_parts = []
            for k in ("dma_10", "dma_20", "dma_50", "prior_close"):
                v = kl.get(k)
                if isinstance(v, (int, float)):
                    kl_parts.append(f"{k}={v:.2f}")
            if kl_parts:
                lines.append("- Key levels: " + ", ".join(kl_parts))
            if c.get("state_caps"):
                lines.append(f"- State caps: {', '.join(c['state_caps'])}")
            if c.get("warnings"):
                lines.append(f"- Warnings: {', '.join(c['warnings'])}")
            lines.append("")
    return "\n".join(lines) + "\n"
