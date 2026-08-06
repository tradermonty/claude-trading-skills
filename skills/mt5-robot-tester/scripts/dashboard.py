#!/usr/bin/env python3
"""Local control panel (HTML dashboard) for the mt5-robot-tester pipeline.

A tiny stdlib HTTP server (bound to 127.0.0.1 only) that:

  * lists the bots in each folder (candidates / in-testing / finalists),
  * shows each bot's current phase and verdict from ``state.json``,
  * lets you launch / stop the pipeline with a button,
  * streams the tail of ``run.log``.

A plain HTML file cannot read your folders or start MetaTrader 5 (browsers
sandbox that), so this small local server does it and the page talks to it.

Usage:
    python3 dashboard.py --config C:/path/config.json --output-dir C:/path/out
    # then open http://127.0.0.1:8765/  (opens automatically)
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HTML = _HERE.parent / "assets" / "dashboard.html"
_PIPELINE = _HERE / "mt5_batch_tester.py"

try:
    from mt5_batch_tester import DEFAULTS
except ImportError:  # pragma: no cover - import shim
    sys.path.insert(0, str(_HERE))
    from mt5_batch_tester import DEFAULTS

# Editable cut-off ("gate") parameters, exposed to the HTML settings panel.
# Each: (section in config, key, python type, min, max, label).
GATE_FIELDS = [
    (
        "gates",
        "round1_min_positive",
        int,
        1,
        200,
        "Round 1 — minimum profitable symbols",
    ),
    (
        "gates",
        "round1_min_profit_multiple",
        float,
        0.0,
        100.0,
        "Round 1 — minimum best-symbol profit (deposit multiple)",
    ),
    (
        "gates",
        "finalist_min_profit_multiple",
        float,
        0.0,
        100.0,
        "Round 3 / finalist — minimum profit (deposit multiple)",
    ),
    (
        "gates",
        "finalist_max_drawdown_pct",
        float,
        0.1,
        100.0,
        "Round 3 / finalist — maximum drawdown (%)",
    ),
]
_GATE_KEYS = {key for _, key, *_ in GATE_FIELDS}


# --- pure, testable status helpers ---------------------------------------


def derive_bot_view(name: str, st: dict) -> dict:
    """Reduce a state.json bot entry to a compact dashboard row."""
    status = st.get("status")
    if status == "done":
        phase = "done"
    elif "round3" in st:
        phase = "R3"
    elif "round2" in st:
        phase = "R2"
    elif "round1" in st:
        phase = "R1"
    else:
        phase = "pending"
    verdict = st.get("verdict") if status == "done" else None
    r2 = st.get("round2") or {}
    final = (st.get("round3") or {}).get("final_metrics") or {}
    gate = st.get("round1") or {}
    return {
        "name": name,
        "phase": phase,
        "verdict": verdict,
        "passed": verdict == "finalist",
        "reason": st.get("reason") or gate.get("reason"),
        "best_symbol": gate.get("best_symbol"),
        "r2_profit": r2.get("net_profit"),
        "final_profit": final.get("net_profit"),
        "final_dd_pct": final.get("drawdown_max_pct"),
        "lr": r2.get("lr_correlation"),
    }


def _list_ex5(folder: Path | None) -> list[str]:
    if not folder or not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.ex5"))


def build_status(config: dict, output_dir: Path, running: bool) -> dict:
    folders = config.get("folders", {})

    def _p(key):
        return Path(folders[key]) if folders.get(key) else None

    cand, intest, fin = _p("candidates"), _p("in_testing"), _p("finalists")

    state_path = output_dir / "state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
    bots = [derive_bot_view(n, st) for n, st in state.get("bots", {}).items()]
    bots.sort(key=lambda b: (b["phase"] != "done", b["name"].lower()))

    log_tail = []
    log_path = output_dir / "run.log"
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            log_tail = lines[-40:]
        except OSError:
            pass

    finalists = sum(1 for b in bots if b["passed"])
    rejected = sum(1 for b in bots if b["verdict"] in ("rejected", "error"))
    return {
        "running": running,
        "folders": {
            "candidates": _list_ex5(cand),
            "in_testing": _list_ex5(intest),
            "finalists": _list_ex5(fin),
        },
        "bots": bots,
        "summary": {
            "tested": len(bots),
            "finalists": finalists,
            "rejected": rejected,
            "candidates_left": len(_list_ex5(cand)),
        },
        "log_tail": log_tail,
    }


# --- editable gate parameters ---------------------------------------------


def get_gates(config: dict) -> dict:
    """Current gate values (config overrides merged onto the pipeline defaults),
    annotated with metadata for the settings panel."""
    merged = {**DEFAULTS["gates"], **config.get("gates", {})}
    fields = []
    for section, key, typ, lo, hi, label in GATE_FIELDS:
        fields.append(
            {
                "section": section,
                "key": key,
                "label": label,
                "type": "int" if typ is int else "float",
                "min": lo,
                "max": hi,
                "value": merged.get(key),
            }
        )
    return {"fields": fields}


def apply_gate_updates(config: dict, updates: dict) -> dict:
    """Return a new config with validated gate ``updates`` merged in.

    Raises ValueError on an unknown key or an out-of-range/wrong-type value.
    """
    field_by_key = {key: (typ, lo, hi, label) for _, key, typ, lo, hi, label in GATE_FIELDS}
    new_config = dict(config)
    gates = dict(config.get("gates", {}))
    for key, raw in updates.items():
        if key not in _GATE_KEYS:
            raise ValueError(f"unknown parameter: {key}")
        typ, lo, hi, label = field_by_key[key]
        try:
            value = typ(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{label}: value must be numeric ({raw!r})") from None
        if not (lo <= value <= hi):
            raise ValueError(f"{label}: {value} out of range [{lo}, {hi}]")
        gates[key] = value
    new_config["gates"] = gates
    return new_config


def save_config_atomic(path: Path, config: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# --- server ---------------------------------------------------------------


def _taskkill_command(pid: int) -> list[str]:
    """Build a Windows process-tree command using a resolved executable path."""
    executable = shutil.which("taskkill")
    if executable is None:
        raise FileNotFoundError("taskkill executable was not found on PATH")
    return [executable, "/PID", str(pid), "/T", "/F"]


def terminate_process_tree(proc: subprocess.Popen, timeout: float = 15) -> bool:
    """Stop the exact process tree started by this dashboard and confirm exit."""
    if proc.poll() is not None:
        return True
    try:
        if sys.platform == "win32":
            subprocess.run(
                _taskkill_command(proc.pid),
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout)
    except (OSError, subprocess.TimeoutExpired):
        if proc.poll() is not None:
            return True
        try:
            if sys.platform == "win32":
                subprocess.run(
                    _taskkill_command(proc.pid),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout)
        except (OSError, subprocess.TimeoutExpired):
            return proc.poll() is not None
    return proc.poll() is not None


class Dashboard:
    def __init__(self, config_path: Path, output_dir: Path):
        self.config_path = config_path
        self.output_dir = output_dir
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.csrf_token = secrets.token_urlsafe(32)
        self.allowed_host = ""
        self.allowed_origin = ""

    def configure_server(self, port: int) -> None:
        self.allowed_host = f"127.0.0.1:{port}"
        self.allowed_origin = f"http://{self.allowed_host}"

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> dict:
        with self.lock:
            if self.is_running():
                return {"ok": False, "message": "Pipeline is already running"}
            cmd = [
                sys.executable,
                str(_PIPELINE),
                "--config",
                str(self.config_path),
                "--output-dir",
                str(self.output_dir),
                "--resume",
            ]
            kwargs = (
                {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
                if sys.platform == "win32"
                else {"start_new_session": True}
            )
            try:
                self.proc = subprocess.Popen(cmd, **kwargs)
            except OSError as exc:
                return {"ok": False, "message": f"Could not start pipeline: {exc}"}
            return {"ok": True, "message": "Pipeline started", "pid": self.proc.pid}

    def stop(self) -> dict:
        with self.lock:
            if not self.is_running():
                return {"ok": False, "message": "Pipeline is not running"}
            proc = self.proc
            if not terminate_process_tree(proc):
                return {
                    "ok": False,
                    "message": "Could not confirm that the process tree stopped",
                }
            self.proc = None
            return {"ok": True, "message": "Pipeline stopped"}

    def status(self) -> dict:
        # Reload config each poll so folder edits are reflected.
        try:
            self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return build_status(self.config, self.output_dir, self.is_running())

    def gates(self) -> dict:
        return get_gates(self.config)

    def update_gates(self, updates: dict) -> dict:
        with self.lock:
            if self.is_running():
                return {
                    "ok": False,
                    "message": "Gate parameters cannot be changed while the pipeline is running",
                }
            try:
                new_config = apply_gate_updates(self.config, updates)
            except ValueError as e:
                return {"ok": False, "message": str(e)}
            save_config_atomic(self.config_path, new_config)
            self.config = new_config
            return {"ok": True, "message": "Gate parameters saved", **get_gates(self.config)}


def make_handler(dash: Dashboard):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(
                code,
                json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _valid_host(self) -> bool:
            return hmac.compare_digest(self.headers.get("Host", ""), dash.allowed_host)

        def _valid_control_request(self) -> bool:
            return (
                self._valid_host()
                and hmac.compare_digest(self.headers.get("Origin", ""), dash.allowed_origin)
                and hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), dash.csrf_token)
            )

        def do_GET(self):  # noqa: N802
            if not self._valid_host():
                self._send(403, b"forbidden", "text/plain")
                return
            if self.path in ("/", "/index.html"):
                try:
                    html = _HTML.read_text(encoding="utf-8").replace(
                        "__CSRF_TOKEN__", dash.csrf_token
                    )
                except OSError:
                    html = "<h1>dashboard.html not found</h1>"
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/status":
                self._json(dash.status())
            elif self.path == "/api/gates":
                self._json(dash.gates())
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):  # noqa: N802
            if self.path not in ("/api/start", "/api/stop", "/api/gates"):
                self._send(404, b"not found", "text/plain")
                return
            if not self._valid_control_request():
                self._send(403, b"forbidden", "text/plain")
                return
            if self.path == "/api/start":
                self._json(dash.start())
            elif self.path == "/api/stop":
                self._json(dash.stop())
            else:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    updates = json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    self._json({"ok": False, "message": "Invalid JSON"}, 400)
                    return
                self._json(dash.update_gates(updates))

        def log_message(self, *args):  # silence default logging
            pass

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local control panel for the MT5 pipeline.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        print(f"error: config not found: {config_path}", file=sys.stderr)
        return 1

    dash = Dashboard(config_path, output_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(dash))
    port = server.server_address[1]
    dash.configure_server(port)
    url = f"http://127.0.0.1:{port}/"
    print(f"Control panel available at {url}  (Ctrl+C to exit)")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
    finally:
        if dash.is_running():
            result = dash.stop()
            if not result["ok"]:
                print(result["message"], file=sys.stderr)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
