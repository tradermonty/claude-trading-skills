#!/usr/bin/env python3
"""Manage the local approved-rule ledger used by the pre-trade discipline gate.

Subcommands: activate, list, supersede, retire, extend, restore.

Exit codes: 0 success, 1 invalid input or refused operation, 2 missing dependency.
The ledger is a single-user local file; concurrent writers are not supported.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import approved_rules as ar  # noqa: E402

ET = ZoneInfo("America/New_York")
DEFAULT_LEDGER = Path("state/rules/approved_rules.json")


class MissingDependencyError(RuntimeError):
    """A runtime dependency is not installed (exit 2 with an install hint)."""


def _load_yaml_file(path: Path) -> tuple[Any, bytes]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise MissingDependencyError(
            "PyYAML library not found. Install dependencies with: "
            f"pip install -r {Path(__file__).resolve().parents[1] / 'requirements.txt'}"
        ) from exc
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ar.LedgerError(f"could not read {path}: {exc}") from exc
    try:
        return yaml.safe_load(raw.decode("utf-8")), raw
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ar.LedgerError(f"could not parse {path}: {exc}") from exc


def _today_et() -> date:
    return datetime.now(ET).date()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _state_line(rule_id: str, label: str, state: str, text: str) -> str:
    return f"  {rule_id}  {label:<16} {state:<18} {text}"


def cmd_activate(args: argparse.Namespace) -> int:
    data, raw = _load_yaml_file(args.rule_changes)
    activation = ar.extract_candidates(
        data,
        include_trade_rule_changes=args.include_trade_rule_changes,
        source_review_id=args.source_review_id,
        review_after=args.review_after,
        effective_date=args.effective_date,
    )
    ledger = ar.load_ledger(args.ledger, missing_ok=True)
    new, outcomes = ar.apply_activation(
        ledger,
        activation,
        effective_date=args.effective_date,
        review_after=activation.review_after or "",
        expires_on=args.expires_on,
        source_sha256=ar.sha256_bytes(raw),
        now=_now(),
    )
    today = _today_et()
    status_by_id = {r["rule_id"]: r for r in new["rules"]}
    print(f"Source review: {activation.source_review_id} ({activation.shape} shape)")
    for out in outcomes:
        rule = status_by_id[out.rule_id]
        state = ar.compute_state(rule, today)
        print(_state_line(out.rule_id, out.outcome, state, out.text))
        if out.note:
            print(f"      note: {out.note}")
    for skipped in activation.skipped:
        print(f"  skipped: {skipped}")
    if not args.confirm_activation:
        print(
            "\nNothing was written. Re-run with --confirm-activation to apply these changes.",
            file=sys.stderr,
        )
        return 1
    ar.save_ledger(args.ledger, new)
    print(f"\nLedger written: {args.ledger}")
    if all(o.outcome == ar.OUTCOME_ALREADY_APPLIED for o in outcomes) and any(
        status_by_id[o.rule_id]["status"] != "active" for o in outcomes
    ):
        print(
            "Every rule was already applied from this review and at least one is not active "
            "(retired or superseded). Use 'restore' to bring it back.",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    ledger = ar.load_ledger(args.ledger)
    as_of = ar.parse_date(args.as_of, "--as-of") if args.as_of else _today_et()
    rows = []
    for rule in ledger["rules"]:
        row = {
            "rule_id": rule["rule_id"],
            "state": ar.compute_state(rule, as_of),
            "status": rule["status"],
            "text": rule["text"],
            "effective_date": rule["effective_date"],
            "review_after": rule["review_after"],
            "expires_on": rule["expires_on"],
            "origin": rule["origin"],
            "superseded_by": rule["superseded_by"],
        }
        rows.append(row)
    if args.json:
        print(json.dumps({"as_of_date": as_of.isoformat(), "rules": rows}, indent=2))
        return 0
    print(f"Approved rules as of {as_of.isoformat()} ({len(rows)} total)")
    for row in rows:
        print(
            f"  {row['rule_id']}  {row['state']:<18} eff {row['effective_date']} "
            f"review {row['review_after']} exp {row['expires_on'] or '-'}  {row['text']}"
        )
    return 0


def cmd_supersede(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise ar.LedgerError(
            "supersede creates a rule; re-run with --confirm. Nothing was written."
        )
    ledger = ar.load_ledger(args.ledger)
    new, new_id = ar.supersede_rule(
        ledger,
        rule_id=args.rule_id,
        text=args.text,
        effective_date=args.effective_date,
        review_after=args.review_after,
        expires_on=args.expires_on,
        reason=args.reason,
        now=_now(),
    )
    ar.save_ledger(args.ledger, new)
    print(f"Superseded {args.rule_id} with {new_id}")
    return 0


def cmd_retire(args: argparse.Namespace) -> int:
    ledger = ar.load_ledger(args.ledger)
    ar.save_ledger(
        args.ledger, ar.retire_rule(ledger, rule_id=args.rule_id, reason=args.reason, now=_now())
    )
    print(f"Retired {args.rule_id}")
    return 0


def cmd_extend(args: argparse.Namespace) -> int:
    ledger = ar.load_ledger(args.ledger)
    new = ar.extend_rule(
        ledger,
        rule_id=args.rule_id,
        review_after=args.review_after,
        expires_on=args.expires_on,
        clear_expiry=args.clear_expiry,
        reason=args.reason,
        now=_now(),
    )
    ar.save_ledger(args.ledger, new)
    print(f"Extended {args.rule_id}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    ledger = ar.load_ledger(args.ledger)
    ar.save_ledger(
        args.ledger, ar.restore_rule(ledger, rule_id=args.rule_id, reason=args.reason, now=_now())
    )
    print(f"Restored {args.rule_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the approved-rule ledger for the pre-trade discipline gate"
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--ledger", type=Path, default=DEFAULT_LEDGER, help="Ledger path (default: %(default)s)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("activate", parents=[common], help="Activate approved rules from a file")
    p.add_argument("--rule-changes", type=Path, required=True)
    p.add_argument("--effective-date", required=True)
    p.add_argument("--review-after")
    p.add_argument("--expires-on")
    p.add_argument("--source-review-id")
    p.add_argument("--include-trade-rule-changes", action="store_true")
    p.add_argument("--confirm-activation", action="store_true")
    p.set_defaults(func=cmd_activate)

    p = sub.add_parser("list", parents=[common], help="List rules with computed state")
    p.add_argument("--as-of")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("supersede", parents=[common], help="Replace an active rule")
    p.add_argument("--rule-id", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--effective-date", required=True)
    p.add_argument("--review-after", required=True)
    p.add_argument("--expires-on")
    p.add_argument("--reason", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_supersede)

    p = sub.add_parser("retire", parents=[common], help="Retire an active rule")
    p.add_argument("--rule-id", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_retire)

    p = sub.add_parser("extend", parents=[common], help="Extend review or expiry dates")
    p.add_argument("--rule-id", required=True)
    p.add_argument("--review-after")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--expires-on")
    group.add_argument("--clear-expiry", action="store_true")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_extend)

    p = sub.add_parser("restore", parents=[common], help="Restore a retired or superseded rule")
    p.add_argument("--rule-id", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_restore)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except MissingDependencyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (ar.LedgerError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
