#!/usr/bin/env python3
"""Monthly adherence report for approved operating rules, from gate acknowledgements.

Reads the pre-trade gate journal and the approved-rule ledger and counts, per rule, how often
the trader acknowledged it as followed, an exception, or not applicable. The counts are
self-reported at the gate and are not proof of behavior. The report never changes the ledger.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import approved_rules as ar
from review_rule_experiment import MIN_RATE_SAMPLE

SCHEMA_VERSION = 1
SOURCE = "pre_trade_gate_acknowledgements"
MONTH_RE = re.compile(r"[0-9]{4}-[0-9]{2}")
JOURNAL_GLOB = "pre_trade_discipline_*.jsonl"
HUMAN_NOTE = (
    "Acknowledgements are self-reported at the gate and are not proof of behavior. This report "
    "never activates, extends, retires or supersedes a rule; use manage_approved_rules.py after "
    "a human decision. For a controlled check of one rule use review_rule_experiment.py."
)
LEDGER_HINT = "inspect it with manage_approved_rules.py list"
MISSING = "missing_from_ledger"


class ReportError(ValueError):
    """A fatal input problem; the CLI prints it and exits 1."""


def get_et_zone() -> ZoneInfo:
    """Resolve New York time lazily so a missing tzdata package is reported by main()."""
    return ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------------


def parse_datetime(value: Any, default_tz: Any) -> datetime | None:
    """Parse an ISO timestamp; naive values get default_tz. Returns None when it cannot be read."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=default_tz)


class JournalRow:
    """One validated gate journal row, reduced to what the report reads."""

    def __init__(self, raw: dict[str, Any], day: date, generated_at: datetime, order: int):
        block = raw.get("approved_rules")
        self.status = block["status"] if isinstance(block, dict) else "none"
        self.applied = block["applied"] if self.status == "loaded" else []
        self.candidates = raw["candidate_results"]
        ledger_path = raw.get("inputs", {}).get("approved_rules_ledger")
        self.ledger_path = ledger_path if isinstance(ledger_path, str) else None
        self.day = day
        self.generated_at = generated_at
        self.order = order  # scan position: file name, then line number
        self.sort_key = (generated_at, order)


def _candidate_ok(candidate: Any) -> bool:
    return (
        isinstance(candidate, dict)
        and isinstance(candidate.get("symbol"), str)
        and isinstance(candidate.get("order_intent"), str)
        and isinstance(candidate.get("actionable"), bool)
    )


def _block_ok(block: Any) -> bool:
    """Valid forms: absent, unavailable, or loaded with a list of applied rule objects."""
    if block is None:
        return True
    if not isinstance(block, dict):
        return False
    if block.get("status") == "unavailable":
        return True
    if block.get("status") != "loaded":
        return False
    applied = block.get("applied")
    return isinstance(applied, list) and all(
        isinstance(rule, dict) and isinstance(rule.get("rule_id"), str) for rule in applied
    )


def _row_day(raw: dict[str, Any], as_of: datetime, et: Any) -> date:
    block = raw.get("approved_rules")
    if isinstance(block, dict) and block.get("status") == "loaded":
        stored = block.get("as_of_date")
        if isinstance(stored, str) and ar.DATE_RE.fullmatch(stored):
            try:
                return date.fromisoformat(stored)
            except ValueError:
                pass
    return as_of.astimezone(et).date()


def parse_row(raw: Any, order: int, et: Any) -> JournalRow | None:
    """Return a validated row, or None when any required field is missing or malformed."""
    if not isinstance(raw, dict):
        return None
    as_of = parse_datetime(raw.get("as_of"), et)
    generated_at = parse_datetime(raw.get("generated_at"), timezone.utc)
    candidates = raw.get("candidate_results")
    if as_of is None or generated_at is None or not isinstance(candidates, list):
        return None
    if not all(_candidate_ok(candidate) for candidate in candidates):
        return None
    if not _block_ok(raw.get("approved_rules")):
        return None
    if not isinstance(raw.get("inputs", {}), dict):
        return None
    return JournalRow(raw, _row_day(raw, as_of, et), generated_at, order)


class JournalScan:
    """Rows read from the journal directory plus the problems met on the way."""

    def __init__(self) -> None:
        self.rows: list[JournalRow] = []
        self.malformed: list[str] = []


