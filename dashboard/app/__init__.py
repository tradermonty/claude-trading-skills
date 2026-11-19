"""Trading dashboard: a Flask app over claude-trading-skills output.

Everything is read-only except the trade journal (/journal), which saves to its own
SQLite file in JOURNAL_DIR. Nothing here can place, change or cancel orders.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import markdown as md_lib
from flask import Flask, abort, jsonify, render_template, request
from jinja2 import UndefinedError
from markupsafe import Markup

from . import alpaca, readers
from .charts import line_chart

STALE_HOURS = 30  # a weekday report older than this missed a run


def _render_markdown(text: str) -> Markup:
    return Markup(md_lib.markdown(text, extensions=["tables", "fenced_code", "sane_lists"]))


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    cfg = {
        "REPORTS_DIR": Path(os.environ.get("REPORTS_DIR", "/data/reports")),
        "STATE_DIR": Path(os.environ.get("STATE_DIR", "/data/state")),
        "TIMEZONE": os.environ.get("TZ_DISPLAY", "America/New_York"),
        "ALPACA": "env",
        "JOURNAL_DIR": os.environ.get("JOURNAL_DIR") or None,
        "MAX_CONTENT_LENGTH": 16 * 1024 * 1024,  # biggest upload: a CSV or a screenshot
    }
    cfg.update(config or {})
    if cfg["ALPACA"] == "env":
        cfg["ALPACA"] = alpaca.from_env(os.environ)
    cfg["REPORTS_DIR"] = Path(cfg["REPORTS_DIR"])
    cfg["STATE_DIR"] = Path(cfg["STATE_DIR"])
    app.config.update(cfg)
    tz = ZoneInfo(cfg["TIMEZONE"])

    from .journal.views import bp as journal_bp

    app.register_blueprint(journal_bp)

    def now_local() -> datetime:
        return datetime.now(tz)

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        client = app.config["ALPACA"]
        return {
            "now_local": now_local(),
            "report_types": readers.REPORT_TYPES,
            "account_mode": None if client is None else ("Paper" if client.paper else "Live"),
        }

    @app.template_filter("money")
    def money(value: Any) -> str:
        try:
            v = float(value)
        except (TypeError, ValueError, UndefinedError):
            return "—"
        sign = "-" if v < 0 else ""
        return f"{sign}${abs(v):,.2f}"

    @app.template_filter("pct")
    def pct(value: Any, digits: int = 1) -> str:
        try:
            return f"{float(value):.{digits}f}%"
        except (TypeError, ValueError, UndefinedError):
            return "—"

    def report_card(key: str) -> dict[str, Any] | None:
        latest = readers.latest(app.config["REPORTS_DIR"], key)
        if latest and latest["stamp"]:
            latest["age_hours"] = readers.age_hours(latest["stamp"])
            latest["stale"] = latest["age_hours"] > STALE_HOURS
        return latest

    @app.get("/")
    def overview():
        reports_dir = app.config["REPORTS_DIR"]
        theses, thesis_errors = readers.load_theses(app.config["STATE_DIR"])
        client = app.config["ALPACA"]
        charts = {
            "exposure": line_chart(
                readers.history(reports_dir, "exposure"),
                suffix="%",
                step=True,
                label="Exposure ceiling by day",
            ),
            "breadth": line_chart(
                readers.history(reports_dir, "breadth"), label="Breadth score by day"
            ),
            "uptrend": line_chart(
                readers.history(reports_dir, "uptrend"), label="Uptrend score by day"
            ),
        }
        vcp = report_card("vcp")
        return render_template(
            "overview.html",
            exposure=report_card("exposure"),
            breadth=report_card("breadth"),
            uptrend=report_card("uptrend"),
            circuit=report_card("circuit"),
            vcp=vcp,
            vcp_rows=(vcp["data"].get("results") or [])[:10] if vcp else [],
            charts=charts,
            summary=readers.thesis_summary(theses, today=now_local().date()),
            open_theses=[t for t in theses if t.get("status") not in readers.TERMINAL_STATUSES],
            thesis_errors=thesis_errors,
            broker=client.snapshot() if client else None,
        )

    @app.get("/theses")
    def theses_page():
        theses, errors = readers.load_theses(app.config["STATE_DIR"])
        status = request.args.get("status", "").upper()
        statuses = sorted({str(t.get("status")) for t in theses})
        shown = [t for t in theses if not status or t.get("status") == status]
        return render_template(
            "theses.html", theses=shown, statuses=statuses, status=status, errors=errors
        )

    @app.get("/theses/<thesis_id>")
    def thesis_detail(thesis_id: str):
        theses, _ = readers.load_theses(app.config["STATE_DIR"])
        thesis = readers.find_thesis(theses, thesis_id)
        if thesis is None:
            abort(404)
        journal = readers.journal_for(app.config["STATE_DIR"], thesis_id)
        return render_template(
            "thesis.html",
            t=thesis,
            journal=_render_markdown(journal) if journal else None,
            raw=json.dumps(thesis, indent=2, default=str),
        )

    @app.get("/reports")
    def reports_page():
        return render_template(
            "reports.html", groups=readers.all_reports(app.config["REPORTS_DIR"])
        )

    @app.get("/reports/view/<path:relname>")
    def report_view(relname: str):
        path = readers.safe_report_path(app.config["REPORTS_DIR"], relname)
        if path is None:
            abort(404)
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".md":
            body = _render_markdown(text)
        else:
            data = readers.load_json(path)
            pretty = json.dumps(data, indent=2) if data is not None else text
            body = Markup("<pre>") + pretty + Markup("</pre>")
        return render_template("report.html", name=relname, body=body)

    @app.get("/healthz")
    def healthz():
        return jsonify(
            ok=True,
            reports_dir=app.config["REPORTS_DIR"].is_dir(),
            state_dir=app.config["STATE_DIR"].is_dir(),
            alpaca=app.config["ALPACA"] is not None,
            journal=bool(app.config["JOURNAL_DIR"]),
        )

    @app.errorhandler(404)
    def not_found(_):
        return render_template(
            "message.html", title="Not found", text="That page or file doesn't exist."
        ), 404

    return app
