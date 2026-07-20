#!/usr/bin/env python3
"""
Contrarian Setup Gate -- CLI

The center of Jason Shapiro's contrarian pipeline (steps 1-3 already run):
reads the three upstream report JSONs -- cot-contrarian-detector (crowding,
required), news-reaction-failure-analyzer (news, optional), and
technical-analyst's contrarian-confirmation mode (price action, optional) --
and synthesizes them into one actionable `setup_status` via the fail-closed
state machine in gate_logic.py.

PURE and OFFLINE: no network, no API keys, no environment reads beyond the
three local report files this CLI is pointed at. The CLI's own job is
narrow: load the three JSON files with hardening -- unreadable / parse_error
/ non_finite are caught here in `load_json_file` (non_finite: a whole-file
iterative scan rejecting any non-finite float anywhere, even in a field the
gate never reads -- PR #249 user-review round 3; this closes off the only
route by which a raw non-finite value could otherwise reach the JSON
writer's `allow_nan=False` via an audit-echo field and crash with exit 1
on an entirely different code path than the one that determined the input
was bad); malformed / stale / and the remaining field-level classes are
detected inside gate_logic.normalize_*, which degrades a wrong-shaped or
otherwise-invalid report to INVALID rather than crashing -- then call into
gate_logic.py to normalize and synthesize, then write the JSON/Markdown
report. It never crashes on a bad input file: every run exits 0 and writes
a report, with the specific reason named in the failed input's
`inputs.<step>.state` / `missing_confirmations` (identical fail-closed
contract to every upstream skill in this pipeline).

Output:
  - JSON: contrarian_setup_gate_<symbol>_<as-of>.json
  - Markdown: contrarian_setup_gate_<symbol>_<as-of>.md
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import gate_logic

SKILL_NAME = "contrarian-setup-gate"


def _contains_non_finite(value: Any) -> bool:
    """Iteratively check whether a JSON-parsed structure contains any
    non-finite float (`inf`, `-inf`, `nan`) ANYWHERE -- at any depth, in
    any dict value or list item, regardless of whether that field is one
    the gate actually reads. Catches both a syntactically valid JSON
    number that overflows to `inf` on parse (e.g. `1e309` -- `math.isinf`
    catches this even though no `parse_constant` hook ever sees it, since
    the overflow happens inside `float()` itself, after the token has
    already been recognized as an ordinary number) and the bare
    `Infinity`/`-Infinity`/`NaN` literals `json.loads` accepts by default
    as a non-standard extension (PR #249 user-review round 3).

    Uses an explicit stack, NOT recursion: an ordinary, legitimate JSON
    document can be nested hundreds of levels deep (all finite, in a
    field the gate never even reads) and is perfectly valid input -- a
    recursive walker raises `RecursionError` well before that (confirmed
    empirically: a plain recursive version of this function fails
    starting around depth ~500, since each JSON nesting level costs more
    than one Python call frame once the `any(... for ...)` generator
    expressions are counted), which used to crash the CLI with exit 1 on
    a file that should have produced a completely NORMAL result (PR #249
    user-review round 4). The iterative form has no depth limit -- it is
    bounded only by available memory, not the call stack -- and is O(n)
    over the total number of scalar/container nodes in the structure."""
    stack: list[Any] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, float):
            if not math.isfinite(current):
                return True
        elif isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return False


def load_json_file(path: str) -> tuple[Any | None, str | None]:
    """Read and parse a JSON file. Returns (data, None) on success, or
    (None, reason) on failure, where `reason` is `"unreadable"` (missing,
    permission-denied, a directory, or not valid UTF-8), `"parse_error"`
    (the file opened and decoded fine but isn't valid JSON), or
    `"non_finite"` (the file parsed as valid JSON, but contains a
    non-finite float somewhere -- see `_contains_non_finite`).

    Modeled on technical-analyst's post-#247 hardened loader
    (skills/technical-analyst/scripts/check_weekly_price_action.py
    load_json_file, the current merged version -- NOT
    news-reaction-failure-analyzer's older 2-tuple OSError-only loader,
    which still crashes on non-UTF-8 input; see issue #248). Catches
    `(OSError, UnicodeError)`, not `OSError` alone: a readable file that
    isn't valid UTF-8 raises `UnicodeDecodeError`, a `UnicodeError` /
    `ValueError` subclass, NOT an `OSError` -- it would otherwise escape
    this function entirely and crash with a traceback. `MemoryError` and
    other unrelated exceptions are deliberately left uncaught -- those
    aren't "this input is bad" conditions.

    The `non_finite` check runs BEFORE this data is handed to
    gate_logic.normalize_* at all -- it is deliberately whole-file, not
    field-scoped: gate_logic's normalize_* functions preserve some
    raw-but-invalid values (e.g. an unknown `classification`) verbatim in
    their `NormalizedInput` for audit transparency, and the CLI's JSON
    writer uses `allow_nan=False` as a second, independent defense layer
    -- a non-finite float that reached that echo path would otherwise
    raise `ValueError` at write time and break the exit-0-always-writes-
    a-report contract on an entirely different path than the one that
    determined the input was bad (PR #249 user-review round 3: this
    scenario was reproduced live -- `classification: 1e309` normalized
    correctly to INVALID, but then crashed the CLI with exit 1 when the
    raw `inf` value was echoed into the audit block and hit `allow_nan=
    False`). Scanning the whole parsed structure up front, before
    gate_logic ever sees it, closes that off structurally rather than
    requiring every future echo site to remember to guard itself.

    Wrong-shape JSON (valid JSON, but not a dict / missing required keys /
    wrong types) is NOT this function's concern -- that's detected inside
    gate_logic.normalize_*, which degrades to an INVALID state with a
    named `<input>_malformed` reason rather than raising here.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, "unreadable"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, "parse_error"
    except RecursionError:
        # json.loads itself -- not just our own scanner -- can raise this
        # on extreme nesting. Confirmed empirically in this environment:
        # the C accelerator handles depth 100,000 fine but raises
        # RecursionError around depth 200,000 ("Stack overflow ... while
        # decoding a JSON array"). RecursionError is NOT a ValueError /
        # JSONDecodeError subclass, so it must be caught explicitly, or
        # it escapes this function entirely and crashes the CLI (PR #249
        # user-review round 4). Routed to the same structured
        # `parse_error` class as any other unparsable input -- exit 0,
        # a report is still written, named `<input>_parse_error`.
        return None, "parse_error"
    if _contains_non_finite(data):
        return None, "non_finite"
    return data, None


def _as_of_type(value: str) -> str:
    """argparse type for --as-of: must be YYYY-MM-DD. This validates an
    OPERATOR-supplied CLI argument (not one of the three untrusted report
    files), so a bad value is a genuine usage error, not a degraded-input
    case -- argparse fails the run before any file is even opened."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--as-of must be YYYY-MM-DD, got {value!r}") from exc
    return value


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synthesize the three Shapiro contrarian-pipeline verdicts "
        "(crowding / news-failure / price-action) into one actionable setup_status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", required=True, help="The market under evaluation, e.g. B6")
    parser.add_argument(
        "--detector-json", required=True, help="cot-contrarian-detector JSON report path (step 1)"
    )
    parser.add_argument(
        "--news-json", help="news-reaction-failure-analyzer JSON report path (step 2, optional)"
    )
    parser.add_argument(
        "--price-action-json",
        help="technical-analyst contrarian-confirmation JSON report path (step 3, optional)",
    )
    parser.add_argument(
        "--as-of", required=True, type=_as_of_type, help="Reference date for staleness (YYYY-MM-DD)"
    )
    parser.add_argument("--max-detector-age-days", type=int, default=10)
    parser.add_argument("--max-report-age-days", type=int, default=7)
    parser.add_argument("--output-dir", default="reports/")
    parser.add_argument("--format", choices=["json", "md", "both"], default="both")
    return parser.parse_args()


def generate_json_report(result: dict[str, Any], output_path: Path) -> None:
    # allow_nan=False is defense-in-depth (PR #249 user-review round 2,
    # P1-B): gate_logic's own validation should already reject any
    # non-finite number before it reaches this payload, but if one ever
    # did slip through, json.dumps would otherwise silently emit the
    # non-standard `Infinity`/`-Infinity`/`NaN` literals instead of
    # raising -- this makes that failure loud instead of producing an
    # invalid JSON file.
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=False, allow_nan=False) + "\n", encoding="utf-8"
    )


def _fmt(value: Any) -> str:
    return "n/a" if value is None else str(value)


def generate_markdown_report(result: dict[str, Any], output_path: Path) -> None:
    inputs = result.get("inputs", {})
    missing = result.get("missing_confirmations", [])
    warnings = result.get("warnings", [])
    run_context = result.get("run_context", {})

    lines = [
        "# Contrarian Setup Gate",
        "",
        f"Symbol: {result.get('symbol')}",
        f"As-of date: {run_context.get('as_of')}",
        "",
        "## Setup Status",
        "",
        f"**{result.get('setup_status')}**",
        f"Direction: `{_fmt(result.get('direction'))}`",
        f"Gate confidence: {_fmt(result.get('gate_confidence'))}",
        f"Entry trigger: {_fmt(result.get('entry_trigger'))}",
        f"Invalidation level: {_fmt(result.get('invalidation_level'))}",
        "",
        "## Pipeline Inputs",
        "",
        "| Step | State | Verdict/Classification | Confidence | Reason | Age (days) | Report |",
        "|---|---|---|---|---|---|---|",
    ]
    for step_key, label in (
        ("crowding", "1. Crowding (cot-contrarian-detector)"),
        ("news_failure", "2. News Failure (news-reaction-failure-analyzer)"),
        ("price_action", "3. Price Action (technical-analyst)"),
    ):
        block = inputs.get(step_key, {})
        verdict_or_classification = block.get("classification") or block.get("verdict")
        reason = block.get("verdict_reason") or ""
        lines.append(
            f"| {label} | {block.get('state')} | {_fmt(verdict_or_classification)} | "
            f"{_fmt(block.get('confidence'))} | {reason} | {_fmt(block.get('age_days'))} | "
            f"{_fmt(block.get('report_path'))} |"
        )

    lines += ["", "## Missing / Blocking Confirmations", ""]
    if missing:
        lines += ["| Step | State | Reason |", "|---|---|---|"]
        for item in missing:
            lines.append(f"| {item.get('step')} | {item.get('state')} | {item.get('reason')} |")
    else:
        lines.append("None.")

    lines += ["", "## Warnings", ""]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("None.")

    lines += [
        "",
        "## Guardrails",
        "",
        "This gate never places or recommends an order. READY_FOR_PLAN is the "
        "furthest this skill advances -- position sizing and order entry are "
        "downstream decisions. INSUFFICIENT_EVIDENCE and REJECTED never advance "
        "regardless of any other input. Not investment advice.",
        "",
        "## Methodology",
        "",
        "Synthesizes Jason Shapiro's 3-step contrarian process (COT crowding -> "
        "news-reaction failure -> weekly price-action confirmation) via an "
        "explicit precedence state machine. See "
        "`references/gate-decision-table.md` for the full decision table.",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_arguments()
    print("=" * 72)
    print("Contrarian Setup Gate")
    print("=" * 72)

    symbol = args.symbol.strip().upper()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"contrarian_setup_gate_{symbol}_{args.as_of}.json"
    md_path = output_dir / f"contrarian_setup_gate_{symbol}_{args.as_of}.md"

    detector_data, detector_load_error = load_json_file(args.detector_json)
    crowding = gate_logic.normalize_crowding(
        detector_data,
        detector_load_error,
        symbol=symbol,
        as_of=args.as_of,
        max_age_days=args.max_detector_age_days,
        report_path=args.detector_json,
    )

    if args.news_json:
        news_data, news_load_error = load_json_file(args.news_json)
        news = gate_logic.normalize_news(
            news_data,
            news_load_error,
            symbol=symbol,
            as_of=args.as_of,
            max_age_days=args.max_report_age_days,
            detector=crowding,
            report_path=args.news_json,
        )
    else:
        news = gate_logic.pending_input(gate_logic.STEP_NEWS)

    if args.price_action_json:
        price_data, price_load_error = load_json_file(args.price_action_json)
        price = gate_logic.normalize_price_action(
            price_data,
            price_load_error,
            symbol=symbol,
            as_of=args.as_of,
            max_age_days=args.max_report_age_days,
            detector=crowding,
            report_path=args.price_action_json,
        )
    else:
        price = gate_logic.pending_input(gate_logic.STEP_PRICE)

    result = gate_logic.build_gate_result(
        symbol=symbol,
        crowding=crowding,
        news=news,
        price=price,
        max_detector_age_days=args.max_detector_age_days,
        max_report_age_days=args.max_report_age_days,
        as_of=args.as_of,
    )

    if args.format in ("json", "both"):
        generate_json_report(result, json_path)
    if args.format in ("md", "both"):
        generate_markdown_report(result, md_path)

    print(f"Setup status: {result['setup_status']} (direction: {result['direction']})")
    if result["missing_confirmations"]:
        for item in result["missing_confirmations"]:
            print(f"  - {item['step']}: {item['state']} ({item['reason']})")
    if args.format in ("json", "both"):
        print(f"  JSON Report: {json_path}")
    if args.format in ("md", "both"):
        print(f"  Markdown Report: {md_path}")

    # Every valid decision (including INSUFFICIENT_EVIDENCE and REJECTED)
    # exits 0 -- those are correct, fail-closed outcomes, not errors.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - CLI should return a clear message, not a traceback.
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
