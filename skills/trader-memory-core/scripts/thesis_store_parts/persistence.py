# thesis_store part: Persistence and IO: timestamps, IDs, fingerprints, atomic YAML/JSON
# writes, thesis files, and the _index.json summary (including rebuild).
#
# This file is a source fragment of thesis_store.py, not an importable module.
# thesis_store.py executes it into its own namespace (see _exec_parts there), so
# every name below is a thesis_store attribute and all fragments share one set
# of globals. The TYPE_CHECKING block only declares, for linters and readers,
# which names this fragment uses from the shared namespace; it never runs.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import hashlib
    import json
    import os
    import tempfile
    import uuid
    from datetime import datetime, timezone
    from pathlib import Path

    import thesis_store
    import yaml

    INDEX_FILE = thesis_store.INDEX_FILE
    _TYPE_ABBR = thesis_store._TYPE_ABBR
    _VALID_THESIS_TYPES = thesis_store._VALID_THESIS_TYPES
    _validate_thesis = thesis_store._validate_thesis
    logger = thesis_store.logger


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
        with os.fdopen(fd, "w", encoding="utf-8") as f:
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
        with os.fdopen(fd, "w", encoding="utf-8") as f:
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


def _save_thesis(state_dir: Path, thesis: dict, *, allow_legacy_short: bool = False) -> None:
    """Validate and save a thesis YAML file atomically."""
    _validate_thesis(thesis, allow_legacy_short=allow_legacy_short)
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