def scan_journal(journal_dir: Path, et: Any) -> JournalScan:
    """Read every pre_trade_discipline_*.jsonl file; bad lines are recorded, never fatal."""
    if not journal_dir.is_dir():
        raise ReportError(f"journal directory not found: {journal_dir}")
    scan = JournalScan()
    order = 0
    for path in sorted(journal_dir.glob(JOURNAL_GLOB)):
        try:
            data = path.read_bytes()
        except OSError:
            scan.malformed.append(f"{path.name}:0")
            continue
        for lineno, raw_line in enumerate(data.splitlines(), start=1):
            if not raw_line.strip():
                continue
            order += 1
            try:
                # utf-8-sig drops a BOM left by editors that add one.
                row = parse_row(json.loads(raw_line.decode("utf-8-sig")), order, et)
            except (ValueError, OverflowError, RecursionError):
                # Hand-edited rows: bad JSON, out-of-range dates, deep nesting.
                row = None
            if row is None:
                scan.malformed.append(f"{path.name}:{lineno}")
            else:
                scan.rows.append(row)
    return scan


# ---------------------------------------------------------------------------
# Window selection
# ---------------------------------------------------------------------------


def parse_month(value: str) -> tuple[date, date]:
    """Return the first and last day of a YYYY-MM month."""
    if not MONTH_RE.fullmatch(value or ""):
        raise ReportError(f"--month must be YYYY-MM, got {value!r}")
    try:
        start = date(int(value[:4]), int(value[5:]), 1)
    except ValueError as exc:
        raise ReportError(f"--month is not a valid month: {value!r}") from exc
    following = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, following - timedelta(days=1)


def select_window_rows(
    rows: list[JournalRow], start: date, end: date, as_of: date, et: Any
) -> tuple[list[JournalRow], dict[str, int]]:
    """Keep rows inside the month that existed on the review date."""
    cutoff = datetime.combine(as_of, time.max, tzinfo=et)
    kept: list[JournalRow] = []
    dropped = {"rows_after_as_of": 0, "rows_outside_window": 0}
    for row in rows:
        if row.day > as_of or row.generated_at > cutoff:
            dropped["rows_after_as_of"] += 1
        elif not start <= row.day <= end:
            dropped["rows_outside_window"] += 1
        else:
            kept.append(row)
    return kept, dropped


# ---------------------------------------------------------------------------
# Occasions
# ---------------------------------------------------------------------------


def candidate_key(row: JournalRow, candidate: dict[str, Any]) -> tuple:
    """Identity of one gated candidate for rerun dedupe (a thesis collapses its order intents)."""
    thesis_id = candidate.get("thesis_id")
    if isinstance(thesis_id, str) and thesis_id.strip():
        return (row.day, "thesis", thesis_id)
    return (row.day, "symbol", candidate["symbol"], candidate["order_intent"])


def pick_winners(rows: list[JournalRow]) -> tuple[dict[tuple, JournalRow], int]:
    """Per candidate key, the latest row wins; count candidates left in losing rows."""
    winners: dict[tuple, JournalRow] = {}
    for row in rows:
        for candidate in row.candidates:
            key = candidate_key(row, candidate)
            if key not in winners or row.sort_key > winners[key].sort_key:
                winners[key] = row
    superseded = 0
    for row in rows:
        for candidate in row.candidates:
            if winners[candidate_key(row, candidate)] is not row:
                superseded += 1
    return winners, superseded


def assess(rule_id: str, candidate: dict[str, Any]) -> str:
    """Classify one acknowledgement; anything the gate would not accept is unacknowledged."""
    checks = candidate.get("approved_rule_checks")
    entries = checks if isinstance(checks, list) else []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("rule_id") != rule_id:
            continue
        status = entry.get("status")
        note = entry.get("note")
        if status in ("followed", "not_applicable"):
            return str(status)
        if status == "exception" and isinstance(note, str) and note.strip():
            return "exception"
        return "unacknowledged"
    return "unacknowledged"


