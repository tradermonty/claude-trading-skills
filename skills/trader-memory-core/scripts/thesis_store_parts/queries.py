# thesis_store part: Read-side query helpers and the file/index consistency doctor.
#
# This file is a source fragment of thesis_store.py, not an importable module.
# thesis_store.py executes it into its own namespace (see _exec_parts there), so
# every name below is a thesis_store attribute and all fragments share one set
# of globals. The TYPE_CHECKING block only declares, for linters and readers,
# which names this fragment uses from the shared namespace; it never runs.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    import thesis_store

    _TERMINAL_STATUSES = thesis_store._TERMINAL_STATUSES
    _load_index = thesis_store._load_index
    _load_thesis = thesis_store._load_thesis
    _project_index_fields = thesis_store._project_index_fields
    _validate_thesis = thesis_store._validate_thesis
    logger = thesis_store.logger


def get(state_dir: Path, thesis_id: str) -> dict:
    """Supported read API: load thesis YAML by ID without modifying state.

    Return freshly parsed data without schema or business validation. Call
    validate_thesis() explicitly when consuming persisted or legacy content.

    Raises:
        FileNotFoundError: If thesis does not exist.
        yaml.YAMLError: If the stored YAML cannot be parsed.
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
