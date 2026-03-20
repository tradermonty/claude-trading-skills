# tests/test_settings_manager.py
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_load_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    from settings_manager import SettingsManager
    monkeypatch.setattr("settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    sm = SettingsManager()
    s = sm.load()
    assert s["mode"] == "advisory"
    assert isinstance(s["default_risk_pct"], float)


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    from settings_manager import SettingsManager
    monkeypatch.setattr("settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    sm = SettingsManager()
    sm.save({"mode": "semi_auto", "default_risk_pct": 1.5, "max_positions": 3,
             "max_position_size_pct": 8.0, "environment": "paper"})
    loaded = sm.load()
    assert loaded["mode"] == "semi_auto"
    assert loaded["default_risk_pct"] == 1.5


def test_get_mode_default(tmp_path, monkeypatch):
    from settings_manager import SettingsManager
    monkeypatch.setattr("settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    sm = SettingsManager()
    assert sm.get_mode() == "advisory"


def test_set_mode_persists(tmp_path, monkeypatch):
    from settings_manager import SettingsManager
    monkeypatch.setattr("settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    sm = SettingsManager()
    sm.set_mode("semi_auto")
    assert sm.get_mode() == "semi_auto"


def test_set_mode_rejects_invalid(tmp_path, monkeypatch):
    from settings_manager import SettingsManager
    monkeypatch.setattr("settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    sm = SettingsManager()
    try:
        sm.set_mode("turbo")
        assert False, "should have raised"
    except ValueError:
        pass
