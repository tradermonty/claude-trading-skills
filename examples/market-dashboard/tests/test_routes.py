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
    r = client.get("/settings")
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


def test_dashboard_shows_auto_banner_in_auto_mode():
    """When settings mode=auto, dashboard HTML must contain auto-banner element."""
    client = make_client()
    # Set mode to auto first
    r = client.post("/api/settings", data={
        "mode": "auto", "default_risk_pct": "1.0",
        "max_positions": "5", "max_position_size_pct": "10.0",
        "environment": "paper",
    })
    assert r.status_code == 200

    r = client.get("/")
    assert r.status_code == 200
    assert b"auto-banner" in r.content


def test_dashboard_no_auto_banner_in_advisory_mode():
    """Advisory mode must not show auto-banner."""
    client = make_client()
    r = client.get("/")
    assert b"auto-banner" not in r.content


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


def test_post_settings_redirects_to_settings_page():
    """POST /api/settings must redirect (303) to /settings, not return modal HTML."""
    client = make_client()
    response = client.post(
        "/api/settings",
        data={
            "mode": "advisory",
            "default_risk_pct": "1.0",
            "max_positions": "5",
            "max_position_size_pct": "10.0",
            "environment": "paper",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/settings")


def test_monitor_status_returns_json():
    client = make_client()
    r = client.get("/api/monitor/status")
    assert r.status_code == 200
    data = r.json()
    assert "active" in data
    assert "candidate_count" in data
    assert "triggered" in data


def test_order_confirm_in_advisory_mode_returns_403():
    client = make_client()
    r = client.post("/api/order/confirm", json={
        "symbol": "AAPL", "qty": 10, "limit_price": 155.0, "stop_price": 150.0,
        "skill": "vcp", "confidence_tag": "CLEAR",
    })
    assert r.status_code == 403


def test_order_confirm_passes_take_profit_price_to_alpaca(monkeypatch):
    """order_confirm must pass an explicit take_profit_price, not rely on 2:1 default."""
    from main import alpaca
    from config import SETTINGS_FILE
    import json

    captured = {}

    def fake_place(symbol, qty, limit_price, stop_price, take_profit_price=None):
        captured["take_profit_price"] = take_profit_price
        return {"id": "ord1", "symbol": symbol, "qty": qty, "limit_price": limit_price, "status": "new"}

    monkeypatch.setattr(alpaca, "api_key", "test")
    monkeypatch.setattr(alpaca, "secret_key", "test")
    monkeypatch.setattr(alpaca, "place_bracket_order", fake_place)
    SETTINGS_FILE.write_text(json.dumps({"mode": "auto", "environment": "paper"}))

    client = make_client()
    r = client.post("/api/order/confirm", json={
        "symbol": "AAPL", "qty": 10, "limit_price": 155.0, "stop_price": 150.0,
        "skill": "vcp", "confidence_tag": "CLEAR",
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert captured.get("take_profit_price") is not None
    assert captured["take_profit_price"] > 155.0


def test_order_confirm_missing_regime_cache_does_not_error(monkeypatch, tmp_path):
    """Missing macro-regime cache must not block order placement."""
    from main import alpaca
    from config import SETTINGS_FILE, CACHE_DIR
    import json, shutil

    monkeypatch.setattr(alpaca, "api_key", "test")
    monkeypatch.setattr(alpaca, "secret_key", "test")
    monkeypatch.setattr(
        alpaca, "place_bracket_order",
        lambda symbol, qty, limit_price, stop_price, take_profit_price=None: {
            "id": "ord2", "symbol": symbol, "qty": qty,
            "limit_price": limit_price, "status": "new",
        }
    )
    SETTINGS_FILE.write_text(json.dumps({"mode": "auto", "environment": "paper"}))

    regime_file = CACHE_DIR / "macro-regime-detector.json"
    backup = tmp_path / "macro-regime-detector.json.bak"
    existed = regime_file.exists()
    if existed:
        shutil.copy(regime_file, backup)
        regime_file.unlink()
    try:
        client = make_client()
        r = client.post("/api/order/confirm", json={
            "symbol": "AAPL", "qty": 5, "limit_price": 100.0, "stop_price": 97.0,
            "skill": "vcp", "confidence_tag": "CLEAR",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True
    finally:
        if existed:
            shutil.copy(backup, regime_file)


def test_order_preview_includes_multiplier_in_response(monkeypatch):
    """order_preview HTML must contain the take-profit multiplier."""
    from main import alpaca
    from config import SETTINGS_FILE
    import json

    monkeypatch.setattr(alpaca, "api_key", "test")
    monkeypatch.setattr(alpaca, "secret_key", "test")
    monkeypatch.setattr(alpaca, "get_last_price", lambda sym: 155.0)
    monkeypatch.setattr(alpaca, "get_account", lambda: {"portfolio_value": 100_000.0})
    SETTINGS_FILE.write_text(json.dumps({"mode": "auto", "environment": "paper"}))

    client = make_client()
    r = client.post("/api/order/preview", data={
        "symbol": "AAPL", "entry_price": "155.0", "stop_price": "150.0", "skill": "vcp",
    })
    assert r.status_code == 200
    assert "×" in r.text or "x R" in r.text.lower()


def test_new_settings_fields_save_and_load_round_trip():
    """New capital-protection fields must persist through POST and appear in GET."""
    client = make_client()
    r = client.post("/api/settings", data={
        "mode": "advisory",
        "default_risk_pct": "1.0",
        "max_positions": "5",
        "max_position_size_pct": "10.0",
        "environment": "paper",
        "max_weekly_drawdown_pct": "8.0",
        "max_daily_loss_pct": "3.5",
        "earnings_blackout_days": "7",
    })
    assert r.status_code == 200
    from settings_manager import SettingsManager
    s = SettingsManager().load()
    assert s["max_weekly_drawdown_pct"] == 8.0
    assert s["max_daily_loss_pct"] == 3.5
    assert s["earnings_blackout_days"] == 7


def test_new_settings_fields_have_defaults_when_not_set():
    """When settings.json is absent, new fields must return their defaults."""
    from settings_manager import SettingsManager
    s = SettingsManager().load()
    assert s["max_weekly_drawdown_pct"] == 10.0
    assert s["max_daily_loss_pct"] == 5.0
    assert s["earnings_blackout_days"] == 5


def test_settings_form_includes_new_fields():
    """GET /settings HTML must contain the three new input field names."""
    client = make_client()
    r = client.get("/settings")
    assert r.status_code == 200
    assert b"max_weekly_drawdown_pct" in r.content
    assert b"max_daily_loss_pct" in r.content
    assert b"earnings_blackout_days" in r.content


def test_tier2_settings_fields_round_trip():
    """All 4 Tier 2 settings fields survive a POST /api/settings round-trip."""
    client = make_client()
    r = client.post("/api/settings", data={
        "mode": "advisory",
        "default_risk_pct": "1.0",
        "max_positions": "5",
        "max_position_size_pct": "10.0",
        "environment": "paper",
        "min_volume_ratio": "2.0",
        "avoid_open_close_minutes": "15",
        "breadth_threshold_pct": "55.0",
        "breadth_size_reduction_pct": "40.0",
    })
    assert r.status_code == 200
    from settings_manager import SettingsManager
    saved = SettingsManager().load()
    assert saved["min_volume_ratio"] == 2.0
    assert saved["avoid_open_close_minutes"] == 15
    assert saved["breadth_threshold_pct"] == 55.0
    assert saved["breadth_size_reduction_pct"] == 40.0

def test_tier2_defaults_present_without_settings_file():
    """When settings.json doesn't exist, all Tier 2 defaults must be returned."""
    from settings_manager import SettingsManager
    s = SettingsManager().load()
    assert s.get("min_volume_ratio") == 1.5
    assert s.get("avoid_open_close_minutes") == 30
    assert s.get("breadth_threshold_pct") == 60.0
    assert s.get("breadth_size_reduction_pct") == 50.0


def test_stats_route_returns_200():
    """GET /stats returns 200."""
    client = make_client()
    response = client.get("/stats")
    assert response.status_code == 200


def test_trades_route_returns_200():
    """GET /trades returns 200."""
    client = make_client()
    response = client.get("/trades")
    assert response.status_code == 200


def test_settings_route_returns_200():
    """GET /settings returns 200."""
    client = make_client()
    response = client.get("/settings")
    assert response.status_code == 200
