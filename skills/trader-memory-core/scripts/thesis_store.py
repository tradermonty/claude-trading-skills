"""Trader Memory Core — thesis CRUD and index management.

Provides atomic read/write operations for thesis YAML files and the
_index.json summary.  All writes use tempfile + os.replace for safety.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml
from jsonschema import Draft7Validator, FormatChecker

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
        raise ValueError(f"Invalid date-time: {value}")
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


# -- Helpers ------------------------------------------------------------------


def _get_schema() -> dict:
    global _SCHEMA
    if _SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _SCHEMA = json.load(f)
    return _SCHEMA


def _validate_thesis(thesis: dict) -> None:
    """JSON Schema + business invariants. Called by _save_thesis()."""
    schema = _get_schema()
    validator = Draft7Validator(schema, format_checker=_FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(thesis), key=lambda e: list(e.path))
    if errors:
        raise ValueError(f"Schema validation failed: {errors[0].message}")

    status = thesis.get("status")

    position = thesis.get("position") or {}

    if status == "ACTIVE":
        entry = thesis.get("entry", {})
        if entry.get("actual_price") is None:
            raise ValueError("ACTIVE thesis requires entry.actual_price")
        if entry.get("actual_date") is None:
            raise ValueError("ACTIVE thesis requires entry.actual_date")
        # Legacy-lenient: pre-PR-80B ACTIVE files may lack shares_remaining
        # (runtime defaults it to shares). Only enforce when present.
        rem = position.get("shares_remaining")
        sh = position.get("shares")
        if rem is not None and sh is not None and rem != sh:
            raise ValueError(f"ACTIVE thesis: shares_remaining ({rem}) must equal shares ({sh})")

    if status == "PARTIALLY_CLOSED":
        # PR-80B-only status — NO legacy leniency: a PARTIALLY_CLOSED record
        # must be fully specified.
        entry = thesis.get("entry", {})
        if entry.get("actual_price") is None:
            raise ValueError("PARTIALLY_CLOSED thesis requires entry.actual_price")
        if entry.get("actual_date") is None:
            raise ValueError("PARTIALLY_CLOSED thesis requires entry.actual_date")
        if not thesis.get("position"):
            raise ValueError("PARTIALLY_CLOSED thesis requires a position")
        sh = position.get("shares")
        rem = position.get("shares_remaining")
        if sh is None:
            raise ValueError("PARTIALLY_CLOSED thesis requires position.shares")
        if rem is None:
            raise ValueError("PARTIALLY_CLOSED thesis requires position.shares_remaining")
        if not (0 < rem < sh):
            raise ValueError(
                f"PARTIALLY_CLOSED thesis requires 0 < shares_remaining ({rem}) < shares ({sh})"
            )

    if status == "CLOSED":
        exit_data = thesis.get("exit", {})
        if exit_data.get("actual_price") is None:
            raise ValueError("CLOSED thesis requires exit.actual_price")
        if exit_data.get("actual_date") is None:
            raise ValueError("CLOSED thesis requires exit.actual_date")
        exit_reason = exit_data.get("exit_reason")
        if exit_reason not in _VALID_EXIT_REASONS:
            raise ValueError(f"Invalid exit_reason: {exit_reason}")
        entry_date = thesis.get("entry", {}).get("actual_date")
        exit_date = exit_data.get("actual_date")
        if entry_date and exit_date and _parse_dt(exit_date) < _parse_dt(entry_date):
            raise ValueError("exit.actual_date must be >= entry.actual_date")
        # Legacy-lenient: only enforce when shares_remaining is present.
        rem = position.get("shares_remaining")
        if rem is not None and rem != 0:
            raise ValueError(f"CLOSED thesis requires shares_remaining == 0, got {rem}")

    if status == "INVALIDATED":
        exit_data = thesis.get("exit", {})
        exit_reason = exit_data.get("exit_reason")
        if exit_reason is not None and exit_reason != "invalidated":
            raise ValueError(
                f"INVALIDATED thesis must have exit_reason='invalidated', got '{exit_reason}'"
            )
        entry_date = thesis.get("entry", {}).get("actual_date")
        exit_date = exit_data.get("actual_date")
        if entry_date and exit_date and _parse_dt(exit_date) < _parse_dt(entry_date):
            raise ValueError("exit.actual_date must be >= entry.actual_date")

    # -- status_history monotonic check --
    history = thesis.get("status_history", [])
    for i in range(1, len(history)):
        prev_at = history[i - 1].get("at", "")
        curr_at = history[i].get("at", "")
        if prev_at and curr_at and _parse_dt(curr_at) < _parse_dt(prev_at):
            raise ValueError(
                f"status_history[{i}].at ({curr_at}) is before "
                f"status_history[{i - 1}].at ({prev_at})"
            )
    if history and history[-1]["status"] != thesis["status"]:
        raise ValueError(
            f"status_history[-1].status ({history[-1]['status']}) "
            f"!= thesis.status ({thesis['status']})"
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _coerce_dt(value: str | None) -> str | None:
    """Normalize a CLI date arg to an RFC 3339 date-time string.

    ``status_history.at`` / ``entry.actual_date`` are schema ``date-time``
    (``_check_datetime`` requires a 'T' separator + timezone). A bare
    ``YYYY-MM-DD`` is widened to midnight UTC — the same idiom register()
    applies to ``_source_date``. A value that already contains 'T' (a full
    timestamp) is returned unchanged; ``None`` stays ``None``.
    """
    if value is None:
        return None
    if "T" in value:
        return value
    return f"{value}T00:00:00+00:00"


def _generate_thesis_id(ticker: str, thesis_type: str, date_str: str) -> str:
    """Generate a thesis ID with a 4-char hash suffix for uniqueness."""
    abbr = _TYPE_ABBR.get(thesis_type)
    if abbr is None:
        raise ValueError(
            f"Unknown thesis_type: {thesis_type}. Must be one of {sorted(_VALID_THESIS_TYPES)}"
        )
    salt = uuid.uuid4().hex[:8]
    hash4 = hashlib.sha256(f"{ticker}_{thesis_type}_{date_str}_{salt}".encode()).hexdigest()[:4]
    return f"th_{ticker.lower()}_{abbr}_{date_str}_{hash4}"


def _compute_origin_fingerprint(thesis_data: dict) -> str:
    """Compute a deterministic fingerprint for deduplication."""
    parts = [
        thesis_data.get("ticker", ""),
        thesis_data.get("thesis_type", ""),
        thesis_data.get("thesis_statement", ""),
        thesis_data.get("_source_date", ""),
    ]
    origin = thesis_data.get("origin", {})
    parts.append(origin.get("skill", ""))
    # output_file excluded from fingerprint (path-dependent, not content-dependent)
    raw = origin.get("raw_provenance", {})
    if raw:
        parts.append(json.dumps(raw, sort_keys=True, default=str))
    content = "|".join(parts)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _find_by_fingerprint(state_dir: Path, fingerprint: str) -> str | None:
    """Find thesis ID by fingerprint. Index first, always YAML fallback."""
    index = _load_index(state_dir)
    for tid, entry in index.get("theses", {}).items():
        if entry.get("origin_fingerprint") == fingerprint:
            return tid
    # Always fall back to YAML scan (index may be partial)
    for yaml_path in state_dir.glob("th_*.yaml"):
        try:
            thesis = yaml.safe_load(yaml_path.read_text())
            if thesis and thesis.get("origin_fingerprint") == fingerprint:
                return thesis["thesis_id"]
        except (OSError, yaml.YAMLError, KeyError):
            continue
    return None


def _atomic_write_yaml(path: Path, data: dict) -> None:
    """Write YAML atomically using tempfile + os.replace."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically using tempfile + os.replace."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_index(state_dir: Path) -> dict:
    """Load _index.json or return empty index."""
    idx_path = state_dir / INDEX_FILE
    if idx_path.exists():
        with open(idx_path) as f:
            return json.load(f)
    return {"version": 1, "theses": {}}