class RuleTally:
    """Per-rule counters collected while walking the window rows."""

    def __init__(self, rule_id: str) -> None:
        self.rule_id = rule_id
        self.text: str | None = None
        self.text_key: tuple | None = None
        self.counts = {"followed": 0, "exception": 0, "not_applicable": 0, "unacknowledged": 0}
        self.days: set = set()
        self.candidates: set = set()

    def note_text(self, row: JournalRow, text: Any) -> None:
        if isinstance(text, str) and (self.text_key is None or row.sort_key > self.text_key):
            self.text, self.text_key = text, row.sort_key


def tally_rows(rows: list[JournalRow]) -> tuple[dict[str, RuleTally], int]:
    """Count applied days and de-duplicated occasions per rule; return the tallies."""
    tallies: dict[str, RuleTally] = {}

    def tally_for(rule_id: str) -> RuleTally:
        return tallies.setdefault(rule_id, RuleTally(rule_id))

    loaded = [row for row in rows if row.status == "loaded"]
    for row in loaded:
        for rule in row.applied:
            tally = tally_for(rule["rule_id"])
            tally.days.add(row.day)
            tally.note_text(row, rule.get("text"))
    winners, superseded = pick_winners(rows)
    for row in loaded:
        # A hand-edited row may list a rule twice; count it once per candidate.
        applied_ids = list(dict.fromkeys(rule["rule_id"] for rule in row.applied))
        for candidate in row.candidates:
            key = candidate_key(row, candidate)
            if winners[key] is not row or not candidate["actionable"]:
                continue
            for rule_id in applied_ids:
                tally = tally_for(rule_id)
                tally.counts[assess(rule_id, candidate)] += 1
                tally.candidates.add(key)
    return tallies, superseded


# ---------------------------------------------------------------------------
# Rule entries
# ---------------------------------------------------------------------------


def adherence_rate(counts: dict[str, int], window_open: bool) -> tuple[float | None, Any]:
    """Followed share of acknowledged occasions, or None with the reason it is withheld."""
    applicable = counts["followed"] + counts["exception"]
    if window_open:
        return None, "window_open"
    if counts["unacknowledged"]:
        return None, "unacknowledged_occasions"
    if applicable < MIN_RATE_SAMPLE:
        return None, "small_sample"
    return round(100 * counts["followed"] / applicable, 1), None


def reconsider_reasons(counts: dict[str, int], state: str) -> list[str]:
    reasons = []
    if state == ar.STATE_REVIEW_DUE:
        reasons.append("review_due")
    if state not in ar.APPLIED_STATES:
        reasons.append("not_applied_at_review")
    if counts["followed"] + counts["exception"] == 0:
        reasons.append("no_applicable_occasions")
    if counts["exception"]:
        reasons.append("exceptions_present")
    if counts["unacknowledged"]:
        reasons.append("unacknowledged_occasions")
    return reasons


def rule_entry(
    rule_id: str,
    tally: RuleTally | None,
    ledger_rule: dict[str, Any] | None,
    as_of: date,
    window_open: bool,
) -> dict[str, Any]:
    counts = dict(tally.counts) if tally else dict.fromkeys(RuleTally(rule_id).counts, 0)
    state = ar.compute_state(ledger_rule, as_of) if ledger_rule else MISSING
    rate, reason = adherence_rate(counts, window_open)
    text = tally.text if tally and tally.text else (ledger_rule or {}).get("text")
    return {
        "rule_id": rule_id,
        "text": text,
        "followed": counts["followed"],
        "exception": counts["exception"],
        "not_applicable": counts["not_applicable"],
        "unacknowledged": counts["unacknowledged"],
        "occasions": sum(counts.values()),
        "distinct_candidates": len(tally.candidates) if tally else 0,
        "days_in_applied": len(tally.days) if tally else 0,
        "acknowledged_followed_pct": rate,
        "rate_suppressed_reason": reason,
        "ledger_state_at_review": state,
        "review_after": ledger_rule["review_after"] if ledger_rule else None,
        "expires_on": ledger_rule["expires_on"] if ledger_rule else None,
        "superseded_by": ledger_rule["superseded_by"] if ledger_rule else None,
        "reconsider_reasons": reconsider_reasons(counts, state),
    }


