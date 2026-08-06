"""Tests for the dashboard status helpers."""

import http.client
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dashboard as dashboard_module  # noqa: E402
from dashboard import Dashboard, build_status, derive_bot_view, make_handler  # noqa: E402


def test_derive_finalist():
    st = {
        "status": "done",
        "verdict": "finalist",
        "reason": "ok",
        "round1": {"best_symbol": "XAUUSD"},
        "round2": {"net_profit": 84.1, "lr_correlation": 0.95},
        "round3": {
            "per_param": [],
            "final_metrics": {"net_profit": 84.1, "drawdown_max_pct": 0.25},
        },
    }
    v = derive_bot_view("Bot", st)
    assert v["phase"] == "done"
    assert v["passed"] is True
    assert v["best_symbol"] == "XAUUSD"
    assert v["final_dd_pct"] == 0.25


def test_derive_rejected_and_phase_progression():
    assert derive_bot_view("B", {"round1": {}})["phase"] == "R1"
    assert derive_bot_view("B", {"round1": {}, "round2": {}})["phase"] == "R2"
    assert derive_bot_view("B", {})["phase"] == "pending"
    r = derive_bot_view(
        "B",
        {
            "status": "done",
            "verdict": "rejected",
            "round1": {"reason": "R1: too few profitable symbols"},
        },
    )
    assert r["passed"] is False
    assert r["verdict"] == "rejected"


def test_build_status_reads_state_and_folders(tmp_path):
    cand = tmp_path / "cand"
    cand.mkdir()
    (cand / "A.ex5").write_text("x")
    (cand / "B.ex5").write_text("x")
    fin = tmp_path / "fin"
    fin.mkdir()
    (fin / "A.ex5").write_text("x")
    out = tmp_path / "out"
    out.mkdir()
    (out / "state.json").write_text(
        '{"bots":{"A":{"status":"done","verdict":"finalist","round1":{},'
        '"round2":{},"round3":{"per_param":[]}},'
        '"B":{"status":"done","verdict":"rejected","round1":{}}}}',
        encoding="utf-8",
    )
    (out / "run.log").write_text("line1\nline2\n", encoding="utf-8")

    config = {
        "folders": {
            "candidates": str(cand),
            "in_testing": str(tmp_path / "none"),
            "finalists": str(fin),
        }
    }
    s = build_status(config, out, running=True)
    assert s["running"] is True
    assert s["summary"]["finalists"] == 1
    assert s["summary"]["rejected"] == 1
    assert s["folders"]["candidates"] == ["A", "B"]
    assert s["folders"]["finalists"] == ["A"]
    assert s["log_tail"] == ["line1", "line2"]


def _dashboard(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"folders": {}}', encoding="utf-8")
    return Dashboard(config, tmp_path / "output")


def _request(server, method, path, *, host=None, origin=None, token=None):
    port = server.server_address[1]
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if origin is not None:
        headers["Origin"] = origin
    if token is not None:
        headers["X-CSRF-Token"] = token
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, headers=headers)
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, body


def test_control_endpoints_require_exact_same_origin_and_csrf(tmp_path, monkeypatch):
    dash = _dashboard(tmp_path)
    calls = []
    monkeypatch.setattr(dash, "start", lambda: calls.append("start") or {"ok": True})
    server = dashboard_module.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(dash))
    port = server.server_address[1]
    dash.configure_server(port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert (
            _request(
                server,
                "POST",
                "/api/start",
                origin="https://attacker.invalid",
                token=dash.csrf_token,
            )[0]
            == 403
        )
        assert (
            _request(
                server,
                "POST",
                "/api/start",
                origin=dash.allowed_origin,
                token="wrong",
            )[0]
            == 403
        )
        assert (
            _request(
                server,
                "POST",
                "/api/start",
                host="attacker.invalid",
                origin=dash.allowed_origin,
                token=dash.csrf_token,
            )[0]
            == 403
        )
        assert (
            _request(
                server,
                "POST",
                "/api/start?unexpected=1",
                origin=dash.allowed_origin,
                token=dash.csrf_token,
            )[0]
            == 404
        )
        assert (
            _request(
                server,
                "POST",
                "/api/start",
                origin=dash.allowed_origin,
                token=dash.csrf_token,
            )[0]
            == 200
        )
        assert calls == ["start"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_html_receives_per_server_csrf_token(tmp_path):
    dash = _dashboard(tmp_path)
    server = dashboard_module.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(dash))
    port = server.server_address[1]
    dash.configure_server(port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body = _request(server, "GET", "/")
        assert status == 200
        assert dash.csrf_token.encode() in body
        assert b"__CSRF_TOKEN__" not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_start_uses_dedicated_process_group(tmp_path, monkeypatch):
    dash = _dashboard(tmp_path)

    class Proc:
        pid = 4321

        @staticmethod
        def poll():
            return None

    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return Proc()

    monkeypatch.setattr(dashboard_module.subprocess, "Popen", fake_popen)
    result = dash.start()

    assert result["ok"] is True
    if sys.platform == "win32":
        assert captured["kwargs"]["creationflags"]
    else:
        assert captured["kwargs"]["start_new_session"] is True


def test_stop_waits_for_exact_spawned_process_tree(tmp_path, monkeypatch):
    dash = _dashboard(tmp_path)

    class Proc:
        pid = 4321

        @staticmethod
        def poll():
            return None

    proc = Proc()
    dash.proc = proc
    seen = []
    monkeypatch.setattr(
        dashboard_module,
        "terminate_process_tree",
        lambda target: seen.append(target) or True,
    )

    result = dash.stop()

    assert result["ok"] is True
    assert seen == [proc]
    assert dash.proc is None


def test_stop_reports_failure_when_process_tree_survives(tmp_path, monkeypatch):
    dash = _dashboard(tmp_path)

    class Proc:
        pid = 4321

        @staticmethod
        def poll():
            return None

    proc = Proc()
    dash.proc = proc
    monkeypatch.setattr(dashboard_module, "terminate_process_tree", lambda _target: False)

    result = dash.stop()

    assert result["ok"] is False
    assert dash.proc is proc


def test_taskkill_command_uses_resolved_executable(monkeypatch):
    executable = r"C:\Windows\System32\taskkill.exe"
    monkeypatch.setattr(dashboard_module.shutil, "which", lambda name: executable)

    assert dashboard_module._taskkill_command(4321) == [
        executable,
        "/PID",
        "4321",
        "/T",
        "/F",
    ]


def test_taskkill_command_fails_closed_when_unavailable(monkeypatch):
    monkeypatch.setattr(dashboard_module.shutil, "which", lambda name: None)

    with pytest.raises(FileNotFoundError, match="taskkill"):
        dashboard_module._taskkill_command(4321)
