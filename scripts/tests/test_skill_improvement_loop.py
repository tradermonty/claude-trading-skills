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


def test_is_safe_dirty_tree_reports_only(loop_module):
    """Tracked changes only under reports/ and logs/ are safe."""
    assert loop_module._is_safe_dirty_tree(" M reports/summary.md\n M logs/run.log\n") is True


def test_is_safe_dirty_tree_blocks_source_files(loop_module):
    """Tracked changes to source files are blocked."""
    assert loop_module._is_safe_dirty_tree(" M scripts/run_skill_improvement_loop.py\n") is False


def test_is_safe_dirty_tree_blocks_untracked(loop_module):
    """Untracked files are always blocked, even under reports/."""
    assert loop_module._is_safe_dirty_tree("?? reports/new_report.md\n") is False


def test_is_safe_dirty_tree_mixed(loop_module):
    """Mixed safe and unsafe files should block."""
    output = " M reports/summary.md\n M skills/foo/SKILL.md\n"
    assert loop_module._is_safe_dirty_tree(output) is False


def test_is_safe_dirty_tree_allows_untracked_state(loop_module):
    """Untracked files under state/ are allowed (new thesis files)."""
    assert loop_module._is_safe_dirty_tree("?? state/theses/new.yaml\n") is True


def test_is_safe_dirty_tree_allows_untracked_state_journal(loop_module):
    """Untracked files under state/journal/ are allowed."""
    assert loop_module._is_safe_dirty_tree("?? state/journal/pm_new.md\n") is True


def test_is_safe_dirty_tree_blocks_untracked_skills(loop_module):
    """Untracked files under skills/ are still blocked."""
    assert loop_module._is_safe_dirty_tree("?? skills/new/SKILL.md\n") is False


def test_is_safe_dirty_tree_allows_tracked_state(loop_module):
    """Tracked changes under state/ are allowed."""
    assert loop_module._is_safe_dirty_tree(" M state/theses/_index.json\n") is True


def test_git_safe_check_safe_dirty_passes(loop_module, tmp_path: Path, monkeypatch):
    """Dirty tree with only reports/ changes should pass."""
    call_count = [0]

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess

        call_count[0] += 1
        if "status" in cmd:
            return CompletedProcess(cmd, 0, " M reports/summary.md\n", "")
        if "rev-parse" in cmd:
            return CompletedProcess(cmd, 0, "main\n", "")
        # git pull --ff-only
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    assert loop_module.git_safe_check(tmp_path) is True


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
    result = loop_module._extract_json_from_claude(raw, ["score"])
    assert result is not None
    assert result["score"] == 85


def test_extract_json_from_claude_wrapped(loop_module):
    """JSON wrapped in claude --output-format json envelope."""
    wrapper = json.dumps(
        {
            "result": 'Here is the review:\n{"score": 72, "summary": "ok", "findings": []}',
        }
    )
    result = loop_module._extract_json_from_claude(wrapper, ["score"])
    assert result is not None
    assert result["score"] == 72


def test_extract_json_from_claude_greedy_fix(loop_module):
    """Trailing JSON block should not cause greedy over-match."""
    # With greedy [\s\S]*, regex would span from first { to last },
    # capturing invalid JSON. Non-greedy stops at the first valid closing }.
    text = (
        "Here is the review:\n\n"
        '{"score": 90, "summary": "x", "findings": []}\n\n'
        'Some trailing text with {"other": "data"}'
    )
    result = loop_module._extract_json_from_claude(text, ["score"])
    assert result is not None
    assert result["score"] == 90


def test_extract_json_from_claude_nested_findings(loop_module):
    """JSON with nested objects in findings array is correctly extracted."""
    text = json.dumps(
        {
            "score": 65,
            "summary": "needs work",
            "findings": [
                {"severity": "high", "message": "missing {tests}", "improvement": "add tests"},
                {"severity": "low", "message": "ok", "improvement": "none"},
            ],
        }
    )
    result = loop_module._extract_json_from_claude(text, ["score"])
    assert result is not None
    assert result["score"] == 65
    assert len(result["findings"]) == 2


