# tests/test_settings_manager.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import tempfile
import json
from unittest.mock import patch


def test_defaults_include_markets():
    """_DEFAULTS must contain a markets list with us, oslo, lse entries."""
    from settings_manager import _DEFAULTS
    assert "markets" in _DEFAULTS
    ids = [m["id"] for m in _DEFAULTS["markets"]]
    assert "us" in ids
    assert "oslo" in ids
    assert "lse" in ids


def test_get_enabled_markets_returns_only_enabled(tmp_path):
    """get_enabled_markets returns only markets where enabled=True."""
    from settings_manager import SettingsManager
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "markets": [
            {"id": "us", "enabled": True, "broker": "alpaca"},
            {"id": "oslo", "enabled": False, "broker": "ibkr"},
            {"id": "lse", "enabled": True, "broker": "ibkr"},
        ]
    }))
    with patch("settings_manager.SETTINGS_FILE", settings_file):
        sm = SettingsManager()
        result = sm.get_enabled_markets()
    ids = [m["id"] for m in result]
    assert "us" in ids
    assert "lse" in ids
    assert "oslo" not in ids


def test_save_rejects_all_disabled_markets(tmp_path):
    """save() must reject settings where all markets are disabled."""
    from settings_manager import SettingsManager
    settings_file = tmp_path / "settings.json"
    with patch("settings_manager.SETTINGS_FILE", settings_file):
        sm = SettingsManager()
        with pytest.raises(ValueError, match="at least one market"):
            sm.save({
                "mode": "advisory",
                "environment": "paper",
                "markets": [
                    {"id": "us", "enabled": False, "broker": "alpaca"},
                    {"id": "oslo", "enabled": False, "broker": "ibkr"},
                ]
            })


def test_save_rejects_unknown_broker(tmp_path):
    """save() must reject unknown broker values in markets list."""
    from settings_manager import SettingsManager
    settings_file = tmp_path / "settings.json"
    with patch("settings_manager.SETTINGS_FILE", settings_file):
        sm = SettingsManager()
        with pytest.raises(ValueError, match="broker"):
            sm.save({
                "mode": "advisory",
                "environment": "paper",
                "markets": [
                    {"id": "us", "enabled": True, "broker": "unknown_broker"},
                ]
            })


def test_load_merges_defaults_with_stored(tmp_path):
    """load() merges _DEFAULTS with stored settings, markets preserved."""
    from settings_manager import SettingsManager
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"mode": "auto"}))
    with patch("settings_manager.SETTINGS_FILE", settings_file):
        sm = SettingsManager()
        result = sm.load()
    assert result["mode"] == "auto"
    assert "markets" in result
