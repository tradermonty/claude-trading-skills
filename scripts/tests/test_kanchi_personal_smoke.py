"""#507: real personal-skill CLI outputs on public fictional contracts only."""

import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "examples/kanchi-personal-smoke"
CONTRACT = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
BOOTSTRAP = """
from pathlib import Path
import runpy
import sys
attempt, started, script = map(Path, sys.argv[1:4])
def guard(event, args):
    if event.startswith("socket."):
        attempt.write_text("blocked", encoding="utf-8")
        raise RuntimeError("Socket operation blocked by synthetic smoke")
sys.addaudithook(guard)
started.write_text("ready", encoding="utf-8")
if str(script) == "probe":
    import socket
    try:
        socket.create_connection(("127.0.0.1", 9))
    except RuntimeError:
        pass
else:
    sys.argv = [str(script), *sys.argv[4:]]
    runpy.run_path(str(script), run_name="__main__")
"""


def child(tmp_path, script, args=(), attempted=False):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR"}
    }
    env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home))
    marker, startup = tmp_path / "network-attempt", tmp_path / "guard-ready"
    result = subprocess.run(
        [sys.executable, "-S", "-c", BOOTSTRAP, str(marker), str(startup), str(script), *args],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert startup.read_text(encoding="utf-8") == "ready"
    assert marker.exists() is attempted
    return result


@pytest.mark.parametrize("case", CONTRACT["cases"], ids=lambda c: c["skill"])
def test_kanchi_public_fictional_cli_contract(case, tmp_path):
    source = FIXTURES / case["input"]
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "reports"
    args = ["--input", str(source), "--output-dir", str(output), *case.get("args", [])]
    result = child(tmp_path, ROOT / case["script"], args)
    assert result.returncode == 0, result.stderr
    for name in case["outputs"].values():
        assert (output / name).stat().st_size > 0
    markdown = (output / case["outputs"]["md"]).read_text(encoding="utf-8")
    assert CONTRACT["as_of"] in markdown
    if "json" in case["outputs"]:
        report = json.loads((output / case["outputs"]["json"]).read_text(encoding="utf-8"))
        assert report["as_of"] == CONTRACT["as_of"]
        assert {r["ticker"]: r["status"] for r in report["results"]} == case["expected"]
        assert any(
            f["trigger"] == case["required_trigger"] and f["status"] == "REVIEW"
            for r in report["results"]
            for f in r["findings"]
        )
    else:
        with (output / case["outputs"]["csv"]).open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert {r["ticker"]: r["classification"] for r in rows} == case["expected"]
    for ticker, verdict in case["expected"].items():
        assert ticker in markdown and verdict in markdown
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original


def test_socket_guard_records_a_swallowed_attempt(tmp_path):
    assert child(tmp_path, "probe", attempted=True).returncode == 0
