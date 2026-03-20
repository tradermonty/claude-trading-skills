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

_STATUS_ORDER = ["IDEA", "ENTRY_READY", "ACTIVE", "CLOSED", "INVALIDATED"]
_TERMINAL_STATUSES = {"CLOSED", "INVALIDATED"}


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

    if status == "ACTIVE":
        entry = thesis.get("entry", {})
        if entry.get("actual_price") is None:
            raise ValueError("ACTIVE thesis requires entry.actual_price")
        if entry.get("actual_date") is None:
            raise ValueError("ACTIVE thesis requires entry.actual_date")

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


def transition(state_dir: Path, thesis_id: str, new_status: str, reason: str) -> dict:
    """Transition thesis to a new status.

    Only allows IDEA → ENTRY_READY. All terminal statuses (ACTIVE, CLOSED,
    INVALIDATED) are blocked — use open_position(), close(), or terminate().

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
    thesis["status"] = new_status
    thesis["status_history"].append({"status": new_status, "at": now, "reason": reason})
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

    # Determine sizing method from whichever calculation was actually used
    sizing_method = None
    calcs = report.get("calculations", {})
    for method_key in ("fixed_fractional", "atr_based", "kelly"):
        if calcs.get(method_key) is not None:
            sizing_method = calcs[method_key].get("method", method_key)
            break

    thesis["position"] = {
        "shares": report.get("final_recommended_shares"),
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


def close(
    state_dir: Path,
    thesis_id: str,
    exit_reason: str,
    actual_price: float,
    actual_date: str,
    event_date: str | None = None,
) -> dict:
    """Close an ACTIVE thesis and compute outcome.

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
        ValueError: If thesis is not ACTIVE or entry data is missing.
    """
    thesis = _load_thesis(state_dir, thesis_id)

    if thesis["status"] != "ACTIVE":
        raise ValueError(f"Can only close ACTIVE thesis, current status: {thesis['status']}")

    entry_price = thesis["entry"].get("actual_price")
    entry_date = thesis["entry"].get("actual_date")

    if entry_price is None:
        raise ValueError("Cannot close thesis: entry.actual_price is not set")

    # Set exit data
    thesis["exit"]["actual_price"] = actual_price
    thesis["exit"]["actual_date"] = actual_date
    thesis["exit"]["exit_reason"] = exit_reason

    # Compute outcome
    pnl_dollars = actual_price - entry_price
    if thesis.get("position") and thesis["position"].get("shares"):
        pnl_dollars *= thesis["position"]["shares"]

    pnl_pct = ((actual_price - entry_price) / entry_price) * 100 if entry_price else None

    holding_days = None
    if entry_date:
        try:
            holding_days = (_parse_dt(actual_date) - _parse_dt(entry_date)).days
        except (ValueError, TypeError):
            pass

    thesis["outcome"]["pnl_dollars"] = round(pnl_dollars, 2) if pnl_dollars is not None else None
    thesis["outcome"]["pnl_pct"] = round(pnl_pct, 2) if pnl_pct is not None else None
    thesis["outcome"]["holding_days"] = holding_days

    # Transition to CLOSED
    now = _now_iso()
    history_at = event_date or now
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
        pnl_pct or 0,
    )
    return thesis


def open_position(
    state_dir: Path,
    thesis_id: str,
    actual_price: float,
    actual_date: str,
    reason: str = "position opened",
    shares: int | None = None,
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

    # Compute P&L if we have both entry and exit prices (ACTIVE thesis with price)
    entry_price = thesis["entry"].get("actual_price")
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

    history_at = event_date or now
    thesis["status"] = "INVALIDATED"
    thesis["status_history"].append(
        {"status": "INVALIDATED", "at": history_at, "reason": f"invalidated: {exit_reason}"}
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

if __name__ == "__main__":
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

    args = parser.parse_args()
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
    else:
        parser.print_help()
