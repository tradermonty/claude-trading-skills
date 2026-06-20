#!/usr/bin/env python3
"""Weekly Performance Digest Generator.

Pulls closed trades from trader-memory-core, calculates performance metrics,
identifies patterns, and generates structured digest reports (JSON + Markdown).

Pure calculation; no API required. Reads CLOSED (and, for the partial-trim block,
PARTIALLY_CLOSED) thesis YAML files written by trader-memory-core
(``state/theses/th_*.yaml``).

Double-counting invariant
-------------------------
A CLOSED thesis's ``outcome.pnl_dollars`` is the *cumulative* realized P&L over every
trim plus the final leg. Therefore:

* Headline metrics (summary + metrics) are computed over **CLOSED theses only**, keyed
  on ``exit.actual_date``, using the cumulative ``outcome.*`` values.
* The ``partial_trims`` block scans ``status_history[]`` of **PARTIALLY_CLOSED theses
  only** (still open). Trims of CLOSED theses are already inside the cumulative
  ``outcome.pnl_dollars`` and would be double-counted if scanned here.
* ``partial_trims`` is informational and is **never** added into the headline totals or
  win-rate.

A thesis trimmed in week 1 then closed in week 2 will appear as a partial trim in week
1's digest and (via cumulative ``outcome``) inside week 2's CLOSED headline. That is
correct per-report; the same dollars surface across two weekly reports by design.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = "1.0"
REPORT_TYPE = "weekly_performance_digest"
DEFAULT_TOP_N = 3

logger = logging.getLogger("weekly_performance_digest")


# --------------------------------------------------------------------------- #
# Utilities
# --------------------------------------------------------------------------- #
def _parse_dt(value: str) -> datetime:
    """Parse an ISO 8601 / RFC 3339 string into an aware datetime (assume UTC)."""
    text = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_thesis(path: Path) -> dict | None:
    """Load a thesis YAML file, or return None if it cannot be parsed."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("Skipping %s: not a mapping", path)
        return None
    return data


def _get(thesis: dict, *keys: str) -> Any:
    """Safely walk nested mappings; return None if any level is missing/None."""
    node: Any = thesis
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


# --------------------------------------------------------------------------- #
# Data collection
# --------------------------------------------------------------------------- #
def gather_closed_theses(state_dir: Path, from_date: str, to_date: str) -> list[dict]:
    """Gather CLOSED theses whose exit.actual_date falls within [from_date, to_date]."""
    start = _parse_dt(f"{from_date}T00:00:00+00:00")
    end = _parse_dt(f"{to_date}T23:59:59+00:00")
    out: list[dict] = []
    for path in sorted(state_dir.glob("th_*.yaml")):
        thesis = _load_thesis(path)
        if thesis is None or thesis.get("status") != "CLOSED":
            continue
        exit_date = _get(thesis, "exit", "actual_date")
        if not exit_date:
            continue
        try:
            when = _parse_dt(exit_date)
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid exit date in %s: %s (%s)", path, exit_date, exc)
            continue
        if start <= when <= end:
            out.append(thesis)
    return out


def gather_partial_trims(state_dir: Path, from_date: str, to_date: str) -> list[dict]:
    """Collect realized trims recorded in-week from PARTIALLY_CLOSED theses ONLY.

    CLOSED theses are deliberately excluded: their trims are already part of the
    cumulative ``outcome.pnl_dollars`` counted in the headline metrics (see module
    docstring's double-counting invariant).
    """
    start = _parse_dt(f"{from_date}T00:00:00+00:00")
    end = _parse_dt(f"{to_date}T23:59:59+00:00")
    trims: list[dict] = []
    for path in sorted(state_dir.glob("th_*.yaml")):
        thesis = _load_thesis(path)
        if thesis is None or thesis.get("status") != "PARTIALLY_CLOSED":
            continue
        for entry in thesis.get("status_history") or []:
            realized = entry.get("realized_pnl")
            at = entry.get("at")
            if realized is None or not at:
                continue
            try:
                when = _parse_dt(at)
            except (ValueError, TypeError):
                continue
            if start <= when <= end:
                trims.append(
                    {
                        "thesis_id": thesis.get("thesis_id"),
                        "ticker": thesis.get("ticker"),
                        "date": at,
                        "realized_pnl": realized,
                        "shares_sold": entry.get("shares_sold"),
                        "price": entry.get("price"),
                    }
                )
    return trims


