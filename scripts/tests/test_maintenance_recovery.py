"""Real local Git launcher regression and isolated heartbeat/installer contracts."""

import importlib.util
import json
import os
import plistlib
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clean_git_env():
    # Hooks export repository/index/config variables. -C alone cannot isolate Git.
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=clean_git_env(),
    ).stdout


@pytest.mark.parametrize("hook_env", [False, True])
def test_real_wrapper_symlinks_reach_scoring_twice(tmp_path, monkeypatch, hook_env):
    # A disposable outer repository models pre-push variables, never the user's
    # checkout. Assert its HEAD, index and configuration survive the entire test.
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-b", "main")
    (outer / "sentinel").write_text("outside fixture")
    git(outer, "add", ".")
    git(
        outer,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "sentinel",
    )
    before_head = git(outer, "rev-parse", "HEAD")
    before = {name: (outer / ".git" / name).read_bytes() for name in ("index", "config")}
    if hook_env:
        monkeypatch.setenv("GIT_DIR", str(outer / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(outer))
        monkeypatch.setenv("GIT_INDEX_FILE", str(outer / ".git/index"))
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.bare")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    primary = tmp_path / "primary"
    primary.mkdir()
    git(primary, "init", "-b", "main")
    (primary / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
    scripts = primary / "scripts"
    scripts.mkdir()
    shutil.copy(ROOT / "scripts/run_skill_improvement.sh", scripts)
    shutil.copy(ROOT / "scripts/run_skill_improvement_loop.py", scripts / "safety.py")
    (scripts / "run_skill_improvement_loop.py").write_text("""
import argparse
from pathlib import Path
from safety import git_safe_check
p = argparse.ArgumentParser()
p.add_argument('--project-root')
a = p.parse_args()
r = Path(a.project_root)
if not git_safe_check(r):
    raise SystemExit(1)
with (r / 'reports' / 'synthetic-scores.txt').open('a') as f:
    f.write('scoring reached\\n')
""")
    git(primary, "add", ".")
    git(
        primary,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(primary), str(remote)],
        check=True,
        capture_output=True,
        env=clean_git_env(),
        timeout=30,
    )
    git(primary, "remote", "add", "origin", str(remote))
    bot = tmp_path / "bot"
    env = dict(
        clean_git_env(),
        SKILL_LOOP_CHECKOUT=str(bot),
        SKILL_LOOP_NOTIFY="off",
        GIT_CONFIG_NOSYSTEM="1",
    )
    for _ in range(2):
        result = subprocess.run(
            ["bash", str(scripts / "run_skill_improvement.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert git(bot, "status", "--porcelain") == ""
        for name in ("logs", "reports"):
            assert (bot / name).is_symlink()
            assert (bot / name).resolve() == primary / name
            assert git(bot, "check-ignore", name).strip() == name
    assert (primary / "reports/synthetic-scores.txt").read_text().splitlines() == [
        "scoring reached"
    ] * 2
    (bot / "unsafe.py").write_text("untracked source")
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; from safety import git_safe_check; raise SystemExit(0 if git_safe_check(Path.cwd().parent) else 1)",
        ],
        cwd=bot / "scripts",
        capture_output=True,
        text=True,
        env=clean_git_env(),
        timeout=30,
    )
    # Use the root explicitly; importing safety from scripts must not change the Git target.
    assert check.returncode == 1
    assert "untracked file: unsafe.py" in check.stderr
    assert git(outer, "rev-parse", "HEAD") == before_head
    assert before == {name: (outer / ".git" / name).read_bytes() for name in before}


def heartbeat_state(root, stamp):
    (root / "logs").mkdir(exist_ok=True)
    (root / "logs/.skill_improvement_state.json").write_text(
        json.dumps({"last_success_at": stamp.isoformat()})
    )
    (root / "logs/.skill_generation_state.json").write_text(
        json.dumps({"last_success_at": {"daily": stamp.isoformat(), "weekly": stamp.isoformat()}})
    )


@pytest.mark.parametrize("hours,expected", [(0, 0), (49, 1), (400, 1)])
def test_notifying_heartbeat_default_and_status(tmp_path, monkeypatch, hours, expected):
    monitor = load_script("job_monitor")
    monkeypatch.delenv("SKILL_LOOP_NOTIFY", raising=False)
    heartbeat_state(tmp_path, datetime.now(timezone.utc) - timedelta(hours=hours))
    call = Mock()
    monkeypatch.setattr(monitor.subprocess, "run", call)
    monkeypatch.setattr(
        sys, "argv", ["monitor", "--notify-heartbeat", "--project-root", str(tmp_path)]
    )
    before = {p: p.read_bytes() for p in (tmp_path / "logs").iterdir()}
    assert monitor.main() == expected
    assert call.call_count == (0 if hours == 0 else 2 if hours == 49 else 3)
    for entry in call.call_args_list:
        assert entry.args[0][0] == "osascript"
        assert "fresh success heartbeat" in entry.args[0][-1]
        assert entry.kwargs["timeout"] == 5
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("mode", ["off", "macos"])
def test_heartbeat_missing_and_delivery_failure(tmp_path, monkeypatch, mode):
    monitor = load_script("job_monitor")
    monkeypatch.setenv("SKILL_LOOP_NOTIFY", mode)
    call = Mock(side_effect=OSError("private exception"))
    monkeypatch.setattr(monitor.subprocess, "run", call)
    monkeypatch.setattr(
        sys, "argv", ["monitor", "--notify-heartbeat", "--project-root", str(tmp_path)]
    )
    assert monitor.main() == 1
    assert call.call_count == (0 if mode == "off" else 3)


@pytest.mark.parametrize("mode", [None, "off", "webhook"])
def test_watchdog_wrapper_defaults_and_args(tmp_path, mode):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(ROOT / "scripts/run_skill_heartbeat.sh", scripts)
    # Stub the interpreter after PATH setup; no real notification or environment sourcing.
    p = scripts / "run_skill_heartbeat.sh"
    text = p.read_text()
    text = text.replace(
        "SCRIPT_DIR=",
        'python3() { printf "%s\\n" "$SKILL_LOOP_NOTIFY" "$@"; return 1; }\nSCRIPT_DIR=',
        1,
    )
    p.write_text(text)
    env = dict(os.environ)
    env.pop("SKILL_LOOP_NOTIFY", None)
    if mode is not None:
        env["SKILL_LOOP_NOTIFY"] = mode
    result = subprocess.run(["bash", str(p)], env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        mode or "macos",
        str(scripts / "job_monitor.py"),
        "--notify-heartbeat",
        "--project-root",
        str(tmp_path),
    ]


def installer_fixture(tmp_path):
    root = tmp_path / "project & <test> $HOME"
    (root / "launchd").mkdir(parents=True)
    for p in (ROOT / "launchd").glob("*.plist"):
        shutil.copy(p, root / "launchd")
    return root, tmp_path / "agents", tmp_path / "home & $PROJECT_DIR"


def test_installer_renders_all_and_is_idempotent(tmp_path, monkeypatch):
    installer = load_script("install_launchd")
    root, output, home = installer_fixture(tmp_path)
    call = Mock(side_effect=AssertionError("render must not call launchctl"))
    monkeypatch.setattr(installer.subprocess, "run", call)
    paths = installer.install(root, output, home)
    assert len(paths) == 4
    before = {p: p.read_bytes() for p in paths}
    for p in paths:
        value = plistlib.loads(p.read_bytes())
        assert value["WorkingDirectory"] == str(root)
        assert value["EnvironmentVariables"]["HOME"] == str(home)
        assert value["ProgramArguments"][1].startswith(str(root / "scripts"))
    assert (root / "logs").is_dir()
    assert installer.install(root, output, home) == paths
    assert before == {p: p.read_bytes() for p in paths}
    call.assert_not_called()


def test_installer_preflights_conflicts_before_writes(tmp_path):
    installer = load_script("install_launchd")
    root, output, home = installer_fixture(tmp_path)
    output.mkdir()
    conflict = output / "com.trade-analysis.skill-improvement.plist"
    conflict.write_text("local customized settings")
    with pytest.raises(ValueError, match="existing"):
        installer.install(root, output, home)
    assert list(output.iterdir()) == [conflict]
    assert conflict.read_text() == "local customized settings"
    assert not (root / "logs").exists()


def test_installer_preflights_invalid_template(tmp_path):
    installer = load_script("install_launchd")
    root, output, home = installer_fixture(tmp_path)
    (root / "launchd/com.trade-analysis.skill-improvement.plist").write_text("invalid plist")
    with pytest.raises(ValueError):
        installer.install(root, output, home)
    assert not output.exists()


def test_installer_bootstraps_only_explicit_load(tmp_path, monkeypatch):
    installer = load_script("install_launchd")
    root, output, home = installer_fixture(tmp_path)
    monkeypatch.setattr(installer.sys, "platform", "darwin")
    call = Mock()
    monkeypatch.setattr(installer.subprocess, "run", call)
    paths = installer.install(root, output, home, load=True)
    assert len(call.call_args_list) == 4
    for entry, path in zip(call.call_args_list, paths):
        assert entry.args[0] == ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)]
        assert entry.kwargs["check"] is True
        assert entry.kwargs["timeout"] == 15


def test_installer_load_failure_is_actionable(tmp_path, monkeypatch):
    installer = load_script("install_launchd")
    root, output, home = installer_fixture(tmp_path)
    monkeypatch.setattr(installer.sys, "platform", "darwin")
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        Mock(side_effect=subprocess.CalledProcessError(5, ["launchctl"])),
    )
    with pytest.raises(ValueError, match="bootout"):
        installer.install(root, output, home, load=True)


def test_watchdog_template_is_independent_daily_schedule():
    p = ROOT / "launchd/com.trade-analysis.skill-heartbeat.plist"
    data = plistlib.loads(p.read_bytes())
    assert data["StartCalendarInterval"] == {"Hour": 8, "Minute": 0}
    assert data["ProgramArguments"] == ["/bin/bash", "$PROJECT_DIR/scripts/run_skill_heartbeat.sh"]
    assert data["RunAtLoad"] is False
