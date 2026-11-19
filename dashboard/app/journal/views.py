"""Trade journal pages: /journal.

This is the only part of the dashboard that saves anything. It writes to its own
SQLite file in JOURNAL_DIR and never talks to a broker.
"""

from __future__ import annotations

import csv
import io
import os
import secrets
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from ..charts import line_chart
from ..security import same_origin
from . import db, pnl, robinhood

bp = Blueprint("journal", __name__, url_prefix="/journal")

IMAGE_TYPES = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
    b"GIF87a": ".gif",
    b"GIF89a": ".gif",
}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_initialized: set[str] = set()


# ---------------------------------------------------------------- plumbing


def journal_dir() -> Path | None:
    value = current_app.config.get("JOURNAL_DIR")
    return Path(value) if value else None


def get_conn() -> sqlite3.Connection:
    if "journal_conn" not in g:
        root = journal_dir()
        path = root / "journal.db"
        conn = db.connect(path)
        if str(path) not in _initialized:
            db.init(conn)
            _initialized.add(str(path))
        g.journal_conn = conn
    return g.journal_conn


@bp.teardown_app_request
def close_conn(_exc):
    conn = g.pop("journal_conn", None)
    if conn is not None:
        conn.close()


@bp.before_request
def guard():
    root = journal_dir()
    if root is None or not (root.is_dir() and os.access(root, os.W_OK)):
        return render_template(
            "message.html",
            title="Journal not set up",
            text="The journal needs a writable JOURNAL_DIR folder. See the dashboard README, "
            "section 'Trade journal'.",
        ), 503
    if request.method == "POST" and not same_origin():
        abort(403)
    return None


def tz() -> ZoneInfo:
    return ZoneInfo(current_app.config.get("TIMEZONE", "America/New_York"))