def _save_index(state_dir: Path, index: dict) -> None:
    """Save _index.json atomically."""
    _atomic_write_json(state_dir / INDEX_FILE, index)


def _load_thesis(state_dir: Path, thesis_id: str) -> dict:
    """Load a thesis YAML file."""
    path = state_dir / f"{thesis_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Thesis not found: {thesis_id}")
    with open(path) as f:
        return yaml.safe_load(f)


def _save_thesis(state_dir: Path, thesis: dict) -> None:
    """Validate and save a thesis YAML file atomically."""
    _validate_thesis(thesis)
    path = state_dir / f"{thesis['thesis_id']}.yaml"
    _atomic_write_yaml(path, thesis)


def _default_thesis() -> dict:
    """Return a thesis template with all fields set to defaults."""
    return {
        "thesis_id": None,
        "ticker": None,
        "created_at": None,
        "updated_at": None,
        "thesis_type": None,
        "setup_type": None,
        "catalyst": None,
        "status": "IDEA",
        "status_history": [],
        "thesis_statement": None,
        "mechanism_tag": None,
        "evidence": [],
        "kill_criteria": [],
        "confidence": None,
        "confidence_score": None,
        "origin_fingerprint": None,
        "entry": {
            "target_price": None,
            "conditions": [],
            "actual_price": None,
            "actual_date": None,
        },
        "exit": {
            "stop_loss": None,
            "stop_loss_pct": None,
            "take_profit": None,
            "take_profit_rr": None,
            "time_stop_days": None,
            "actual_price": None,
            "actual_date": None,
            "exit_reason": None,
        },
        "position": None,
        "market_context": None,
        "monitoring": {
            "review_interval_days": 30,
            "next_review_date": None,
            "last_review_date": None,
            "review_status": "OK",
            "triggers_config": [],
            "alerts": [],
        },
        "origin": {
            "skill": None,
            "output_file": None,
            "screening_grade": None,
            "screening_score": None,
            "raw_provenance": {},
        },
        "linked_reports": [],
        "outcome": {
            "pnl_dollars": None,
            "pnl_pct": None,
            "holding_days": None,
            "mae_pct": None,
            "mfe_pct": None,
            "mae_mfe_source": None,
            "lessons_learned": None,
        },
    }


def _project_index_fields(thesis: dict) -> dict:
    """Project thesis fields into the lightweight index representation."""
    created_date = thesis["created_at"][:10] if thesis["created_at"] else None
    updated_at = thesis.get("updated_at") or thesis["created_at"]
    updated_date = updated_at[:10] if updated_at else None
    return {
        "ticker": thesis["ticker"],
        "status": thesis["status"],
        "thesis_type": thesis["thesis_type"],
        "created_at": created_date,
        "updated_at": updated_date,
        "next_review_date": thesis.get("monitoring", {}).get("next_review_date"),
        "review_status": thesis.get("monitoring", {}).get("review_status", "OK"),
        "origin_fingerprint": thesis.get("origin_fingerprint"),
    }


def _update_index_entry(index: dict, thesis: dict) -> None:
    """Update the index entry for a thesis."""
    tid = thesis["thesis_id"]
    index["theses"][tid] = _project_index_fields(thesis)


# -- Public API ---------------------------------------------------------------