# --------------------------------------------------------------------------- #
# Per-thesis calculations
# --------------------------------------------------------------------------- #
def calculate_pnl(thesis: dict) -> tuple[float | None, float | None]:
    """Return (pnl_dollars, pnl_pct) from outcome; either may be None."""
    return _get(thesis, "outcome", "pnl_dollars"), _get(thesis, "outcome", "pnl_pct")


def calculate_holding_days(thesis: dict) -> int | None:
    """Holding period in days: outcome.holding_days, else exit - entry actual_date."""
    explicit = _get(thesis, "outcome", "holding_days")
    if explicit is not None:
        return explicit
    entry_date = _get(thesis, "entry", "actual_date")
    exit_date = _get(thesis, "exit", "actual_date")
    if not entry_date or not exit_date:
        return None
    try:
        return (_parse_dt(exit_date) - _parse_dt(entry_date)).days
    except (ValueError, TypeError):
        return None


def calculate_r_multiple(thesis: dict) -> float | None:
    """R-multiple = realized P&L / initial risk.

    initial risk = (entry.actual_price - exit.stop_loss) * position.shares.
    Note: stop_loss lives under ``exit`` in the real schema (not ``entry``).
    """
    pnl_dollars, _ = calculate_pnl(thesis)
    entry_price = _get(thesis, "entry", "actual_price")
    stop_loss = _get(thesis, "exit", "stop_loss")
    shares = _get(thesis, "position", "shares")
    if None in (pnl_dollars, entry_price, stop_loss, shares):
        return None
    risk = (entry_price - stop_loss) * shares
    if risk == 0:
        return None
    return round(pnl_dollars / risk, 4)


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def _pnl_value(thesis: dict) -> float | None:
    dollars, pct = calculate_pnl(thesis)
    return dollars if dollars is not None else pct


def calculate_metrics(theses: list[dict]) -> dict:
    """Aggregate performance metrics over CLOSED theses."""
    summary = {
        "total_trades": len(theses),
        "winners": 0,
        "losers": 0,
        "breakeven": 0,
        "win_rate": 0.0,
        "expectancy": 0.0,
        "profit_factor": None,
        "total_realized_pnl": 0.0,
        "total_realized_pnl_pct": 0.0,
    }
    metrics = {
        "avg_winner": None,
        "avg_loser": None,
        "largest_winner": None,
        "largest_loser": None,
        "avg_holding_days_winners": None,
        "avg_holding_days_losers": None,
        "r_multiple_avg": None,
        "r_multiple_stdev": None,
        "avg_mae_pct": None,
        "avg_mfe_pct": None,
    }
    if not theses:
        return {"summary": summary, "metrics": metrics}

    winners: list[float] = []
    losers: list[float] = []
    win_hold: list[int] = []
    loss_hold: list[int] = []
    pnl_dollars_all: list[float] = []
    pnl_pct_all: list[float] = []
    r_multiples: list[float] = []
    mae_vals: list[float] = []
    mfe_vals: list[float] = []

    for thesis in theses:
        dollars, pct = calculate_pnl(thesis)
        value = dollars if dollars is not None else pct
        if value is None:
            continue
        pnl_dollars_all.append(dollars if dollars is not None else 0.0)
        if pct is not None:
            pnl_pct_all.append(pct)
        hold = calculate_holding_days(thesis)
        if value > 0:
            summary["winners"] += 1
            winners.append(value)
            if hold is not None:
                win_hold.append(hold)
        elif value < 0:
            summary["losers"] += 1
            losers.append(value)
            if hold is not None:
                loss_hold.append(hold)
        else:
            summary["breakeven"] += 1
        r = calculate_r_multiple(thesis)
        if r is not None:
            r_multiples.append(r)
        # Normalize to the documented sign convention: MAE is adverse (<= 0),
        # MFE is favorable (>= 0). TMC does not clamp, so an always-profitable
        # trade can carry mae_pct > 0 (and vice versa); clamp on read.
        mae = _get(thesis, "outcome", "mae_pct")
        if mae is not None:
            mae_vals.append(min(mae, 0.0))
        mfe = _get(thesis, "outcome", "mfe_pct")
        if mfe is not None:
            mfe_vals.append(max(mfe, 0.0))

    total = summary["total_trades"]
    summary["win_rate"] = round(summary["winners"] / total, 4) if total else 0.0
    summary["total_realized_pnl"] = round(sum(pnl_dollars_all), 2)
    summary["total_realized_pnl_pct"] = round(sum(pnl_pct_all), 4)
    summary["expectancy"] = round(statistics.mean(pnl_dollars_all), 2) if pnl_dollars_all else 0.0
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    if gross_loss > 0:
        summary["profit_factor"] = round(gross_profit / gross_loss, 4)
    elif winners:
        summary["profit_factor"] = None  # all winners, no losses -> undefined

    metrics["avg_winner"] = round(statistics.mean(winners), 2) if winners else None
    metrics["avg_loser"] = round(statistics.mean(losers), 2) if losers else None
    metrics["largest_winner"] = round(max(winners), 2) if winners else None
    metrics["largest_loser"] = round(min(losers), 2) if losers else None
    metrics["avg_holding_days_winners"] = round(statistics.mean(win_hold), 1) if win_hold else None
    metrics["avg_holding_days_losers"] = round(statistics.mean(loss_hold), 1) if loss_hold else None
    if r_multiples:
        metrics["r_multiple_avg"] = round(statistics.mean(r_multiples), 4)
        metrics["r_multiple_stdev"] = (
            round(statistics.stdev(r_multiples), 4) if len(r_multiples) > 1 else 0.0
        )
    if mae_vals:
        metrics["avg_mae_pct"] = round(statistics.mean(mae_vals), 4)
    if mfe_vals:
        metrics["avg_mfe_pct"] = round(statistics.mean(mfe_vals), 4)

    return {"summary": summary, "metrics": metrics}


