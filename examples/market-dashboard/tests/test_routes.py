# tests/test_routes.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient


def make_client():
    from main import app
    return TestClient(app)


def test_root_returns_200():
    client = make_client()
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_api_signals_returns_html_fragment():
    client = make_client()
    r = client.get("/api/signals")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_api_market_state_returns_json():
    client = make_client()
    r = client.get("/api/market-state")
    assert r.status_code == 200
    data = r.json()
    assert "state" in data
    assert data["state"] in ("pre_market", "market_open", "market_closed")


def test_detail_vcp_returns_200():
    client = make_client()
    r = client.get("/detail/vcp")
    assert r.status_code == 200


def test_detail_ftd_returns_200():
    client = make_client()
    r = client.get("/detail/ftd")
    assert r.status_code == 200


def test_detail_unknown_returns_404():
    client = make_client()
    r = client.get("/detail/notapage")
    assert r.status_code == 404


def test_get_settings_returns_html():
    client = make_client()
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_post_settings_updates_mode():
    client = make_client()
    r = client.post("/api/settings", data={"mode": "semi_auto", "default_risk_pct": "1.5",
                                            "max_positions": "5", "max_position_size_pct": "10.0",
                                            "environment": "paper"})
    assert r.status_code == 200


def test_skill_refresh_returns_202():
    client = make_client()
    r = client.post("/api/skill/ftd-detector/refresh")
    assert r.status_code == 202


def test_static_css_served():
    client = make_client()
    r = client.get("/static/style.css")
    assert r.status_code == 200

import pytest
from config import DETAIL_ROUTES

@pytest.mark.parametrize("page", list(DETAIL_ROUTES.keys()))
def test_all_detail_routes_return_200(page):
    client = make_client()
    r = client.get(f"/detail/{page}")
    assert r.status_code == 200, f"/detail/{page} returned {r.status_code}"
