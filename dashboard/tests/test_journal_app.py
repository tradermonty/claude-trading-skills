import io
from pathlib import Path

import pytest
from app import create_app

from .test_journal_robinhood import SAMPLE

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
SAME = {"Origin": "http://localhost"}


@pytest.fixture
def jdir(tmp_path: Path) -> Path:
    d = tmp_path / "journal"
    d.mkdir()
    return d


@pytest.fixture
def client(reports_dir, state_dir, jdir):
    app = create_app(
        {"REPORTS_DIR": reports_dir, "STATE_DIR": state_dir, "ALPACA": None, "JOURNAL_DIR": jdir}
    )
    app.testing = True
    return app.test_client()


def post(client, url, data=None, **kw):
    return client.post(url, data=data or {}, headers=SAME, **kw)


def new_trade(client, **over):
    data = {
        "asset_class": "stock",
        "symbol": "abc",
        "side": "buy",
        "quantity": "10",
        "price": "50",
        "fee": "",
        "executed_at": "2026-11-18T10:30",
        "setup": "Breakout",
        "planned_stop": "45",
    }
    data.update(over)
    r = post(client, "/journal/new", data)
    assert r.status_code == 302, r.get_data(as_text=True)
    return int(r.headers["Location"].split("/journal/")[1].split("?")[0])


def test_empty_journal_page(client):
    body = client.get("/journal/").get_data(as_text=True)
    assert "No trades yet" in body
    assert "Journal" in client.get("/").get_data(as_text=True)


def test_journal_disabled_without_dir(reports_dir, state_dir):
    app = create_app({"REPORTS_DIR": reports_dir, "STATE_DIR": state_dir, "ALPACA": None})
    assert app.test_client().get("/journal/").status_code == 503


def test_cross_site_post_blocked(client):
    assert client.post("/journal/new", data={"symbol": "X"}).status_code == 403
    r = client.post(
        "/journal/new", data={"symbol": "X"}, headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403


def test_log_close_and_review_trade(client):
    tid = new_trade(client)
    page = client.get(f"/journal/{tid}").get_data(as_text=True)
    assert "ABC" in page and "open" in page
    # Time typed in Eastern is stored in UTC and shown back in Eastern.
    assert "10:30 AM" in page
    r = post(
        client,
        f"/journal/{tid}/fills",
        {
            "instrument_id": "1",
            "side": "sell",
            "quantity": "10",
            "price": "60",
            "fee": "1",
            "executed_at": "2026-11-19T11:00",
        },
    )
    assert r.status_code == 302
    r = post(
        client,
        f"/journal/{tid}/edit",
        {
            "setup": "Breakout",
            "grade": "B",
            "mistakes": ["Sold too early"],
            "new_mistake": "Hesitated",
            "lesson": "Trust the plan",
            "planned_stop": "45",
        },
    )
    page = client.get(f"/journal/{tid}").get_data(as_text=True)
    assert "$99.00" in page  # (60-50)*10 - 1
    assert "+1.98R" in page  # 99 / (5 * 10)
    assert "Hesitated" in page and "Trust the plan" in page
    stats = client.get("/journal/stats").get_data(as_text=True)
    assert "Breakout" in stats and "Sold too early" in stats and "100.0%" in stats
    listing = client.get("/journal/?result=win").get_data(as_text=True)
    assert "ABC" in listing


def test_bad_input_shows_error(client):
    r = post(
        client,
        "/journal/new",
        {"asset_class": "stock", "symbol": "ABC", "side": "buy", "quantity": "", "price": "1"},
    )
    assert r.status_code == 400
    assert "needs a number" in r.get_data(as_text=True)


def test_option_and_crypto_trades(client):
    tid = new_trade(
        client,
        asset_class="option",
        symbol="aaa",
        expiry="2026-12-19",
        strike="250",
        right="call",
        side="buy",
        quantity="1",
        price="2.00",
        planned_stop="",
    )
    post(
        client,
        f"/journal/{tid}/fills",
        {"instrument_id": "1", "side": "sell", "quantity": "1", "price": "3.50", "executed_at": ""},
    )
    page = client.get(f"/journal/{tid}").get_data(as_text=True)
    assert "AAA 2026-12-19 250 C" in page and "$150.00" in page
    cid = new_trade(
        client,
        asset_class="crypto",
        symbol="btc",
        quantity="0.0005",
        price="60000",
        fee="0.000001",
        fee_currency="BTC",
        planned_stop="",
    )
    page = client.get(f"/journal/{cid}").get_data(as_text=True)
    assert "BTC-USD" in page and "0.0005" in page and "BTC" in page


def test_import_robinhood_twice_and_merge(client, jdir):
    r = post(
        client,
        "/journal/import",
        {"csv": (io.BytesIO(SAMPLE.encode()), "rh.csv")},
        content_type="multipart/form-data",
    )
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "ACH × 1" in body
    listing = client.get("/journal/").get_data(as_text=True)
    assert "BBB" in listing and "AAA" in listing
    again = post(
        client,
        "/journal/import",
        {"csv": (io.BytesIO(SAMPLE.encode()), "rh.csv")},
        content_type="multipart/form-data",
    ).get_data(as_text=True)
    assert "Already imported" in again
    import sqlite3

    conn = sqlite3.connect(jdir / "journal.db")
    assert conn.execute("SELECT COUNT(*) FROM fill").fetchone()[0] == 4
    trades = dict(conn.execute("SELECT symbol, id FROM trade").fetchall())
    conn.close()
    # Option: sold to open at 0.80, expired worthless -> +80 minus 0.05 fee.
    page = client.get(f"/journal/{trades['AAA']}").get_data(as_text=True)
    assert "$79.95" in page and "closed" in page
    # Stock: half sold, so still open.
    assert "Still open" in client.get(f"/journal/{trades['BBB']}").get_data(as_text=True)
    post(client, f"/journal/{trades['BBB']}/merge", {"other_id": str(trades["AAA"])})
    assert client.get(f"/journal/{trades['AAA']}").status_code == 404


def test_import_rejects_wrong_file(client):
    r = post(
        client,
        "/journal/import",
        {"csv": (io.BytesIO(b"a,b\n1,2\n"), "x.csv")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400 and "Robinhood" in r.get_data(as_text=True)


def test_screenshots_upload_serve_delete(client, jdir):
    tid = new_trade(client)
    post(
        client,
        f"/journal/{tid}/attachments",
        {"screenshot": [(io.BytesIO(PNG), "chart.png"), (io.BytesIO(b"<svg/>"), "evil.svg")]},
        content_type="multipart/form-data",
    )
    files = list((jdir / "screenshots").iterdir())
    assert len(files) == 1 and files[0].suffix == ".png"
    page = client.get(f"/journal/{tid}").get_data(as_text=True)
    assert "chart.png" in page
    r = client.get("/journal/screenshots/1")
    assert r.status_code == 200 and r.data == PNG
    r.close()
    post(client, f"/journal/{tid}/attachments/1/delete")
    assert not list((jdir / "screenshots").iterdir())


def test_delete_needs_confirm_and_export(client):
    tid = new_trade(client)
    csv_text = client.get("/journal/export.csv").get_data(as_text=True)
    assert csv_text.startswith("trade_id,") and "ABC" in csv_text
    post(client, f"/journal/{tid}/delete", {})
    assert client.get(f"/journal/{tid}").status_code == 200
    post(client, f"/journal/{tid}/delete", {"confirm": "yes"})
    assert client.get(f"/journal/{tid}").status_code == 404