def register(state_dir: Path, thesis_data: dict) -> str:
    """Register a new thesis from provided data.

    Args:
        state_dir: Path to state/theses/ directory.
        thesis_data: Partial thesis dict with at least ticker, thesis_type,
                     thesis_statement, and origin fields.

    Returns:
        The generated thesis_id.

    Raises:
        ValueError: If required fields are missing or thesis_type is invalid.
    """
    required = ["ticker", "thesis_type", "thesis_statement"]
    for field in required:
        if not thesis_data.get(field):
            raise ValueError(f"Missing required field: {field}")

    if thesis_data["thesis_type"] not in _VALID_THESIS_TYPES:
        raise ValueError(
            f"Invalid thesis_type: {thesis_data['thesis_type']}. "
            f"Must be one of {sorted(_VALID_THESIS_TYPES)}"
        )

    # Validate origin sub-fields (clear error messages before schema check)
    origin = thesis_data.get("origin", {})
    if not origin.get("skill"):
        raise ValueError("Missing required field: origin.skill")
    if not origin.get("output_file"):
        raise ValueError("Missing required field: origin.output_file")

    # Build thesis from template + provided data
    state_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = _compute_origin_fingerprint(thesis_data)

    thesis = _default_thesis()
    now = _now_iso()

    # Use source date if provided (e.g., report's as_of), else today
    source_date = thesis_data.get("_source_date")  # "YYYY-MM-DD" or None
    if source_date:
        date_str = source_date.replace("-", "")
        created_at = f"{source_date}T00:00:00+00:00"
        source_base = created_at  # status_history and next_review use source date
    else:
        date_str = _today_str()
        created_at = now
        source_base = now
    thesis_id = _generate_thesis_id(thesis_data["ticker"], thesis_data["thesis_type"], date_str)

    thesis["thesis_id"] = thesis_id
    thesis["ticker"] = thesis_data["ticker"].upper()
    thesis["created_at"] = created_at
    thesis["updated_at"] = now
    thesis["thesis_type"] = thesis_data["thesis_type"]
    thesis["origin_fingerprint"] = fingerprint
    thesis["status"] = "IDEA"
    thesis["status_history"] = [
        {
            "status": "IDEA",
            "at": source_base,
            "reason": thesis_data.get("_register_reason", "registered"),
        }
    ]

    # Copy optional fields
    for key in [
        "setup_type",
        "catalyst",
        "thesis_statement",
        "mechanism_tag",
        "evidence",
        "kill_criteria",
        "confidence",
        "confidence_score",
    ]:
        if key in thesis_data:
            thesis[key] = thesis_data[key]

    # Copy nested objects
    if "entry" in thesis_data:
        thesis["entry"].update(thesis_data["entry"])
    if "exit" in thesis_data:
        thesis["exit"].update(thesis_data["exit"])
    if "market_context" in thesis_data:
        thesis["market_context"] = thesis_data["market_context"]
    if "monitoring" in thesis_data:
        thesis["monitoring"].update(thesis_data["monitoring"])
    if "origin" in thesis_data:
        thesis["origin"].update(thesis_data["origin"])

    # Set next_review_date based on source date (not wall-clock)
    interval = thesis["monitoring"].get("review_interval_days", 30)
    base_dt = datetime.fromisoformat(source_base)
    next_review = (base_dt + timedelta(days=interval)).strftime("%Y-%m-%d")
    thesis["monitoring"]["next_review_date"] = next_review

    # Validate complete thesis BEFORE idempotency check —
    # invalid input must fail even if fingerprint matches an existing thesis.
    _validate_thesis(thesis)

    # Idempotency: check fingerprint after validation passes
    existing_tid = _find_by_fingerprint(state_dir, fingerprint)
    if existing_tid:
        logger.info(
            "Idempotent register: %s already exists for fingerprint %s",
            existing_tid,
            fingerprint[:8],
        )
        return existing_tid

    # Persist
    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Registered thesis %s for %s", thesis_id, thesis["ticker"])
    return thesis_id


def get(state_dir: Path, thesis_id: str) -> dict:
    """Load a thesis by ID.

    Raises:
        FileNotFoundError: If thesis does not exist.
    """
    return _load_thesis(state_dir, thesis_id)


