"""Disposable local repositories prove generation never operates on primary Git."""

import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_skill_generation_isolated as isolated

ROOT = Path(__file__).resolve().parents[2]
REAL_GIT = shutil.which("git")
STUB = """import json, os, subprocess, sys, time
from pathlib import Path
root = Path(sys.argv[sys.argv.index("--project-root") + 1]).resolve()
assert Path.cwd() == root
assert not any(k.startswith("GIT_") for k in os.environ)
subprocess.run(["git", "status", "--porcelain"], check=True)
if os.environ.get("TEST_MUTATE"):
    subprocess.run(["git", "checkout", "-b", "isolated-test"], check=True)
    (root / "scratch-to-clean").write_text("temporary")
    subprocess.run(["git", "clean", "-fd", "--", "scratch-to-clean"], check=True)
    subprocess.run(["git", "checkout", "main"], check=True)
(root / "logs/proof.json").write_text(json.dumps({"root": str(root), "args": sys.argv[1:]}))
if os.environ.get("TEST_READY"):
    Path(os.environ["TEST_READY"]).write_text(str(os.getpid()))
    while not Path(os.environ["TEST_STOP"]).exists():
        time.sleep(.05)
sys.exit(int(os.environ.get("TEST_EXIT", "0")))
"""


def fixture_git_env():
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def git(root, *args):
    return subprocess.run(
        [REAL_GIT, *args],
        cwd=root,
        env=fixture_git_env(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def init_bare(path):
    subprocess.run(
        [REAL_GIT, "init", "--bare", "--initial-branch=main", str(path)],
        env=fixture_git_env(),
        check=True,
        capture_output=True,
    )


def snapshot(primary):
    return {
        "head": git(primary, "rev-parse", "HEAD"),
        "branch": git(primary, "branch", "--show-current"),
        "status": git(primary, "status", "--porcelain"),
        "index": (primary / ".git/index").read_bytes(),
        "readme": (primary / "README").read_bytes(),
        "untracked": (primary / "personal-note").read_bytes(),
    }


@pytest.fixture(autouse=True)
def clean_fixture_git_environment(monkeypatch):
    # Push hooks export GIT_DIR and related repository selectors. Clear them
    # before even fixture init/config; explicit attack tests set their own later.
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    init_bare(remote)
    primary = tmp_path / "primary"
    primary.mkdir()
    git(primary, "init", "--initial-branch=main")
    git(primary, "config", "user.email", "fixture@example.test")
    git(primary, "config", "user.name", "Fictional test")
    git(primary, "remote", "add", "origin", str(remote))
    (primary / "scripts").mkdir()
    (primary / "scripts/run_skill_generation_pipeline.py").write_text(STUB)
    (primary / "README").write_text("original")
    (primary / ".gitignore").write_text("logs/\nreports/\nstate/\n.envrc\n")
    git(primary, "add", ".")
    git(primary, "commit", "-m", "fictional fixture")
    git(primary, "push", "origin", "main")
    git(primary, "checkout", "-b", "maintainer-work")
    (primary / "README").write_text("staged maintainer changes")
    git(primary, "add", "README")
    (primary / "README").write_text("unstaged maintainer changes")
    (primary / "personal-note").write_text("preserve this")
    calls = tmp_path / "git-calls.jsonl"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fakegit = bindir / "git"
    fakegit.write_text(f"""#!{sys.executable}
import json,os,sys
with open({str(calls)!r},"a") as out:
    out.write(json.dumps({{"cwd":os.getcwd(),"args":sys.argv[1:]}})+"\\n")
os.execv({REAL_GIT!r},[{REAL_GIT!r},*sys.argv[1:]])
""")
    fakegit.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    checkout = tmp_path / "generation-bot"
    monkeypatch.setenv("SKILL_GENERATION_CHECKOUT", str(checkout))
    return primary, remote, checkout, calls


def test_all_git_and_child_operations_use_isolated_checkout(repos, monkeypatch):
    primary, _, checkout, calls = repos
    before = snapshot(primary)
    monkeypatch.setenv("TEST_MUTATE", "1")
    monkeypatch.setenv("GIT_DIR", str(primary / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(primary))
    assert isolated.launch(primary, "daily", True) == 0
    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_WORK_TREE")
    assert snapshot(primary) == before
    logged = [json.loads(x) for x in calls.read_text().splitlines()]
    assert logged and all(Path(x["cwd"]) == checkout for x in logged)
    assert any("clone" in x["args"] for x in logged)
    assert any("clean" in x["args"] for x in logged)
    proof = json.loads((primary / "logs/proof.json").read_text())
    assert proof["root"] == str(checkout)
    assert proof["args"] == ["--mode", "daily", "--dry-run", "--project-root", str(checkout)]
    assert git(checkout, "status", "--porcelain") == ""
    assert (checkout / "logs").resolve() == primary / "logs"
    assert (checkout / "reports").resolve() == primary / "reports"


@pytest.mark.parametrize("target", ["primary", "ancestor", "descendant", "alias", "improvement"])
def test_unsafe_checkout_paths_are_rejected_without_git(repos, tmp_path, monkeypatch, target):
    primary, _, _, calls = repos
    paths = {
        "primary": primary,
        "ancestor": primary.parent,
        "descendant": primary / "bot",
        "improvement": tmp_path / "improvement",
    }
    if target == "alias":
        paths[target] = tmp_path / "alias"
        paths[target].symlink_to(primary, target_is_directory=True)
    monkeypatch.setenv("SKILL_LOOP_CHECKOUT", str(tmp_path / "improvement"))
    monkeypatch.setenv("SKILL_GENERATION_CHECKOUT", str(paths[target]))
    before = snapshot(primary)
    with pytest.raises(isolated.LaunchError):
        isolated.launch(primary, "daily", True)
    assert not calls.exists()
    assert snapshot(primary) == before


@pytest.mark.parametrize(
    "problem", ["dirty", "off-main", "wrong-origin", "gitfile", "git-symlink", "common-dir"]
)
def test_existing_checkout_problems_preserve_data(repos, problem):
    primary, remote, checkout, _ = repos
    git(checkout.parent, "clone", "--branch", "main", str(remote), str(checkout))
    if problem == "dirty":
        (checkout / "README").write_text("valuable unfinished change")
    elif problem == "off-main":
        git(checkout, "checkout", "-b", "unfinished")
    elif problem == "wrong-origin":
        git(checkout, "remote", "set-url", "origin", str(remote.parent / "other"))
    elif problem == "gitfile":
        shutil.rmtree(checkout / ".git")
        (checkout / ".git").write_text(f"gitdir: {primary / '.git'}\n")
    elif problem == "git-symlink":
        shutil.rmtree(checkout / ".git")
        (checkout / ".git").symlink_to(primary / ".git", target_is_directory=True)
    else:
        (checkout / ".git/commondir").write_text(str(primary / ".git"))
    before = (checkout / "README").read_bytes()
    primary_before = snapshot(primary)
    with pytest.raises(isolated.LaunchError):
        isolated.launch(primary, "daily", True)
    assert (checkout / "README").read_bytes() == before
    assert snapshot(primary) == primary_before


def test_nonempty_nonrepo_and_unexpected_output_links_are_preserved(repos):
    primary, remote, checkout, _ = repos
    checkout.mkdir()
    (checkout / "precious").write_text("retain")
    with pytest.raises(isolated.LaunchError):
        isolated.launch(primary, "daily", True)
    assert (checkout / "precious").read_text() == "retain"
    (checkout / "precious").unlink()
    git(checkout.parent, "clone", "--branch", "main", str(remote), str(checkout))
    (checkout / "logs").mkdir()
    (checkout / "logs/precious").write_text("retain too")
    with pytest.raises(isolated.LaunchError):
        isolated.launch(primary, "daily", True)
    assert (checkout / "logs/precious").read_text() == "retain too"


def test_lock_contention_skips_before_any_git(repos):
    primary, _, _, calls = repos
    (primary / "logs").mkdir()
    with (primary / "logs/.skill_generation_launcher.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert isolated.launch(primary, "daily", True) == 0
        assert not calls.exists()


def test_child_failure_releases_locks_and_preserves_exit(repos, monkeypatch):
    primary, _, _, _ = repos
    monkeypatch.setenv("TEST_EXIT", "7")
    assert isolated.launch(primary, "daily", True) == 7
    monkeypatch.setenv("TEST_EXIT", "0")
    assert isolated.launch(primary, "daily", True) == 0


def test_real_daily_dry_run_uses_fictional_shared_backlog(repos):
    primary, remote, checkout, _ = repos
    seed = remote.parent / "seed"
    git(seed.parent, "clone", str(remote), str(seed))
    shutil.copy(ROOT / "scripts/run_skill_generation_pipeline.py", seed / "scripts")
    git(
        seed,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.test",
        "commit",
        "-am",
        "real pipeline",
    )
    git(seed, "push", "origin", "main")
    (primary / "logs").mkdir()
    (primary / "logs/.skill_generation_backlog.yaml").write_text(
        "ideas:\n- id: raw_fiction_001\n  title: Fictional isolation fixture\n  status: pending\n  scores:\n    trading_value: 20\n    composite: 80\n"
    )
    before = snapshot(primary)
    assert isolated.launch(primary, "daily", True) == 0
    state = json.loads((primary / "logs/.skill_generation_state.json").read_text())
    assert state["history"][-1]["dry_run"] is True
    assert snapshot(primary) == before
    assert git(checkout, "status", "--porcelain") == ""


def test_wrapper_never_executes_primary_envrc_or_accepts_project_root(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(ROOT / "scripts/run_skill_generation.sh", scripts)
    shutil.copy(ROOT / "scripts/run_skill_generation_isolated.py", scripts)
    marker = tmp_path / "unsafe-envrc"
    (tmp_path / ".envrc").write_text(f'git status\ntouch "{marker}"\n')
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "direnv").write_text(f"#!/bin/sh\necho 'touch \"{marker}\"'\n")
    (bindir / "direnv").chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
        "SKILL_LOOP_NOTIFY": "",
    }
    result = subprocess.run(
        [
            "bash",
            str(scripts / "run_skill_generation.sh"),
            "--mode",
            "daily",
            "--project-root",
            str(tmp_path),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert not marker.exists()


def test_parent_death_keeps_child_exclusion(repos, tmp_path, monkeypatch):
    primary, _, _, calls = repos
    ready, stop = tmp_path / "ready", tmp_path / "stop"
    monkeypatch.setenv("TEST_READY", str(ready))
    monkeypatch.setenv("TEST_STOP", str(stop))
    code = "import sys;sys.path.insert(0,sys.argv[1]);from run_skill_generation_isolated import launch;launch(__import__('pathlib').Path(sys.argv[2]),'daily',True)"
    parent = subprocess.Popen([sys.executable, "-c", code, str(ROOT / "scripts"), str(primary)])
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists()
        parent.kill()
        parent.wait(timeout=5)
        before = calls.read_bytes()
        assert isolated.launch(primary, "weekly", True) == 0
        assert calls.read_bytes() == before
        # A different clone must still be blocked by the inherited state lock.
        monkeypatch.setenv("SKILL_GENERATION_CHECKOUT", str(tmp_path / "other-bot"))
        assert isolated.launch(primary, "daily", True) == 0
        assert calls.read_bytes() == before
    finally:
        stop.touch()
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)


def test_default_checkout_and_shared_exclude_are_safe(repos, monkeypatch):
    primary, _, _, _ = repos
    monkeypatch.delenv("SKILL_GENERATION_CHECKOUT")
    expected = Path(os.environ["HOME"]) / ".local/share/claude-trading-skills-generation-bot"
    assert isolated.launch(primary, "weekly", True) == 0
    assert json.loads((primary / "logs/proof.json").read_text())["root"] == str(expected)
    exclude = expected / ".git/info/exclude"
    with exclude.open("a") as out:
        out.write("/personal-preserved\n")
    assert isolated.launch(primary, "daily", True) == 0
    assert "/personal-preserved" in exclude.read_text()
    assert exclude.read_text().splitlines().count("/logs") == 1


def test_primary_linked_worktree_origin_read_without_git(repos, tmp_path):
    primary, remote, checkout, calls = repos
    worktree = tmp_path / "primary-worktree"
    git(primary, "worktree", "add", "-b", "another-worktree", str(worktree), "main")
    assert isolated.origin_from(worktree) == str(remote)
    assert isolated.launch(worktree, "daily", True) == 0
    logged = [json.loads(x) for x in calls.read_text().splitlines()]
    assert all(Path(x["cwd"]) == checkout for x in logged)


def test_checkout_lock_is_shared_across_different_primary_roots(repos, tmp_path):
    primary, _, checkout, calls = repos
    another = tmp_path / "another-primary"
    git(primary, "worktree", "add", "-b", "other-primary", str(another), "main")
    lockpath = checkout.parent / f".{checkout.name}.generation.lock"
    with lockpath.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert isolated.launch(another, "daily", True) == 0
        assert not calls.exists()


def test_fast_forward_updates_bot_only(repos, tmp_path):
    primary, remote, checkout, _ = repos
    assert isolated.launch(primary, "daily", True) == 0
    before = snapshot(primary)
    seed = tmp_path / "seed"
    git(tmp_path, "clone", str(remote), str(seed))
    (seed / "new-file").write_text("new remote evidence")
    git(seed, "add", "new-file")
    git(
        seed,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.test",
        "commit",
        "-m",
        "update",
    )
    git(seed, "push", "origin", "main")
    assert isolated.launch(primary, "daily", True) == 0
    assert (checkout / "new-file").read_text() == "new remote evidence"
    assert snapshot(primary) == before


def test_unpushed_main_commit_is_preserved_and_refused(repos):
    primary, _, checkout, _ = repos
    assert isolated.launch(primary, "daily", True) == 0
    (checkout / "local-work").write_text("valuable")
    git(checkout, "add", "local-work")
    git(
        checkout,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.test",
        "commit",
        "-m",
        "local work",
    )
    head = git(checkout, "rev-parse", "HEAD")
    with pytest.raises(isolated.LaunchError):
        isolated.launch(primary, "daily", True)
    assert git(checkout, "rev-parse", "HEAD") == head
    assert (checkout / "local-work").read_text() == "valuable"


def test_wrong_shared_link_and_active_worktree_config_are_refused(repos, tmp_path):
    primary, remote, checkout, _ = repos
    git(tmp_path, "clone", str(remote), str(checkout))
    outside = tmp_path / "outside"
    outside.mkdir()
    (checkout / "reports").symlink_to(outside, target_is_directory=True)
    with pytest.raises(isolated.LaunchError):
        isolated.launch(primary, "daily", True)
    assert (checkout / "reports").resolve() == outside
    (checkout / "reports").unlink()
    git(checkout, "config", "core.worktree", str(primary))
    before = snapshot(primary)
    with pytest.raises(isolated.LaunchError):
        isolated.launch(primary, "daily", True)
    assert snapshot(primary) == before


def test_fetch_failure_preserves_checkout(repos, monkeypatch):
    primary, remote, checkout, _ = repos
    assert isolated.launch(primary, "daily", True) == 0
    moved = remote.with_name("remote-offline.git")
    remote.rename(moved)
    head = git(checkout, "rev-parse", "HEAD")
    with pytest.raises(isolated.LaunchError):
        isolated.launch(primary, "daily", True)
    assert git(checkout, "rev-parse", "HEAD") == head


def test_credential_origin_is_rejected_without_exposing_it(repos):
    primary, _, _, calls = repos
    git(
        primary,
        "remote",
        "set-url",
        "origin",
        "https://user:fixture-password@example.test/repo.git",  # pragma: allowlist secret
    )
    with pytest.raises(isolated.LaunchError) as error:
        isolated.launch(primary, "daily", True)
    assert "fixture-password" not in str(error.value)
    assert not calls.exists()


def test_remote_tracked_outputs_cannot_overwrite_shared_state(repos, tmp_path):
    primary, remote, checkout, _ = repos
    assert isolated.launch(primary, "daily", True) == 0
    sentinel = primary / "logs/keep"
    sentinel.write_text("valuable shared state")
    head = git(checkout, "rev-parse", "HEAD")
    seed = tmp_path / "seed"
    git(tmp_path, "clone", str(remote), str(seed))
    (seed / "logs").mkdir()
    (seed / "logs/keep").write_text("unexpected tracked data")
    git(seed, "add", "-f", "logs/keep")
    git(
        seed,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.test",
        "commit",
        "-m",
        "unexpected tracked outputs",
    )
    git(seed, "push", "origin", "main")
    with pytest.raises(isolated.LaunchError):
        isolated.launch(primary, "daily", True)
    assert sentinel.read_text() == "valuable shared state"
    assert git(checkout, "rev-parse", "HEAD") == head


@pytest.mark.parametrize("conditional", [False, True])
def test_primary_include_cannot_select_a_different_origin(repos, tmp_path, conditional):
    primary, _, _, calls = repos
    included = tmp_path / "included.gitconfig"
    fork = tmp_path / "fork.git"
    included.write_text(f'[remote "origin"]\n url = {fork}\n')
    config = primary / ".git/config"
    section = f'[includeIf "gitdir:{primary}/"]' if conditional else "[include]"
    config.write_text(f"{section}\n path = {included}\n" + config.read_text())
    assert git(primary, "remote", "get-url", "origin") == str(fork)
    before = snapshot(primary)
    with pytest.raises(isolated.LaunchError, match="include"):
        isolated.launch(primary, "daily", True)
    assert not calls.exists()
    assert snapshot(primary) == before


def test_primary_worktree_config_is_not_silently_ignored(repos):
    primary, _, _, calls = repos
    (primary / ".git/config.worktree").write_text('[remote "origin"]\n url = unexpected.git\n')
    with pytest.raises(isolated.LaunchError, match="worktree config"):
        isolated.launch(primary, "daily", True)
    assert not calls.exists()


def test_global_origin_override_is_not_silently_followed(repos, monkeypatch):
    primary, remote, checkout, _ = repos
    fork = remote.parent / "global-fork.git"
    git(remote.parent, "clone", "--bare", str(remote), str(fork))
    home = Path(os.environ["HOME"])
    home.mkdir()
    (home / ".gitconfig").write_text(f'[remote "origin"]\n url = {fork}\n')
    with pytest.raises(isolated.LaunchError):
        isolated.launch(primary, "daily", True)
    assert not (primary / "logs/proof.json").exists()


def test_fixture_git_setup_cannot_mutate_push_hook_repository(tmp_path, monkeypatch):
    outer = tmp_path / "hook-repository"
    outer.mkdir()
    git(outer, "init", "--initial-branch=main")
    git(outer, "config", "user.name", "Outer fixture")
    git(outer, "config", "user.email", "outer@example.test")
    (outer / "README").write_text("preserve outer repository")
    git(outer, "add", "README")
    git(outer, "commit", "-m", "outer fixture")
    before = {name: (outer / ".git" / name).read_bytes() for name in ("config", "HEAD", "index")}
    for key, value in {
        "GIT_DIR": str(outer / ".git"),
        "GIT_WORK_TREE": str(outer),
        "GIT_COMMON_DIR": str(outer / ".git"),
        "GIT_INDEX_FILE": str(outer / ".git/index"),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "remote.origin.url",
        "GIT_CONFIG_VALUE_0": "unexpected-hook-origin",
    }.items():
        monkeypatch.setenv(key, value)
    remote = tmp_path / "disposable-origin.git"
    init_bare(remote)
    inner = tmp_path / "disposable-primary"
    inner.mkdir()
    git(inner, "init", "--initial-branch=main")
    git(inner, "config", "user.name", "Inner fixture")
    git(inner, "config", "user.email", "inner@example.test")
    git(inner, "remote", "add", "origin", str(remote))
    assert git(inner, "config", "user.name") == "Inner fixture"
    assert {name: (outer / ".git" / name).read_bytes() for name in before} == before
    assert (outer / "README").read_text() == "preserve outer repository"
