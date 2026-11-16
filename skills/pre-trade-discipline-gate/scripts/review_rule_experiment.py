#!/usr/bin/env python3
"""Plan and review a local two-week experiment for one approved operating rule."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import approved_rules as rules

WINDOW_DAYS = 14
MIN_RATE_SAMPLE = 10
ASSESSMENTS = ("followed", "exception", "not_applicable", "unassessed")
DECISIONS = ("enter", "wait", "pass")
SESSIONS = ("open", "mid_session", "close", "other")
PLAN_FIELDS = {
    "schema_version",
    "rule_id",
    "rule_fingerprint",
    "start_date",
    "end_date",
    "applicable_when",
}
OBSERVATION_FIELDS = {"occasion_id", "date", "decision", "assessment", "session", "evidence_ref"}


def today_et() -> date:
    return datetime.now(ZoneInfo("America/New_York")).date()


def required_text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def check_fields(value, fields: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if value.keys() - fields:
        raise ValueError(f"{label} has unexpected fields")
    missing = fields - value.keys()
    if missing:
        raise ValueError(f"{label} is missing {', '.join(sorted(missing))}")


def get_rule(ledger: dict, rule_id: str) -> dict:
    for rule in ledger["rules"]:
        if rule["rule_id"] == rule_id:
            return rule
    raise ValueError("rule ID does not exist in the approved-rule ledger")


def fingerprint(rule: dict) -> str:
    canonical = json.dumps(rule, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return rules.sha256_bytes(canonical.encode("ascii"))


def require_active_window(rule: dict, start: date, end: date) -> None:
    if any(rules.compute_state(rule, day) not in rules.APPLIED_STATES for day in (start, end)):
        raise ValueError("rule must apply throughout the two-week window")


def make_plan(ledger: dict, rule_id: str, applicable_when: str, start: date) -> dict:
    rule = get_rule(ledger, rule_id)
    end = start + timedelta(days=WINDOW_DAYS - 1)
    require_active_window(rule, start, end)
    return {
        "schema_version": 1,
        "rule_id": rule_id,
        "rule_fingerprint": fingerprint(rule),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "applicable_when": required_text(applicable_when, "applicable-when"),
    }


def count_observations(rows, start: date, end: date, as_of: date) -> tuple[dict, dict]:
    if not isinstance(rows, list):
        raise ValueError("observations must be a JSON array")
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    exceptions_by_session: Counter[str] = Counter()
    for index, row in enumerate(rows, 1):
        label = f"observation #{index}"
        check_fields(row, OBSERVATION_FIELDS, label)
        occasion_id = required_text(row["occasion_id"], f"{label} occasion_id")
        if occasion_id in seen:
            raise ValueError(f"{label} has a duplicate occasion_id")
        seen.add(occasion_id)
        observed = rules.parse_date(row["date"], f"{label} date")
        if not start <= observed <= end:
            raise ValueError(f"{label} is outside the experiment window")
        if observed > as_of:
            raise ValueError(f"{label} is after the review date")
        required_text(row["evidence_ref"], f"{label} evidence_ref")
        for field, options in (
            ("decision", DECISIONS),
            ("assessment", ASSESSMENTS),
            ("session", SESSIONS),
        ):
            if row[field] not in options:
                raise ValueError(f"{label} has invalid {field}; expected {', '.join(options)}")
        assessment = row["assessment"]
        counts[assessment] += 1
        if assessment == "exception":
            exceptions_by_session[row["session"]] += 1
        if assessment == "followed" and row["decision"] == "pass":
            counts["followed_passes"] += 1

    return {
        "recorded": len(rows),
        "applicable": counts["followed"] + counts["exception"],
        "followed": counts["followed"],
        "exceptions": counts["exception"],
        "not_applicable": counts["not_applicable"],
        "unassessed": counts["unassessed"],
        "followed_passes": counts["followed_passes"],
    }, dict(exceptions_by_session)


def review_plan(ledger: dict, plan, rows, as_of: date) -> dict:
    check_fields(plan, PLAN_FIELDS, "plan")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("plan schema_version must be 1")
    rule = get_rule(ledger, plan["rule_id"])
    if plan["rule_fingerprint"] != fingerprint(rule):
        raise ValueError("ledger rule changed since the experiment started")
    start = rules.parse_date(plan["start_date"], "plan start_date")
    end = rules.parse_date(plan["end_date"], "plan end_date")
    if (end - start).days != WINDOW_DAYS - 1:
        raise ValueError("plan must cover exactly 14 calendar days")
    if as_of < start:
        raise ValueError("review date is before the experiment window")
    require_active_window(rule, start, end)
    applicable_when = required_text(plan["applicable_when"], "plan applicable_when")
    counts, by_session = count_observations(rows, start, end, as_of)

    rate = None
    reason = None
    if as_of <= end:
        reason = "window_open"
    elif counts["unassessed"]:
        reason = "unassessed_occasions"
    elif counts["applicable"] < MIN_RATE_SAMPLE:
        reason = "small_sample"
    else:
        rate = round(100 * counts["followed"] / counts["applicable"], 1)
    return {
        "schema_version": 1,
        "rule_id": rule["rule_id"],
        "rule_review_after": rule["review_after"],
        "applicable_when": applicable_when,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "as_of_date": as_of.isoformat(),
        "window_status": "open" if as_of <= end else "ended",
        "counts": counts,
        "exceptions_by_session": by_session,
        "adherence_rate_pct": rate,
        "rate_suppressed_reason": reason,
        "source": "self_reported_observations",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("state/rules/approved_rules.json"))
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Print a plan for a rule that applies today")
    start.add_argument("--rule-id", required=True)
    start.add_argument("--applicable-when", required=True)
    review = commands.add_parser("review", help="Report on locally recorded decisions")
    review.add_argument("--plan", type=Path, required=True)
    review.add_argument("--observations", type=Path, required=True)
    review.add_argument("--as-of", help="Use an earlier review date (YYYY-MM-DD, New York time)")
    args = parser.parse_args(argv)

    try:
        ledger = rules.load_ledger(args.ledger)
        today = today_et()
        if args.command == "start":
            result = make_plan(ledger, args.rule_id, args.applicable_when, today)
        else:
            as_of = rules.parse_date(args.as_of, "--as-of") if args.as_of else today
            if as_of > today:
                raise ValueError("review date cannot be in the future")
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            observations = json.loads(args.observations.read_text(encoding="utf-8"))
            result = review_plan(ledger, plan, observations, as_of)
    except ZoneInfoNotFoundError:
        print(
            "Error: New York timezone data is missing. Install it with pip install tzdata.",
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