def query(
    state_dir: Path,
    *,
    ticker: str | None = None,
    status: str | None = None,
    thesis_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Query theses by filter criteria using the index.

    Args:
        state_dir: Path to state/theses/ directory.
        ticker: Filter by ticker symbol.
        status: Filter by status.
        thesis_type: Filter by thesis type.
        date_from: Filter by created_at >= date_from (YYYY-MM-DD).
        date_to: Filter by created_at <= date_to (YYYY-MM-DD).

    Returns list of matching index entries (lightweight, not full thesis).
    """
    index = _load_index(state_dir)
    results = []
    for tid, entry in index.get("theses", {}).items():
        if ticker and entry.get("ticker", "").upper() != ticker.upper():
            continue
        if status and entry.get("status") != status:
            continue
        if thesis_type and entry.get("thesis_type") != thesis_type:
            continue
        created = entry.get("created_at", "")
        if date_from and created < date_from:
            continue
        if date_to and created > date_to:
            continue
        results.append({"thesis_id": tid, **entry})
    return results


def update(state_dir: Path, thesis_id: str, fields: dict) -> dict:
    """Partial update of a thesis.

    Args:
        state_dir: Path to state/theses/ directory.
        thesis_id: Thesis to update.
        fields: Dict of fields to update (shallow merge for top-level,
                deep merge for nested dicts like entry, exit, monitoring).

    Returns:
        The updated thesis dict.
    """
    thesis = _load_thesis(state_dir, thesis_id)
    now = _now_iso()

    # Deep merge nested dicts
    _protected = frozenset(
        {
            "thesis_id",
            "created_at",
            "status",
            "status_history",
            "ticker",
            "thesis_type",
            "origin_fingerprint",
        }
    )
    _nested_keys = {"entry", "exit", "monitoring", "market_context", "origin", "outcome"}
    for key, value in fields.items():
        if key in _protected:
            raise ValueError(f"Cannot update protected field: {key}")
        if key in _nested_keys and isinstance(value, dict) and isinstance(thesis.get(key), dict):
            thesis[key].update(value)
        else:
            thesis[key] = value

    thesis["updated_at"] = now
    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    return thesis


def transition(
    state_dir: Path,
    thesis_id: str,
    new_status: str,
    reason: str,
    event_date: str | None = None,
) -> dict:
    """Transition thesis to a new status.

    Only allows IDEA → ENTRY_READY. All terminal statuses (ACTIVE, CLOSED,
    INVALIDATED) are blocked — use open_position(), close(), or terminate().

    Args:
        event_date: Optional ISO/date string for status_history.at (for
            backfilling existing broker positions). Defaults to now. Mirrors
            open_position(); a bare YYYY-MM-DD is widened to midnight UTC so a
            later backdated open_position() stays monotonic.

    Raises:
        ValueError: If the transition is invalid.
    """
    thesis = _load_thesis(state_dir, thesis_id)
    current = thesis["status"]

    if current in _TERMINAL_STATUSES:
        raise ValueError(f"Cannot transition from terminal status {current}")

    if new_status == "ACTIVE":
        raise ValueError(
            "Use open_position() to transition to ACTIVE — "
            "it requires actual_price and actual_date."
        )

    if new_status == "PARTIALLY_CLOSED":
        raise ValueError(
            "Use trim() to reach PARTIALLY_CLOSED — it requires shares_sold, price, and date."
        )

    if new_status in _TERMINAL_STATUSES:
        raise ValueError(
            f"Cannot transition to terminal status {new_status} via transition(). "
            "Use close() for CLOSED or terminate() for INVALIDATED."
        )

    # Forward-only check (only IDEA → ENTRY_READY remains)
    current_idx = _STATUS_ORDER.index(current)
    try:
        new_idx = _STATUS_ORDER.index(new_status)
    except ValueError:
        raise ValueError(f"Invalid status: {new_status}")
    if new_idx <= current_idx:
        raise ValueError(f"Cannot transition backward from {current} to {new_status}")

    now = _now_iso()
    history_at = _coerce_dt(event_date) or now
    thesis["status"] = new_status
    thesis["status_history"].append({"status": new_status, "at": history_at, "reason": reason})
    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Transitioned %s: %s → %s (%s)", thesis_id, current, new_status, reason)
    return thesis


def attach_position(
    state_dir: Path,
    thesis_id: str,
    position_report_path: str,
    expected_entry: float | None = None,
    expected_stop: float | None = None,
) -> dict:
    """Attach position-sizer output to an existing thesis.

    Validates:
      1. Report mode must be "shares" (budget mode has no shares/value/risk).
      2. If expected_entry is provided, must match report's entry_price.
      3. If expected_stop is provided, must match report's stop_price.

    Raises:
        ValueError: If validation fails.
        FileNotFoundError: If report or thesis doesn't exist.
    """
    report_path = Path(position_report_path)
    if not report_path.exists():
        raise FileNotFoundError(f"Position report not found: {position_report_path}")

    with open(report_path) as f:
        report = json.load(f)

    # Validate mode
    mode = report.get("mode")
    if mode != "shares":
        raise ValueError(
            f"Position report mode is '{mode}', expected 'shares'. "
            "Budget mode does not produce shares/value/risk fields."
        )

    # Validate expected entry/stop
    params = report.get("parameters", {})
    if expected_entry is not None:
        actual_entry = params.get("entry_price")
        if actual_entry is not None and abs(actual_entry - expected_entry) > 0.01:
            raise ValueError(
                f"Entry price mismatch: thesis expects {expected_entry}, report has {actual_entry}"
            )
    if expected_stop is not None:
        actual_stop = params.get("stop_price")
        if actual_stop is not None and abs(actual_stop - expected_stop) > 0.01:
            raise ValueError(
                f"Stop price mismatch: thesis expects {expected_stop}, report has {actual_stop}"
            )

    thesis = _load_thesis(state_dir, thesis_id)

    # attach_position() (re)writes position incl. shares_remaining == shares.
    # That is only coherent before the position is opened or while it is fully
    # open. On PARTIALLY_CLOSED it would violate 0 < shares_remaining < shares,
    # on CLOSED it would violate shares_remaining == 0, and either would
    # clobber the trim ledger relationship — reject those (and terminal
    # INVALIDATED) explicitly.
    _ATTACH_ALLOWED = {"IDEA", "ENTRY_READY", "ACTIVE"}
    if thesis["status"] not in _ATTACH_ALLOWED:
        raise ValueError(
            f"attach_position() not allowed for status {thesis['status']}; "
            f"only {sorted(_ATTACH_ALLOWED)} (would corrupt shares_remaining)"
        )

    # Determine sizing method from whichever calculation was actually used
    sizing_method = None
    calcs = report.get("calculations", {})
    for method_key in ("fixed_fractional", "atr_based", "kelly"):
        if calcs.get(method_key) is not None:
            sizing_method = calcs[method_key].get("method", method_key)
            break

    thesis["position"] = {
        "shares": report.get("final_recommended_shares"),
        "shares_remaining": report.get("final_recommended_shares"),
        "position_value": report.get("final_position_value"),
        "risk_dollars": report.get("final_risk_dollars"),
        "risk_pct_of_account": report.get("final_risk_pct"),
        "account_type": None,
        "sizing_method": sizing_method,
        "raw_source": {
            "skill": "position-sizer",
            "file": str(position_report_path),
            "fields": {
                "final_recommended_shares": report.get("final_recommended_shares"),
                "final_position_value": report.get("final_position_value"),
                "final_risk_dollars": report.get("final_risk_dollars"),
            },
        },
    }
    thesis["updated_at"] = _now_iso()

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Attached position to %s: %s shares", thesis_id, thesis["position"]["shares"])
    return thesis


def link_report(state_dir: Path, thesis_id: str, skill: str, file: str, date: str) -> dict:
    """Add a linked report to the thesis."""
    thesis = _load_thesis(state_dir, thesis_id)
    thesis["linked_reports"].append({"skill": skill, "file": file, "date": date})
    thesis["updated_at"] = _now_iso()

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    return thesis


def _sum_realized(history: list[dict]) -> float:
    """Σ realized_pnl over status_history ledger entries (trims + final leg)."""
    return sum(e["realized_pnl"] for e in history if "realized_pnl" in e)


def _finalize_outcome(
    thesis: dict,
    *,
    exit_price: float,
    exit_date: str,
    history_at: str,
    status: str,
    reason: str,
    append_entry: bool,
) -> None:
    """Roll up the cumulative realized outcome for a position-backed thesis.

    Single owner of the final-leg status_history ledger append. Callers:
      - close() / terminate(): append_entry=True (this appends the one final
        ledger entry for the still-open remainder).
      - trim() full close-out: append_entry=False (trim already appended the
        final ledger entry; here we only sum + finalize).

    Precondition: thesis has a position with shares (legacy / no-position
    theses keep their pre-PR-80B code path in the caller and never reach here).
    """
    entry_price = thesis["entry"].get("actual_price")
    entry_date = thesis["entry"].get("actual_date")
    position = thesis["position"]
    original = position["shares"]
    remaining = position.get("shares_remaining", original)

    if append_entry:
        thesis["status_history"].append(
            {
                "status": status,
                "at": history_at,
                "reason": reason,
                "shares_sold": remaining,
                "price": exit_price,
                "proceeds": round(exit_price * remaining, 2),
                "realized_pnl": round((exit_price - entry_price) * remaining, 2),
            }
        )

    position["shares_remaining"] = 0
    thesis["status"] = status

    pnl_dollars = round(_sum_realized(thesis["status_history"]), 2)
    thesis["outcome"]["pnl_dollars"] = pnl_dollars
    if entry_price and original:
        thesis["outcome"]["pnl_pct"] = round(pnl_dollars / (entry_price * original) * 100, 2)
    else:
        thesis["outcome"]["pnl_pct"] = None

    holding_days = None
    if entry_date:
        try:
            holding_days = (_parse_dt(exit_date) - _parse_dt(entry_date)).days
        except (ValueError, TypeError):
            pass
    thesis["outcome"]["holding_days"] = holding_days


def close(
    state_dir: Path,
    thesis_id: str,
    exit_reason: str,
    actual_price: float,
    actual_date: str,
    event_date: str | None = None,
) -> dict:
    """Close an ACTIVE or PARTIALLY_CLOSED thesis and compute outcome.

    With a position: outcome is the cumulative realized P&L (Σ trim
    realized_pnl + this final leg). With no position: the pre-PR-80B
    single-leg behaviour is kept verbatim.

    Args:
        state_dir: Path to state/theses/.
        thesis_id: Thesis to close.
        exit_reason: One of stop_hit, target_hit, time_stop, invalidated, manual.
        actual_price: Exit price.
        actual_date: Exit date (ISO format).
        event_date: Optional ISO timestamp for status_history.at (for backfilling).

    Returns:
        Updated thesis dict.

    Raises:
        ValueError: If thesis is not ACTIVE/PARTIALLY_CLOSED or entry missing.
    """
    thesis = _load_thesis(state_dir, thesis_id)

    if thesis["status"] not in ("ACTIVE", "PARTIALLY_CLOSED"):
        raise ValueError(
            f"Can only close ACTIVE or PARTIALLY_CLOSED thesis, current status: {thesis['status']}"
        )

    entry_price = thesis["entry"].get("actual_price")
    entry_date = thesis["entry"].get("actual_date")

    if entry_price is None:
        raise ValueError("Cannot close thesis: entry.actual_price is not set")

    # Set exit data
    thesis["exit"]["actual_price"] = actual_price
    thesis["exit"]["actual_date"] = actual_date
    thesis["exit"]["exit_reason"] = exit_reason

    now = _now_iso()
    history_at = event_date or now
    position = thesis.get("position")

    if position and position.get("shares"):
        # Cumulative path (single-owner ledger append in _finalize_outcome).
        _finalize_outcome(
            thesis,
            exit_price=actual_price,
            exit_date=actual_date,
            history_at=history_at,
            status="CLOSED",
            reason=f"closed: {exit_reason}",
            append_entry=True,
        )
    else:
        # Legacy no-position path — pre-PR-80B behaviour, byte-identical.
        pnl_dollars = actual_price - entry_price
        pnl_pct = ((actual_price - entry_price) / entry_price) * 100 if entry_price else None
        holding_days = None
        if entry_date:
            try:
                holding_days = (_parse_dt(actual_date) - _parse_dt(entry_date)).days
            except (ValueError, TypeError):
                pass
        thesis["outcome"]["pnl_dollars"] = (
            round(pnl_dollars, 2) if pnl_dollars is not None else None
        )
        thesis["outcome"]["pnl_pct"] = round(pnl_pct, 2) if pnl_pct is not None else None
        thesis["outcome"]["holding_days"] = holding_days
        thesis["status"] = "CLOSED"
        thesis["status_history"].append(
            {"status": "CLOSED", "at": history_at, "reason": f"closed: {exit_reason}"}
        )

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Closed %s: %s, P&L=%.2f%%",
        thesis_id,
        exit_reason,
        thesis["outcome"].get("pnl_pct") or 0,
    )
    return thesis


def trim(
    state_dir: Path,
    thesis_id: str,
    shares_sold: float,
    price: float,
    date: str,
    reason: str = "position trimmed",
    exit_reason: str | None = None,
    event_date: str | None = None,
) -> dict:
    """Partially close (trim) an ACTIVE / PARTIALLY_CLOSED position.

    Records a status_history ledger entry (shares_sold / price / proceeds /
    realized_pnl) and decrements position.shares_remaining. If the trim sells
    the entire remaining quantity it becomes a full close-out (status CLOSED,
    exit fields set, cumulative outcome).

    Args:
        shares_sold: Quantity sold in this trim (0 < shares_sold <= remaining).
        price: Trim execution price.
        date: Trim execution date (YYYY-MM-DD or ISO).
        exit_reason: Only used when this trim fully closes the position
            (default "manual"); ∈ stop_hit/target_hit/time_stop/invalidated/manual.
        event_date: Overrides the ledger timestamp (else --date is used).

    Raises:
        ValueError: On bad status / missing entry / no position / bad qty.
    """
    thesis = _load_thesis(state_dir, thesis_id)
    status = thesis["status"]
    if status not in ("ACTIVE", "PARTIALLY_CLOSED"):
        raise ValueError(
            f"Can only trim ACTIVE or PARTIALLY_CLOSED thesis, current status: {status}"
        )

    entry_price = thesis["entry"].get("actual_price")
    if entry_price is None:
        raise ValueError("Cannot trim thesis: entry.actual_price is not set")

    position = thesis.get("position")
    if not position or position.get("shares") is None:
        raise ValueError("trim requires a recorded position — run open-position --shares first")

    original = position["shares"]
    remaining = position.get("shares_remaining", original)  # legacy default
    if not (0 < shares_sold <= remaining):
        raise ValueError(
            f"shares_sold ({shares_sold}) must be > 0 and <= shares_remaining ({remaining})"
        )

    realized = round((price - entry_price) * shares_sold, 2)
    proceeds = round(price * shares_sold, 2)
    # Round to kill float-subtraction noise (7.86 - 4.00 == 3.86000…3),
    # then epsilon-snap a ~0 remainder to an exact 0.0 (→ full close-out).
    new_remaining = round(remaining - shares_sold, 8)
    if abs(new_remaining) < 1e-9:
        new_remaining = 0.0

    now = _now_iso()
    history_at = _coerce_dt(event_date) or _coerce_dt(date)
    full_close = new_remaining == 0
    new_status = "CLOSED" if full_close else "PARTIALLY_CLOSED"

    # trim() owns its ledger append (exactly one entry per trim).
    thesis["status_history"].append(
        {
            "status": new_status,
            "at": history_at,
            "reason": reason,
            "shares_sold": shares_sold,
            "price": price,
            "proceeds": proceeds,
            "realized_pnl": realized,
        }
    )
    position["shares_remaining"] = new_remaining

    if full_close:
        exit_date = _coerce_dt(date)
        thesis["exit"]["actual_price"] = price
        thesis["exit"]["actual_date"] = exit_date
        thesis["exit"]["exit_reason"] = exit_reason or "manual"
        thesis["status"] = "CLOSED"
        # Ledger entry already appended above → append_entry=False (sum only).
        _finalize_outcome(
            thesis,
            exit_price=price,
            exit_date=exit_date,
            history_at=history_at,
            status="CLOSED",
            reason=reason,
            append_entry=False,
        )
    else:
        thesis["status"] = "PARTIALLY_CLOSED"

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Trimmed %s: sold %s @ %.4f → %s remaining, status %s",
        thesis_id,
        shares_sold,
        price,
        new_remaining,
        thesis["status"],
    )
    return thesis


def open_position(
    state_dir: Path,
    thesis_id: str,
    actual_price: float,
    actual_date: str,
    reason: str = "position opened",
    shares: float | None = None,
    event_date: str | None = None,
) -> dict:
    """Transition thesis from ENTRY_READY to ACTIVE with entry data.

    This is the only way to reach ACTIVE status. transition() blocks ACTIVE.

    Args:
        state_dir: Path to state/theses/.
        thesis_id: Thesis to activate.
        actual_price: Entry price.
        actual_date: Entry date (ISO format).
        reason: Transition reason.
        shares: Optional share count to record.
        event_date: Optional ISO timestamp for status_history.at (for backfilling).

    Returns:
        Updated thesis dict.

    Raises:
        ValueError: If thesis is not ENTRY_READY.
    """
    thesis = _load_thesis(state_dir, thesis_id)

    if thesis["status"] != "ENTRY_READY":
        raise ValueError(f"open_position() requires ENTRY_READY status, got {thesis['status']}")

    now = _now_iso()
    thesis["entry"]["actual_price"] = actual_price
    thesis["entry"]["actual_date"] = actual_date
    if shares is not None:
        if thesis["position"] is None:
            thesis["position"] = {}
        thesis["position"]["shares"] = shares
    # A PR-80B-era ACTIVE thesis carries shares_remaining explicitly (== the
    # full opened quantity). Covers both --shares here and an earlier
    # attach_position()-populated position; legacy (no shares) stays absent.
    pos = thesis.get("position")
    if pos and pos.get("shares") is not None and pos.get("shares_remaining") is None:
        pos["shares_remaining"] = pos["shares"]

    history_at = event_date or now
    thesis["status"] = "ACTIVE"
    thesis["status_history"].append({"status": "ACTIVE", "at": history_at, "reason": reason})
    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Opened position %s at %.2f", thesis_id, actual_price)
    return thesis


def terminate(
    state_dir: Path,
    thesis_id: str,
    terminal_status: str,
    exit_reason: str,
    actual_price: float | None = None,
    actual_date: str | None = None,
    event_date: str | None = None,
) -> dict:
    """Move thesis to a terminal state (CLOSED or INVALIDATED).

    For CLOSED: delegates to close() which requires actual_price/date.
    For INVALIDATED: actual_price/date are optional. If ACTIVE with price,
    computes P&L. Partial outcome (no P&L) is allowed.

    Args:
        event_date: Optional ISO timestamp for status_history.at (for backfilling).

    Raises:
        ValueError: If terminal_status is invalid or thesis is already terminal.
    """
    if terminal_status == "CLOSED":
        if actual_price is None or actual_date is None:
            raise ValueError("CLOSED requires actual_price and actual_date")
        return close(
            state_dir, thesis_id, exit_reason, actual_price, actual_date, event_date=event_date
        )

    if terminal_status != "INVALIDATED":
        raise ValueError(f"terminal_status must be CLOSED or INVALIDATED, got {terminal_status}")

    thesis = _load_thesis(state_dir, thesis_id)

    if thesis["status"] in _TERMINAL_STATUSES:
        raise ValueError(f"Cannot terminate: already in terminal status {thesis['status']}")

    now = _now_iso()

    # Set exit data if provided
    if actual_price is not None:
        thesis["exit"]["actual_price"] = actual_price
    if actual_date is not None:
        thesis["exit"]["actual_date"] = actual_date
    # exit_reason enum: use "invalidated"; user's reason goes in status_history
    thesis["exit"]["exit_reason"] = "invalidated"

    entry_price = thesis["entry"].get("actual_price")
    history_at = event_date or now
    position = thesis.get("position")

    if (
        position
        and position.get("shares")
        and actual_price is not None
        and actual_date is not None
        and entry_price
    ):
        # Cumulative path: single-owner ledger append + roll-up. For a no-trim
        # ACTIVE thesis (shares_remaining == shares) this yields the same
        # pnl_dollars/pct as the legacy block below; for a PARTIALLY_CLOSED
        # thesis it correctly sums prior trims (no double-count).
        _finalize_outcome(
            thesis,
            exit_price=actual_price,
            exit_date=actual_date,
            history_at=history_at,
            status="INVALIDATED",
            reason=f"invalidated: {exit_reason}",
            append_entry=True,
        )
    else:
        # Pre-PR-80B partial-outcome path — verbatim (covers no-price
        # terminate INVALIDATED, incl. position-attached but no exit price).
        if entry_price and actual_price:
            pnl_pct = ((actual_price - entry_price) / entry_price) * 100
            pnl_dollars = actual_price - entry_price
            if thesis.get("position") and thesis["position"].get("shares"):
                pnl_dollars *= thesis["position"]["shares"]
            thesis["outcome"]["pnl_pct"] = round(pnl_pct, 2)
            thesis["outcome"]["pnl_dollars"] = round(pnl_dollars, 2)

            entry_date = thesis["entry"].get("actual_date")
            if entry_date and actual_date:
                try:
                    holding_days = (_parse_dt(actual_date) - _parse_dt(entry_date)).days
                    thesis["outcome"]["holding_days"] = holding_days
                except (ValueError, TypeError):
                    pass

        thesis["status"] = "INVALIDATED"
        thesis["status_history"].append(
            {
                "status": "INVALIDATED",
                "at": history_at,
                "reason": f"invalidated: {exit_reason}",
            }
        )

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Terminated %s → INVALIDATED: %s", thesis_id, exit_reason)
    return thesis


def mark_reviewed(
    state_dir: Path,
    thesis_id: str,
    *,
    review_date: str,
    outcome: str = "OK",
    notes: str | None = None,
) -> dict:
    """Record a review and advance next_review_date.

    Args:
        state_dir: Path to state/theses/.
        thesis_id: Thesis to review.
        review_date: Date of review (YYYY-MM-DD).
        outcome: One of "OK", "WARN", "REVIEW".
        notes: Optional review notes (appended to alerts).

    Returns:
        Updated thesis dict.

    Raises:
        ValueError: If thesis is in terminal status or outcome is invalid.
    """
    valid_outcomes = {"OK", "WARN", "REVIEW"}
    if outcome not in valid_outcomes:
        raise ValueError(f"outcome must be one of {valid_outcomes}, got {outcome}")

    thesis = _load_thesis(state_dir, thesis_id)

    if thesis["status"] in _TERMINAL_STATUSES:
        raise ValueError(f"Cannot review terminal thesis ({thesis['status']})")

    interval = thesis["monitoring"].get("review_interval_days", 30)
    review_dt = datetime.fromisoformat(f"{review_date}T00:00:00+00:00")
    next_review = (review_dt + timedelta(days=interval)).strftime("%Y-%m-%d")

    thesis["monitoring"]["last_review_date"] = review_date
    thesis["monitoring"]["next_review_date"] = next_review
    thesis["monitoring"]["review_status"] = outcome

    if notes:
        thesis["monitoring"]["alerts"].append(f"[{review_date}] {outcome}: {notes}")

    thesis["updated_at"] = _now_iso()

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Reviewed %s: %s → next %s", thesis_id, outcome, next_review)
    return thesis


def list_active(state_dir: Path) -> list[dict]:
    """List all ACTIVE theses from the index."""
    return query(state_dir, status="ACTIVE")


def list_review_due(state_dir: Path, as_of: str) -> list[dict]:
    """List theses with next_review_date <= as_of.

    Args:
        state_dir: Path to state/theses/.
        as_of: Date string (YYYY-MM-DD) for comparison.

    Returns:
        List of index entries for theses due for review.
    """
    as_of_date = date.fromisoformat(as_of)
    index = _load_index(state_dir)
    results = []
    for tid, entry in index.get("theses", {}).items():
        if entry.get("status") in _TERMINAL_STATUSES:
            continue
        nrd = entry.get("next_review_date")
        if nrd:
            try:
                if date.fromisoformat(nrd) <= as_of_date:
                    results.append({"thesis_id": tid, **entry})
            except ValueError:
                logger.warning("Skipping unparsable next_review_date for %s: %s", tid, nrd)
    return results


# -- Recovery tools -----------------------------------------------------------


def rebuild_index(state_dir: Path) -> dict:
    """Rebuild _index.json from valid th_*.yaml files.

    Skips files that fail schema or business invariant validation.

    Returns:
        The rebuilt index dict.
    """
    index = {"version": 1, "theses": {}}
    for yaml_path in sorted(state_dir.glob("th_*.yaml")):
        try:
            thesis = yaml.safe_load(yaml_path.read_text())
            if thesis and "thesis_id" in thesis:
                _validate_thesis(thesis)
                _update_index_entry(index, thesis)
        except Exception as e:
            logger.warning("Skipping invalid file %s: %s", yaml_path.name, e)
            continue

    _save_index(state_dir, index)
    logger.info("Rebuilt index: %d theses", len(index["theses"]))
    return index


def validate_state(state_dir: Path) -> dict:
    """Check file ⇔ index consistency and schema validity.

    Returns:
        {"ok": bool, "missing_in_index": [...], "orphaned_in_index": [...],
         "field_mismatches": [...], "schema_errors": [...]}
    """
    index = _load_index(state_dir)
    index_ids = set(index.get("theses", {}).keys())
    file_ids = set()

    for yaml_path in state_dir.glob("th_*.yaml"):
        stem = yaml_path.stem
        file_ids.add(stem)

    missing_in_index = file_ids - index_ids
    orphaned_in_index = index_ids - file_ids

    field_mismatches = []
    schema_errors = []
    for tid in file_ids & index_ids:
        try:
            thesis = _load_thesis(state_dir, tid)
        except Exception:
            field_mismatches.append({"thesis_id": tid, "error": "failed to load"})
            continue

        try:
            _validate_thesis(thesis)
        except (ValueError, Exception) as e:
            schema_errors.append({"thesis_id": tid, "error": str(e)})
            continue

        idx_entry = index["theses"][tid]
        expected = _project_index_fields(thesis)
        for field, exp_val in expected.items():
            if idx_entry.get(field) != exp_val:
                field_mismatches.append(
                    {
                        "thesis_id": tid,
                        "field": field,
                        "file_value": exp_val,
                        "index_value": idx_entry.get(field),
                    }
                )

    ok = (
        not missing_in_index
        and not orphaned_in_index
        and not field_mismatches
        and not schema_errors
    )
    return {
        "ok": ok,
        "missing_in_index": sorted(missing_in_index),
        "orphaned_in_index": sorted(orphaned_in_index),
        "field_mismatches": field_mismatches,
        "schema_errors": schema_errors,
    }


# -- CLI entry point ----------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code (0 ok, non-zero error).

    Extracted from the former ``if __name__ == "__main__"`` block (behavior of
    the pre-existing subcommands is unchanged) so the lifecycle subcommands are
    unit-testable via ``main([...])``.
    """
    import argparse

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

    # transition (IDEA → ENTRY_READY); --event-date backdates the history stamp
    tr_p = sub.add_parser("transition", help="Transition thesis status (e.g. ENTRY_READY)")
    tr_p.add_argument("thesis_id", help="Thesis ID")
    tr_p.add_argument("new_status", help="Target status (e.g. ENTRY_READY)")
    tr_p.add_argument("--reason", required=True, help="Reason for the transition")
    tr_p.add_argument("--event-date", default=None, help="Backdate status_history.at (YYYY-MM-DD)")

    # open-position (ENTRY_READY → ACTIVE)
    op_p = sub.add_parser("open-position", help="Open a position (→ ACTIVE)")
    op_p.add_argument("thesis_id", help="Thesis ID")
    op_p.add_argument("--actual-price", type=float, required=True, help="Entry price")
    op_p.add_argument("--actual-date", required=True, help="Entry date (YYYY-MM-DD or ISO)")
    op_p.add_argument("--shares", type=float, default=None, help="Share count (fractional ok)")
    op_p.add_argument("--reason", default="position opened", help="Transition reason")
    op_p.add_argument("--event-date", default=None, help="Backdate status_history.at")

    # attach-position (position-sizer report)
    ap_p = sub.add_parser("attach-position", help="Attach a position-sizer report")
    ap_p.add_argument("thesis_id", help="Thesis ID")
    ap_p.add_argument("--report", required=True, help="Path to position-sizer JSON report")
    ap_p.add_argument("--expected-entry", type=float, default=None, help="Expected entry price")
    ap_p.add_argument("--expected-stop", type=float, default=None, help="Expected stop price")

    # close (ACTIVE → CLOSED)
    cl_p = sub.add_parser("close", help="Close an ACTIVE thesis")
    cl_p.add_argument("thesis_id", help="Thesis ID")
    cl_p.add_argument(
        "--exit-reason",
        required=True,
        choices=["stop_hit", "target_hit", "time_stop", "invalidated", "manual"],
    )
    cl_p.add_argument("--actual-price", type=float, required=True, help="Exit price")
    cl_p.add_argument("--actual-date", required=True, help="Exit date (YYYY-MM-DD or ISO)")
    cl_p.add_argument("--event-date", default=None, help="Backdate status_history.at")

    # trim (partial close: ACTIVE/PARTIALLY_CLOSED → PARTIALLY_CLOSED or CLOSED)
    tr2_p = sub.add_parser("trim", help="Partially close (trim) a position")
    tr2_p.add_argument("thesis_id", help="Thesis ID")
    tr2_p.add_argument("--shares-sold", type=float, required=True, help="Quantity sold")
    tr2_p.add_argument("--price", type=float, required=True, help="Trim execution price")
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
    tm_p.add_argument("--actual-price", type=float, default=None, help="Exit price (optional)")
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
        t = open_position(
            state_dir,
            args.thesis_id,
            args.actual_price,
            _coerce_dt(args.actual_date),
            reason=args.reason,
            shares=args.shares,
            event_date=_coerce_dt(args.event_date),
        )
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
        t = trim(
            state_dir,
            args.thesis_id,
            args.shares_sold,
            args.price,
            _coerce_dt(args.date),
            reason=args.reason,
            exit_reason=args.exit_reason,
            event_date=_coerce_dt(args.event_date),
        )
        rem = (t.get("position") or {}).get("shares_remaining")
        print(
            f"{args.thesis_id} → {t['status']} "
            f"(sold {args.shares_sold} @ {args.price}, remaining {rem})"
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
    raise SystemExit(main())
