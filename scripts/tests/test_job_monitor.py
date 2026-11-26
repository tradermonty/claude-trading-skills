"""Offline notification, heartbeat and launcher exit regressions."""

import importlib.util
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("job_monitor", SCRIPTS / "job_monitor.py")
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def test_unconfigured_is_noop(monkeypatch):
    monkeypatch.delenv("SKILL_LOOP_NOTIFY", raising=False)
    call = Mock(side_effect=AssertionError("must not notify"))
    monkeypatch.setattr(monitor.subprocess, "run", call)
    monkeypatch.setattr(monitor.urllib.request, "build_opener", call)
    monitor.notify_failure("improvement", 1)
    call.assert_not_called()


def test_webhook_fixed_payload_and_redacted_error(monkeypatch, capsys):
    monkeypatch.setenv("SKILL_LOOP_NOTIFY", "webhook")
    monkeypatch.setenv("SKILL_LOOP_WEBHOOK_URL", "https://example.invalid/secret-token")
    opener = Mock()
    opener.open.side_effect = RuntimeError("https://example.invalid/secret-token")
    monkeypatch.setattr(monitor.urllib.request, "build_opener", Mock(return_value=opener))
    monitor.notify_failure("generation-weekly", 7)
    request = opener.open.call_args.args[0]
    assert json.loads(request.data) == {
        "text": "Skill automation generation-weekly failed (exit 7). Check local logs."
    }
    assert opener.open.call_args.kwargs == {"timeout": 5}
    assert "secret-token" not in capsys.readouterr().err
    assert (
        monitor.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid")
        is None
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid",
        "https://user:secret@example.invalid",  # pragma: allowlist secret - synthetic rejected URL
        "",
    ],
)
def test_invalid_webhook_does_not_send(monkeypatch, url):
    monkeypatch.setenv("SKILL_LOOP_NOTIFY", "webhook")
    monkeypatch.setenv("SKILL_LOOP_WEBHOOK_URL", url)
    call = Mock()
    monkeypatch.setattr(monitor.urllib.request, "build_opener", call)
    monitor.notify_failure("improvement", 1)
    call.assert_not_called()


def test_macos_bounded_argv(monkeypatch):
    monkeypatch.setenv("SKILL_LOOP_NOTIFY", "macos")
    call = Mock()
    monkeypatch.setattr(monitor.subprocess, "run", call)
    monitor.notify_failure("improvement", 3)
    assert call.call_args.args[0][0] == "osascript"
    assert call.call_args.kwargs["timeout"] == 5
    assert "shell" not in call.call_args.kwargs


def write_heartbeats(root, now):
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    (logs / ".skill_improvement_state.json").write_text(
        json.dumps({"last_success_at": now.isoformat()})
    )
    (logs / ".skill_generation_state.json").write_text(
        json.dumps({"last_success_at": {"daily": now.isoformat(), "weekly": now.isoformat()}})
    )


def test_heartbeat_modes_and_read_only(tmp_path):
    now = datetime.now(timezone.utc)
    write_heartbeats(tmp_path, now - timedelta(days=5))
    before = {p: p.read_bytes() for p in (tmp_path / "logs").iterdir()}
    results = dict(monitor.heartbeat_checks(tmp_path, now))
    assert results["generation-weekly"] == "ok"
    assert results["generation-daily"].startswith("stale")
    assert results["improvement"].startswith("stale")
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "null",
        "{",
        '{"last_success_at": null}',
        '{"last_success_at": "2026-01-01T00:00:00"}',
        '{"last_success_at": 123}',
        '{"last_success_at": {}}',
    ],
)
def test_corrupt_heartbeat_warns(tmp_path, content):
    (tmp_path / "logs").mkdir()
    for filename, _, _ in monitor.JOBS.values():
        (tmp_path / filename).write_text(content)
    assert all(status != "ok" for _, status in monitor.heartbeat_checks(tmp_path))


def test_missing_and_future_heartbeat(tmp_path):
    assert all(status != "ok" for _, status in monitor.heartbeat_checks(tmp_path))
    now = datetime.now(timezone.utc)
    write_heartbeats(tmp_path, now + timedelta(hours=1))
    assert all("future" in status for _, status in monitor.heartbeat_checks(tmp_path, now))


@pytest.mark.parametrize(
    "wrapper,args,job",
    [
        ("generation", ["--mode", "daily"], "generation-daily"),
        ("generation", ["--mode=weekly"], "generation-weekly"),
        ("improvement", [], "improvement"),
    ],
)
@pytest.mark.parametrize("failure", ["setup", "orchestrator"])
def test_wrapper_failure_preserves_exit(tmp_path, wrapper, args, job, failure):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(SCRIPTS / f"run_skill_{wrapper}.sh", scripts)
    # Inject fake commands after PATH setup, so installed Python/git cannot run.
    path = scripts / f"run_skill_{wrapper}.sh"
    source = path.read_text()
    pos = source.index("SCRIPT_DIR=")
    source = (
        source[:pos]
        + """
python3() {
    case "$1" in
        *job_monitor.py) printf '%s\\n' "$*" > "$TEST_NOTIFICATION"; return 99 ;;
        *) return 7 ;;
    esac
}
git() {
    if [ "$TEST_FAILURE" = setup ]; then return 8; fi
    if [ "$1" = -C ] && [ "$3" = remote ]; then echo fake-origin; fi
    return 0
}
direnv() { return 0; }
"""
        + source[pos:]
    )
    # generation setup failure is cd failure (not a git operation).
    if wrapper == "generation" and failure == "setup":
        source = source.replace('cd "${SCRIPT_DIR}/.." || exit 1', "false || exit 8")
    path.write_text(source)
    checkout = tmp_path / "bot"
    (checkout / ".git").mkdir(parents=True)
    marker = tmp_path / "notification"
    env = dict(
        os.environ,
        SKILL_LOOP_NOTIFY="macos",
        SKILL_LOOP_CHECKOUT=str(checkout),
        TEST_NOTIFICATION=str(marker),
        TEST_FAILURE=failure,
    )
    result = subprocess.run(["bash", str(path), *args], env=env, capture_output=True, timeout=10)
    assert result.returncode == (
        1 if wrapper == "improvement" and failure == "setup" else 8 if failure == "setup" else 7
    )
    assert f"--notify-failure {job} --exit-code {result.returncode}" in marker.read_text()


def _improvement_status(tmp_path, age_hours):
    now = datetime.now(timezone.utc)
    write_heartbeats(tmp_path, now - timedelta(hours=age_hours))
    return dict(monitor.heartbeat_checks(tmp_path, now))["improvement"]


def test_improvement_threshold_follows_72h_cadence(tmp_path, monkeypatch):
    monkeypatch.delenv("SKILL_LOOP_MIN_INTERVAL_HOURS", raising=False)
    assert _improvement_status(tmp_path, 95) == "ok"
    assert _improvement_status(tmp_path, 97).startswith("stale")


def test_improvement_threshold_tracks_interval_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_LOOP_MIN_INTERVAL_HOURS", "24")
    assert _improvement_status(tmp_path, 47) == "ok"
    assert _improvement_status(tmp_path, 49).startswith("stale")
    monkeypatch.setenv("SKILL_LOOP_MIN_INTERVAL_HOURS", "bad")
    assert _improvement_status(tmp_path, 95) == "ok"


def test_generation_thresholds_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_LOOP_MIN_INTERVAL_HOURS", "720")
    now = datetime.now(timezone.utc)
    write_heartbeats(tmp_path, now - timedelta(hours=49))
    assert dict(monitor.heartbeat_checks(tmp_path, now))["generation-daily"].startswith("stale")
