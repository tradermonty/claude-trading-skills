"""Add a trader-memory-core thesis from the dashboard: /theses/new.

The thesis is created by trader-memory-core's own code (the same `manual`
ingest adapter and register() the CLI uses), so the YAML file, thesis ID, index
and validation are exactly what the skills expect. The dashboard only needs:
- SKILLS_DIR: the repo's skills/ folder (mounted read-only), to import the code
- THESES_DIR: state/theses (the one part of state/ mounted writable)

A new thesis always starts as IDEA, like every other ingest path. Moving it to
ENTRY_READY / ACTIVE stays with the trader-memory-core CLI for now.
"""

from __future__ import annotations

import importlib
import os
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from .security import same_origin

bp = Blueprint("thesis_form", __name__)

THESIS_TYPES = [
    ("pivot_breakout", "Pivot breakout"),
    ("growth_momentum", "Growth momentum"),
    ("earnings_drift", "Earnings drift"),
    ("mean_reversion", "Mean reversion"),
    ("dividend_income", "Dividend income"),
]
_lock = threading.Lock()


def _tmc_scripts() -> Path | None:
    skills = current_app.config.get("SKILLS_DIR")
    if not skills:
        return None
    path = Path(skills) / "trader-memory-core" / "scripts"
    return path if (path / "thesis_ingest.py").is_file() else None


def _theses_dir() -> Path | None:
    value = current_app.config.get("THESES_DIR")
    if not value:
        return None
    path = Path(value)
    return path if path.is_dir() and os.access(path, os.W_OK) else None


def _load_tmc(scripts: Path) -> tuple[ModuleType, ModuleType]:
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return importlib.import_module("thesis_ingest"), importlib.import_module("thesis_store")


def build_record(form: Any) -> dict[str, Any]:
    """Form fields -> a trader-memory-core `manual` record (empty fields left out)."""
    record: dict[str, Any] = {
        "ticker": (form.get("ticker") or "").strip().upper(),
        "thesis_type": form.get("thesis_type") or "",
        "thesis_statement": (form.get("thesis_statement") or "").strip(),
    }
    for key in ("setup_type", "catalyst", "notes", "entry_date"):
        value = (form.get(key) or "").strip()
        if value:
            record[key] = value
    for key in ("entry_price", "stop_loss", "take_profit"):
        value = (form.get(key) or "").strip().replace("$", "").replace(",", "")
        if value:
            try:
                record[key] = float(value)
            except ValueError as exc:
                raise ValueError(f"'{key.replace('_', ' ')}' needs a number") from exc
    record["entered_via"] = "dashboard"
    return record


def create_thesis(record: dict[str, Any]) -> str:
    scripts = _tmc_scripts()
    theses_dir = _theses_dir()
    if scripts is None or theses_dir is None:
        raise RuntimeError("not set up")
    ingest, store = _load_tmc(scripts)
    with _lock:  # one write at a time in this process (single user, so this is enough)
        data = ingest.ingest_manual(record, "dashboard")
        catalyst = record.get("catalyst")
        if catalyst:
            data["catalyst"] = catalyst
        return store.register(theses_dir, data)


@bp.before_request
def guard():
    if request.method == "POST" and not same_origin():
        abort(403)


@bp.route("/theses/new", methods=["GET", "POST"])
def new_thesis():
    ready = _tmc_scripts() is not None and _theses_dir() is not None
    if not ready:
        return render_template(
            "message.html",
            title="Adding theses isn't set up",
            text="The dashboard needs the skills folder (SKILLS_DIR) and a writable "
            "state/theses folder (THESES_DIR). See the dashboard README, section 'Adding theses'.",
        ), 503
    form: Any = {}
    error = None
    if request.method == "POST":
        form = request.form
        try:
            thesis_id = create_thesis(build_record(form))
        except ValueError as exc:
            error = str(exc)
        else:
            return redirect(
                url_for("thesis_detail", thesis_id=thesis_id, msg="Thesis added as IDEA.")
            )
    return render_template("thesis_new.html", form=form, error=error, thesis_types=THESIS_TYPES), (
        400 if error else 200
    )
