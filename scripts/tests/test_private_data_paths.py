"""Index safety, including forced adds, alternate indexes and empty placeholders."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_private_data_paths.py"


def clean_env():
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def git(root, *args, env=None, data=None):
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", *args],
        cwd=root,
        env=env or clean_env(),
        input=data,
        capture_output=True,
        check=True,
    ).stdout


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    return tmp_path


def stage(root, name, data=b"PRIVATE_SENTINEL", env=None):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    git(root, "add", "-f", "--", name, env=env)
    return path


def run_guard(cwd, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        env=env or clean_env(),
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.local",
        ".envrc",
        ".envrc.bak",
        ".mcp.json",
        ".mcp.json.backup",
        "state/theses/PRIVATE.yaml",
        "logs/a.json",
        "reports/PRIVATE.csv",
        "reviews/a.md",
        ".cache/a.json",
        ".claude/a.jsonl",
        ".staging/a.py",
        "private-backups/a.tar",
        ".aws/credentials",
        ".ssh/id_ed25519",
        "STATE/PRIVATE",
        "Reports/PRIVATE.md",
        "reports",
    ],
)
def test_forced_private_index_paths_block_without_data_echo(repo, name):
    stage(repo, name)
    result = run_guard(repo)
    assert result.returncode == 1
    assert "PRIVATE" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "name",
    [
        "README.md",
        "docs/en/privacy.md",
        "scripts/example.py",
        "examples/demo/state/fictional.json",
        "scripts/tests/fixtures/a.json",
    ],
)
def test_reviewed_public_locations_are_not_blanket_banned(repo, name):
    stage(repo, name, b"fictional")
    assert run_guard(repo).returncode == 0


def test_only_exact_empty_indexed_placeholders_pass(repo):
    for name in ("state/journal/.gitkeep", "state/theses/.gitkeep"):
        stage(repo, name, b"")
    assert run_guard(repo).returncode == 0
    stage(repo, "state/other/.gitkeep", b"")
    assert run_guard(repo).returncode == 1


def test_working_empty_file_cannot_hide_staged_private_placeholder(repo):
    path = stage(repo, "state/theses/.gitkeep")
    path.write_bytes(b"")
    result = run_guard(repo)
    assert result.returncode == 1
    assert "PRIVATE" not in result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["120000", "160000"])
def test_non_regular_placeholder_modes_never_pass(repo, mode):
    oid = git(repo, "hash-object", "-w", "--stdin", data=b"").decode().strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid},state/theses/.gitkeep")
    assert run_guard(repo).returncode == 1


def test_active_alternate_index_cannot_bypass_audit(repo):
    alternate = clean_env() | {"GIT_INDEX_FILE": str(repo / "alternate-index")}
    git(repo, "read-tree", "--empty", env=alternate)
    stage(repo, ".env.local", env=alternate)
    assert run_guard(repo, env=alternate).returncode == 1
    assert run_guard(repo).returncode == 0


def test_subdirectory_invocation_checks_whole_index(repo):
    stage(repo, "reports/PRIVATE.json")
    subdir = repo / "scripts"
    subdir.mkdir()
    assert run_guard(subdir).returncode == 1


def test_no_repository_fails_closed(tmp_path):
    result = run_guard(tmp_path)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_repository_index_has_no_private_data():
    # Existing CI's repo-scripts row enforces the guard on the actual checkout.
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def test_canonical_paths_are_ignored():
    probes = [
        ".env",
        ".env.local",
        ".envrc",
        ".mcp.json",
        ".mcp.json.bak",
        "state/new.yaml",
        "reports/new.json",
        "logs/new.log",
        "reviews/new.md",
        ".cache/new.json",
        ".claude/new.jsonl",
        ".staging/new.py",
        "private-backups/new",
        ".aws/credentials",
        ".ssh/id_ed25519",
    ]
    for path in probes:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", "--", path], cwd=ROOT, capture_output=True
        )
        assert result.returncode == 0, path


def test_replacement_refs_cannot_hide_private_placeholder_blob(repo):
    stage(repo, "state/theses/.gitkeep")
    original = git(repo, "rev-parse", ":state/theses/.gitkeep").decode().strip()
    empty = git(repo, "hash-object", "-w", "--stdin", data=b"").decode().strip()
    git(repo, "replace", original, empty)
    # Normal cat-file now sees the empty replacement; the commit retains original.
    assert git(repo, "cat-file", "-s", original).strip() == b"0"
    assert run_guard(repo).returncode == 1
