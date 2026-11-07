"""Exercise publication and recovery against a real local Git remote, offline."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/propose_quality_dashboard.sh"
BRANCH = "automation/quality-dashboard-123-1"
PAGES = [
    "docs/assets/quality-dashboard-sources.json",
    "docs/en/quality-dashboard.md",
    "docs/ja/quality-dashboard.md",
]


@pytest.fixture(autouse=True)
def _isolate_from_hook_git_env(monkeypatch):
    """Pre-push hooks export GIT_DIR/GIT_INDEX_FILE; without this scrub the
    fixture's ``git init --bare``/``git config``/``git add`` act on the real
    repository, flipping ``core.bare`` and replacing its identity and index
    (mirrors test_package_skills)."""
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key, raising=False)


def git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


@pytest.fixture
def publication(tmp_path):
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    repo.mkdir()
    git(tmp_path, "init", "--bare", str(remote))
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test Bot")
    git(repo, "config", "user.email", "test@example.invalid")
    for name in PAGES:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("baseline\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "baseline")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "origin", "main")
    original_sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    for name in PAGES:
        (repo / name).write_text("refreshed\n")
    (repo / "unrelated.txt").write_text("leave alone\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, subprocess, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['CALL_LOG'], 'a') as f: f.write(json.dumps(args) + '\\n')\n"
        "mode = os.environ.get('MODE', '')\n"
        "if args[:2] == ['pr', 'list']:\n"
        "    if '--head' not in args: print('1' if mode == 'pending' else '0')\n"
        "    elif mode == 'unknown': sys.exit(1)\n"
        "    elif mode == 'malformed': print('garbage')\n"
        "    else: print('1' if mode in ('lost-response', 'closed-pr') else '0')\n"
        "elif args[:2] == ['pr', 'create']:\n"
        "    assert '--body-file' in args\n"
        "    assert Path(args[args.index('--body-file') + 1]).read_text()\n"
        "    if mode == 'moved':\n"
        "        subprocess.run(['git', '--git-dir=' + os.environ['TEST_REMOTE'],\n"
        "                        'update-ref', 'refs/heads/' + os.environ['TEST_BRANCH'],\n"
        "                        os.environ['ORIGINAL_SHA']], check=True)\n"
        "    if mode != 'success': sys.exit(1)\n"
        "    print('https://example.invalid/pull/1')\n"
        "else: sys.exit(99)\n"
    )
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        "GH_REPO": "owner/repo",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        "RUNNER_TEMP": str(tmp_path),
        "CALL_LOG": str(tmp_path / "calls"),
        "TEST_REMOTE": str(remote),
        "TEST_BRANCH": BRANCH,
        "ORIGINAL_SHA": original_sha,
        # Do not inherit global hooks or contact the network through signing.
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/dev/null",
        "GIT_CONFIG_KEY_1": "commit.gpgsign",
        "GIT_CONFIG_VALUE_1": "false",
    }
    return repo, remote, env


def run(publication, mode="success"):
    repo, _, env = publication
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=repo,
        env={**env, "MODE": mode},
        capture_output=True,
        text=True,
        timeout=30,
    )


def remote_sha(publication):
    repo, _, _ = publication
    return git(repo, "ls-remote", "origin", "refs/heads/" + BRANCH).stdout.split()


def summary(publication):
    return Path(publication[2]["GITHUB_STEP_SUMMARY"]).read_text()


def test_success_publishes_only_dashboard_paths(publication):
    git(publication[0], "add", "unrelated.txt")
    result = run(publication)
    assert result.returncode == 0, result.stderr
    assert remote_sha(publication)
    repo = publication[0]
    assert set(
        git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").stdout.split()
    ) == set(PAGES)
    assert git(repo, "status", "--short").stdout == "A  unrelated.txt\n"
    assert "https://example.invalid/pull/1" in summary(publication)


@pytest.mark.parametrize("mode", ["pending", "no-change"])
def test_early_exit_does_not_publish(publication, mode):
    if mode == "no-change":
        git(publication[0], "restore", "docs")
    result = run(publication, mode)
    assert result.returncode == 0, result.stderr
    assert not remote_sha(publication)
    calls = Path(publication[2]["CALL_LOG"]).read_text()
    assert '"create"' not in calls


def test_denied_pr_creation_removes_only_new_branch(publication):
    result = run(publication, "denied")
    assert result.returncode != 0
    assert not remote_sha(publication)
    assert "removed" in summary(publication).lower()
    assert "permission" in summary(publication).lower()
    calls = [json.loads(line) for line in Path(publication[2]["CALL_LOG"]).read_text().splitlines()]
    recovery = calls[-1]
    assert recovery[recovery.index("--state") + 1] == "all"
    assert recovery[recovery.index("--head") + 1] == BRANCH


@pytest.mark.parametrize("mode", ["lost-response", "closed-pr", "unknown", "malformed", "moved"])
def test_recovery_preserves_used_uncertain_or_changed_branch(publication, mode):
    result = run(publication, mode)
    assert result.returncode != 0
    actual = remote_sha(publication)
    assert actual
    if mode == "moved":
        assert actual[0] == publication[2]["ORIGINAL_SHA"]
    assert BRANCH in summary(publication)
    assert "preserved" in summary(publication).lower()


def test_preexisting_remote_branch_is_untouched(publication):
    git(publication[0], "push", "origin", "HEAD:refs/heads/" + BRANCH)
    before = remote_sha(publication)
    result = run(publication)
    assert result.returncode != 0
    assert remote_sha(publication) == before
    assert '"create"' not in Path(publication[2]["CALL_LOG"]).read_text()


def test_accepted_push_with_lost_response_is_recovered(publication):
    repo, _, env = publication
    real_git = subprocess.check_output(["which", "git"], text=True).strip()
    wrapper = Path(env["PATH"].split(os.pathsep)[0]) / "git"
    wrapper.write_text(
        f'#!/bin/bash\n{real_git} "$@"\nstatus=$?\n'
        'if [[ "$1" == push && "$*" == *HEAD:refs/heads/* && "$status" == 0 ]]; then exit 1; fi\n'
        'exit "$status"\n'
    )
    wrapper.chmod(0o755)
    result = run(publication, "denied")
    assert result.returncode != 0
    assert not remote_sha(publication)
    assert "removed" in summary(publication).lower()
    assert git(repo, "rev-parse", "HEAD").stdout.strip() != env["ORIGINAL_SHA"]


def test_invalid_run_identity_cannot_publish(publication):
    publication[2]["GITHUB_RUN_ID"] = "../unexpected"
    result = run(publication)
    assert result.returncode != 0
    assert not remote_sha(publication)


def test_no_dashboard_change_leaves_unrelated_index_untouched(publication):
    repo = publication[0]
    git(repo, "restore", "docs")
    git(repo, "add", "unrelated.txt")
    result = run(publication)
    assert result.returncode == 0, result.stderr
    assert not remote_sha(publication)
    assert git(repo, "status", "--short").stdout == "A  unrelated.txt\n"


def test_preexisting_local_branch_is_untouched(publication):
    git(publication[0], "branch", BRANCH)
    result = run(publication)
    assert result.returncode != 0
    assert not remote_sha(publication)
    assert git(publication[0], "rev-parse", BRANCH).stdout.strip() == publication[2]["ORIGINAL_SHA"]


def test_cleanup_denied_is_reported_as_failure(publication):
    hook = publication[1] / "hooks/pre-receive"
    hook.write_text(
        "#!/bin/bash\nwhile read -r old new ref; do\n"
        'if [[ "$new" == 0000000000000000000000000000000000000000 ]]; then exit 1; fi\n'
        "done\n"
    )
    hook.chmod(0o755)
    result = run(publication, "denied")
    assert result.returncode != 0
    assert remote_sha(publication)
    assert "guarded cleanup failed" in summary(publication)
