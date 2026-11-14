# thesis_store part: State-transition core: registration, field updates, status transitions,
# report links, and review bookkeeping.
#
# This file is a source fragment of thesis_store.py, not an importable module.
# thesis_store.py executes it into its own namespace (see _exec_parts there), so
# every name below is a thesis_store attribute and all fragments share one set
# of globals. The TYPE_CHECKING block only declares, for linters and readers,
# which names this fragment uses from the shared namespace; it never runs.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime, timedelta
    from pathlib import Path

    import thesis_store
    import yaml

    _STATUS_ORDER = thesis_store._STATUS_ORDER
    _TERMINAL_STATUSES = thesis_store._TERMINAL_STATUSES
    _UPDATE_OUTCOME_FIELDS = thesis_store._UPDATE_OUTCOME_FIELDS
    _VALID_THESIS_TYPES = thesis_store._VALID_THESIS_TYPES
    _YAML_DUMP_KWARGS = thesis_store._YAML_DUMP_KWARGS
    _coerce_dt = thesis_store._coerce_dt
    _compute_origin_fingerprint = thesis_store._compute_origin_fingerprint
    _default_thesis = thesis_store._default_thesis
    _find_by_fingerprint = thesis_store._find_by_fingerprint
    _generate_thesis_id = thesis_store._generate_thesis_id
    _load_index = thesis_store._load_index
    _load_thesis = thesis_store._load_thesis
    _now_iso = thesis_store._now_iso
    _require_long_equity_direction = thesis_store._require_long_equity_direction
    _save_index = thesis_store._save_index
    _save_thesis = thesis_store._save_thesis
    _today_str = thesis_store._today_str
    _update_index_entry = thesis_store._update_index_entry
    _valid_finite_number = thesis_store._valid_finite_number
    _validate_equity_long_only = thesis_store._validate_equity_long_only
    _validate_thesis = thesis_store._validate_thesis
    logger = thesis_store.logger


# -- Public API ---------------------------------------------------------------


def _build_thesis_for_registration(thesis_data: dict) -> dict:
    """Build and validate the full thesis object without writing it."""
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

    # These unsupported direction fields would otherwise be silently dropped
    # by template copying. Registration does not import a raw position; futures
    # SHORT intent belongs on the validated futures attach/direct-open boundary.
    _require_long_equity_direction(thesis_data.get("direction"), normalize=True)
    raw_position = thesis_data.get("position")
    if isinstance(raw_position, dict):
        _require_long_equity_direction(raw_position.get("direction"), normalize=True)

    # Build thesis from template + provided data
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
    return thesis


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
    # Build and validate before any idempotency or persistence checks.
    thesis = _build_thesis_for_registration(thesis_data)
    fingerprint = thesis["origin_fingerprint"]
    state_dir.mkdir(parents=True, exist_ok=True)

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

    logger.info("Registered thesis %s for %s", thesis["thesis_id"], thesis["ticker"])
    return thesis["thesis_id"]


def update(state_dir: Path, thesis_id: str, fields: dict) -> dict:
    """Partial update of a thesis.

    Args:
        state_dir: Path to state/theses/ directory.
        thesis_id: Thesis to update.
        fields: Dict of fields to update (shallow merge for top-level,
                deep merge for nested dicts like entry, exit, monitoring).

    Returns:
        The updated thesis dict.

    Raises:
        ValueError: If a protected field is targeted, if any direct
            `position` write is attempted, or if `outcome` contains fields
            not owned by the review workflow.
    """
    thesis = _load_thesis(state_dir, thesis_id)
    _validate_equity_long_only(thesis)  # Do not erase unsupported legacy intent in a merge.
    now = _now_iso()

    # Issue #255: position is lifecycle-owned for both equities and
    # futures. Generic replacement bypasses validation and audit history,
    # including when the incoming payload omits the asset markers used by
    # _is_futures(). Refuse the key itself so None, empty/metadata-only
    # dicts, malformed values, and every current or future money field all
    # fail closed before any in-memory mutation or persistence.
    if "position" in fields:
        raise ValueError(
            "update() cannot modify position — use attach_position() / "
            "attach_futures_position() / open_position() / trim() / close() / "
            "terminate() instead; direct position writes bypass lifecycle "
            "validation and audit history"
        )

    # Review code legitimately owns excursion metrics and lessons. P&L and
    # holding duration are lifecycle-owned and must only be computed by the
    # close/trim/terminate paths. An allowlist also prevents future outcome
    # fields from becoming silently writable through this generic API.
    if "outcome" in fields:
        outcome_fields = fields["outcome"]
        if not isinstance(outcome_fields, dict):
            raise ValueError("update() outcome must be a dict of review-owned fields")
        disallowed_outcome_fields = set(outcome_fields) - _UPDATE_OUTCOME_FIELDS
        if disallowed_outcome_fields:
            names = ", ".join(sorted(repr(name) for name in disallowed_outcome_fields))
            raise ValueError(
                "update() outcome may only modify review-owned fields "
                f"{sorted(_UPDATE_OUTCOME_FIELDS)}; disallowed: {names}"
            )
        for metric_name in ("mae_pct", "mfe_pct"):
            if metric_name not in outcome_fields:
                continue
            metric_value = outcome_fields[metric_name]
            if metric_value is not None and _valid_finite_number(metric_value) is None:
                raise ValueError(
                    f"update() outcome.{metric_name} must be null or a finite "
                    f"number, got {metric_value!r}"
                )

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