def _end_event_day(rule: dict[str, Any], et: Any) -> date | None:
    """ET date of the latest retired or superseded history event, when it can be read."""
    days = []
    for event in rule["history"]:
        if event.get("event") in ("retired", "superseded"):
            when = parse_datetime(event.get("at"), et)
            if when is not None:
                days.append(when.astimezone(et).date())
    return max(days) if days else None


def overlaps_window(rule: dict[str, Any], start: date, end: date, et: Any) -> bool:
    """Whether a rule that no row mentions could have been in force during the window."""
    if date.fromisoformat(rule["effective_date"]) > end:
        return False
    expires = rule["expires_on"]
    if expires is not None and date.fromisoformat(expires) < start:
        return False
    if rule["status"] in ("retired", "superseded"):
        ended = _end_event_day(rule, et)
        if ended is not None and ended < start:
            return False
    return True


def build_rules(
    tallies: dict[str, RuleTally],
    ledger: dict[str, Any],
    window: tuple[date, date],
    as_of: date,
    et: Any,
) -> list[dict[str, Any]]:
    start, end = window
    window_open = as_of <= end
    by_id = {rule["rule_id"]: rule for rule in ledger["rules"]}
    entries = [
        rule_entry(rule_id, tally, by_id.get(rule_id), as_of, window_open)
        for rule_id, tally in tallies.items()
    ]
    for rule_id, rule in by_id.items():
        if rule_id not in tallies and overlaps_window(rule, start, end, et):
            entries.append(rule_entry(rule_id, None, rule, as_of, window_open))
    return sorted(entries, key=lambda entry: entry["rule_id"])


# ---------------------------------------------------------------------------
# Report assembly and output
# ---------------------------------------------------------------------------