def local_to_utc(text: str) -> str | None:
    """'2026-11-18T10:30' typed in Eastern time -> '2026-11-18T15:30:00Z'."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return date.fromisoformat(text).isoformat()
        local = datetime.fromisoformat(text).replace(tzinfo=tz())
    except ValueError:
        return None
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_day(stamp: str | None) -> date | None:
    if not stamp:
        return None
    if len(stamp) == 10:
        return date.fromisoformat(stamp)
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(tz()).date()


@bp.app_template_filter("when")
def when(stamp: str | None) -> str:
    if not stamp:
        return "—"
    if len(stamp) == 10:
        return date.fromisoformat(stamp).strftime("%b %-d, %Y")
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(tz())
    return moment.strftime("%b %-d, %Y %-I:%M %p")


@bp.app_template_filter("qty")
def qty(value: Any) -> str:
    number = pnl.dec(value, None)
    if number is None:
        return "—"
    text = f"{number.normalize():f}"
    return text


@bp.app_template_filter("rmult")
def rmult(value: Any) -> str:
    return "—" if value is None else f"{value:+.2f}R"


def _field(name: str) -> str | None:
    value = (request.form.get(name) or "").strip()
    return value or None


def _decimal_field(name: str, required: bool = False) -> Decimal | None:
    value = pnl.dec(request.form.get(name), None)
    if value is None and required:
        raise ValueError(f"'{name.replace('_', ' ')}' needs a number")
    return value


def _trade_or_404(trade_id: int) -> dict[str, Any]:
    trades = db.load_trades(get_conn(), trade_id)
    if not trades:
        abort(404)
    return trades[0]


def _instrument_from_form(conn: sqlite3.Connection) -> tuple[int, str]:
    asset = request.form.get("asset_class", "stock")
    symbol = (_field("symbol") or "").upper()
    if not symbol:
        raise ValueError("Symbol is required")
    if asset == "option":
        expiry = _field("expiry")
        strike = _decimal_field("strike", required=True)
        right = request.form.get("right")
        if not expiry or right not in ("call", "put"):
            raise ValueError("Options need an expiry date and call or put")
        name = db.option_symbol(symbol, expiry, strike, right)
        return db.instrument_id(
            conn,
            "option",
            name,
            underlying=symbol,
            expiry=expiry,
            strike=strike,
            right=right,
            multiplier=_decimal_field("multiplier") or Decimal("100"),
        ), symbol
    if asset == "crypto":
        name = symbol if "-" in symbol else f"{symbol}-USD"
        return db.instrument_id(conn, "crypto", name), name
    return db.instrument_id(conn, "stock", symbol), symbol


def _fill_from_form(conn: sqlite3.Connection, trade_id: int, instrument: int) -> None:
    side = request.form.get("side")
    if side not in ("buy", "sell"):
        raise ValueError("Pick buy or sell")
    quantity = _decimal_field("quantity", required=True)
    price = _decimal_field("price", required=True)
    if quantity <= 0 or price < 0:
        raise ValueError("Quantity must be above 0 and price can't be negative")
    executed = local_to_utc(request.form.get("executed_at", "")) or db.now_utc()
    db.add_fill(
        conn,
        trade_id,
        instrument,
        side,
        quantity,
        price,
        executed,
        fee=_decimal_field("fee") or pnl.ZERO,
        fee_currency=(_field("fee_currency") or "USD").upper(),
    )


def _back(endpoint: str, msg: str, kind: str = "good", **kwargs: Any):
    """Redirect with a one-line notice in the URL (no session cookie, so no secret key)."""
    return redirect(url_for(endpoint, msg=msg, kind=kind, **kwargs))


# ---------------------------------------------------------------- pages


@bp.get("/")
def index():
    conn = get_conn()
    trades = db.load_trades(conn)
    status = request.args.get("status", "")
    symbol = request.args.get("symbol", "").upper().strip()
    setup = request.args.get("setup", "")
    result = request.args.get("result", "")
    shown = [
        t
        for t in trades
        if (not status or t["status"] == status)
        and (not symbol or t["symbol"] == symbol)
        and (not setup or (t["setup"] or "") == setup)
        and (
            not result
            or (result == "win" and t["status"] == "closed" and t["net"] > 0)
            or (result == "loss" and t["status"] == "closed" and t["net"] < 0)
        )
    ]
    closed = [t for t in trades if t["status"] == "closed"]
    return render_template(
        "journal/index.html",
        trades=shown,
        total=len(trades),
        summary=pnl.summarize(closed),
        open_count=sum(1 for t in trades if t["status"] == "open"),
        setups=db.all_setups(conn),
        f={"status": status, "symbol": symbol, "setup": setup, "result": result},
    )


@bp.get("/stats")
def stats():
    conn = get_conn()
    closed = [t for t in db.load_trades(conn) if t["status"] == "closed"]
    closed.sort(key=lambda t: (t["closed_at"] or "", t["id"]))

    def group(key_fn) -> list[dict[str, Any]]:
        buckets: dict[str, list] = defaultdict(list)
        for t in closed:
            for key in key_fn(t):
                buckets[key].append(t)
        rows = [dict(name=k, **pnl.summarize(v)) for k, v in buckets.items()]
        rows.sort(key=lambda r: r["net"], reverse=True)
        return rows

    curve: list[tuple[str, float]] = []
    running = pnl.ZERO
    by_day: dict[str, Decimal] = {}
    for t in closed:
        day = local_day(t["closed_at"])
        running += t["net"]
        by_day[day.isoformat() if day else "?"] = running
    curve = [(d, float(v)) for d, v in by_day.items()]
    values = [v for _, v in curve] + [0.0]
    low, high = min(values), max(values)
    pad = (high - low) * 0.1 or 1
    rs = [t["r"] for t in closed if t["r"] is not None]
    return render_template(
        "journal/stats.html",
        summary=pnl.summarize(closed),
        curve=line_chart(
            curve, y_min=round(low - pad), y_max=round(high + pad), label="Cumulative net P&L"
        ),
        by_setup=group(lambda t: [t["setup"] or "(no setup)"]),
        by_mistake=group(lambda t: t["mistakes"] or ["(no mistakes tagged)"]),
        by_weekday=sorted(
            group(
                lambda t: [WEEKDAYS[local_day(t["closed_at"]).weekday()]] if t["closed_at"] else []
            ),
            key=lambda r: WEEKDAYS.index(r["name"]),
        ),
        by_asset=group(lambda t: t["asset_classes"]),
        avg_r=(sum(rs, pnl.ZERO) / len(rs)) if rs else None,
        r_count=len(rs),
    )


@bp.route("/new", methods=["GET", "POST"])
def new_trade():
    conn = get_conn()
    if request.method == "POST":
        try:
            instrument, display = _instrument_from_form(conn)
            asset = request.form.get("asset_class", "stock")
            trade_id = db.create_trade(
                conn,
                display.split("-")[0] if asset == "crypto" else display,
                setup=_field("setup"),
                reason=_field("reason"),
                planned_stop=_field("planned_stop"),
                planned_target=_field("planned_target"),
                notes=_field("notes"),
                account=_field("account"),
            )
            _fill_from_form(conn, trade_id, instrument)
        except ValueError as exc:
            conn.rollback()
            return render_template(
                "journal/new.html", setups=db.all_setups(conn), form=request.form, error=str(exc)
            ), 400
        conn.commit()
        return _back("journal.detail", "Trade saved.", trade_id=trade_id)
    return render_template("journal/new.html", setups=db.all_setups(conn), form={})


@bp.get("/<int:trade_id>")
def detail(trade_id: int):
    conn = get_conn()
    t = _trade_or_404(trade_id)
    attachments = conn.execute(
        "SELECT * FROM attachment WHERE trade_id = ? ORDER BY id", (trade_id,)
    ).fetchall()
    others = conn.execute(
        "SELECT id, symbol FROM trade WHERE id != ? ORDER BY id DESC LIMIT 200", (trade_id,)
    ).fetchall()
    instruments = []
    seen = set()
    for f in t["fills"]:
        if f["instrument_id"] not in seen:
            seen.add(f["instrument_id"])
            instruments.append(f)
    names = {f["instrument_id"]: f["symbol"] for f in instruments}
    open_legs = [
        (names[leg.instrument], leg.open_qty) for leg in t["result"].legs if leg.open_qty != 0
    ]
    return render_template(
        "journal/detail.html",
        t=t,
        attachments=attachments,
        mistakes=db.all_mistakes(conn),
        setups=db.all_setups(conn),
        others=others,
        instruments=instruments,
        open_legs=open_legs,
        now_local_input=datetime.now(tz()).strftime("%Y-%m-%dT%H:%M"),
    )


@bp.post("/<int:trade_id>/edit")
def edit(trade_id: int):
    conn = get_conn()
    _trade_or_404(trade_id)
    grade = request.form.get("grade") or None
    fields = {k: _field(k) for k in db.TRADE_FIELDS if k != "grade"}
    fields["grade"] = grade if grade in ("A", "B", "C", "D", "F") else None
    db.update_trade(conn, trade_id, fields)
    names = request.form.getlist("mistakes")
    extra = _field("new_mistake")
    if extra:
        names.append(extra)
    db.set_mistakes(conn, trade_id, names)
    conn.commit()
    return _back("journal.detail", "Saved.", trade_id=trade_id)


@bp.post("/<int:trade_id>/fills")
def add_fill(trade_id: int):
    conn = get_conn()
    _trade_or_404(trade_id)
    try:
        existing = request.form.get("instrument_id")
        if existing and existing != "new":
            instrument = int(existing)
        else:
            instrument, _ = _instrument_from_form(conn)
        _fill_from_form(conn, trade_id, instrument)
    except ValueError as exc:
        conn.rollback()
        return _back("journal.detail", str(exc), "bad", trade_id=trade_id)
    conn.commit()
    return _back("journal.detail", "Fill added.", trade_id=trade_id)


@bp.post("/<int:trade_id>/fills/<int:fill_id>/delete")
def delete_fill(trade_id: int, fill_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM fill WHERE id = ? AND trade_id = ?", (fill_id, trade_id))
    conn.commit()
    return _back("journal.detail", "Fill removed.", trade_id=trade_id)


@bp.post("/<int:trade_id>/merge")
def merge(trade_id: int):
    conn = get_conn()
    _trade_or_404(trade_id)
    try:
        other = int(request.form.get("other_id", ""))
    except ValueError:
        return _back("journal.detail", "Pick a trade to merge in.", "bad", trade_id=trade_id)
    if (
        other == trade_id
        or not conn.execute("SELECT 1 FROM trade WHERE id = ?", (other,)).fetchone()
    ):
        abort(400)
    db.merge_trades(conn, trade_id, other)
    conn.commit()
    return _back("journal.detail", f"Merged trade #{other} into this one.", trade_id=trade_id)


@bp.post("/<int:trade_id>/delete")
def delete_trade(trade_id: int):
    conn = get_conn()
    _trade_or_404(trade_id)
    if request.form.get("confirm") != "yes":
        return _back(
            "journal.detail",
            "Tick the box to confirm deleting this trade.",
            "bad",
            trade_id=trade_id,
        )
    files = [
        r["filename"]
        for r in conn.execute("SELECT filename FROM attachment WHERE trade_id = ?", (trade_id,))
    ]
    conn.execute("DELETE FROM trade WHERE id = ?", (trade_id,))
    conn.commit()
    for name in files:
        (journal_dir() / "screenshots" / name).unlink(missing_ok=True)
    return _back("journal.index", f"Trade #{trade_id} deleted.")


@bp.post("/<int:trade_id>/attachments")
def upload(trade_id: int):
    conn = get_conn()
    _trade_or_404(trade_id)
    files = [f for f in request.files.getlist("screenshot") if f and f.filename]
    if not files:
        return _back("journal.detail", "Choose an image first.", "bad", trade_id=trade_id)
    saved = 0
    rejected = []
    for f in files:
        data = f.read()
        ext = next((e for magic, e in IMAGE_TYPES.items() if data.startswith(magic)), None)
        if ext is None and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ext = ".webp"
        if ext is None:
            rejected.append(Path(f.filename).name)
            continue
        folder = journal_dir() / "screenshots"
        folder.mkdir(exist_ok=True)
        name = secrets.token_hex(12) + ext
        (folder / name).write_bytes(data)
        conn.execute(
            "INSERT INTO attachment(trade_id, filename, original_name, created_at) VALUES (?, ?, ?, ?)",
            (trade_id, name, Path(f.filename).name[:200], db.now_utc()),
        )
        saved += 1
    conn.commit()
    if rejected:
        return _back(
            "journal.detail",
            f"Only PNG, JPG, GIF or WebP images. Not added: {', '.join(rejected)}",
            "bad",
            trade_id=trade_id,
        )
    return _back(
        "journal.detail", f"Added {saved} screenshot{'s' if saved > 1 else ''}.", trade_id=trade_id
    )


@bp.get("/screenshots/<int:attachment_id>")
def screenshot(attachment_id: int):
    row = (
        get_conn()
        .execute("SELECT filename FROM attachment WHERE id = ?", (attachment_id,))
        .fetchone()
    )
    if row is None:
        abort(404)
    return send_from_directory(journal_dir() / "screenshots", row["filename"], max_age=86400)


@bp.post("/<int:trade_id>/attachments/<int:attachment_id>/delete")
def delete_attachment(trade_id: int, attachment_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT filename FROM attachment WHERE id = ? AND trade_id = ?", (attachment_id, trade_id)
    ).fetchone()
    if row:
        conn.execute("DELETE FROM attachment WHERE id = ?", (attachment_id,))
        conn.commit()
        (journal_dir() / "screenshots" / row["filename"]).unlink(missing_ok=True)
    return _back("journal.detail", "Screenshot removed.", trade_id=trade_id)


@bp.route("/import", methods=["GET", "POST"])
def import_csv():
    if request.method == "GET":
        return render_template("journal/import.html", outcome=None)
    upload = request.files.get("csv")
    if not upload or not upload.filename:
        return render_template(
            "journal/import.html", outcome=None, error="Choose your Robinhood CSV file first."
        ), 400
    try:
        parsed = robinhood.parse(upload.read())
    except robinhood.NotRobinhoodCSV as exc:
        return render_template("journal/import.html", outcome=None, error=str(exc)), 400
    outcome = db.import_fills(get_conn(), parsed.fills)
    outcome["skipped"] = parsed.skipped
    outcome["errors"] = parsed.errors
    return render_template("journal/import.html", outcome=outcome)


@bp.get("/export.csv")
def export_csv():
    conn = get_conn()
    rows = conn.execute(
        db.FILL_SELECT.replace("SELECT f.*", "SELECT f.*, t.setup, t.grade, t.account")
        + " LEFT JOIN trade t ON t.id = f.trade_id ORDER BY f.executed_at, f.seq, f.id"
    ).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    cols = [
        "trade_id",
        "executed_at",
        "asset_class",
        "symbol",
        "underlying",
        "expiry",
        "strike",
        "right",
        "multiplier",
        "side",
        "quantity",
        "price",
        "fee",
        "fee_currency",
        "source",
        "note",
        "setup",
        "grade",
        "account",
    ]
    w.writerow(cols)
    for r in rows:
        w.writerow([r[c] for c in cols])
    stamp = datetime.now(tz()).strftime("%Y-%m-%d")
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="trade-journal-{stamp}.csv"'},
    )