def test_extract_json_from_claude_nested_in_prose(loop_module):
    """JSON embedded in prose text is correctly extracted."""
    text = (
        "Here is my review of the skill:\n\n"
        + json.dumps(
            {
                "score": 78,
                "summary": "decent",
                "findings": [
                    {"severity": "medium", "message": "refactor", "improvement": "split"},
                ],
            }
        )
        + "\n\nLet me know if you need more details."
    )
    result = loop_module._extract_json_from_claude(text, ["score"])
    assert result is not None
    assert result["score"] == 78


def test_extract_json_from_claude_braces_in_string(loop_module):
    """Braces within string values don't break parsing."""
    text = json.dumps(
        {
            "score": 55,
            "summary": "missing {tests} in code",
            "findings": [
                {
                    "severity": "high",
                    "message": "no {unit} tests found",
                    "improvement": "add {pytest} tests",
                },
            ],
        }
    )
    result = loop_module._extract_json_from_claude(text, ["score"])
    assert result is not None
    assert result["score"] == 55
    assert "{tests}" in result["summary"]


def test_extract_json_from_claude_no_score(loop_module):
    """JSON without 'score' key returns None."""
    text = '{"summary": "review", "findings": []}'
    result = loop_module._extract_json_from_claude(text, ["score"])
    assert result is None


def test_extract_json_from_claude_empty_input(loop_module):
    """Empty input returns None."""
    result = loop_module._extract_json_from_claude("", ["score"])
    assert result is None


# ── LLM review fallback tests ──


def test_run_llm_review_falls_back_to_plain_json(loop_module, tmp_path, monkeypatch):
    """When --json-schema fails, run_llm_review falls back to plain-json mode."""
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Review this skill", encoding="utf-8")

    call_count = [0]

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess

        call_count[0] += 1
        # First strategy (json-schema): all attempts fail
        if "--json-schema" in cmd:
            return CompletedProcess(cmd, 1, "", "schema error")
        # Second strategy (plain-json): succeeds
        response = json.dumps(
            {"result": json.dumps({"score": 78, "summary": "decent", "findings": []})}
        )
        return CompletedProcess(cmd, 0, response, "")

    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    monkeypatch.setattr(loop_module.shutil, "which", lambda x: "/usr/bin/claude")

    result = loop_module.run_llm_review(tmp_path, "test-skill", str(prompt_file))
    assert result is not None
    assert result["score"] == 78
    # json-schema attempts (CLAUDE_RETRIES + 1) + plain-json attempt(s)
    assert call_count[0] >= loop_module.CLAUDE_RETRIES + 2


def test_run_llm_review_plain_json_appends_schema_instruction(loop_module, tmp_path, monkeypatch):
    """Plain-json fallback appends schema instructions to prompt."""
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Review this", encoding="utf-8")

    captured_inputs = []

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess

        captured_inputs.append(kwargs.get("input", ""))
        if "--json-schema" in cmd:
            return CompletedProcess(cmd, 1, "", "fail")
        # Plain-json mode: succeed on first attempt
        response = json.dumps(
            {"result": json.dumps({"score": 80, "summary": "ok", "findings": []})}
        )
        return CompletedProcess(cmd, 0, response, "")

    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    monkeypatch.setattr(loop_module.shutil, "which", lambda x: "/usr/bin/claude")

    loop_module.run_llm_review(tmp_path, "test-skill", str(prompt_file))

    # The last captured input should have the appended instructions
    plain_json_inputs = [i for i in captured_inputs if "IMPORTANT: Respond with" in i]
    assert len(plain_json_inputs) >= 1


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