def ledger_path_counts(rows: list[JournalRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.ledger_path is not None:
            counts[row.ledger_path] = counts.get(row.ledger_path, 0) + 1
    return counts


def build_report(args: argparse.Namespace, as_of: date, et: Any) -> dict[str, Any]:
    start, end = parse_month(args.month)
    if start > as_of:
        raise ReportError(f"--month {args.month} starts after --as-of {as_of.isoformat()}")
    try:
        ledger = ar.load_ledger(args.ledger)
    except ar.LedgerError as exc:
        raise ReportError(f"ledger {args.ledger} is not usable ({exc}); {LEDGER_HINT}") from exc
    scan = scan_journal(args.journal_dir, et)
    rows, dropped = select_window_rows(scan.rows, start, end, as_of, et)
    tallies, superseded = tally_rows(rows)
    paths = ledger_path_counts(rows)
    rules = build_rules(tallies, ledger, (start, end), as_of, et)
    warnings = []
    if not rules:
        warnings.append("no_rules_in_window: no approved rule applied or was in force this month")
    if not rows:
        warnings.append("no_gate_runs_in_window: no usable journal rows fall in this month")
    for raw_path in sorted(paths):
        if raw_path != str(args.ledger):
            warnings.append(
                f"different_ledger_path: {paths[raw_path]} journal row(s) used {raw_path}, "
                f"not --ledger {args.ledger}"
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "month": args.month,
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "status": "open" if as_of <= end else "ended",
        },
        "as_of": as_of.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {"journal_dir": str(args.journal_dir), "ledger": str(args.ledger)},
        "source": SOURCE,
        "input_quality": {
            "malformed_rows": {"count": len(scan.malformed), "locations": scan.malformed},
            "ledger_unavailable_runs": sum(1 for r in rows if r.status == "unavailable"),
            "runs_without_ledger": sum(1 for r in rows if r.status == "none"),
            "superseded_reruns": superseded,
            "rows_after_as_of": dropped["rows_after_as_of"],
            "rows_outside_window": dropped["rows_outside_window"],
            "ledger_paths": paths,
        },
        "rules": rules,
        "warnings": warnings,
        "human_decision_note": HUMAN_NOTE,
    }


def _md_text(text: Any) -> str:
    """One Markdown-safe line: no newlines, no table pipes, no raw HTML."""
    if not isinstance(text, str) or not text.strip():
        return "(text unavailable)"
    # Replace lone surrogates from hand-edited JSON so the file encodes as UTF-8.
    flat = " ".join(text.encode("utf-8", "replace").decode("utf-8").split())
    flat = flat.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return flat.replace("|", "\\|")


def render_markdown(report: dict[str, Any]) -> str:
    window = report["window"]
    lines = [
        f"# Rule adherence review {report['month']}",
        "",
        f"Window {window['start']} to {window['end']} ({window['status']}), "
        f"as of {report['as_of']}. Source: {report['source']}.",
        "",
        f"> {report['human_decision_note']}",
        "",
        "| Rule | Followed | Exception | N/A | Unacknowledged | Followed % | Ledger state |"
        " Reconsider |",
        "|---|---|---|---|---|---|---|---|",
    ]
    if not report["rules"]:
        lines = lines[:-2] + ["No approved rules in the window."]
    for rule in report["rules"]:
        pct = rule["acknowledged_followed_pct"]
        shown = f"{pct}" if pct is not None else f"withheld ({rule['rate_suppressed_reason']})"
        lines.append(
            f"| {_md_text(rule['rule_id'])} | {rule['followed']} | {rule['exception']} "
            f"| {rule['not_applicable']} | {rule['unacknowledged']} | {shown} "
            f"| {rule['ledger_state_at_review']} | {', '.join(rule['reconsider_reasons']) or '-'} |"
        )
    if report["rules"]:
        lines += ["", "## Rule details", ""]
    for rule in report["rules"]:
        lines.append(f"- {_md_text(rule['rule_id'])}: {_md_text(rule['text'])}")
        lines.append(
            f"  - occasions {rule['occasions']}, distinct_candidates "
            f"{rule['distinct_candidates']}, days_in_applied {rule['days_in_applied']}; "
            f"review_after {rule['review_after'] or '-'}, expires_on "
            f"{rule['expires_on'] or '-'}, superseded_by {rule['superseded_by'] or '-'}"
        )
    quality = report["input_quality"]
    lines += ["", "## Input quality", ""]
    for name, value in quality.items():
        if name == "ledger_paths":
            for path, count in sorted(value.items()):
                lines.append(f"- ledger path {_md_text(path)}: {count} row(s)")
        elif isinstance(value, dict) and "count" in value:
            lines.append(f"- {name}: {value['count']}")
            lines += [f"  - {_md_text(loc)}" for loc in value.get("locations", [])]
        else:
            lines.append(f"- {name}: {value}")
    if report["warnings"]:
        lines += ["", "## Warnings", ""] + [f"- {_md_text(w)}" for w in report["warnings"]]
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"rule_adherence_{report['month']}_as-of_{report['as_of']}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    # Render both bodies before writing, so a failure leaves no half-written pair.
    json_body = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    md_body = render_markdown(report)
    json_path.write_text(json_body, encoding="utf-8")
    md_path.write_text(md_body, encoding="utf-8")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="Calendar month to review, YYYY-MM")
    parser.add_argument(
        "--journal-dir", type=Path, default=Path("state/journal/pre-trade-discipline")
    )
    parser.add_argument("--ledger", type=Path, default=Path("state/rules/approved_rules.json"))
    parser.add_argument(
        "--as-of",
        help=(
            "Review date YYYY-MM-DD in New York time (default today). Cannot be in the"
            " future; journal rows dated or generated after it are left out."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("reports/pre-trade-discipline"))
    parser.add_argument("--stdout", action="store_true", help="Print the JSON; write no files")
    return parser


def resolve_as_of(value: str | None, et: Any) -> date:
    today = datetime.now(et).date()
    if not value:
        return today
    try:
        as_of = ar.parse_date(value, "--as-of")
    except ar.LedgerError as exc:
        raise ReportError(str(exc)) from exc
    if as_of > today:
        raise ReportError("--as-of cannot be in the future")
    return as_of


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        et = get_et_zone()
        report = build_report(args, resolve_as_of(args.as_of, et), et)
    except ZoneInfoNotFoundError:
        print(
            "Error: New York timezone data is missing. Install it with pip install tzdata.",
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    for warning in report["warnings"]:
        print(f"Warning: {warning}", file=sys.stderr)
    if args.stdout:
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
        return 0
    try:
        json_path, md_path = write_report(report, args.output_dir)
    except (OSError, ValueError) as exc:
        print(f"Error: cannot write the report: {exc}", file=sys.stderr)
        return 1
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
