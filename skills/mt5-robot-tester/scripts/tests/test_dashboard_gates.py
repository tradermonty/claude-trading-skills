"""Tests for the editable gate-parameter settings panel (dashboard backend)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import Dashboard, apply_gate_updates, get_gates, save_config_atomic  # noqa: E402


def test_get_gates_returns_defaults_when_unset():
    fields = get_gates({})["fields"]
    by_key = {f["key"]: f for f in fields}
    assert by_key["round1_min_positive"]["value"] == 5
    assert by_key["round1_min_profit_multiple"]["value"] == 3.0
    assert by_key["finalist_min_profit_multiple"]["value"] == 4.0
    assert by_key["finalist_max_drawdown_pct"]["value"] == 12.0


def test_get_gates_reflects_config_overrides():
    config = {"gates": {"round1_min_positive": 8, "finalist_max_drawdown_pct": 9.5}}
    by_key = {f["key"]: f for f in get_gates(config)["fields"]}
    assert by_key["round1_min_positive"]["value"] == 8
    assert by_key["finalist_max_drawdown_pct"]["value"] == 9.5
    # Untouched fields keep their default.
    assert by_key["finalist_min_profit_multiple"]["value"] == 4.0


def test_apply_gate_updates_valid():
    config = {"gates": {"round1_min_positive": 5}}
    new_config = apply_gate_updates(
        config, {"round1_min_positive": 7, "finalist_max_drawdown_pct": 10.0}
    )
    assert new_config["gates"]["round1_min_positive"] == 7
    assert new_config["gates"]["finalist_max_drawdown_pct"] == 10.0
    assert isinstance(new_config["gates"]["round1_min_positive"], int)


def test_apply_gate_updates_rejects_unknown_key():
    with pytest.raises(ValueError, match="unknown parameter"):
        apply_gate_updates({}, {"not_a_real_field": 1})


def test_apply_gate_updates_rejects_out_of_range():
    with pytest.raises(ValueError, match="out of range"):
        apply_gate_updates({}, {"finalist_max_drawdown_pct": 500})


def test_apply_gate_updates_rejects_non_numeric():
    with pytest.raises(ValueError, match="numeric"):
        apply_gate_updates({}, {"round1_min_positive": "abc"})


def test_save_config_atomic_round_trip(tmp_path):
    path = tmp_path / "config.json"
    save_config_atomic(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert not path.with_suffix(".json.tmp").exists()


def test_dashboard_update_gates_persists_to_disk(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"gates": {}}), encoding="utf-8")
    dash = Dashboard(cfg_path, tmp_path / "out")
    result = dash.update_gates({"round1_min_positive": 6})
    assert result["ok"] is True
    reloaded = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert reloaded["gates"]["round1_min_positive"] == 6


def test_dashboard_update_gates_blocked_while_running(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"gates": {}}), encoding="utf-8")
    dash = Dashboard(cfg_path, tmp_path / "out")
    monkeypatch.setattr(dash, "is_running", lambda: True)
    result = dash.update_gates({"round1_min_positive": 6})
    assert result["ok"] is False
    assert "running" in result["message"]


def test_gate_save_request_includes_csrf_token():
    html = (Path(__file__).resolve().parents[2] / "assets" / "dashboard.html").read_text(
        encoding="utf-8"
    )
    assert "'Content-Type':'application/json','X-CSRF-Token':csrfToken" in html
