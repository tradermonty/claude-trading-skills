import pytest
from app import create_app


@pytest.fixture
def client(reports_dir, state_dir):
    app = create_app({"REPORTS_DIR": reports_dir, "STATE_DIR": state_dir, "ALPACA": None})
    app.testing = True
    return app.test_client()


def test_overview_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "50%" in body  # latest exposure ceiling
    assert "Neutral" in body  # breadth zone
    assert "AAA" in body  # VCP + thesis
    assert "<svg" in body  # history chart
    assert "not set up" in body.lower()  # Alpaca not configured


def test_theses_page_and_filter(client):
    body = client.get("/theses").get_data(as_text=True)
    assert "AAA" in body and "CCC" in body
    body = client.get("/theses?status=CLOSED").get_data(as_text=True)
    assert "CCC" in body and "th_aaa_1" not in body


def test_thesis_detail_with_journal(client):
    body = client.get("/theses/th_ccc_1").get_data(as_text=True)
    assert "Stopped out" in body


def test_thesis_missing_404(client):
    assert client.get("/theses/nope").status_code == 404


def test_reports_list_and_view(client):
    assert "exposure_posture_2026-11-18_211500.json" in client.get("/reports").get_data(
        as_text=True
    )
    md = client.get("/reports/view/exposure_posture_2026-11-18_211500.md").get_data(as_text=True)
    assert "<table>" in md
    js = client.get("/reports/view/exposure_posture_2026-11-18_211500.json").get_data(as_text=True)
    assert "exposure_ceiling_pct" in js


def test_report_traversal_404(client):
    assert client.get("/reports/view/..%2Fstate%2Ftheses%2Fth_aaa_1.yaml").status_code == 404


def test_post_not_allowed(client):
    assert client.post("/").status_code == 405


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_empty_dirs_still_render(tmp_path):
    app = create_app({"REPORTS_DIR": tmp_path / "r", "STATE_DIR": tmp_path / "s", "ALPACA": None})
    body = app.test_client().get("/").get_data(as_text=True)
    assert "No report yet" in body


class _FakeClient:
    def __init__(self, paper):
        self.paper = paper

    def snapshot(self):
        return {
            "paper": self.paper,
            "error": None,
            "account": {
                "equity": "1000",
                "last_equity": "990",
                "cash": "500",
                "buying_power": "1000",
            },
            "positions": [
                {
                    "symbol": "ZZZ",
                    "qty": "2",
                    "avg_entry_price": "10",
                    "current_price": "11",
                    "market_value": "22",
                    "unrealized_pl": "2",
                    "unrealized_plpc": "0.1",
                }
            ],
        }


@pytest.mark.parametrize(
    "paper,word,css", [(True, "PAPER", "banner-paper"), (False, "LIVE", "banner-live")]
)
def test_mode_banner_on_every_page(reports_dir, state_dir, paper, word, css):
    app = create_app(
        {"REPORTS_DIR": reports_dir, "STATE_DIR": state_dir, "ALPACA": _FakeClient(paper)}
    )
    c = app.test_client()
    for url in ("/", "/theses", "/reports"):
        body = c.get(url).get_data(as_text=True)
        assert css in body and word in body
    body = c.get("/").get_data(as_text=True)
    assert "ZZZ" in body and "$10.00" in body  # day change 1000 - 990


def test_no_banner_without_broker(client):
    assert "banner-" not in client.get("/").get_data(as_text=True)