_PATTERN_DIMENSIONS = (
    ("by_source_skill", ("origin", "skill")),
    ("by_exit_reason", ("exit", "exit_reason")),
    ("by_thesis_type", ("thesis_type",)),
    ("by_sector", ("market_context", "sector")),
    ("by_mechanism_tag", ("mechanism_tag",)),
    ("by_screening_grade", ("origin", "screening_grade")),
)


def analyze_patterns(theses: list[dict]) -> dict:
    """Win/loss breakdown across source skill, exit reason, type, sector, etc."""
    result: dict[str, dict] = {name: {} for name, _ in _PATTERN_DIMENSIONS}
    for thesis in theses:
        value = _pnl_value(thesis)
        if value is None:
            continue
        is_win = value > 0
        is_loss = value < 0
        for name, keys in _PATTERN_DIMENSIONS:
            bucket_key = _get(thesis, *keys)
            if bucket_key is None:
                bucket_key = "unknown"
            bucket = result[name].setdefault(
                bucket_key, {"wins": 0, "losses": 0, "total": 0, "win_rate": 0.0}
            )
            bucket["total"] += 1
            if is_win:
                bucket["wins"] += 1
            elif is_loss:
                bucket["losses"] += 1
    for buckets in result.values():
        for bucket in buckets.values():
            decided = bucket["wins"] + bucket["losses"]
            bucket["win_rate"] = round(bucket["wins"] / decided, 4) if decided else 0.0
    return result


def _lesson_row(thesis: dict) -> dict:
    dollars, pct = calculate_pnl(thesis)
    return {
        "thesis_id": thesis.get("thesis_id"),
        "ticker": thesis.get("ticker"),
        "thesis_type": thesis.get("thesis_type"),
        "pnl_dollars": dollars,
        "pnl_pct": pct,
        "holding_days": calculate_holding_days(thesis),
        "r_multiple": calculate_r_multiple(thesis),
        "exit_reason": _get(thesis, "exit", "exit_reason"),
        "source_skill": _get(thesis, "origin", "skill"),
        "lessons_learned": _get(thesis, "outcome", "lessons_learned"),
    }


