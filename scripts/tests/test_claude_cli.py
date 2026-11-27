"""Tests for scripts/claude_cli.py: pick the newest claude CLI on PATH (#652)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from scripts import claude_cli


def _fake_claude(directory: Path, version_line: str | None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / "claude"
    if version_line is None:
        body = "#!/bin/sh\nexit 1\n"
    else:
        body = f"#!/bin/sh\necho '{version_line}'\n"
    exe.write_text(body, encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    monkeypatch.delenv(claude_cli.CLAUDE_BIN_ENV, raising=False)


def test_newest_version_wins_over_path_order(tmp_path):
    old = _fake_claude(tmp_path / "homebrew", "2.0.69 (Claude Code)")
    new = _fake_claude(tmp_path / "native", "2.1.332 (Claude Code)")
    path = os.pathsep.join([str(old.parent), str(new.parent)])

    choice = claude_cli.resolve_claude_bin(path=path)

    assert choice.path == str(new)
    assert choice.version == (2, 1, 332)
    assert choice.candidates == [(str(old), (2, 0, 69)), (str(new), (2, 1, 332))]


def test_version_compares_numerically_not_as_text(tmp_path):
    nine = _fake_claude(tmp_path / "a", "2.1.9 (Claude Code)")
    ten = _fake_claude(tmp_path / "b", "2.1.10 (Claude Code)")
    path = os.pathsep.join([str(ten.parent), str(nine.parent)])

    assert claude_cli.resolve_claude_bin(path=path).path == str(ten)


def test_unreadable_version_ranks_below_any_known_version(tmp_path):
    broken = _fake_claude(tmp_path / "broken", None)
    known = _fake_claude(tmp_path / "known", "1.0.0 (Claude Code)")
    path = os.pathsep.join([str(broken.parent), str(known.parent)])

    assert claude_cli.resolve_claude_bin(path=path).path == str(known)


def test_single_candidate_is_used_without_a_version_probe(tmp_path, monkeypatch):
    only = _fake_claude(tmp_path / "only", "2.1.332 (Claude Code)")

    def no_probe(*a, **kw):
        raise AssertionError("a single candidate must not be probed")

    monkeypatch.setattr(claude_cli.subprocess, "run", no_probe)
    choice = claude_cli.resolve_claude_bin(path=str(only.parent))

    assert choice.path == str(only)
    assert choice.version is None


def test_duplicate_directories_and_symlinks_count_once(tmp_path):
    real = _fake_claude(tmp_path / "real", "2.1.332 (Claude Code)")
    link_dir = tmp_path / "link"
    link_dir.mkdir()
    (link_dir / "claude").symlink_to(real)
    path = os.pathsep.join([str(real.parent), str(link_dir), str(real.parent)])

    choice = claude_cli.resolve_claude_bin(path=path)

    assert choice.path == str(real)
    assert len(choice.candidates) == 1


def test_non_executable_file_is_ignored(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "claude").write_text("not a program", encoding="utf-8")

    assert claude_cli.resolve_claude_bin(path=str(plain)) is None


def test_no_candidate_returns_none(tmp_path):
    assert claude_cli.resolve_claude_bin(path=str(tmp_path)) is None


def test_override_wins_and_is_not_probed(tmp_path, monkeypatch):
    old = _fake_claude(tmp_path / "old", "2.0.69 (Claude Code)")
    new = _fake_claude(tmp_path / "new", "2.1.332 (Claude Code)")
    monkeypatch.setenv(claude_cli.CLAUDE_BIN_ENV, str(old))
    path = os.pathsep.join([str(old.parent), str(new.parent)])

    choice = claude_cli.resolve_claude_bin(path=path)

    assert choice.path == str(old)
    assert choice.source == "override"


def test_unusable_override_is_reported_not_silently_replaced(tmp_path, monkeypatch):
    _fake_claude(tmp_path / "new", "2.1.332 (Claude Code)")
    monkeypatch.setenv(claude_cli.CLAUDE_BIN_ENV, str(tmp_path / "missing" / "claude"))

    with pytest.raises(claude_cli.ClaudeBinError):
        claude_cli.resolve_claude_bin(path=str(tmp_path / "new"))


def test_relative_and_empty_path_entries_resolve_to_absolute_paths(tmp_path, monkeypatch):
    rel = _fake_claude(tmp_path / "rel" / "bin", "2.1.332 (Claude Code)")
    here = _fake_claude(tmp_path / "here", "2.1.300 (Claude Code)")
    monkeypatch.chdir(tmp_path / "here")

    rel_choice = claude_cli.resolve_claude_bin(path=os.path.join("..", "rel", "bin"))
    empty_choice = claude_cli.resolve_claude_bin(path="")

    assert os.path.isabs(rel_choice.path)
    assert os.path.samefile(rel_choice.path, rel)
    assert os.path.samefile(empty_choice.path, here)


def test_relative_pin_is_rejected(tmp_path, monkeypatch):
    _fake_claude(tmp_path / "pin", "2.1.332 (Claude Code)")
    monkeypatch.chdir(tmp_path / "pin")
    monkeypatch.setenv(claude_cli.CLAUDE_BIN_ENV, "claude")

    with pytest.raises(claude_cli.ClaudeBinError, match="absolute"):
        claude_cli.resolve_claude_bin(path=str(tmp_path))


def test_undecodable_version_banner_does_not_abort(tmp_path):
    odd = tmp_path / "odd"
    odd.mkdir()
    exe = odd / "claude"
    exe.write_text("#!/bin/sh\nprintf '\\377 9.9.9\\n'\nprintf '\\377' >&2\n", encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    good = _fake_claude(tmp_path / "good", "2.1.332 (Claude Code)")
    path = os.pathsep.join([str(odd), str(good.parent)])

    choice = claude_cli.resolve_claude_bin(path=path)

    assert choice.path == str(exe)
    assert choice.version == (9, 9, 9)


def test_version_probe_timeout_ranks_as_unknown(tmp_path, monkeypatch):
    a = _fake_claude(tmp_path / "a", "2.1.332 (Claude Code)")
    b = _fake_claude(tmp_path / "b", "2.0.69 (Claude Code)")
    real_run = subprocess.run

    def slow_for_a(cmd, **kw):
        if cmd[0] == str(a):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        return real_run(cmd, **kw)

    monkeypatch.setattr(claude_cli.subprocess, "run", slow_for_a)
    path = os.pathsep.join([str(a.parent), str(b.parent)])

    assert claude_cli.resolve_claude_bin(path=path).path == str(b)