def test_apply_improvement_skips_empty_improvement_items(loop_module, tmp_path: Path, monkeypatch):
    """When improvement_items is empty, skip improvement to avoid unguided changes."""
    monkeypatch.setattr(loop_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(loop_module, "check_existing_pr", lambda *a, **kw: False)

    rollback_called = []
    monkeypatch.setattr(
        loop_module.subprocess,
        "run",
        lambda cmd, **kw: __import__("subprocess").CompletedProcess(cmd, 0, "", ""),
    )
    monkeypatch.setattr(loop_module, "_rollback", lambda *a, **kw: rollback_called.append(True))

    report = {
        "auto_review": {"score": 88},
        "final_review": {"score": 88, "improvement_items": [], "findings": []},
    }
    result = loop_module.apply_improvement(tmp_path, "test-skill", report, dry_run=False)

    assert result is None, "Should return None when improvement_items is empty"
    assert rollback_called, "Should call _rollback when skipping"


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
    monkeypatch.setattr(
        loop_module, "load_state", lambda *a: {"last_skill_index": -1, "history": []}
    )

    apply_called = []
    monkeypatch.setattr(
        loop_module,
        "apply_improvement",
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
    monkeypatch.setattr(
        loop_module, "load_state", lambda *a: {"last_skill_index": -1, "history": []}
    )

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
    monkeypatch.setattr(
        loop_module.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None
    )
    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)

    # Create a fake report file for the function to find
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    fake_report = {"auto_review": {"score": 75}, "final_review": {"score": 75}}
    (reports_dir / "skill_review_test-skill_2026.json").write_text(
        json.dumps(fake_report),
        encoding="utf-8",
    )

    result = loop_module.run_auto_score(tmp_path, "test-skill")

    assert result is not None
    assert result["auto_review"]["score"] == 75
    # Verify two calls: first uv (failed), then sys.executable (succeeded)
    assert len(call_log) == 2
    assert call_log[0][0] == "uv"
    assert call_log[1][0] == sys.executable


# ── CalledProcessError and pre-commit integration tests ──


def test_apply_improvement_logs_stderr_on_commit_failure(
    loop_module,
    tmp_path: Path,
    monkeypatch,
    caplog,
):
    """CalledProcessError with stderr is logged and triggers rollback."""
    import logging
    import subprocess as sp

    re_report = {
        "auto_review": {"score": 85},
        "final_review": {"score": 85, "findings": [], "improvement_items": []},
    }

    def fake_run(cmd, **kwargs):
        cmd_list = list(cmd)
        check = kwargs.get("check", False)
        # Raise CalledProcessError on git add with check=True (staging step)
        if cmd_list[:2] == ["git", "add"] and check:
            raise sp.CalledProcessError(
                1,
                cmd,
                output=b"",
                stderr=b"fatal: pathspec error",
            )
        return sp.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    monkeypatch.setattr(loop_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(loop_module, "check_existing_pr", lambda *a, **kw: False)
    monkeypatch.setattr(loop_module, "run_auto_score", lambda *a, **kw: re_report)

    report = {
        "auto_review": {"score": 70},
        "final_review": {"score": 70, "improvement_items": ["fix X"], "findings": []},
    }
    with caplog.at_level(logging.ERROR, logger="skill_improvement"):
        result = loop_module.apply_improvement(tmp_path, "test-skill", report, dry_run=False)

    assert result is None
    assert any("fatal: pathspec error" in rec.message for rec in caplog.records)


def test_apply_improvement_runs_precommit_before_commit(
    loop_module,
    tmp_path: Path,
    monkeypatch,
):
    """pre-commit runs before commit; auto-fixed files are re-staged."""
    re_report = {
        "auto_review": {"score": 85},
        "final_review": {"score": 85, "findings": [], "improvement_items": []},
    }

    call_log = []
    pre_commit_count = [0]

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess

        cmd_list = list(cmd)
        call_log.append(cmd_list)

        # git diff --cached --name-only returns staged files
        if cmd_list[:3] == ["git", "diff", "--cached"]:
            return CompletedProcess(cmd, 0, "skills/test-skill/SKILL.md\n", "")
        # pre-commit: first run fails (auto-fix), second run succeeds
        if cmd_list[0] == "pre-commit":
            pre_commit_count[0] += 1
            if pre_commit_count[0] == 1:
                return CompletedProcess(cmd, 1, "Fixing trailing whitespace...Fixed\n", "")
            return CompletedProcess(cmd, 0, "all passed\n", "")
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

    assert result is not None
    # Verify pre-commit was called twice (auto-fix + verify)
    pre_commit_calls = [c for c in call_log if c[0] == "pre-commit"]
    assert len(pre_commit_calls) == 2
    # Verify git add was called at least twice (initial + re-stage after pre-commit)
    git_add_calls = [c for c in call_log if c[:2] == ["git", "add"]]
    assert len(git_add_calls) >= 2


def test_apply_improvement_precommit_not_installed(
    loop_module,
    tmp_path: Path,
    monkeypatch,
):
    """When pre-commit is not installed, commit proceeds without it."""
    re_report = {
        "auto_review": {"score": 85},
        "final_review": {"score": 85, "findings": [], "improvement_items": []},
    }

    call_log = []

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess

        call_log.append(list(cmd))
        return CompletedProcess(cmd, 0, "", "")

    def fake_which(name):
        if name == "pre-commit":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    monkeypatch.setattr(loop_module.shutil, "which", fake_which)
    monkeypatch.setattr(loop_module, "check_existing_pr", lambda *a, **kw: False)
    monkeypatch.setattr(loop_module, "run_auto_score", lambda *a, **kw: re_report)

    report = {
        "auto_review": {"score": 70},
        "final_review": {"score": 70, "improvement_items": ["fix X"], "findings": []},
    }
    result = loop_module.apply_improvement(tmp_path, "test-skill", report, dry_run=False)

    assert result is not None
    # Verify pre-commit was never called
    pre_commit_calls = [c for c in call_log if c[0] == "pre-commit"]
    assert len(pre_commit_calls) == 0
    # Verify git commit was still called
    commit_calls = [c for c in call_log if c[:2] == ["git", "commit"]]
    assert len(commit_calls) == 1


def test_apply_improvement_noop_commit_rolls_back_without_error(
    loop_module,
    tmp_path: Path,
    monkeypatch,
):
    """No-op commit output (nothing to commit) should not be treated as hard failure."""
    from subprocess import CompletedProcess

    re_report = {
        "auto_review": {"score": 85},
        "final_review": {"score": 85, "findings": [], "improvement_items": []},
    }

    call_log = []

    def fake_run(cmd, **kwargs):
        cmd_list = list(cmd)
        call_log.append(cmd_list)
        if cmd_list[:2] == ["git", "commit"]:
            return CompletedProcess(
                cmd,
                1,
                "trim trailing whitespace...(no files to check)Skipped\n"
                "On branch skill-improvement/test\n"
                "nothing to commit, working tree clean\n",
                "",
            )
        return CompletedProcess(cmd, 0, "", "")

    def fake_which(name):
        if name == "pre-commit":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    monkeypatch.setattr(loop_module.shutil, "which", fake_which)
    monkeypatch.setattr(loop_module, "check_existing_pr", lambda *a, **kw: False)
    monkeypatch.setattr(loop_module, "run_auto_score", lambda *a, **kw: re_report)

    report = {
        "auto_review": {"score": 70},
        "final_review": {"score": 70, "improvement_items": ["fix X"], "findings": []},
    }
    result = loop_module.apply_improvement(tmp_path, "test-skill", report, dry_run=False)

    assert result is None
    push_calls = [c for c in call_log if c[:2] == ["git", "push"]]
    assert len(push_calls) == 0


def test_apply_improvement_precommit_unfixable_failure(
    loop_module,
    tmp_path: Path,
    monkeypatch,
):
    """When pre-commit fails on 2nd pass, rollback occurs."""
    re_report = {
        "auto_review": {"score": 85},
        "final_review": {"score": 85, "findings": [], "improvement_items": []},
    }

    call_log = []

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess

        cmd_list = list(cmd)
        call_log.append(cmd_list)

        # git diff --cached returns staged files
        if cmd_list[:3] == ["git", "diff", "--cached"]:
            return CompletedProcess(cmd, 0, "skills/test-skill/SKILL.md\n", "")
        # pre-commit always fails
        if cmd_list[0] == "pre-commit":
            return CompletedProcess(cmd, 1, "ERROR: unfixable\n", "")
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

    # Should return None due to rollback
    assert result is None
    # Verify no commit was made
    commit_calls = [c for c in call_log if c[:2] == ["git", "commit"]]
    assert len(commit_calls) == 0


# ── Code-faithfulness gate tests ──


def _setup_faithfulness_project(
    tmp_path: Path,
    skill_name: str,
    prereq_body: str,
    script_src: str = "",
    requires_python: str = ">=3.9",
    heading: str = "Prerequisites",
) -> Path:
    """Build a temp project: pyproject + one skill with a Prerequisites section."""
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nrequires-python = "{requires_python}"\n',
        encoding="utf-8",
    )
    skill_dir = tmp_path / "skills" / skill_name
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    skill_md = (
        f"---\nname: {skill_name}\ndescription: test\n---\n\n"
        f"# {skill_name}\n\n"
        f"## {heading}\n\n{prereq_body}\n\n"
        f"## Workflow\n\nDo the thing.\n"
    )
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    if script_src:
        (skill_dir / "scripts" / "run.py").write_text(script_src, encoding="utf-8")
    return tmp_path


def test_faithfulness_flags_unimported_library(loop_module, tmp_path: Path):
    """PR #164 case: `pandas` listed but no script imports it."""
    _setup_faithfulness_project(
        tmp_path,
        "uptrend",
        "- **Python 3.9+** with `pandas` and `requests` libraries",
        script_src="import requests\nimport csv\n",
    )
    violations = loop_module.check_prerequisites_faithfulness(tmp_path, "uptrend")
    assert any("pandas" in v for v in violations)
    assert not any("requests" in v for v in violations)  # requests IS imported


def test_faithfulness_passes_when_library_imported(loop_module, tmp_path: Path):
    _setup_faithfulness_project(
        tmp_path,
        "uptrend",
        "- **Python 3.9+** with the `requests` library (stdlib `csv`/`io` used)",
        script_src="import requests\nimport csv\nimport io\n",
    )
    assert loop_module.check_prerequisites_faithfulness(tmp_path, "uptrend") == []


def test_faithfulness_flags_python_floor_below_repo(loop_module, tmp_path: Path):
    """PR #164 case: `Python 3.8+` while repo requires >=3.9."""
    _setup_faithfulness_project(
        tmp_path,
        "uptrend",
        "- **Python 3.8+** with `requests`",
        script_src="import requests\n",
        requires_python=">=3.9",
    )
    violations = loop_module.check_prerequisites_faithfulness(tmp_path, "uptrend")
    assert any("3.8" in v and "3.9" in v for v in violations)


def test_faithfulness_passes_python_floor_at_repo(loop_module, tmp_path: Path):
    _setup_faithfulness_project(
        tmp_path,
        "uptrend",
        "- **Python 3.9+** with `requests`",
        script_src="import requests\n",
    )
    assert loop_module.check_prerequisites_faithfulness(tmp_path, "uptrend") == []


def test_faithfulness_passes_python_floor_above_repo(loop_module, tmp_path: Path):
    _setup_faithfulness_project(
        tmp_path,
        "uptrend",
        "- **Python 3.10+** with `requests`",
        script_src="import requests\n",
    )
    assert loop_module.check_prerequisites_faithfulness(tmp_path, "uptrend") == []


def test_faithfulness_skips_negated_library_mention(loop_module, tmp_path: Path):
    """A negated line such as "No `pandas` required" must not be flagged."""
    _setup_faithfulness_project(
        tmp_path,
        "uptrend",
        "- **Python 3.9+** with `requests`\n- No `pandas` dependency required",
        script_src="import requests\n",
    )
    assert loop_module.check_prerequisites_faithfulness(tmp_path, "uptrend") == []


def test_faithfulness_handles_version_pin(loop_module, tmp_path: Path):
    """`pandas>=2.0` strips the pin and still flags the unimported lib."""
    _setup_faithfulness_project(
        tmp_path,
        "uptrend",
        "- `pandas>=2.0`",
        script_src="import requests\n",
    )
    violations = loop_module.check_prerequisites_faithfulness(tmp_path, "uptrend")
    assert any("pandas" in v for v in violations)


def test_faithfulness_pyyaml_maps_to_yaml_import(loop_module, tmp_path: Path):
    """`PyYAML` is faithful when a script imports `yaml`."""
    _setup_faithfulness_project(
        tmp_path,
        "edge",
        "- **Python 3.9+** with `PyYAML` installed",
        script_src="import yaml\n",
    )
    assert loop_module.check_prerequisites_faithfulness(tmp_path, "edge") == []


def test_faithfulness_recognizes_input_requirements_alias(loop_module, tmp_path: Path):
    """The reviewer accepts `## Input Requirements` as the Prerequisites section."""
    _setup_faithfulness_project(
        tmp_path,
        "uptrend",
        "- **Python 3.9+** with `pandas`",
        script_src="import requests\n",
        heading="Input Requirements",
    )
    violations = loop_module.check_prerequisites_faithfulness(tmp_path, "uptrend")
    assert any("pandas" in v for v in violations)


def test_faithfulness_no_section_returns_empty(loop_module, tmp_path: Path):
    skill_dir = tmp_path / "skills" / "noprereq"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: noprereq\ndescription: t\n---\n# noprereq\n## Workflow\nx\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text('requires-python = ">=3.9"\n', encoding="utf-8")
    assert loop_module.check_prerequisites_faithfulness(tmp_path, "noprereq") == []


def test_faithfulness_missing_skill_returns_empty(loop_module, tmp_path: Path):
    assert loop_module.check_prerequisites_faithfulness(tmp_path, "ghost") == []


def test_faithfulness_section_stops_at_next_h2(loop_module, tmp_path: Path):
    """A library named in a LATER section must not be attributed to Prerequisites."""
    _setup_faithfulness_project(
        tmp_path,
        "uptrend",
        "- **Python 3.9+** with `requests`",
        script_src="import requests\n",
    )
    skill_md = tmp_path / "skills" / "uptrend" / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\n## Notes\n\nWe avoid `pandas` here.\n",
        encoding="utf-8",
    )
    assert loop_module.check_prerequisites_faithfulness(tmp_path, "uptrend") == []


