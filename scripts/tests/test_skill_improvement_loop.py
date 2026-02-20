"""Tests for the skill improvement loop orchestrator."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def loop_module():
    """Load run_skill_improvement_loop.py as a module."""
    script_path = Path(__file__).resolve().parents[1] / "run_skill_improvement_loop.py"
    spec = importlib.util.spec_from_file_location("run_skill_improvement_loop", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load run_skill_improvement_loop.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_skill(project_root: Path, name: str) -> None:
    """Create a minimal skill directory."""
    skill_dir = project_root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n# {name}\n",
        encoding="utf-8",
    )


# ── Lock tests ──


def test_acquire_lock_creates_file(loop_module, tmp_path: Path):
    assert loop_module.acquire_lock(tmp_path) is True
    lock_path = tmp_path / loop_module.LOCK_FILE
    assert lock_path.exists()
    assert lock_path.read_text().strip() == str(os.getpid())
    loop_module.release_lock(tmp_path)
    assert not lock_path.exists()


def test_acquire_lock_rejects_running_pid(loop_module, tmp_path: Path):
    lock_path = tmp_path / loop_module.LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()))  # Current PID is alive

    assert loop_module.acquire_lock(tmp_path) is False
    lock_path.unlink()


def test_acquire_lock_removes_stale(loop_module, tmp_path: Path):
    lock_path = tmp_path / loop_module.LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("999999999")  # Unlikely to be a real PID

    assert loop_module.acquire_lock(tmp_path) is True
    loop_module.release_lock(tmp_path)


# ── State tests ──


def test_load_state_empty(loop_module, tmp_path: Path):
    state = loop_module.load_state(tmp_path)
    assert state == {"last_skill_index": -1, "history": []}


def test_save_and_load_state(loop_module, tmp_path: Path):
    state = {"last_skill_index": 2, "history": [{"skill": "a", "score": 80}]}
    loop_module.save_state(tmp_path, state)

    loaded = loop_module.load_state(tmp_path)
    assert loaded["last_skill_index"] == 2
    assert loaded["history"][0]["skill"] == "a"


def test_save_state_trims_history(loop_module, tmp_path: Path):
    state = {
        "last_skill_index": 0,
        "history": [{"i": i} for i in range(100)],
    }
    loop_module.save_state(tmp_path, state)
    loaded = loop_module.load_state(tmp_path)
    assert len(loaded["history"]) == loop_module.HISTORY_LIMIT


# ── Skill discovery tests ──


def test_discover_skills_excludes_reviewer(loop_module, tmp_path: Path):
    _make_skill(tmp_path, "alpha-skill")
    _make_skill(tmp_path, "beta-skill")
    _make_skill(tmp_path, loop_module.SELF_SKILL_NAME)

    skills = loop_module.discover_skills(tmp_path)
    assert loop_module.SELF_SKILL_NAME not in skills
    assert "alpha-skill" in skills
    assert "beta-skill" in skills


def test_discover_skills_ignores_dirs_without_skill_md(loop_module, tmp_path: Path):
    (tmp_path / "skills" / "no-skill-md").mkdir(parents=True)
    _make_skill(tmp_path, "valid-skill")

    skills = loop_module.discover_skills(tmp_path)
    assert "valid-skill" in skills
    assert "no-skill-md" not in skills


# ── Pick next skill (round-robin) ──


def test_pick_next_skill_round_robin(loop_module):
    skills = ["a", "b", "c"]
    state = {"last_skill_index": -1, "history": []}

    picks = []
    for _ in range(5):
        pick = loop_module.pick_next_skill(skills, state)
        picks.append(pick)
    assert picks == ["a", "b", "c", "a", "b"]


def test_pick_next_skill_empty(loop_module):
    state = {"last_skill_index": 0}
    assert loop_module.pick_next_skill([], state) is None


# ── Git safe check ──


def test_git_safe_check_dirty_tree(loop_module, tmp_path: Path, monkeypatch):
    """Dirty working tree should fail."""
    def fake_run(cmd, **kwargs):
        if "status" in cmd:
            from subprocess import CompletedProcess
            return CompletedProcess(cmd, 0, " M dirty.py\n", "")
        return CompletedProcess(cmd, 0, "main\n", "")

    import subprocess as sp
    monkeypatch.setattr(sp, "run", fake_run)
    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)

    assert loop_module.git_safe_check(tmp_path) is False


def test_git_safe_check_not_on_main(loop_module, tmp_path: Path, monkeypatch):
    """Not on main branch should fail."""
    call_count = [0]
    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess
        call_count[0] += 1
        if "status" in cmd:
            return CompletedProcess(cmd, 0, "", "")
        if "rev-parse" in cmd:
            return CompletedProcess(cmd, 0, "feature-branch\n", "")
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    assert loop_module.git_safe_check(tmp_path) is False


# ── Dry-run mode ──


def test_dry_run_skips_improvement(loop_module, tmp_path: Path):
    """apply_improvement in dry-run mode should return None without side effects."""
    report = {"final_review": {"score": 70, "improvement_items": ["fix X"]}}
    result = loop_module.apply_improvement(tmp_path, "test-skill", report, dry_run=True)
    assert result is None


# ── Daily summary ──


def test_write_daily_summary_creates_file(loop_module, tmp_path: Path):
    report = {
        "final_review": {
            "score": 75,
            "findings": [{"severity": "high"}, {"severity": "low"}],
        },
    }
    loop_module.write_daily_summary(tmp_path, "test-skill", report, improved=False)

    summary_dir = tmp_path / loop_module.SUMMARY_DIR
    files = list(summary_dir.glob("*_summary.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "test-skill" in content
    assert "Score: 75/100" in content


def test_write_daily_summary_appends(loop_module, tmp_path: Path):
    report = {"final_review": {"score": 80, "findings": []}}
    loop_module.write_daily_summary(tmp_path, "skill-a", report, improved=True)
    loop_module.write_daily_summary(tmp_path, "skill-b", report, improved=False)

    summary_dir = tmp_path / loop_module.SUMMARY_DIR
    files = list(summary_dir.glob("*_summary.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "skill-a" in content
    assert "skill-b" in content


# ── JSON extraction tests ──


def test_extract_json_from_claude_simple(loop_module):
    """Simple JSON with score field is extracted."""
    raw = '{"score": 85, "summary": "good", "findings": []}'
    result = loop_module._extract_json_from_claude(raw)
    assert result is not None
    assert result["score"] == 85


def test_extract_json_from_claude_wrapped(loop_module):
    """JSON wrapped in claude --output-format json envelope."""
    wrapper = json.dumps({
        "result": 'Here is the review:\n{"score": 72, "summary": "ok", "findings": []}',
    })
    result = loop_module._extract_json_from_claude(wrapper)
    assert result is not None
    assert result["score"] == 72


def test_extract_json_from_claude_greedy_fix(loop_module):
    """Trailing JSON block should not cause greedy over-match."""
    # With greedy [\s\S]*, regex would span from first { to last },
    # capturing invalid JSON. Non-greedy stops at the first valid closing }.
    text = (
        'Here is the review:\n\n'
        '{"score": 90, "summary": "x", "findings": []}\n\n'
        'Some trailing text with {"other": "data"}'
    )
    result = loop_module._extract_json_from_claude(text)
    assert result is not None
    assert result["score"] == 90


# ── Log rotation tests ──


def test_rotate_logs_removes_old(loop_module, tmp_path: Path):
    """Log files older than retention period should be removed."""
    import time

    log_dir = tmp_path / loop_module.LOG_DIR
    log_dir.mkdir(parents=True)

    # Create an "old" log file with mtime in the past
    old_log = log_dir / "old.log"
    old_log.write_text("old log content")
    old_time = time.time() - (60 * 86400)
    os.utime(old_log, (old_time, old_time))

    # Create a "new" log file
    new_log = log_dir / "new.log"
    new_log.write_text("new log content")

    loop_module.rotate_logs(tmp_path)

    assert not old_log.exists(), "Old log should have been removed"
    assert new_log.exists(), "New log should still exist"


# ── Improvement result tests ──


def test_apply_improvement_returns_report(loop_module, tmp_path: Path, monkeypatch):
    """Successful improvement returns the post-improvement report dict."""
    re_report = {
        "auto_review": {"score": 85},
        "final_review": {"score": 85, "findings": [], "improvement_items": []},
    }

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    monkeypatch.setattr(loop_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(loop_module, "check_existing_pr", lambda *a, **kw: False)
    monkeypatch.setattr(loop_module, "run_auto_score", lambda *a, **kw: re_report)

    report = {
        "auto_review": {"score": 70},
        "final_review": {"score": 70, "improvement_items": ["fix X"], "findings": []},
    }
    result = loop_module.apply_improvement(tmp_path, "test-skill", report, dry_run=False)

    assert isinstance(result, dict)
    assert result["final_review"]["score"] == 85


def test_apply_improvement_uses_auto_score_for_comparison(loop_module, tmp_path: Path, monkeypatch):
    """Quality gate compares auto_review scores, not final_review (LLM-merged)."""
    # post-improvement report: auto=78
    re_report = {
        "auto_review": {"score": 78},
        "final_review": {"score": 78, "findings": [], "improvement_items": []},
    }

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    monkeypatch.setattr(loop_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(loop_module, "check_existing_pr", lambda *a, **kw: False)
    monkeypatch.setattr(loop_module, "run_auto_score", lambda *a, **kw: re_report)

    # pre: auto=70, final=80 (LLM merged higher)
    # Before fix: pre_score=80 (final), re_score=78 → 78<=80 → rollback → None
    # After fix:  pre_score=70 (auto),  re_score=78 → 78>70  → success → re_report
    report = {
        "auto_review": {"score": 70},
        "final_review": {"score": 80, "improvement_items": ["fix Y"], "findings": []},
    }
    result = loop_module.apply_improvement(tmp_path, "test-skill", report, dry_run=False)

    assert result is not None, "Should succeed: auto 78 > auto 70"
    assert result["auto_review"]["score"] == 78


def test_run_uses_auto_score_for_improvement_trigger(loop_module, tmp_path: Path, monkeypatch):
    """run() uses auto_review score for improvement trigger, not final_review.

    Scenario: auto=92 (>= 90), final=81 (< 90).
    Should skip improvement because auto score meets threshold.
    """
    _make_skill(tmp_path, "high-auto-skill")

    report = {
        "auto_review": {"score": 92},
        "final_review": {"score": 81, "findings": [], "improvement_items": ["fix Z"]},
    }

    monkeypatch.setattr(loop_module, "acquire_lock", lambda *a: True)
    monkeypatch.setattr(loop_module, "release_lock", lambda *a: None)
    monkeypatch.setattr(loop_module, "git_safe_check", lambda *a: True)
    monkeypatch.setattr(loop_module, "discover_skills", lambda *a: ["high-auto-skill"])
    monkeypatch.setattr(loop_module, "pick_next_skill", lambda *a: "high-auto-skill")
    monkeypatch.setattr(loop_module, "run_auto_score", lambda *a, **kw: report)
    monkeypatch.setattr(loop_module, "write_daily_summary", lambda *a, **kw: None)
    monkeypatch.setattr(loop_module, "save_state", lambda *a, **kw: None)
    monkeypatch.setattr(loop_module, "load_state", lambda *a: {"last_skill_index": -1, "history": []})

    apply_called = []
    monkeypatch.setattr(
        loop_module, "apply_improvement",
        lambda *a, **kw: apply_called.append(1) or None,
    )

    rc = loop_module.run(tmp_path, dry_run=True)

    assert rc == 0
    assert len(apply_called) == 0, "apply_improvement should NOT be called when auto >= 90"


def test_dry_run_does_not_record_improved(loop_module, tmp_path: Path, monkeypatch):
    """In dry-run mode, history should record improved=False (not True)."""
    _make_skill(tmp_path, "low-score-skill")

    report = {
        "auto_review": {"score": 70},
        "final_review": {"score": 70, "findings": [], "improvement_items": ["fix A"]},
    }

    saved_states = []

    monkeypatch.setattr(loop_module, "acquire_lock", lambda *a: True)
    monkeypatch.setattr(loop_module, "release_lock", lambda *a: None)
    monkeypatch.setattr(loop_module, "git_safe_check", lambda *a: True)
    monkeypatch.setattr(loop_module, "discover_skills", lambda *a: ["low-score-skill"])
    monkeypatch.setattr(loop_module, "pick_next_skill", lambda *a: "low-score-skill")
    monkeypatch.setattr(loop_module, "run_auto_score", lambda *a, **kw: report)
    monkeypatch.setattr(loop_module, "write_daily_summary", lambda *a, **kw: None)
    monkeypatch.setattr(loop_module, "save_state", lambda root, state: saved_states.append(state))
    monkeypatch.setattr(loop_module, "load_state", lambda *a: {"last_skill_index": -1, "history": []})

    rc = loop_module.run(tmp_path, dry_run=True)

    assert rc == 0
    assert len(saved_states) == 1
    history_entry = saved_states[0]["history"][-1]
    assert history_entry["improved"] is False, "dry-run should not record improved=True"


def test_run_auto_score_fallback_on_uv_failure(loop_module, tmp_path: Path, monkeypatch):
    """When uv run fails, run_auto_score retries with sys.executable."""
    call_log = []

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess
        call_log.append(list(cmd))
        # First call (uv) fails; second call (python) succeeds
        if cmd[0] == "uv":
            return CompletedProcess(cmd, 1, "", "uv error")
        return CompletedProcess(cmd, 0, "", "")

    # Ensure _build_reviewer_cmd picks uv
    monkeypatch.setattr(loop_module.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)

    # Create a fake report file for the function to find
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    fake_report = {"auto_review": {"score": 75}, "final_review": {"score": 75}}
    (reports_dir / "skill_review_test-skill_2026.json").write_text(
        json.dumps(fake_report), encoding="utf-8",
    )

    result = loop_module.run_auto_score(tmp_path, "test-skill")

    assert result is not None
    assert result["auto_review"]["score"] == 75
    # Verify two calls: first uv (failed), then sys.executable (succeeded)
    assert len(call_log) == 2
    assert call_log[0][0] == "uv"
    assert call_log[1][0] == sys.executable
