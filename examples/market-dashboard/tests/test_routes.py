# tests/test_routes.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from config import DETAIL_ROUTES, SETTINGS_FILE


@pytest.fixture(autouse=True)
def clean_settings():
    """Delete settings.json before each test so mode defaults to 'advisory'."""
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()
    yield
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()


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


@pytest.mark.parametrize("page", list(DETAIL_ROUTES.keys()))
def test_all_detail_routes_return_200(page):
    client = make_client()
    r = client.get(f"/detail/{page}")
    assert r.status_code == 200, f"/detail/{page} returned {r.status_code}"


def test_startup_does_not_crash():
    """Server starts without exception even with empty cache."""
    client = make_client()
    r = client.get("/")
    assert r.status_code == 200


def test_api_portfolio_returns_html():
    client = make_client()
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # Alpaca is not configured in test env → "connect Alpaca" message renders
    assert b"ALPACA_API_KEY" in r.content


def test_order_preview_endpoint_exists():
    """POST /api/order/preview returns 403 in advisory mode (the default)."""
    client = make_client()
    r = client.post("/api/order/preview", data={
        "symbol": "AAPL",
        "entry_price": "150.0",
        "stop_price": "145.0",
        "skill": "vcp-screener",
    })
    # Default mode is advisory (DEFAULT_TRADING_MODE = "advisory" in config.py)
    assert r.status_code == 403


def test_order_confirm_advisory_mode_returns_403():
    """Advisory mode (the default) never executes orders — must return 403."""
    client = make_client()
    # Default mode is advisory (DEFAULT_TRADING_MODE = "advisory" in config.py)
    r = client.post("/api/order/confirm", json={
        "symbol": "AAPL",
        "qty": 10,
        "limit_price": 150.0,
        "stop_price": 145.0,
    })
    assert r.status_code == 403


def test_post_settings_live_without_confirm_returns_400():
    client = make_client()
    r = client.post("/api/settings", data={
        "mode": "advisory",
        "default_risk_pct": "1.0",
        "max_positions": "5",
        "max_position_size_pct": "10.0",
        "environment": "live",
        # live_confirm absent → must be rejected
    })
    assert r.status_code == 400


def test_post_settings_live_with_correct_confirm_succeeds():
    client = make_client()
    r = client.post("/api/settings", data={
        "mode": "advisory",
        "default_risk_pct": "1.0",
        "max_positions": "5",
        "max_position_size_pct": "10.0",
        "environment": "live",
        "live_confirm": "CONFIRM LIVE TRADING",
    })
    assert r.status_code == 200


def test_post_settings_paper_needs_no_confirm():
    client = make_client()
    r = client.post("/api/settings", data={
        "mode": "advisory",
        "default_risk_pct": "1.0",
        "max_positions": "5",
        "max_position_size_pct": "10.0",
        "environment": "paper",
    })
    assert r.status_code == 200