def extract_lessons(theses: list[dict], top_n: int = DEFAULT_TOP_N) -> dict:
    """Top winners/losers (by pnl) plus simple process-improvement insights."""
    decided = [t for t in theses if _pnl_value(t) is not None]
    winners = sorted(
        (t for t in decided if _pnl_value(t) > 0),
        key=lambda t: _pnl_value(t),
        reverse=True,
    )
    losers = sorted((t for t in decided if _pnl_value(t) < 0), key=lambda t: _pnl_value(t))

    improvements: list[str] = []
    patterns = analyze_patterns(theses)
    for skill, bucket in patterns["by_source_skill"].items():
        if bucket["losses"] >= 2 and bucket["win_rate"] < 0.5:
            improvements.append(
                f"Source skill '{skill}' had {bucket['losses']} losses "
                f"(win rate {bucket['win_rate']:.0%}) this week — review its setups."
            )
    for reason, bucket in patterns["by_exit_reason"].items():
        if reason == "stop_hit" and bucket["total"] >= 2:
            improvements.append(
                f"{bucket['total']} trades exited via stop_hit — check entry timing/sizing."
            )

    return {
        "top_wins": [_lesson_row(t) for t in winners[:top_n]],
        "top_losses": [_lesson_row(t) for t in losers[:top_n]],
        "process_improvements": improvements,
    }


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _fmt_money(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "n/a"


def _fmt_pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def _fmt_num(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def generate_markdown_report(digest: dict, from_date: str, to_date: str) -> str:
    summary = digest["summary"]
    metrics = digest["metrics"]
    patterns = digest["pattern_analysis"]
    lessons = digest["lessons"]
    partial = digest.get("partial_trims", {})
    lines: list[str] = []
    lines.append("# Weekly Performance Digest")
    lines.append("")
    lines.append(f"**Period:** {from_date} to {to_date}")
    lines.append(f"**Generated:** {digest['generated_at']}")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        f"- Closed trades: **{summary['total_trades']}** "
        f"({summary['winners']}W / {summary['losers']}L / {summary['breakeven']}BE)"
    )
    lines.append(f"- Win rate: **{_fmt_pct(summary['win_rate'])}**")
    lines.append(f"- Expectancy: **{_fmt_money(summary['expectancy'])}** per trade")
    lines.append(f"- Total realized P&L: **{_fmt_money(summary['total_realized_pnl'])}**")
    if partial.get("count"):
        lines.append(
            f"- Partial trims (open positions, informational): "
            f"{partial['count']} trims, {_fmt_money(partial.get('total_realized_pnl'))} "
            f"(not included in headline totals)"
        )
    lines.append("")
    lines.append("## Performance Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Profit factor | {_fmt_num(summary['profit_factor'])} |")
    lines.append(f"| Avg winner | {_fmt_money(metrics['avg_winner'])} |")
    lines.append(f"| Avg loser | {_fmt_money(metrics['avg_loser'])} |")
    lines.append(f"| Largest winner | {_fmt_money(metrics['largest_winner'])} |")
    lines.append(f"| Largest loser | {_fmt_money(metrics['largest_loser'])} |")
    lines.append(f"| Avg R-multiple | {_fmt_num(metrics['r_multiple_avg'])} |")
    lines.append(f"| R-multiple stdev | {_fmt_num(metrics['r_multiple_stdev'])} |")
    lines.append(f"| Avg MAE % | {_fmt_num(metrics['avg_mae_pct'])} |")
    lines.append(f"| Avg MFE % | {_fmt_num(metrics['avg_mfe_pct'])} |")
    lines.append(
        f"| Avg hold (W/L) days | "
        f"{_fmt_num(metrics['avg_holding_days_winners'])} / "
        f"{_fmt_num(metrics['avg_holding_days_losers'])} |"
    )
    lines.append("")
    lines.append("## Pattern Analysis")
    lines.append("")
    for name, label in (
        ("by_source_skill", "By source skill"),
        ("by_exit_reason", "By exit reason"),
        ("by_thesis_type", "By thesis type"),
        ("by_sector", "By sector"),
        ("by_mechanism_tag", "By mechanism tag"),
        ("by_screening_grade", "By screening grade"),
    ):
        buckets = patterns.get(name) or {}
        if not buckets:
            continue
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| Bucket | Wins | Losses | Win rate |")
        lines.append("|---|---|---|---|")
        for key, bucket in sorted(buckets.items()):
            lines.append(
                f"| {key} | {bucket['wins']} | {bucket['losses']} | "
                f"{_fmt_pct(bucket['win_rate'])} |"
            )
        lines.append("")
    lines.append("## Lessons Learned")
    lines.append("")
    lines.append("### Top Winners")
    lines.append("")
    if lessons["top_wins"]:
        for row in lessons["top_wins"]:
            lines.append(
                f"- **{row['ticker']}** ({row['thesis_type']}): "
                f"{_fmt_money(row['pnl_dollars'])} — {row.get('lessons_learned') or 'n/a'}"
            )
    else:
        lines.append("- None")
    lines.append("")
    lines.append("### Top Losers")
    lines.append("")
    if lessons["top_losses"]:
        for row in lessons["top_losses"]:
            lines.append(
                f"- **{row['ticker']}** ({row['thesis_type']}): "
                f"{_fmt_money(row['pnl_dollars'])} — {row.get('lessons_learned') or 'n/a'}"
            )
    else:
        lines.append("- None")
    lines.append("")
    lines.append("### Process Improvements")
    lines.append("")
    if lessons["process_improvements"]:
        for item in lessons["process_improvements"]:
            lines.append(f"- {item}")
    else:
        lines.append("- No systematic issues flagged this week.")
    lines.append("")
    return "\n".join(lines)


def generate_digest(state_dir: Path, from_date: str, to_date: str, output_dir: Path) -> dict:
    """Build the digest, write JSON + Markdown, and return the digest dict."""
    logger.info("Gathering closed theses from %s to %s", from_date, to_date)
    closed = gather_closed_theses(state_dir, from_date, to_date)
    logger.info("Found %d closed theses", len(closed))
    trims = gather_partial_trims(state_dir, from_date, to_date)

    metrics_block = calculate_metrics(closed)
    digest = {
        "schema_version": SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "period": {"from": from_date, "to": to_date},
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": metrics_block["summary"],
        "metrics": metrics_block["metrics"],
        "pattern_analysis": analyze_patterns(closed),
        "partial_trims": {
            "count": len(trims),
            "total_realized_pnl": round(sum(t["realized_pnl"] for t in trims), 2),
            "trims": trims,
        },
        "lessons": extract_lessons(closed),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"weekly_digest_{to_date}.json"
    json_path.write_text(json.dumps(digest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("Wrote JSON report: %s", json_path)
    md_path = output_dir / f"weekly_digest_{to_date}.md"
    md_path.write_text(generate_markdown_report(digest, from_date, to_date), encoding="utf-8")
    logger.info("Wrote Markdown report: %s", md_path)
    return digest


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate a weekly performance digest from closed trades."
    )
    parser.add_argument(
        "--state-dir",
        default="state/theses",
        help="trader-memory-core state directory (default: state/theses).",
    )
    parser.add_argument(
        "--from-date",
        default=None,
        help="Inclusive start date YYYY-MM-DD (default: 7 days ago).",
    )
    parser.add_argument(
        "--to-date",
        default=None,
        help="Inclusive end date YYYY-MM-DD (default: today).",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Output directory for reports (default: reports/).",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    to_date = args.to_date or _today_str()
    from_date = args.from_date or (
        _parse_dt(f"{to_date}T00:00:00+00:00") - timedelta(days=7)
    ).strftime("%Y-%m-%d")

    state_dir = Path(args.state_dir)
    if not state_dir.is_dir():
        print(f"error: state dir not found: {state_dir}", file=sys.stderr)
        return 1

    try:
        digest = generate_digest(state_dir, from_date, to_date, Path(args.output_dir))
    except Exception as exc:  # pragma: no cover - top-level guard
        logger.error("Failed to generate digest: %s", exc)
        return 1

    summary = digest["summary"]
    print(
        f"Generated digest: {summary['total_trades']} trades, "
        f"{summary['winners']}W/{summary['losers']}L, "
        f"P&L {_fmt_money(summary['total_realized_pnl'])}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
