from pathlib import Path

import pytest
import yaml
from app import create_app

SKILLS = Path(__file__).resolve().parents[2] / "skills"
SAME = {"Origin": "http://localhost"}


@pytest.fixture
def client(reports_dir, state_dir):
    app = create_app(
        {
            "REPORTS_DIR": reports_dir,
            "STATE_DIR": state_dir,
            "ALPACA": None,
            "SKILLS_DIR": SKILLS,
            "THESES_DIR": state_dir / "theses",
        }
    )
    app.testing = True
    return app.test_client()


FORM = {
    "ticker": "zzz",
    "thesis_type": "pivot_breakout",
    "thesis_statement": "Tight base under 50; volume dry-up. Wrong if it closes below 46.",
    "setup_type": "VCP",
    "catalyst": "Earnings next month",
    "entry_price": "50.25",
    "stop_loss": "46",
    "take_profit": "60",
    "entry_date": "2026-11-18",
}


def test_new_thesis_form_renders(client):
    body = client.get("/theses/new").get_data(as_text=True)
    assert "Pivot breakout" in body
    assert "New thesis" in client.get("/theses").get_data(as_text=True)


def test_add_thesis_writes_tmc_yaml(client, state_dir):
    # The shared fixture's "{}" index isn't a real trader-memory-core index; start fresh.
    (state_dir / "theses" / "_index.json").unlink()
    r = client.post("/theses/new", data=FORM, headers=SAME)
    assert r.status_code == 302, r.get_data(as_text=True)
    files = sorted((state_dir / "theses").glob("th_zzz_*.yaml"))
    assert len(files) == 1
    t = yaml.safe_load(files[0].read_text())
    assert t["status"] == "IDEA"
    assert t["ticker"] == "ZZZ"
    assert t["exit"]["stop_loss"] == 46.0 and t["exit"]["take_profit"] == 60.0
    assert t["origin"]["skill"] == "manual"
    assert t["thesis_id"] in (state_dir / "theses" / "_index.json").read_text()
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "ZZZ" in page and "Thesis added as IDEA" in page
    assert "ZZZ" in client.get("/theses").get_data(as_text=True)


def test_stop_above_entry_rejected(client, state_dir):
    r = client.post("/theses/new", data=dict(FORM, stop_loss="55"), headers=SAME)
    assert r.status_code == 400
    assert not list((state_dir / "theses").glob("th_zzz_*.yaml"))


def test_missing_statement_and_bad_number(client):
    r = client.post("/theses/new", data=dict(FORM, thesis_statement=""), headers=SAME)
    assert r.status_code == 400
    r = client.post("/theses/new", data=dict(FORM, entry_price="abc"), headers=SAME)
    assert r.status_code == 400 and "needs a number" in r.get_data(as_text=True)


def test_cross_site_blocked(client):
    assert client.post("/theses/new", data=FORM).status_code == 403


def test_not_set_up_without_dirs(reports_dir, state_dir):
    app = create_app({"REPORTS_DIR": reports_dir, "STATE_DIR": state_dir, "ALPACA": None})
    assert app.test_client().get("/theses/new").status_code == 503
