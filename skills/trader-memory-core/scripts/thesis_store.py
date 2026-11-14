"""Trader Memory Core — thesis CRUD and index management.

Provides atomic read/write operations for thesis YAML files and the
_index.json summary.  All writes use tempfile + os.replace for safety.
"""

from __future__ import annotations

# Names marked noqa: F401 are used by the thesis_store_parts/ fragments, which
# run in this module's namespace (see _exec_parts below).
import hashlib  # noqa: F401
import json
import logging
import math
import os  # noqa: F401
import re
import sys
import tempfile  # noqa: F401
import uuid  # noqa: F401
from datetime import date, datetime, timedelta, timezone  # noqa: F401
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from jsonschema import Draft7Validator, FormatChecker  # noqa: F401

logger = logging.getLogger(__name__)

# -- Constants ----------------------------------------------------------------

_STATUS_ORDER = [
    "IDEA",
    "ENTRY_READY",
    "ACTIVE",
    "PARTIALLY_CLOSED",
    "CLOSED",
    "INVALIDATED",
]
_TERMINAL_STATUSES = {"CLOSED", "INVALIDATED"}  # PARTIALLY_CLOSED is non-terminal

# Used by attach_position() (equity): (re)writing position incl.
# shares_remaining == shares is only coherent before the position is
# opened or while it is fully open. On PARTIALLY_CLOSED it would violate
# 0 < shares_remaining < shares, on CLOSED it would violate
# shares_remaining == 0, and either would clobber the trim ledger
# relationship — reject those (and terminal INVALIDATED) explicitly.
# ACTIVE is safe to re-attach for equity: attach_position() only ever
# rewrites shares/shares_remaining/position_value/risk_dollars, none of
# which encode a directional sign.
_ATTACH_ALLOWED = {"IDEA", "ENTRY_READY", "ACTIVE"}

# Futures-only, deliberately STRICTER than _ATTACH_ALLOWED above (P1-1,
# user independent review, money-critical): re-attaching on ACTIVE would
# silently overwrite the ENTIRE position dict of an already-open futures
# position, INCLUDING `direction`. A LONG position re-attached with a
# SHORT SIZED report would flip `_sign()` for every subsequent P&L
# computation — a real loss would compute as a fabricated profit and vice
# versa, with no error raised anywhere. Equity attach_position() has no
# such sign-flip risk (see _ATTACH_ALLOWED above), so this guard is
# futures-specific. Correcting an already-open futures position (wrong
# contracts/multiplier/direction) is out of scope for this PR — that needs
# a dedicated history-preserving "amend" operation, not a re-attach.
_ATTACH_FUTURES_ALLOWED = {"IDEA", "ENTRY_READY"}