_LESSONS_ALLOWED_STATUSES = ("CLOSED", "INVALIDATED")
_LESSONS_MAX_CHARS = 10_000
_LESSONS_MODES = ("error", "append", "replace")


def _yaml_round_trips(value: str) -> bool:
    """True if the YAML writer stores ``value`` and reads it back unchanged.

    Some characters (e.g. NEL U+0085) are altered by YAML. Dumps with the same
    options as _atomic_write_yaml (_YAML_DUMP_KWARGS) so the two cannot drift.
    """
    return yaml.safe_load(yaml.dump(value, **_YAML_DUMP_KWARGS)) == value


def record_lessons(
    state_dir: Path, thesis_id: str, text: str, *, mode: str = "error"
) -> tuple[dict, str]:
    """Record post-trade lessons in ``outcome.lessons_learned`` (Issue #701).

    Only CLOSED / INVALIDATED theses are accepted, the statuses that the
    postmortem and monthly-report renderers cover. Validates, then delegates to
    update(), so there is no second write path.

    Args:
        text: Lesson text (stripped; non-empty; at most 10_000 characters).
            One plain paragraph per lesson renders best in reports.
        mode: What to do when a non-empty lesson is already stored. "error"
            refuses, "append" joins with a single newline, "replace"
            overwrites. With no stored lesson every mode stores the text.

    Returns:
        (updated thesis, effective action "new" | "append" | "replace").

    Raises:
        ValueError: Invalid mode or text, status not CLOSED/INVALIDATED,
            existing lesson in "error" mode, or a legacy unsupported short.
        FileNotFoundError: Unknown thesis_id.
    """
    if mode not in _LESSONS_MODES:
        raise ValueError(f"Invalid mode: {mode!r}. Must be one of {list(_LESSONS_MODES)}")
    if not isinstance(text, str):
        raise ValueError(f"lessons text must be a string, got {type(text).__name__}")
    new_text = text.strip()
    if not new_text:
        raise ValueError("lessons text is empty")
    try:
        new_text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(
            "lessons text is not valid UTF-8 (undecodable bytes in --text?); use --file"
        ) from None
    if len(new_text) > _LESSONS_MAX_CHARS:
        raise ValueError(
            f"lessons text is {len(new_text)} characters; limit is {_LESSONS_MAX_CHARS}"
        )

    thesis = _load_thesis(state_dir, thesis_id)
    status = thesis["status"]
    if status not in _LESSONS_ALLOWED_STATUSES:
        raise ValueError(
            f"Cannot record lessons for {thesis_id}: status is {status}; "
            f"allowed statuses are {list(_LESSONS_ALLOWED_STATUSES)}"
        )

    existing = (thesis.get("outcome") or {}).get("lessons_learned")
    has_existing = isinstance(existing, str) and bool(existing.strip())
    if not has_existing:
        action, stored = "new", new_text
    elif mode == "error":
        raise ValueError(
            f"{thesis_id} already has lessons recorded; "
            "pass --append to add to them or --replace to overwrite"
        )
    elif mode == "append":
        if not _yaml_round_trips(existing):
            raise ValueError(
                f"the lesson already stored on {thesis_id} contains characters that do not "
                "round-trip through YAML (for example U+0085), so it cannot be appended to; "
                "use --replace to overwrite it"
            )
        action, stored = "append", f"{existing}\n{new_text}"
    else:
        action, stored = "replace", new_text

    if len(stored) > _LESSONS_MAX_CHARS:
        raise ValueError(
            f"total lessons would be {len(stored)} characters after {action}; "
            f"limit is {_LESSONS_MAX_CHARS}"
        )
    if not _yaml_round_trips(stored):
        raise ValueError(
            "lessons text contains characters that do not round-trip through YAML "
            "(for example U+0085); remove them"
        )

    updated = update(state_dir, thesis_id, {"outcome": {"lessons_learned": stored}})
    return updated, action


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
        raise ValueError(f"Invalid status: {new_status}") from None
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

    # Review scheduling changes no financial fields or direction.
    _save_thesis(state_dir, thesis, allow_legacy_short=True)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Reviewed %s: %s → next %s", thesis_id, outcome, next_review)
    return thesis