def test_faithfulness_import_from_form_counts(loop_module, tmp_path: Path):
    """`from pandas import ...` also counts as importing pandas."""
    _setup_faithfulness_project(
        tmp_path,
        "uptrend",
        "- **Python 3.9+** with `pandas`",
        script_src="from pandas import DataFrame\n",
    )
    assert loop_module.check_prerequisites_faithfulness(tmp_path, "uptrend") == []


def test_faithfulness_lib_referenced_as_string_literal_is_faithful(loop_module, tmp_path: Path):
    """A lib used by name (lxml as a BeautifulSoup parser) is not flagged as unused."""
    _setup_faithfulness_project(
        tmp_path,
        "canslim",
        "- **Python 3.9+** with `beautifulsoup4` and `lxml`",
        script_src='from bs4 import BeautifulSoup\n\nsoup = BeautifulSoup("<p/>", "lxml")\n',
    )
    assert loop_module.check_prerequisites_faithfulness(tmp_path, "canslim") == []


def test_repo_python_floor_parses_pyproject(loop_module, tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.11"\n', encoding="utf-8"
    )
    assert loop_module._repo_python_floor(tmp_path) == (3, 11)


def test_repo_python_floor_missing_returns_none(loop_module, tmp_path: Path):
    assert loop_module._repo_python_floor(tmp_path) is None


