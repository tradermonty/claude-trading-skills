"""Offline config-boundary regressions for #784; no provider access is allowed."""

import builtins
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import ibd_monitor as monitor
import pytest

MARKER = "issue784-marker-key"


@pytest.fixture
def no_provider(monkeypatch):
    build = Mock(side_effect=AssertionError("configuration errors must not build a provider"))
    fetch = Mock(side_effect=AssertionError("configuration errors must not fetch data"))
    monkeypatch.setattr(monitor, "build_fmp_client", build)
    monkeypatch.setattr(monitor, "fetch_ohlcv", fetch)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    return build, fetch


def assert_config_error(path, tmp_path, capsys, no_provider, expected):
    out = tmp_path / "reports"
    assert monitor.main(["--config", str(path), "--output-dir", str(out)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ERROR:")
    assert "configuration" in captured.err.lower()
    assert expected in captured.err
    assert "Traceback" not in captured.err
    assert MARKER not in captured.err
    assert not out.exists()
    for mock in no_provider:
        mock.assert_not_called()


def test_missing_config_returns_controlled_error(tmp_path, capsys, no_provider):
    assert_config_error(
        tmp_path / "missing.yaml", tmp_path, capsys, no_provider, "FileNotFoundError"
    )


def test_directory_config_returns_controlled_error(tmp_path, capsys, no_provider):
    assert_config_error(tmp_path, tmp_path, capsys, no_provider, str(tmp_path))


def test_unreadable_config_returns_controlled_error(tmp_path, monkeypatch, capsys, no_provider):
    path = tmp_path / "private.yaml"
    path.write_text("{}", encoding="utf-8")
    real_open = builtins.open

    def denied(file, *args, **kwargs):
        if Path(file) == path:
            raise PermissionError("injected permission denied")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", denied)
    assert_config_error(path, tmp_path, capsys, no_provider, "PermissionError")


def test_yaml_error_does_not_echo_credential_line(tmp_path, capsys, no_provider):
    path = tmp_path / "malformed.yaml"
    path.write_text(f"data:\n  api_key: [{MARKER}\n", encoding="utf-8")
    assert_config_error(path, tmp_path, capsys, no_provider, "YAML")


def test_invalid_utf8_config_returns_controlled_error(tmp_path, capsys, no_provider):
    path = tmp_path / "bad-encoding.yaml"
    path.write_bytes(b"data: \xff")
    assert_config_error(path, tmp_path, capsys, no_provider, "UTF-8")


@pytest.mark.parametrize("text", ["[]", "[QQQ]", "hello", "17", "0", "true", "false", "''"])
def test_non_mapping_config_is_rejected_before_api_key_resolution(
    tmp_path, capsys, no_provider, text
):
    path = tmp_path / "wrong-type.yaml"
    path.write_text(text, encoding="utf-8")
    assert_config_error(path, tmp_path, capsys, no_provider, "mapping")


@pytest.mark.parametrize("kind", ["missing", "malformed", "list"])
def test_config_failure_cli_contract(tmp_path, kind):
    path = tmp_path / "config.yaml"
    if kind != "missing":
        path.write_text(f"data: [{MARKER}" if kind == "malformed" else "[QQQ]", encoding="utf-8")
    env = dict(os.environ)
    env.pop("FMP_API_KEY", None)
    out = tmp_path / "reports"
    result = subprocess.run(
        [
            sys.executable,
            str(Path(monitor.__file__)),
            "--config",
            str(path),
            "--output-dir",
            str(out),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("ERROR:")
    assert "Traceback" not in result.stderr
    assert MARKER not in result.stderr
    assert not out.exists()


@pytest.mark.parametrize("text", ["", "# comments only\n", "null", "~", "{}"])
def test_empty_and_null_config_keep_empty_mapping_compatibility(tmp_path, text):
    path = tmp_path / "empty.yaml"
    path.write_text(text, encoding="utf-8")
    assert monitor.load_config(str(path)) == {}


@pytest.mark.parametrize(
    "text",
    [
        "data: []",
        "data: false",
        "strategy_context: []",
        "strategy_context: 0",
        "indexes: QQQ",
        "indexes: {}",
        "indexes: [QQQ]",
        "indexes: [{}]",
        "indexes: [{symbol: 1}]",
        "indexes: [{symbol: '  '}]",
    ],
)
def test_invalid_nested_shape_is_rejected_before_provider(tmp_path, capsys, no_provider, text):
    path = tmp_path / "nested.yaml"
    path.write_text(text, encoding="utf-8")
    assert_config_error(path, tmp_path, capsys, no_provider, "must")


def test_null_strategy_context_accepts_cli_overrides(monkeypatch, tmp_path, capsys):
    from test_ibd_monitor_coverage import descending_history, read_report, run_main

    path = tmp_path / "null-sections.yaml"
    path.write_text("strategy_context: null\ndata: null\n", encoding="utf-8")
    rc, client, out = run_main(
        monkeypatch,
        tmp_path,
        {"QQQ": descending_history(), "SPY": descending_history()},
        [
            "--config",
            str(path),
            "--instrument",
            "QQQ",
            "--current-exposure",
            "25",
            "--base-trailing-stop",
            "7",
        ],
    )
    assert rc == 0
    assert [symbol for symbol, _ in client.requested] == ["QQQ", "SPY"]
    payload, _ = read_report(out)
    assert payload["audit"]["config_snapshot"]["strategy_context"] == {
        "instrument": "QQQ",
        "current_exposure_pct": 25,
        "base_trailing_stop_pct": 7,
    }


@pytest.mark.parametrize(
    "tagged_value",
    [
        f"!!int {MARKER}",
        f"!!float {MARKER}",
        f"!!bool {MARKER}",
        f"!!timestamp {MARKER}",
        "!!timestamp 2026-99-99",
    ],
)
def test_invalid_tagged_scalar_does_not_escape_or_echo_source(
    tmp_path, capsys, no_provider, tagged_value
):
    path = tmp_path / "invalid-tagged-value.yaml"
    path.write_text(f"data:\n  api_key: {tagged_value}\n", encoding="utf-8")
    assert_config_error(path, tmp_path, capsys, no_provider, "YAML")


def test_tagged_scalar_cli_does_not_leak_marker(tmp_path):
    path = tmp_path / "typed.yaml"
    path.write_text(f"data:\n  api_key: !!int {MARKER}\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(Path(monitor.__file__)), "--config", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("ERROR:")
    assert "YAML" in result.stderr
    assert "Traceback" not in result.stderr
    assert MARKER not in result.stderr


def test_excessive_yaml_nesting_is_a_controlled_config_error(tmp_path, capsys, no_provider):
    path = tmp_path / "deep.yaml"
    path.write_text("[" * 2000 + MARKER + "]" * 2000, encoding="utf-8")
    assert_config_error(path, tmp_path, capsys, no_provider, "YAML")