def _parse_dt(value: str) -> datetime:
    """Parse an ISO 8601 / RFC 3339 string into an aware datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


_TYPE_ABBR = {
    "dividend_income": "div",
    "growth_momentum": "grw",
    "mean_reversion": "rev",
    "earnings_drift": "ern",
    "pivot_breakout": "pvt",
}

_VALID_THESIS_TYPES = set(_TYPE_ABBR.keys())

INDEX_FILE = "_index.json"

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "thesis.schema.json"
_SCHEMA: dict | None = None
_VALID_EXIT_REASONS = {"stop_hit", "target_hit", "time_stop", "invalidated", "manual"}
_UPDATE_OUTCOME_FIELDS = frozenset({"mae_pct", "mfe_pct", "mae_mfe_source", "lessons_learned"})

_FORMAT_CHECKER = FormatChecker()


@_FORMAT_CHECKER.checks("date-time", raises=ValueError)
def _check_datetime(value):
    """Validate RFC 3339 date-time strings (T separator + timezone required)."""
    if not isinstance(value, str):
        return True  # null handled by type validation, not format
    # RFC 3339 requires 'T' separator, not space
    if " " in value:
        raise ValueError(f"date-time must use 'T' separator: {value}")
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        raise ValueError(f"Invalid date-time: {value}") from None
    # RFC 3339 requires timezone offset
    if dt.tzinfo is None:
        raise ValueError(f"date-time must include timezone offset: {value}")
    return True


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@_FORMAT_CHECKER.checks("date", raises=ValueError)
def _check_date(value):
    """Validate YYYY-MM-DD date strings with strict zero-padding."""
    if not isinstance(value, str):
        return True  # null handled by type validation, not format
    if not _DATE_RE.match(value):
        raise ValueError(f"date must be YYYY-MM-DD (zero-padded): {value}")
    date.fromisoformat(value)
    return True


# -- Implementation parts (Issue #502) ----------------------------------------
#
# Most of this module is kept in source fragments under
# ``thesis_store_parts/`` so each area can be reviewed on its own:
#
#   validation.py         field validators, equity/futures position checks,
#                         schema validation (_validate_thesis, validate_thesis)
#   persistence.py        timestamps, IDs, atomic writes, thesis files, index
#   lifecycle.py          register/update/transition/link_report/mark_reviewed
#   positions_equity.py   equity position math and the public close/trim/
#                         open_position/terminate/attach_position dispatchers
#   positions_futures.py  futures position math
#   queries.py            get/query/list_active/list_review_due/validate_state
#
# main() stays below in this file, so the CLI parser lives in the entry script.
#
# The fragments are executed, in order, into THIS module's namespace instead
# of being imported as separate modules. That keeps thesis_store a single
# namespace exactly as before the split: every function's globals are this
# module's dict, so ``monkeypatch.setattr(thesis_store, "_save_thesis", ...)``
# still reaches every caller, the ``_SCHEMA`` cache and ``logger`` stay module
# attributes, functions keep ``__module__ == __name__``, and loading this file
# by path under another module name (pre-trade-discipline-gate and several
# tests do) still yields a fully independent copy with no sys.path change.
# Import ``thesis_store``; never import the fragments at runtime. The
# ``if TYPE_CHECKING:`` block after _exec_parts names fragment modules only so
# linters and readers can see where main()'s names are defined; it never runs.

_PART_FILES = (
    "validation.py",
    "persistence.py",
    "lifecycle.py",
    "positions_equity.py",
    "positions_futures.py",
    "queries.py",
)


def _exec_parts(namespace: dict[str, Any]) -> None:
    """Execute each fragment, in order, into ``namespace`` (this module)."""
    parts_dir = Path(__file__).resolve().parent / "thesis_store_parts"
    for name in _PART_FILES:
        path = parts_dir / name
        source = path.read_text(encoding="utf-8")
        # Bandit B102 is suppressed: this runs only this package's own fragment
        # files listed in _PART_FILES, never user input.
        exec(compile(source, str(path), "exec", dont_inherit=True), namespace)  # nosec B102


_exec_parts(globals())

if TYPE_CHECKING:  # Names main() uses from the fragments; never runs.
    from thesis_store_parts.lifecycle import mark_reviewed, record_lessons, transition
    from thesis_store_parts.persistence import _coerce_dt, rebuild_index
    from thesis_store_parts.positions_equity import (
        attach_position,
        close,
        open_position,
        terminate,
        trim,
    )
    from thesis_store_parts.positions_futures import attach_futures_position
    from thesis_store_parts.queries import get, list_review_due, query, validate_state
    from thesis_store_parts.validation import _MAX_CONTRACTS, _MAX_SHARES


# -- CLI entry point ----------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code (0 ok, non-zero error).

    Extracted from the former ``if __name__ == "__main__"`` block (behavior of
    the pre-existing subcommands is unchanged) so the lifecycle subcommands are
    unit-testable via ``main([...])``.
    """
    import argparse

    def _strict_finite_float(value: str) -> float:
        """Argparse type= for --actual-price/--price (P1-3, user
        independent review, money-critical): a finite float. Plain
        `type=float` accepts "inf"/"-inf"/"nan" as valid Python float
        literals — a NaN/Infinity price would otherwise persist into
        thesis state and NaN-poison every downstream P&L computation.
        Modeled on futures-position-sizer's strict_positive_float /
        _strict_float_type, but deliberately does NOT also require > 0
        here (unlike that helper): this flag is shared between the equity
        and futures CLI paths, and a $0 equity exit price is a legitimate
        real-world value (e.g. a delisted/bankrupt position) — an actual
        downstream consumer test (drawdown-circuit-breaker) exercises
        exactly this. The futures-only finite-AND-positive constraint is
        enforced separately at the Python level by _valid_finite_positive()
        inside _open_futures_position()/_close_futures()/_trim_futures()/
        _terminate_futures() — this CLI guard only needs to close the
        nan/inf hole, not re-litigate positivity for a shared flag."""
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{value!r} is not a valid number") from exc
        if not math.isfinite(parsed):
            raise argparse.ArgumentTypeError(f"{value!r} must be finite (not inf/-inf/nan)")
        return parsed

    def _strict_positive_int(value: str) -> int:
        """Argparse type= for --contracts/--contracts-sold (P1-4, user
        independent review): an exact positive whole number. Parses via
        int(), never float() (same reasoning as futures_sizing.py's
        strict_nonneg_int: float64 loses precision above 2**53, and a
        fractional string like "1.5" must be rejected outright — futures
        trade in whole contracts only, never silently truncated).

        P1-B (user re-review): also enforces the same _MAX_CONTRACTS
        sanity cap as _valid_positive_int()/_valid_nonneg_int() (the
        Python API side). Python's int() parses a 400-digit string with
        no error at all (arbitrary precision) — without this bound, such
        a value would reach the business logic layer as a "successfully
        parsed" CLI arg and only be rejected several calls later, deep
        inside open_position(). Caught here instead as an
        argparse.ArgumentTypeError (exit 2, a usage error) — consistent
        with every other malformed-input case this parser already
        rejects at the CLI boundary."""
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"{value!r} must be a whole number of contracts"
            ) from exc
        if parsed <= 0:
            raise argparse.ArgumentTypeError(f"{value!r} must be greater than 0")
        if parsed > _MAX_CONTRACTS:
            raise argparse.ArgumentTypeError(
                f"{value!r} exceeds the maximum contract count ({_MAX_CONTRACTS})"
            )
        return parsed

    def _strict_positive_finite_float(value: str) -> float:
        """Argparse type= for attach-futures-position's --expected-entry/
        --expected-stop ONLY (P1-C, user re-review) — a dedicated,
        futures-specific parser, distinct from _strict_finite_float above
        (which deliberately allows 0/negative for the shared --actual-price/
        --price flags — see its docstring). An expected futures price is
        never legitimately 0 or negative, so this rejects those too,
        matching _validate_expected_price_match()'s own finite-AND-positive
        requirement on the Python side. Does NOT touch attach-position's
        (equity) --expected-entry/--expected-stop, which keep the original
        plain type=float behavior — cross-attach and price-fail-open fixes
        in this PR are scoped to futures only."""
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{value!r} is not a valid number") from exc
        if not math.isfinite(parsed):
            raise argparse.ArgumentTypeError(f"{value!r} must be finite (not inf/-inf/nan)")
        if parsed <= 0:
            raise argparse.ArgumentTypeError(f"{value!r} must be greater than 0")
        return parsed

    def _strict_shares(value: str) -> float:
        """Argparse type= for --shares (open-position) / --shares-sold
        (trim) ONLY (Issue #254, pre-existing money-critical gap) — a
        dedicated, equity-specific parser, per-domain like
        _strict_positive_int above (NOT a cap bolted onto the shared
        _strict_positive_finite_float, which is documented as
        futures-only and would conflate two independently-tunable sanity
        domains — see _is_futures()'s module docstring on why futures/
        equity code paths must not be merged).

        Parses via float() (never int()) since equity shares are
        legitimately fractional (7.86, matching a real IBKR/Robinhood
        fill) — unlike futures contracts, this does NOT truncate to a
        whole number. Rejects nan/inf/non-numeric (argparse.
        ArgumentTypeError, exit 2, no traceback) and enforces the same
        _MAX_SHARES sanity cap as _valid_finite_positive()'s callers on
        the Python API side, for the same reason _strict_positive_int
        enforces _MAX_CONTRACTS: a 400+-digit CLI string would otherwise
        reach the business logic layer as a "successfully parsed" value
        and only be rejected several calls later, deep inside
        open_position()/trim(). Note the mechanism differs from the
        contracts case: float("1" + "0"*400) returns inf cleanly (no
        exception — string-to-float parsing saturates rather than
        raising OverflowError, unlike int-to-float conversion), so this
        is caught by the isfinite() check below, not a try/except."""
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{value!r} is not a valid number") from exc
        if not math.isfinite(parsed):
            raise argparse.ArgumentTypeError(f"{value!r} must be finite (not inf/-inf/nan)")
        if parsed <= 0:
            raise argparse.ArgumentTypeError(f"{value!r} must be greater than 0")
        if parsed > _MAX_SHARES:
            raise argparse.ArgumentTypeError(
                f"{value!r} exceeds the maximum share count ({_MAX_SHARES})"
            )
        return parsed

    parser = argparse.ArgumentParser(description="Trader Memory Core — thesis store CLI")
    parser.add_argument("--state-dir", default="state/theses", help="Path to thesis state dir")
    sub = parser.add_subparsers(dest="command")

    # list
    list_p = sub.add_parser("list", help="List theses")
    list_p.add_argument("--ticker", help="Filter by ticker")
    list_p.add_argument("--status", help="Filter by status")
    list_p.add_argument("--type", dest="thesis_type", help="Filter by thesis type")
    list_p.add_argument("--date-from", help="Filter by created_at >= YYYY-MM-DD")
    list_p.add_argument("--date-to", help="Filter by created_at <= YYYY-MM-DD")

    # get
    get_p = sub.add_parser("get", help="Get thesis by ID")
    get_p.add_argument("thesis_id", help="Thesis ID")

    # review-due
    review_p = sub.add_parser("review-due", help="List theses due for review")
    review_p.add_argument("--as-of", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    # rebuild-index
    sub.add_parser("rebuild-index", help="Rebuild _index.json from YAML files")

    # doctor
    sub.add_parser("doctor", help="Validate file/index consistency")

    # mark-reviewed
    mr_p = sub.add_parser("mark-reviewed", help="Record a review")
    mr_p.add_argument("thesis_id", help="Thesis ID")
    mr_p.add_argument("--review-date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    mr_p.add_argument("--outcome", default="OK", choices=["OK", "WARN", "REVIEW"])
    mr_p.add_argument("--notes", default=None)

    # record-lessons (CLOSED / INVALIDATED → outcome.lessons_learned)
    rl_p = sub.add_parser(
        "record-lessons", help="Record lessons learned on a CLOSED/INVALIDATED thesis"
    )
    rl_p.add_argument("thesis_id", help="Thesis ID")
    rl_src = rl_p.add_mutually_exclusive_group(required=True)
    rl_src.add_argument("--text", help="Lesson text (use --text=... if it starts with '-')")
    rl_src.add_argument("--file", help="Read lesson text from a UTF-8 file")
    rl_mode = rl_p.add_mutually_exclusive_group()
    rl_mode.add_argument(
        "--append", action="store_true", help="Add to an existing lesson (newline-joined)"
    )
    rl_mode.add_argument("--replace", action="store_true", help="Overwrite an existing lesson")

    # transition (IDEA → ENTRY_READY); --event-date backdates the history stamp
    tr_p = sub.add_parser("transition", help="Transition thesis status (e.g. ENTRY_READY)")
    tr_p.add_argument("thesis_id", help="Thesis ID")
    tr_p.add_argument("new_status", help="Target status (e.g. ENTRY_READY)")
    tr_p.add_argument("--reason", required=True, help="Reason for the transition")
    tr_p.add_argument("--event-date", default=None, help="Backdate status_history.at (YYYY-MM-DD)")

    # open-position (ENTRY_READY → ACTIVE)
    op_p = sub.add_parser("open-position", help="Open a position (→ ACTIVE)")
    op_p.add_argument("thesis_id", help="Thesis ID")
    op_p.add_argument(
        "--actual-price", type=_strict_finite_float, required=True, help="Entry price"
    )
    op_p.add_argument("--actual-date", required=True, help="Entry date (YYYY-MM-DD or ISO)")
    op_p.add_argument(
        "--shares", type=_strict_shares, default=None, help="Share count (fractional ok)"
    )
    op_p.add_argument(
        "--contracts", type=_strict_positive_int, default=None, help="Contract count (futures)"
    )
    op_p.add_argument(
        "--multiplier",
        type=float,
        default=None,
        help="Futures contract multiplier (required with --contracts if no futures "
        "position is already attached)",
    )
    op_p.add_argument(
        "--direction",
        choices=["LONG", "SHORT"],
        default=None,
        help="Futures direction (required with --contracts if no futures position "
        "is already attached)",
    )
    op_p.add_argument("--contract-symbol", default=None, help="Futures contract symbol, e.g. ES")
    op_p.add_argument(
        "--contract-currency",
        default=None,
        help="Futures contract currency (required with --contracts if no futures "
        "position is already attached; USD only)",
    )
    op_p.add_argument("--reason", default="position opened", help="Transition reason")
    op_p.add_argument("--event-date", default=None, help="Backdate status_history.at")

    # attach-position (position-sizer report)
    ap_p = sub.add_parser("attach-position", help="Attach a position-sizer report")
    ap_p.add_argument("thesis_id", help="Thesis ID")
    ap_p.add_argument("--report", required=True, help="Path to position-sizer JSON report")
    ap_p.add_argument("--expected-entry", type=float, default=None, help="Expected entry price")
    ap_p.add_argument("--expected-stop", type=float, default=None, help="Expected stop price")

    # attach-futures-position (futures-position-sizer SIZED report)
    afp_p = sub.add_parser(
        "attach-futures-position", help="Attach a futures-position-sizer SIZED report"
    )
    afp_p.add_argument("thesis_id", help="Thesis ID")
    afp_p.add_argument(
        "--report", required=True, help="Path to futures-position-sizer SIZED JSON report"
    )
    afp_p.add_argument(
        "--expected-entry",
        type=_strict_positive_finite_float,
        default=None,
        help="Expected entry price",
    )
    afp_p.add_argument(
        "--expected-stop",
        type=_strict_positive_finite_float,
        default=None,
        help="Expected stop price",
    )

    # close (ACTIVE → CLOSED)
    cl_p = sub.add_parser("close", help="Close an ACTIVE thesis")
    cl_p.add_argument("thesis_id", help="Thesis ID")
    cl_p.add_argument(
        "--exit-reason",
        required=True,
        choices=["stop_hit", "target_hit", "time_stop", "invalidated", "manual"],
    )
    cl_p.add_argument("--actual-price", type=_strict_finite_float, required=True, help="Exit price")
    cl_p.add_argument("--actual-date", required=True, help="Exit date (YYYY-MM-DD or ISO)")
    cl_p.add_argument("--event-date", default=None, help="Backdate status_history.at")

    # trim (partial close: ACTIVE/PARTIALLY_CLOSED → PARTIALLY_CLOSED or CLOSED)
    tr2_p = sub.add_parser("trim", help="Partially close (trim) a position")
    tr2_p.add_argument("thesis_id", help="Thesis ID")
    tr2_p.add_argument(
        "--shares-sold", type=_strict_shares, default=None, help="Quantity sold (equity)"
    )
    tr2_p.add_argument(
        "--contracts-sold",
        type=_strict_positive_int,
        default=None,
        help="Quantity sold (futures)",
    )
    tr2_p.add_argument(
        "--price", type=_strict_finite_float, required=True, help="Trim execution price"
    )
    tr2_p.add_argument("--date", required=True, help="Trim date (YYYY-MM-DD or ISO)")
    tr2_p.add_argument("--reason", default="position trimmed", help="Trim reason")
    tr2_p.add_argument(
        "--exit-reason",
        default=None,
        choices=["stop_hit", "target_hit", "time_stop", "invalidated", "manual"],
        help="Only used if the trim fully closes the position (default manual)",
    )
    tr2_p.add_argument("--event-date", default=None, help="Override ledger timestamp")

    # terminate (→ CLOSED or INVALIDATED)
    tm_p = sub.add_parser("terminate", help="Move thesis to a terminal state")
    tm_p.add_argument("thesis_id", help="Thesis ID")
    tm_p.add_argument("--terminal-status", required=True, choices=["CLOSED", "INVALIDATED"])
    tm_p.add_argument("--exit-reason", required=True, help="Reason for termination")
    tm_p.add_argument(
        "--actual-price", type=_strict_finite_float, default=None, help="Exit price (optional)"
    )
    tm_p.add_argument("--actual-date", default=None, help="Exit date (optional)")
    tm_p.add_argument("--event-date", default=None, help="Backdate status_history.at")

    args = parser.parse_args(argv)
    state_dir = Path(args.state_dir)

    if args.command == "list":
        results = query(
            state_dir,
            ticker=args.ticker,
            status=args.status,
            thesis_type=args.thesis_type,
            date_from=args.date_from,
            date_to=args.date_to,
        )
        print(json.dumps(results, indent=2))
    elif args.command == "get":
        thesis = get(state_dir, args.thesis_id)
        print(yaml.dump(thesis, default_flow_style=False, sort_keys=False))
    elif args.command == "review-due":
        results = list_review_due(state_dir, args.as_of)
        print(json.dumps(results, indent=2))
    elif args.command == "rebuild-index":
        idx = rebuild_index(state_dir)
        print(f"Rebuilt index: {len(idx['theses'])} theses")
    elif args.command == "doctor":
        result = validate_state(state_dir)
        print(json.dumps(result, indent=2))
    elif args.command == "mark-reviewed":
        t = mark_reviewed(
            state_dir,
            args.thesis_id,
            review_date=args.review_date,
            outcome=args.outcome,
            notes=args.notes,
        )
        print(
            f"Reviewed {args.thesis_id}: {args.outcome}, next review: "
            f"{t['monitoring']['next_review_date']}"
        )
    elif args.command == "record-lessons":
        if args.file is not None:
            try:
                lesson_text = Path(args.file).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as e:
                raise ValueError(f"cannot read --file {args.file}: {e}") from e
        else:
            lesson_text = args.text
        lesson_mode = "append" if args.append else "replace" if args.replace else "error"
        t, action = record_lessons(state_dir, args.thesis_id, lesson_text, mode=lesson_mode)
        stored = t["outcome"]["lessons_learned"]
        print(f"{args.thesis_id} lessons recorded ({len(stored)} chars, action={action})")
        print(f"Re-run 'review postmortem {args.thesis_id}' to refresh the journal report.")
    elif args.command == "transition":
        t = transition(
            state_dir,
            args.thesis_id,
            args.new_status,
            args.reason,
            event_date=_coerce_dt(args.event_date),
        )
        print(f"{args.thesis_id} → {t['status']}")
    elif args.command == "open-position":
        # P3-2: same guard as open_position() itself (defense in depth at
        # the CLI boundary, symmetric with trim's "exactly one of" check).
        if args.shares is not None and args.contracts is not None:
            raise ValueError(
                "open-position got both --shares and --contracts; provide "
                "either --shares (equity) or --contracts (futures), not both"
            )
        t = open_position(
            state_dir,
            args.thesis_id,
            args.actual_price,
            _coerce_dt(args.actual_date),
            reason=args.reason,
            shares=args.shares,
            event_date=_coerce_dt(args.event_date),
            contracts=args.contracts,
            multiplier=args.multiplier,
            direction=args.direction,
            contract_symbol=args.contract_symbol,
            contract_currency=args.contract_currency,
        )
        pos = t.get("position") or {}
        if pos.get("quantity_unit") == "contracts":
            print(
                f"{args.thesis_id} → {t['status']} @ {args.actual_price} "
                f"x {pos.get('quantity')} contracts"
            )
        else:
            print(f"{args.thesis_id} → {t['status']} @ {args.actual_price} x {args.shares}")
    elif args.command == "attach-position":
        t = attach_position(
            state_dir,
            args.thesis_id,
            args.report,
            expected_entry=args.expected_entry,
            expected_stop=args.expected_stop,
        )
        print(f"Attached position to {args.thesis_id}: {t['position']['shares']} shares")
    elif args.command == "attach-futures-position":
        t = attach_futures_position(
            state_dir,
            args.thesis_id,
            args.report,
            expected_entry=args.expected_entry,
            expected_stop=args.expected_stop,
        )
        pos = t["position"]
        print(
            f"Attached futures position to {args.thesis_id}: "
            f"{pos['quantity']} contracts ({pos['direction']})"
        )
    elif args.command == "close":
        t = close(
            state_dir,
            args.thesis_id,
            args.exit_reason,
            args.actual_price,
            _coerce_dt(args.actual_date),
            event_date=_coerce_dt(args.event_date),
        )
        out = t.get("outcome") or {}
        print(
            f"{args.thesis_id} → {t['status']} ({args.exit_reason}), pnl={out.get('pnl_dollars')}"
        )
    elif args.command == "trim":
        if (args.shares_sold is None) == (args.contracts_sold is None):
            raise ValueError(
                "trim requires exactly one of --shares-sold (equity) or --contracts-sold (futures)"
            )
        quantity = args.shares_sold if args.shares_sold is not None else args.contracts_sold
        t = trim(
            state_dir,
            args.thesis_id,
            quantity,
            args.price,
            _coerce_dt(args.date),
            reason=args.reason,
            exit_reason=args.exit_reason,
            event_date=_coerce_dt(args.event_date),
        )
        pos = t.get("position") or {}
        if args.contracts_sold is not None:
            rem = pos.get("quantity_remaining")
            unit = "contracts"
        else:
            rem = pos.get("shares_remaining")
            unit = "shares"
        print(
            f"{args.thesis_id} → {t['status']} "
            f"(sold {quantity} {unit} @ {args.price}, remaining {rem})"
        )
    elif args.command == "terminate":
        t = terminate(
            state_dir,
            args.thesis_id,
            args.terminal_status,
            args.exit_reason,
            actual_price=args.actual_price,
            actual_date=_coerce_dt(args.actual_date),
            event_date=_coerce_dt(args.event_date),
        )
        print(f"{args.thesis_id} → {t['status']} ({args.exit_reason})")
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1) from None
