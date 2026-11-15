"""Execute the published beginner path, including pause and local-only handoff."""

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAGES = [ROOT / f"docs/{lang}/offline-quickstart.md" for lang in ("en", "ja")]
ORDER = ("doctor", "start", "paused-status", "resume", "status", "navigator")
RUN_PATH = "reports/quickstart-demo"
FIXTURE_TIME = "2026-01-15T13:08:00+00:00"
# Record first, then raise: a swallowed exception is still visible to the parent.
GUARD = """
import os
from pathlib import Path
import socket
import sys

attempt = Path(os.environ["QUICKSTART_ATTEMPT"])
def blocked(*args, **kwargs):
    attempt.write_text("blocked", encoding="utf-8")
    raise RuntimeError("Python socket network disabled by quickstart test")

def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
                 "socket.gethostbyaddr", "socket.sendto"}:
        blocked()

sys.addaudithook(audit)
for name in ("connect", "connect_ex", "sendto", "sendmsg"):
    if hasattr(socket.socket, name):
        setattr(socket.socket, name, blocked)
for name in ("create_connection", "getaddrinfo", "gethostbyname",
             "gethostbyname_ex", "gethostbyaddr"):
    setattr(socket, name, blocked)
Path(os.environ["QUICKSTART_STARTED"]).write_text("ready", encoding="utf-8")
"""


def commands(page):
    pairs = re.findall(
        r"<!-- quickstart: ([\w-]+) -->\n```bash\n(.*?)\n```",
        page.read_text(encoding="utf-8"),
        re.S,
    )
    assert tuple(name for name, _ in pairs) == ORDER
    result = {name: shlex.split(command) for name, command in pairs}
    assert all(tokens[0] == "python" for tokens in result.values())
    return result


class Children:
    def __init__(self, root):
        self.root = root
        self.calls = 0
        guard = root / "guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
        home = root / "home"
        home.mkdir()
        # Allow only OS runtime inputs; no inherited credentials or Python loaders.
        self.env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG"}
        }
        self.env.update(
            HOME=str(home),
            USERPROFILE=str(home),
            APPDATA=str(home),
            LOCALAPPDATA=str(home),
            PYTHONPATH=str(guard),
            PYTHONNOUSERSITE="1",
        )

    def call(self, args, *, expect_attempt=False):
        self.calls += 1
        started = self.root / f"started-{self.calls}"
        attempted = self.root / f"attempted-{self.calls}"
        env = self.env | {"QUICKSTART_STARTED": str(started), "QUICKSTART_ATTEMPT": str(attempted)}
        result = subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert started.read_text(encoding="utf-8") == "ready", "Child network guard did not start"
        assert attempted.exists() is expect_attempt, "Unexpected/missing Python network attempt"
        return result


def file_snapshot(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def source_hashes():
    files = [ROOT / "workflows/market-regime-daily.yaml"]
    files.extend((ROOT / "examples/workflows/market-regime-daily/replay-inputs").glob("*.json"))
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_language_commands_match():
    assert commands(PAGES[0]) == commands(PAGES[1])


@pytest.mark.parametrize("page", PAGES, ids=["en", "ja"])
def test_documented_first_session(page, tmp_path, request):
    published = commands(page)
    children = Children(tmp_path)
    directory = tmp_path / "reports/demo"
    original = source_hashes()
    started = time.monotonic()

    def execute(name):
        args = published[name][1:]
        if "--run-dir" in args:
            index = args.index("--run-dir") + 1
            assert args[index] == RUN_PATH
            args[index] = str(directory)
        return children.call(args)

    diagnostic = execute("doctor")
    assert diagnostic.returncode == 0, diagnostic.stderr
    assert "Offline environment doctor" in diagnostic.stdout
    assert "[ok] python:" in diagnostic.stdout
    assert "[unknown] python:" not in diagnostic.stdout
    for provider in ("FMP", "FINVIZ", "Alpaca"):
        assert f"[warning] credentials:{provider}:" in diagnostic.stdout

    paused = execute("start")
    assert paused.returncode == 3, paused.stderr
    state = read(directory / "manifest.json")
    assert state["status"] == "AWAITING_DECISION"
    assert state["evaluation_at"] == FIXTURE_TIME
    assert state["steps"][2]["status"] == "SKIPPED"
    assert not (directory / "journal.json").exists()
    assert not (directory / "03_top_risk_report.json").exists()
    assert execute("paused-status").returncode == 3
    for filename in (
        "01_market_breadth_report.json",
        "02_uptrend_report.json",
        "04_exposure_proposal.json",
    ):
        report = read(directory / filename)
        assert report["run_id"] == state["run_id"]
    proposal = read(directory / "04_exposure_proposal.json")
    assert proposal["fictional"] is True and proposal["evaluation_at"] == FIXTURE_TIME
    assert "top_risk" in proposal["result"]["inputs_missing"]

    resumed = execute("resume")
    assert resumed.returncode == 0, resumed.stderr
    assert read(directory / "manifest.json")["status"] == "COMPLETED"
    journal = read(directory / "journal.json")
    assert journal["run_id"] == state["run_id"]
    assert journal["fictional"] is True and journal["decision"] == "restrict"
    assert journal["destination"] == "trader-memory-core" and journal["delivery"] == "handoff_only"
    before_status = file_snapshot(directory)
    status = execute("status")
    assert status.returncode == 0 and "COMPLETED" in status.stdout
    assert file_snapshot(directory) == before_status
    recommendation = execute("navigator")
    assert recommendation.returncode == 0, recommendation.stderr
    value = json.loads(recommendation.stdout)
    assert value["goal_match"]["workflow"]["id"] == "market-regime-daily"
    assert value["no_api_path"] is True
    elapsed = time.monotonic() - started
    request.node.user_properties.append(("quickstart_command_seconds", round(elapsed, 3)))
    assert elapsed < 900
    # A second attempt cannot erase the completed run (also exercises guard on failure).
    assert execute("start").returncode == 1
    assert file_snapshot(directory) == before_status
    assert source_hashes() == original


@pytest.mark.parametrize(
    "operation",
    [
        "socket.create_connection(('127.0.0.1', 9))",
        "socket.socket().connect(('127.0.0.1', 9))",
        "socket.socket().connect_ex(('127.0.0.1', 9))",
        "socket.socket(type=socket.SOCK_DGRAM).sendto(b'x', ('127.0.0.1', 9))",
        "socket.getaddrinfo('example.invalid', 443)",
    ],
)
def test_network_guard_records_even_swallowed_attempts(tmp_path, operation):
    children = Children(tmp_path)
    result = children.call(
        ["-c", f"import socket\ntry:\n    {operation}\nexcept RuntimeError:\n    print('caught')"],
        expect_attempt=True,
    )
    assert result.returncode == 0 and "caught" in result.stdout