def test_apply_improvement_blocks_newly_introduced_unfaithful_prereqs(
    loop_module, tmp_path: Path, monkeypatch
):
    """The gate rolls back an improvement that ADDS an unfaithful Prerequisites
    section (PR #164 scenario), even when the structural score improved."""
    # Pre-state: faithful Prerequisites (requests is imported, 3.9 floor).
    _setup_faithfulness_project(
        tmp_path,
        "test-skill",
        "- **Python 3.9+** with `requests`",
        script_src="import requests\n",
    )
    bad_md = (
        "---\nname: test-skill\ndescription: t\n---\n\n# test-skill\n\n"
        "## Prerequisites\n\n- **Python 3.8+** with `pandas` and `requests` libraries\n\n"
        "## Workflow\n\nx\n"
    )

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess

        if cmd and cmd[0] == "claude":  # simulate the LLM writing a bad section
            (tmp_path / "skills" / "test-skill" / "SKILL.md").write_text(bad_md, encoding="utf-8")
        return CompletedProcess(cmd, 0, "", "")

    rollback_called = []
    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    monkeypatch.setattr(loop_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(loop_module, "check_existing_pr", lambda *a, **kw: False)
    monkeypatch.setattr(
        loop_module,
        "run_auto_score",
        lambda *a, **kw: {
            "auto_review": {"score": 98},
            "final_review": {"score": 98, "findings": [], "improvement_items": []},
        },
    )
    monkeypatch.setattr(loop_module, "_rollback", lambda *a, **kw: rollback_called.append(True))

    report = {
        "auto_review": {"score": 81},
        "final_review": {"score": 81, "improvement_items": ["Add Prerequisites"], "findings": []},
    }
    result = loop_module.apply_improvement(tmp_path, "test-skill", report, dry_run=False)

    assert result is None, "Improvement introducing unfaithful Prereqs must be rolled back"
    assert rollback_called, "Gate must roll back on a new faithfulness violation"


def test_apply_improvement_allows_preexisting_unfaithful_prereqs(
    loop_module, tmp_path: Path, monkeypatch
):
    """A pre-existing unfaithful Prerequisites section must NOT block an unrelated
    improvement — the gate only fires on NEWLY introduced violations."""
    # Pre-state already has the debt (pandas listed, 3.8 floor); claude leaves it
    # untouched while addressing an unrelated finding.
    _setup_faithfulness_project(
        tmp_path,
        "test-skill",
        "- **Python 3.8+** with `pandas`",
        script_src="import requests\n",
    )

    def fake_run(cmd, **kwargs):
        from subprocess import CompletedProcess

        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    monkeypatch.setattr(loop_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(loop_module, "check_existing_pr", lambda *a, **kw: False)
    monkeypatch.setattr(
        loop_module,
        "run_auto_score",
        lambda *a, **kw: {
            "auto_review": {"score": 85},
            "final_review": {"score": 85, "findings": [], "improvement_items": []},
        },
    )

    report = {
        "auto_review": {"score": 70},
        "final_review": {"score": 70, "improvement_items": ["fix something else"], "findings": []},
    }
    result = loop_module.apply_improvement(tmp_path, "test-skill", report, dry_run=False)

    assert isinstance(result, dict), "Pre-existing debt must not block an unrelated improvement"
    assert result["auto_review"]["score"] == 85
