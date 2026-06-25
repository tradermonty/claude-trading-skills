"""Tests for the skill generation pipeline orchestrator."""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest
import yaml


@pytest.fixture(scope="module")
def pipeline_module():
    """Load run_skill_generation_pipeline.py as a module."""
    script_path = Path(__file__).resolve().parents[1] / "run_skill_generation_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_skill_generation_pipeline", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load run_skill_generation_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# -- Lock tests --


def test_acquire_lock_creates_file(pipeline_module, tmp_path: Path):
    assert pipeline_module.acquire_lock(tmp_path) is True
    lock_path = tmp_path / pipeline_module.LOCK_FILE
    assert lock_path.exists()
    assert lock_path.read_text().strip() == str(os.getpid())
    pipeline_module.release_lock(tmp_path)
    assert not lock_path.exists()


def test_acquire_lock_rejects_running_pid(pipeline_module, tmp_path: Path):
    lock_path = tmp_path / pipeline_module.LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()))  # Current PID is alive

    assert pipeline_module.acquire_lock(tmp_path) is False
    lock_path.unlink()


def test_acquire_lock_removes_stale(pipeline_module, tmp_path: Path):
    lock_path = tmp_path / pipeline_module.LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("999999999")  # Unlikely to be a real PID

    assert pipeline_module.acquire_lock(tmp_path) is True
    pipeline_module.release_lock(tmp_path)


# -- State tests --


def test_load_state_empty(pipeline_module, tmp_path: Path):
    state = pipeline_module.load_state(tmp_path)
    assert state == {"last_run": None, "history": []}


def test_save_and_load_state(pipeline_module, tmp_path: Path):
    state = {"last_run": "2026-03-01T00:00:00", "history": [{"mode": "weekly", "score_ok": True}]}
    pipeline_module.save_state(tmp_path, state)

    loaded = pipeline_module.load_state(tmp_path)
    assert loaded["last_run"] == "2026-03-01T00:00:00"
    assert loaded["history"][0]["mode"] == "weekly"


def test_save_state_trims_history(pipeline_module, tmp_path: Path):
    state = {
        "last_run": None,
        "history": [{"i": i} for i in range(100)],
    }
    pipeline_module.save_state(tmp_path, state)
    loaded = pipeline_module.load_state(tmp_path)
    assert len(loaded["history"]) == pipeline_module.HISTORY_LIMIT


# -- Safe dirty tree tests --


def test_is_safe_dirty_tree_reports_only(pipeline_module):
    """Tracked changes only under reports/ and logs/ are safe."""
    assert pipeline_module._is_safe_dirty_tree(" M reports/summary.md\n M logs/run.log\n") is True


def test_is_safe_dirty_tree_blocks_source_files(pipeline_module):
    """Tracked changes to source files are blocked."""
    assert pipeline_module._is_safe_dirty_tree(" M scripts/main.py\n") is False


def test_is_safe_dirty_tree_blocks_untracked(pipeline_module):
    """Untracked files are always blocked, even under reports/."""
    assert pipeline_module._is_safe_dirty_tree("?? reports/new.md\n") is False


def test_is_safe_dirty_tree_mixed(pipeline_module):
    """Mixed safe and unsafe files should block."""
    output = " M reports/summary.md\n M skills/foo/SKILL.md\n"
    assert pipeline_module._is_safe_dirty_tree(output) is False


def test_is_safe_dirty_tree_allows_untracked_state(pipeline_module):
    """Untracked files under state/ are allowed (new thesis files)."""
    assert pipeline_module._is_safe_dirty_tree("?? state/theses/new.yaml\n") is True


def test_is_safe_dirty_tree_allows_untracked_state_journal(pipeline_module):
    """Untracked files under state/journal/ are allowed."""
    assert pipeline_module._is_safe_dirty_tree("?? state/journal/pm_new.md\n") is True


def test_is_safe_dirty_tree_blocks_untracked_skills(pipeline_module):
    """Untracked files under skills/ are still blocked."""
    assert pipeline_module._is_safe_dirty_tree("?? skills/new/SKILL.md\n") is False


def test_is_safe_dirty_tree_allows_tracked_state(pipeline_module):
    """Tracked changes under state/ are allowed."""
    assert pipeline_module._is_safe_dirty_tree(" M state/theses/_index.json\n") is True


# -- Backlog tests --


def test_load_backlog_empty(pipeline_module, tmp_path: Path):
    backlog = pipeline_module.load_backlog(tmp_path)
    assert backlog == {"ideas": []}


def test_load_backlog_existing(pipeline_module, tmp_path: Path):
    backlog_path = tmp_path / pipeline_module.BACKLOG_FILE
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"ideas": [{"name": "test-idea", "score": 75}]}
    backlog_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    loaded = pipeline_module.load_backlog(tmp_path)
    assert len(loaded["ideas"]) == 1
    assert loaded["ideas"][0]["name"] == "test-idea"


def test_load_backlog_corrupt(pipeline_module, tmp_path: Path):
    backlog_path = tmp_path / pipeline_module.BACKLOG_FILE
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    backlog_path.write_text(":::\ninvalid: [yaml: {broken", encoding="utf-8")

    backlog = pipeline_module.load_backlog(tmp_path)
    assert backlog == {"ideas": []}


# -- Weekly flow tests --


def _setup_mine_script(tmp_path: Path, pipeline_module) -> None:
    """Create a dummy mine script that the pipeline can find."""
    mine_path = tmp_path / pipeline_module.MINE_SCRIPT
    mine_path.parent.mkdir(parents=True, exist_ok=True)
    mine_path.write_text("# placeholder", encoding="utf-8")


def _setup_score_script(tmp_path: Path, pipeline_module) -> None:
    """Create a dummy score script that the pipeline can find."""
    score_path = tmp_path / pipeline_module.SCORE_SCRIPT
    score_path.parent.mkdir(parents=True, exist_ok=True)
    score_path.write_text("# placeholder", encoding="utf-8")


def test_weekly_flow_success(pipeline_module, tmp_path: Path):
    """Mine + score succeed, summary written, state updated."""
    _setup_mine_script(tmp_path, pipeline_module)
    _setup_score_script(tmp_path, pipeline_module)

    # Create a candidates file that run_mine will find
    output_dir = tmp_path / pipeline_module.SUMMARY_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_file = output_dir / "raw_candidates_2026-03-01.yaml"
    candidates_file.write_text(
        yaml.safe_dump({"candidates": [{"name": "test-skill"}]}),
        encoding="utf-8",
    )

    # Create a backlog file for the summary
    backlog_path = tmp_path / pipeline_module.BACKLOG_FILE
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    backlog_path.write_text(
        yaml.safe_dump({"ideas": [{"title": "idea-1", "scores": {"composite": 80}}]}),
        encoding="utf-8",
    )

    def fake_run(cmd, **kwargs):
        return CompletedProcess(cmd, 0, "", "")

    with patch.object(pipeline_module.subprocess, "run", fake_run):
        rc = pipeline_module.run_weekly(tmp_path, dry_run=False)

    assert rc == 0

    # Summary file created
    summary_files = list((tmp_path / pipeline_module.SUMMARY_DIR).glob("*_summary.md"))
    assert len(summary_files) >= 1
    content = summary_files[0].read_text(encoding="utf-8")
    assert "Weekly Mining Summary" in content

    # State updated
    state = pipeline_module.load_state(tmp_path)
    assert len(state["history"]) >= 1
    assert state["history"][-1]["mode"] == "weekly"
    assert state["last_run"] is not None


def test_weekly_flow_mine_failure(pipeline_module, tmp_path: Path):
    """When mine fails, score is not called and run returns 1."""
    _setup_mine_script(tmp_path, pipeline_module)

    call_log = []

    def fake_run(cmd, **kwargs):
        call_log.append(list(cmd))
        # Mine script fails
        return CompletedProcess(cmd, 1, "", "mining error")

    with patch.object(pipeline_module.subprocess, "run", fake_run):
        rc = pipeline_module.run_weekly(tmp_path, dry_run=False)

    assert rc == 1

    # Score script should NOT have been called
    score_calls = [c for c in call_log if pipeline_module.SCORE_SCRIPT in " ".join(c)]
    assert len(score_calls) == 0


def test_weekly_flow_dry_run(pipeline_module, tmp_path: Path):
    """Dry run passes --dry-run to subscripts."""
    _setup_mine_script(tmp_path, pipeline_module)
    _setup_score_script(tmp_path, pipeline_module)

    # Create a candidates file
    output_dir = tmp_path / pipeline_module.SUMMARY_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_file = output_dir / "raw_candidates_2026-03-01.yaml"
    candidates_file.write_text(yaml.safe_dump({"candidates": []}), encoding="utf-8")

    call_log = []

    def fake_run(cmd, **kwargs):
        call_log.append(list(cmd))
        return CompletedProcess(cmd, 0, "", "")

    with patch.object(pipeline_module.subprocess, "run", fake_run):
        rc = pipeline_module.run_weekly(tmp_path, dry_run=True)

    assert rc == 0

    # Verify --dry-run was passed to both subscripts
    mine_calls = [c for c in call_log if pipeline_module.MINE_SCRIPT in " ".join(c)]
    assert len(mine_calls) == 1
    assert "--dry-run" in mine_calls[0]

    score_calls = [c for c in call_log if pipeline_module.SCORE_SCRIPT in " ".join(c)]
    assert len(score_calls) == 1
    assert "--dry-run" in score_calls[0]


def test_weekly_flow_lock_conflict(pipeline_module, tmp_path: Path):
    """When lock is held by another process, exits with 0."""
    lock_path = tmp_path / pipeline_module.LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()))  # Current PID holds lock

    rc = pipeline_module.run_weekly(tmp_path, dry_run=False)
    assert rc == 0

    lock_path.unlink()


# -- Summary tests --


def test_write_weekly_summary_creates(pipeline_module, tmp_path: Path):
    """Summary file is created with mining results."""
    candidates_path = tmp_path / "raw_candidates.yaml"
    candidates_path.write_text("dummy", encoding="utf-8")

    backlog = {
        "ideas": [
            {"title": "idea-a", "scores": {"composite": 90}},
            {"title": "idea-b", "scores": {"composite": 60}},
        ]
    }

    pipeline_module.write_weekly_summary(tmp_path, candidates_path, backlog)

    summary_dir = tmp_path / pipeline_module.SUMMARY_DIR
    files = list(summary_dir.glob("*_summary.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "Weekly Mining Summary" in content
    assert "Total backlog ideas: 2" in content
    assert "idea-a" in content


def test_write_weekly_summary_appends(pipeline_module, tmp_path: Path):
    """Second call appends to existing summary."""
    candidates_path = tmp_path / "raw_candidates.yaml"
    candidates_path.write_text("dummy", encoding="utf-8")

    backlog1 = {"ideas": [{"title": "idea-1", "scores": {"composite": 80}}]}
    backlog2 = {
        "ideas": [
            {"title": "idea-1", "scores": {"composite": 80}},
            {"title": "idea-2", "scores": {"composite": 70}},
        ]
    }

    pipeline_module.write_weekly_summary(tmp_path, candidates_path, backlog1)
    pipeline_module.write_weekly_summary(tmp_path, candidates_path, backlog2)

    summary_dir = tmp_path / pipeline_module.SUMMARY_DIR
    files = list(summary_dir.glob("*_summary.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert content.count("Weekly Mining Summary") == 2


# -- Log rotation test --


def test_run_weekly_score_failure(pipeline_module, tmp_path: Path):
    """When scoring fails, run_weekly returns 1 but still writes summary and state."""
    _setup_mine_script(tmp_path, pipeline_module)
    _setup_score_script(tmp_path, pipeline_module)

    # Create candidates file
    output_dir = tmp_path / pipeline_module.SUMMARY_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_file = output_dir / "raw_candidates_2026-03-01.yaml"
    candidates_file.write_text(
        yaml.safe_dump({"candidates": [{"name": "test-skill"}]}),
        encoding="utf-8",
    )

    # Create backlog
    backlog_path = tmp_path / pipeline_module.BACKLOG_FILE
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    backlog_path.write_text(
        yaml.safe_dump({"ideas": [{"title": "idea-1", "scores": {"composite": 80}}]}),
        encoding="utf-8",
    )

    call_count = [0]

    def fake_run(cmd, **kwargs):
        call_count[0] += 1
        cmd_str = " ".join(str(c) for c in cmd)
        # Score script fails
        if pipeline_module.SCORE_SCRIPT in cmd_str:
            return CompletedProcess(cmd, 1, "", "scoring error")
        return CompletedProcess(cmd, 0, "", "")

    with patch.object(pipeline_module.subprocess, "run", fake_run):
        rc = pipeline_module.run_weekly(tmp_path, dry_run=False)

    # Should return 1 due to scoring failure
    assert rc == 1

    # Summary file should still be created
    summary_files = list((tmp_path / pipeline_module.SUMMARY_DIR).glob("*_summary.md"))
    assert len(summary_files) >= 1

    # State should be updated with score_ok: False
    state = pipeline_module.load_state(tmp_path)
    assert len(state["history"]) >= 1
    assert state["history"][-1]["score_ok"] is False


def test_rotate_logs(pipeline_module, tmp_path: Path):
    """Old logs deleted, recent kept."""
    log_dir = tmp_path / pipeline_module.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create an "old" log file with mtime in the past
    old_log = log_dir / "old.log"
    old_log.write_text("old log content")
    old_time = time.time() - (60 * 86400)
    os.utime(old_log, (old_time, old_time))

    # Create a "new" log file
    new_log = log_dir / "new.log"
    new_log.write_text("new log content")

    pipeline_module.rotate_logs(tmp_path)

    assert not old_log.exists(), "Old log should have been removed"
    assert new_log.exists(), "New log should still exist"


# -- Daily flow: idea selection tests --


def _make_idea(
    id_: str = "raw_001",
    title: str = "test-skill",
    composite: float = 80,
    trading_value: float = 50,
    status: str = "pending",
    retry_count: int = 0,
) -> dict:
    """Helper to build an idea dict."""
    idea = {
        "id": id_,
        "title": title,
        "description": "A test skill description",
        "category": "testing",
        "scores": {"composite": composite, "trading_value": trading_value},
        "status": status,
    }
    if retry_count > 0:
        idea["retry_count"] = retry_count
    return idea


def test_select_next_idea_picks_highest(pipeline_module, tmp_path: Path):
    """Selects the highest composite score pending idea."""
    backlog = {
        "ideas": [
            _make_idea("a", "low", 40),
            _make_idea("b", "high", 90),
            _make_idea("c", "mid", 60),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result is not None
    assert result["id"] == "b"


def test_select_next_idea_skips_non_pending(pipeline_module, tmp_path: Path):
    """Completed, duplicate, and review_failed are not eligible."""
    backlog = {
        "ideas": [
            _make_idea("a", "completed-one", 90, status="completed"),
            _make_idea("b", "duplicate-one", 85, status="duplicate"),
            _make_idea("c", "review-failed", 80, status="review_failed"),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result is None


def test_select_next_idea_retries_design_failed(pipeline_module, tmp_path: Path):
    """design_failed with retry_count <= MAX_RETRIES is eligible."""
    backlog = {
        "ideas": [
            _make_idea("a", "design-failed-retry", 75, status="design_failed", retry_count=1),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result is not None
    assert result["id"] == "a"


def test_select_next_idea_retries_pr_failed(pipeline_module, tmp_path: Path):
    """pr_failed with retry_count <= MAX_RETRIES is eligible."""
    backlog = {
        "ideas": [
            _make_idea("a", "pr-failed-retry", 70, status="pr_failed", retry_count=0),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result is not None
    assert result["id"] == "a"


def test_select_next_idea_skips_review_failed(pipeline_module, tmp_path: Path):
    """review_failed is terminal (not retryable)."""
    backlog = {
        "ideas": [
            _make_idea("a", "review-failed", 80, status="review_failed"),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result is None


def test_select_next_idea_skips_exhausted_retry(pipeline_module, tmp_path: Path):
    """design_failed with retry_count > MAX_RETRIES is skipped."""
    backlog = {
        "ideas": [
            _make_idea("a", "exhausted", 90, status="design_failed", retry_count=2),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result is None


def test_select_next_idea_runtime_dedup(pipeline_module, tmp_path: Path):
    """Skips ideas whose skill directory already exists on disk."""
    # Create existing skill dir
    skill_dir = tmp_path / "skills" / "existing-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: existing-skill\n---\n")

    backlog = {
        "ideas": [
            _make_idea("a", "existing-skill", 90),
            _make_idea("b", "new-skill", 70),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result is not None
    assert result["id"] == "b"


def test_select_next_idea_empty_backlog(pipeline_module, tmp_path: Path):
    """Empty backlog returns None."""
    result = pipeline_module.select_next_idea({"ideas": []}, tmp_path)
    assert result is None


def test_select_next_idea_skips_low_trading_value(pipeline_module, tmp_path):
    """trading_value < MIN_TRADING_VALUE ideas are skipped."""
    backlog = {
        "ideas": [
            _make_idea(id_="low_tv", composite=90, trading_value=8),
            _make_idea(id_="high_tv", composite=60, trading_value=50),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result["id"] == "high_tv"


def test_select_next_idea_all_low_trading_value_returns_none(pipeline_module, tmp_path):
    """All ideas below trading_value threshold returns None."""
    backlog = {
        "ideas": [
            _make_idea(id_="low1", composite=90, trading_value=5),
            _make_idea(id_="low2", composite=80, trading_value=10),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result is None


def test_select_next_idea_skips_retryable_low_trading_value(pipeline_module, tmp_path):
    """Retryable ideas with low trading_value are also skipped."""
    backlog = {
        "ideas": [
            _make_idea(
                id_="retry_low", composite=35, trading_value=8, status="pr_failed", retry_count=1
            ),
            _make_idea(id_="pending_high", composite=60, trading_value=50),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result["id"] == "pending_high"


def test_select_next_idea_boundary_trading_value(pipeline_module, tmp_path):
    """trading_value == MIN_TRADING_VALUE is eligible (boundary check)."""
    backlog = {
        "ideas": [
            _make_idea(id_="boundary", composite=70, trading_value=15),
        ]
    }
    result = pipeline_module.select_next_idea(backlog, tmp_path)
    assert result["id"] == "boundary"


# -- Daily flow: idea_to_skill_name tests --


def test_idea_to_skill_name(pipeline_module):
    """Converts title to lowercase hyphenated name."""
    idea = {"title": "My New Skill!!", "id": "raw_001"}
    assert pipeline_module.idea_to_skill_name(idea) == "my-new-skill"


def test_idea_to_skill_name_unicode(pipeline_module):
    """Falls back to id if title produces no alpha chars."""
    idea = {"title": "日本語スキル", "id": "raw_unicode_001"}
    result = pipeline_module.idea_to_skill_name(idea)
    # Should fall back to id since Japanese chars are non-ascii/alpha
    assert "raw" in result or "unicode" in result


# -- Daily flow: integration tests --


def _setup_daily_backlog(tmp_path: Path, pipeline_module, ideas=None) -> None:
    """Create a backlog file with test ideas."""
    if ideas is None:
        ideas = [_make_idea("raw_001", "test-new-skill", 80)]
    backlog_path = tmp_path / pipeline_module.BACKLOG_FILE
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    backlog_path.write_text(yaml.safe_dump({"ideas": ideas}), encoding="utf-8")


def test_daily_flow_success(pipeline_module, tmp_path: Path):
    """Full daily flow: design, review, PR all succeed."""
    _setup_daily_backlog(tmp_path, pipeline_module)

    # Create design script placeholder
    design_path = tmp_path / pipeline_module.DESIGN_SCRIPT
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text("# placeholder", encoding="utf-8")

    call_log = []

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        call_log.append(cmd_str)

        # git status --porcelain (clean)
        if "status" in cmd_str and "--porcelain" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # git rev-parse (on main)
        if "rev-parse" in cmd_str:
            return CompletedProcess(cmd, 0, "main\n", "")
        # git pull
        if "pull" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # gh pr list (no existing PR)
        if "gh" in cmd_str and "pr" in cmd_str and "list" in cmd_str:
            return CompletedProcess(cmd, 0, "[]", "")
        # git branch -D (stale cleanup)
        if "branch" in cmd_str and "-D" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # git checkout -b
        if "checkout" in cmd_str and "-b" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # build_design_prompt
        if "build_design_prompt" in cmd_str:
            return CompletedProcess(cmd, 0, "design prompt text", "")
        # reviewer (auto score) — check before "claude -p" because the reviewer command's
        # --project-root path may contain "claude" and "--project-root" contains "-p"
        if "run_dual_axis_review" in cmd_str:
            # Create a report JSON
            report_dir = tmp_path / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report = {"auto_review": {"score": 85, "improvement_items": []}}
            report_path = report_dir / "skill_review_test-new-skill_2026.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            return CompletedProcess(cmd, 0, "", "")
        # claude -p (design step) - also create SKILL.md as side effect
        if "claude" in cmd_str and "-p" in cmd_str:
            skill_dir = tmp_path / "skills" / "test-new-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text("---\nname: test-new-skill\n---\n")
            return CompletedProcess(cmd, 0, "", "")
        # git diff / ls-files (no unexpected changes)
        if "diff" in cmd_str and "--name-only" in cmd_str and "HEAD" in cmd_str:
            return CompletedProcess(cmd, 0, "skills/test-new-skill/SKILL.md\n", "")
        if "ls-files" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # ruff
        if "ruff" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # git add
        if "git" in cmd_str and "add" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # git diff --cached (staged files)
        if "diff" in cmd_str and "--cached" in cmd_str:
            return CompletedProcess(cmd, 0, "skills/test-new-skill/SKILL.md\n", "")
        # git commit
        if "commit" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # git push
        if "push" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # gh pr create
        if "gh" in cmd_str and "pr" in cmd_str and "create" in cmd_str:
            return CompletedProcess(cmd, 0, "https://github.com/test/pr/1", "")
        # git checkout main
        if "checkout" in cmd_str and "main" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # gh pr view (cleanup)
        if "gh" in cmd_str and "pr" in cmd_str and "view" in cmd_str:
            return CompletedProcess(cmd, 1, "", "not found")
        # git branch --list
        if "branch" in cmd_str and "--list" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")

        return CompletedProcess(cmd, 0, "", "")

    import json

    with (
        patch.object(pipeline_module.subprocess, "run", fake_run),
        patch.object(pipeline_module.shutil, "which", return_value="/usr/bin/claude"),
    ):
        rc = pipeline_module.run_daily(tmp_path, dry_run=False)

    assert rc == 0

    # Backlog updated to completed
    backlog = pipeline_module.load_backlog(tmp_path)
    idea = backlog["ideas"][0]
    assert idea["status"] == "completed"
    assert idea["pr_url"] == "https://github.com/test/pr/1"

    # State updated
    state = pipeline_module.load_state(tmp_path)
    assert state["history"][-1]["mode"] == "daily"
    assert state["history"][-1]["pr_url"] == "https://github.com/test/pr/1"


def test_daily_flow_no_ideas(pipeline_module, tmp_path: Path):
    """Empty backlog returns 0 with no-op."""
    _setup_daily_backlog(tmp_path, pipeline_module, ideas=[])

    rc = pipeline_module.run_daily(tmp_path, dry_run=False)
    assert rc == 0

    state = pipeline_module.load_state(tmp_path)
    assert state["history"][-1]["idea"] is None


def test_daily_flow_design_failure_with_rollback(pipeline_module, tmp_path: Path):
    """Design failure triggers rollback and sets design_failed status."""
    _setup_daily_backlog(tmp_path, pipeline_module)

    design_path = tmp_path / pipeline_module.DESIGN_SCRIPT
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text("# placeholder", encoding="utf-8")

    rollback_calls = []

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)

        if "status" in cmd_str and "--porcelain" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "rev-parse" in cmd_str:
            return CompletedProcess(cmd, 0, "main\n", "")
        if "pull" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "gh" in cmd_str and "pr" in cmd_str and "list" in cmd_str:
            return CompletedProcess(cmd, 0, "[]", "")
        if "branch" in cmd_str and "-D" in cmd_str:
            rollback_calls.append("branch-D")
            return CompletedProcess(cmd, 0, "", "")
        if "checkout" in cmd_str and "-b" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "build_design_prompt" in cmd_str:
            return CompletedProcess(cmd, 0, "prompt", "")
        # claude -p fails (no SKILL.md created)
        if "claude" in cmd_str and "-p" in cmd_str:
            return CompletedProcess(cmd, 1, "", "design error")
        # rollback commands
        if "reset" in cmd_str:
            rollback_calls.append("reset")
            return CompletedProcess(cmd, 0, "", "")
        if "checkout" in cmd_str and "--" in cmd_str:
            rollback_calls.append("checkout-restore")
            return CompletedProcess(cmd, 0, "", "")
        if "clean" in cmd_str:
            rollback_calls.append("clean")
            return CompletedProcess(cmd, 0, "", "")
        if "checkout" in cmd_str and "main" in cmd_str:
            rollback_calls.append("checkout-main")
            return CompletedProcess(cmd, 0, "", "")

        return CompletedProcess(cmd, 0, "", "")

    with (
        patch.object(pipeline_module.subprocess, "run", fake_run),
        patch.object(pipeline_module.shutil, "which", return_value="/usr/bin/claude"),
    ):
        rc = pipeline_module.run_daily(tmp_path, dry_run=False)

    assert rc == 1

    # Rollback was called
    assert "reset" in rollback_calls
    assert "checkout-main" in rollback_calls

    # Backlog updated to design_failed with retry_count=1
    backlog = pipeline_module.load_backlog(tmp_path)
    idea = backlog["ideas"][0]
    assert idea["status"] == "design_failed"
    assert idea.get("retry_count", 0) == 1


def test_daily_flow_review_failure_terminal(pipeline_module, tmp_path: Path):
    """Review failure sets review_failed (terminal, no retry_count increment)."""
    _setup_daily_backlog(tmp_path, pipeline_module)

    design_path = tmp_path / pipeline_module.DESIGN_SCRIPT
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text("# placeholder", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)

        if "status" in cmd_str and "--porcelain" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "rev-parse" in cmd_str:
            return CompletedProcess(cmd, 0, "main\n", "")
        if "pull" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "gh" in cmd_str and "pr" in cmd_str and "list" in cmd_str:
            return CompletedProcess(cmd, 0, "[]", "")
        if "branch" in cmd_str and "-D" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "checkout" in cmd_str and "-b" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "build_design_prompt" in cmd_str:
            return CompletedProcess(cmd, 0, "prompt", "")
        if "claude" in cmd_str and "-p" in cmd_str:
            skill_dir = tmp_path / "skills" / "test-new-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text("---\nname: test-new-skill\n---\n")
            return CompletedProcess(cmd, 0, "", "")
        # git diff / ls-files (no unexpected changes)
        if "diff" in cmd_str and "--name-only" in cmd_str and "HEAD" in cmd_str:
            return CompletedProcess(cmd, 0, "skills/test-new-skill/SKILL.md\n", "")
        if "ls-files" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # reviewer returns low score
        if "run_dual_axis_review" in cmd_str:
            report_dir = tmp_path / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report = {"auto_review": {"score": 30, "improvement_items": ["fix this"]}}
            report_path = report_dir / "skill_review_test-new-skill_2026.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            return CompletedProcess(cmd, 0, "", "")
        # other git operations
        return CompletedProcess(cmd, 0, "", "")

    import json

    with (
        patch.object(pipeline_module.subprocess, "run", fake_run),
        patch.object(pipeline_module.shutil, "which", return_value="/usr/bin/claude"),
    ):
        rc = pipeline_module.run_daily(tmp_path, dry_run=False)

    assert rc == 1

    # review_failed is terminal
    backlog = pipeline_module.load_backlog(tmp_path)
    idea = backlog["ideas"][0]
    assert idea["status"] == "review_failed"
    # review_failed does NOT increment retry_count
    assert idea.get("retry_count", 0) == 0


def test_daily_flow_dry_run_no_side_effects(pipeline_module, tmp_path: Path):
    """Dry-run: no branch creation, no backlog changes, no file creation."""
    _setup_daily_backlog(tmp_path, pipeline_module)

    # Record original backlog
    original_backlog = pipeline_module.load_backlog(tmp_path)
    original_status = original_backlog["ideas"][0].get("status", "pending")

    rc = pipeline_module.run_daily(tmp_path, dry_run=True)
    assert rc == 0

    # Backlog unchanged
    new_backlog = pipeline_module.load_backlog(tmp_path)
    assert new_backlog["ideas"][0].get("status", "pending") == original_status

    # No skill directory created
    skill_dir = tmp_path / "skills" / "test-new-skill"
    assert not skill_dir.exists()

    # State recorded dry_run
    state = pipeline_module.load_state(tmp_path)
    assert state["history"][-1]["dry_run"] is True

    # Summary file has dry-run tag
    summary_files = list((tmp_path / pipeline_module.SUMMARY_DIR).glob("*_daily.md"))
    assert len(summary_files) >= 1
    content = summary_files[0].read_text(encoding="utf-8")
    assert "dry-run" in content


def test_daily_flow_lock_conflict(pipeline_module, tmp_path: Path):
    """Lock held by current process -> rc=0."""
    lock_path = tmp_path / pipeline_module.LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()))

    rc = pipeline_module.run_daily(tmp_path, dry_run=False)
    assert rc == 0

    lock_path.unlink()


def test_daily_flow_existing_pr(pipeline_module, tmp_path: Path):
    """Existing PR causes skip with rc=0."""
    _setup_daily_backlog(tmp_path, pipeline_module)

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)

        if "status" in cmd_str and "--porcelain" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "rev-parse" in cmd_str:
            return CompletedProcess(cmd, 0, "main\n", "")
        if "pull" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # gh pr list returns match
        if "gh" in cmd_str and "pr" in cmd_str and "list" in cmd_str:
            return CompletedProcess(
                cmd, 0, '[{"number": 42, "url": "https://github.com/test/repo/pull/42"}]', ""
            )

        return CompletedProcess(cmd, 0, "", "")

    with (
        patch.object(pipeline_module.subprocess, "run", fake_run),
        patch.object(pipeline_module.shutil, "which", return_value="/usr/bin/gh"),
    ):
        rc = pipeline_module.run_daily(tmp_path, dry_run=False)

    assert rc == 0


def test_daily_flow_stale_branch_cleaned(pipeline_module, tmp_path: Path):
    """Stale local branch is deleted before checkout -b."""
    _setup_daily_backlog(tmp_path, pipeline_module)

    branch_d_called = [False]

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)

        if "status" in cmd_str and "--porcelain" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "rev-parse" in cmd_str:
            return CompletedProcess(cmd, 0, "main\n", "")
        if "pull" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "gh" in cmd_str and "pr" in cmd_str and "list" in cmd_str:
            return CompletedProcess(cmd, 0, "[]", "")
        # branch -D is called before checkout -b
        if "branch" in cmd_str and "-D" in cmd_str and "skill-generation" in cmd_str:
            branch_d_called[0] = True
            return CompletedProcess(cmd, 0, "", "")
        if "checkout" in cmd_str and "-b" in cmd_str:
            assert branch_d_called[0], "branch -D should be called before checkout -b"
            return CompletedProcess(cmd, 0, "", "")
        if "build_design_prompt" in cmd_str:
            return CompletedProcess(cmd, 0, "prompt", "")
        # claude fails to avoid full flow
        if "claude" in cmd_str and "-p" in cmd_str:
            return CompletedProcess(cmd, 1, "", "error")
        return CompletedProcess(cmd, 0, "", "")

    design_path = tmp_path / pipeline_module.DESIGN_SCRIPT
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text("# placeholder", encoding="utf-8")

    with (
        patch.object(pipeline_module.subprocess, "run", fake_run),
        patch.object(pipeline_module.shutil, "which", return_value="/usr/bin/claude"),
    ):
        pipeline_module.run_daily(tmp_path, dry_run=False)

    assert branch_d_called[0]


# -- Daily flow: update_backlog_status tests --


def test_update_backlog_status_atomic_with_attempted_at(pipeline_module, tmp_path: Path):
    """Atomic update sets status, attempted_at, and retry_count."""
    _setup_daily_backlog(tmp_path, pipeline_module)

    pipeline_module.update_backlog_status(tmp_path, "raw_001", "design_failed")

    backlog = pipeline_module.load_backlog(tmp_path)
    idea = backlog["ideas"][0]
    assert idea["status"] == "design_failed"
    assert idea["attempted_at"] is not None
    assert idea["retry_count"] == 1


# -- Daily flow: review_and_improve tests --


def test_review_and_improve_final_with_tests(pipeline_module, tmp_path: Path):
    """Final scoring pass uses skip_tests=False."""
    skip_tests_values = []

    def fake_auto_score(project_root, skill_name, skip_tests=True):
        skip_tests_values.append(skip_tests)
        return {"auto_review": {"score": 85, "improvement_items": []}}

    with patch.object(pipeline_module, "run_auto_score", fake_auto_score):
        passed, report = pipeline_module.review_and_improve(tmp_path, "test-skill")

    assert passed is True
    # First call skip_tests=True, second call skip_tests=False (final verification)
    assert skip_tests_values == [True, False]


# -- Daily flow: _check_unexpected_changes tests --


def test_check_unexpected_changes_allows_reports(pipeline_module, tmp_path: Path):
    """Changes in reports/ are allowed."""

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "diff" in cmd_str and "--name-only" in cmd_str and "HEAD" in cmd_str:
            return CompletedProcess(
                cmd,
                0,
                "skills/my-skill/SKILL.md\nreports/skill_review_my-skill.json\n",
                "",
            )
        if "ls-files" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        return CompletedProcess(cmd, 0, "", "")

    with patch.object(pipeline_module.subprocess, "run", fake_run):
        result = pipeline_module._check_unexpected_changes(tmp_path, "my-skill")

    assert result is True


def test_check_unexpected_changes_detects_outside(pipeline_module, tmp_path: Path):
    """Changes outside allowed paths return False."""

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "diff" in cmd_str and "--name-only" in cmd_str and "HEAD" in cmd_str:
            return CompletedProcess(
                cmd,
                0,
                "skills/my-skill/SKILL.md\nscripts/some_other_file.py\n",
                "",
            )
        if "ls-files" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        return CompletedProcess(cmd, 0, "", "")

    with patch.object(pipeline_module.subprocess, "run", fake_run):
        result = pipeline_module._check_unexpected_changes(tmp_path, "my-skill")

    assert result is False


def test_check_unexpected_changes_allows_pyproject_and_docs(pipeline_module, tmp_path: Path):
    """pyproject.toml and docs/ changes are allowed."""

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "diff" in cmd_str and "--name-only" in cmd_str and "HEAD" in cmd_str:
            return CompletedProcess(
                cmd,
                0,
                "skills/my-skill/SKILL.md\npyproject.toml\n"
                "docs/en/skills/my-skill.md\ndocs/ja/skills/my-skill.md\n",
                "",
            )
        if "ls-files" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        return CompletedProcess(cmd, 0, "", "")

    with patch.object(pipeline_module.subprocess, "run", fake_run):
        result = pipeline_module._check_unexpected_changes(tmp_path, "my-skill")

    assert result is True


def test_check_unexpected_changes_blocks_other_skill_docs(pipeline_module, tmp_path: Path):
    """Doc changes for a DIFFERENT skill are blocked."""

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "diff" in cmd_str and "--name-only" in cmd_str and "HEAD" in cmd_str:
            return CompletedProcess(
                cmd,
                0,
                "skills/my-skill/SKILL.md\ndocs/en/skills/other-skill.md\n",
                "",
            )
        if "ls-files" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        return CompletedProcess(cmd, 0, "", "")

    with patch.object(pipeline_module.subprocess, "run", fake_run):
        result = pipeline_module._check_unexpected_changes(tmp_path, "my-skill")

    assert result is False


def test_extract_failed_hooks(pipeline_module):
    """_extract_failed_hooks parses pre-commit output correctly."""
    output = (
        "trailing-whitespace..................................................Passed\n"
        "ruff.................................................................Failed\n"
        "docs-completeness...................................................Failed\n"
        "codespell............................................................Passed\n"
    )
    result = pipeline_module._extract_failed_hooks(output)
    assert "ruff" in result
    assert "docs-completeness" in result
    assert "codespell" not in result


def test_extract_failed_hooks_multiword_name(pipeline_module):
    """Multi-word hook names are captured in full (not truncated to last word)."""
    output = "Detect absolute paths with usernames.................................Failed\n"
    result = pipeline_module._extract_failed_hooks(output)
    assert result == "Detect absolute paths with usernames"


def test_extract_failed_hooks_ignores_output_lines(pipeline_module):
    """Hook *output* lines that merely contain 'Failed' are not mistaken for hooks.

    Regression for the garbled "folder, only)" hook names seen in the logs: the
    status must sit immediately after the dot run, so prose containing 'Failed'
    elsewhere is ignored.
    """
    output = (
        "ruff.................................................................Failed\n"
        "  some check ran........ 2 files scanned, 0 Failed in folder, only staged\n"
    )
    result = pipeline_module._extract_failed_hooks(output)
    assert result == "ruff"


# -- Daily flow: existing PR sets pr_open --


def test_daily_flow_existing_pr_sets_pr_open(pipeline_module, tmp_path: Path):
    """Existing PR transitions backlog to pr_open."""
    _setup_daily_backlog(tmp_path, pipeline_module)

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)

        if "status" in cmd_str and "--porcelain" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "rev-parse" in cmd_str:
            return CompletedProcess(cmd, 0, "main\n", "")
        if "pull" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "gh" in cmd_str and "pr" in cmd_str and "list" in cmd_str:
            return CompletedProcess(
                cmd, 0, '[{"number": 99, "url": "https://github.com/test/repo/pull/99"}]', ""
            )
        return CompletedProcess(cmd, 0, "", "")

    with (
        patch.object(pipeline_module.subprocess, "run", fake_run),
        patch.object(pipeline_module.shutil, "which", return_value="/usr/bin/gh"),
    ):
        rc = pipeline_module.run_daily(tmp_path, dry_run=False)

    assert rc == 0

    # Backlog should be pr_open with URL
    backlog = pipeline_module.load_backlog(tmp_path)
    idea = backlog["ideas"][0]
    assert idea["status"] == "pr_open"
    assert idea["pr_url"] == "https://github.com/test/repo/pull/99"


# -- Daily flow: unexpected changes preserves branch --


def test_daily_flow_unexpected_changes_preserves_branch(pipeline_module, tmp_path: Path):
    """Unexpected changes: branch preserved, status=unexpected_changes, rc=1."""
    _setup_daily_backlog(tmp_path, pipeline_module)

    design_path = tmp_path / pipeline_module.DESIGN_SCRIPT
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text("# placeholder", encoding="utf-8")

    rollback_calls = []

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)

        if "status" in cmd_str and "--porcelain" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "rev-parse" in cmd_str:
            return CompletedProcess(cmd, 0, "main\n", "")
        if "pull" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "gh" in cmd_str and "pr" in cmd_str and "list" in cmd_str:
            return CompletedProcess(cmd, 0, "[]", "")
        if "branch" in cmd_str and "-D" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "checkout" in cmd_str and "-b" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        if "build_design_prompt" in cmd_str:
            return CompletedProcess(cmd, 0, "prompt", "")
        if "claude" in cmd_str and "-p" in cmd_str:
            skill_dir = tmp_path / "skills" / "test-new-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text("---\nname: test-new-skill\n---\n")
            return CompletedProcess(cmd, 0, "", "")
        # Report unexpected changes outside skill dir
        if "diff" in cmd_str and "--name-only" in cmd_str and "HEAD" in cmd_str:
            return CompletedProcess(
                cmd,
                0,
                "skills/test-new-skill/SKILL.md\nCLAUDE.md\n",
                "",
            )
        if "ls-files" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        # Track rollback calls (should NOT be called)
        if "reset" in cmd_str:
            rollback_calls.append("reset")
        if "checkout" in cmd_str and "main" in cmd_str:
            return CompletedProcess(cmd, 0, "", "")
        return CompletedProcess(cmd, 0, "", "")

    with (
        patch.object(pipeline_module.subprocess, "run", fake_run),
        patch.object(pipeline_module.shutil, "which", return_value="/usr/bin/claude"),
    ):
        rc = pipeline_module.run_daily(tmp_path, dry_run=False)

    assert rc == 1

    # Rollback should NOT be called (branch preserved for inspection)
    assert "reset" not in rollback_calls

    # Status should be unexpected_changes
    backlog = pipeline_module.load_backlog(tmp_path)
    idea = backlog["ideas"][0]
    assert idea["status"] == "unexpected_changes"


# -- Daily flow: write_daily_generation_summary test --


def test_write_daily_generation_summary(pipeline_module, tmp_path: Path):
    """Summary MD file is created with expected content."""
    idea = _make_idea("raw_001", "test-skill", 80)
    report = {"auto_review": {"score": 85}}
    pr_url = "https://github.com/test/pr/1"

    pipeline_module.write_daily_generation_summary(tmp_path, idea, "test-skill", report, pr_url)

    summary_files = list((tmp_path / pipeline_module.SUMMARY_DIR).glob("*_daily.md"))
    assert len(summary_files) == 1
    content = summary_files[0].read_text(encoding="utf-8")
    assert "test-skill" in content
    assert "85/100" in content
    assert pr_url in content


def test_write_daily_generation_summary_idea_none(pipeline_module, tmp_path: Path):
    """Summary handles idea=None without raising."""
    pipeline_module.write_daily_generation_summary(tmp_path, None, "unknown", None, None)

    summary_files = list((tmp_path / pipeline_module.SUMMARY_DIR).glob("*_daily.md"))
    assert len(summary_files) == 1
    content = summary_files[0].read_text(encoding="utf-8")
    assert "Idea: N/A" in content
    assert "unknown" in content


# -- register_testpaths tests --


def _make_pyproject(tmp_path: Path, existing_skills: list[str] | None = None) -> Path:
    """Create a minimal pyproject.toml with testpaths section."""
    entries = ""
    if existing_skills:
        for s in existing_skills:
            entries += f'    "skills/{s}/scripts/tests",\n'
    content = (
        "[tool.pytest.ini_options]\n"
        'addopts = "--import-mode=importlib"\n'
        "testpaths = [\n"
        f"{entries}"
        '    "scripts/tests",\n'
        "]\n"
    )
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(content)
    return pyproject


def test_register_testpaths_adds_entry(pipeline_module, tmp_path: Path):
    """New skill with test_*.py files gets registered in testpaths."""
    _make_pyproject(tmp_path)
    test_dir = tmp_path / "skills" / "new-skill" / "scripts" / "tests"
    test_dir.mkdir(parents=True)
    (test_dir / "test_example.py").write_text("def test_ok(): pass\n")

    result = pipeline_module.register_testpaths(tmp_path, "new-skill")

    assert result is True
    content = (tmp_path / "pyproject.toml").read_text()
    assert "skills/new-skill/scripts/tests" in content
    # Should appear before scripts/tests (the marker)
    assert content.index("new-skill") < content.index('"scripts/tests"')


def test_register_testpaths_idempotent(pipeline_module, tmp_path: Path):
    """Already registered skill returns False without modifying file."""
    _make_pyproject(tmp_path, existing_skills=["existing-skill"])
    test_dir = tmp_path / "skills" / "existing-skill" / "scripts" / "tests"
    test_dir.mkdir(parents=True)
    (test_dir / "test_example.py").write_text("def test_ok(): pass\n")

    result = pipeline_module.register_testpaths(tmp_path, "existing-skill")

    assert result is False


def test_register_testpaths_no_tests_dir(pipeline_module, tmp_path: Path):
    """Skill without tests/ directory returns False."""
    _make_pyproject(tmp_path)
    # Create skill dir but no tests subdir
    (tmp_path / "skills" / "no-tests" / "scripts").mkdir(parents=True)

    result = pipeline_module.register_testpaths(tmp_path, "no-tests")

    assert result is False


def test_register_testpaths_empty_tests_dir(pipeline_module, tmp_path: Path):
    """Skill with tests/ dir but no test_*.py files returns False."""
    _make_pyproject(tmp_path)
    test_dir = tmp_path / "skills" / "empty-tests" / "scripts" / "tests"
    test_dir.mkdir(parents=True)
    # Create non-test files only
    (test_dir / "conftest.py").write_text("# conftest\n")
    (test_dir / "helpers.py").write_text("# helpers\n")

    result = pipeline_module.register_testpaths(tmp_path, "empty-tests")

    assert result is False


def test_create_skill_pr_uses_unsafe_fixes(pipeline_module, tmp_path: Path):
    """Auto-fix must pass --unsafe-fixes so rules like UP007 are actually fixed."""
    call_log = []

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        call_log.append(cmd_str)
        if "diff" in cmd_str and "--cached" in cmd_str:
            return CompletedProcess(cmd, 0, "skills/x/SKILL.md\n", "")
        if "gh" in cmd_str and "pr" in cmd_str and "create" in cmd_str:
            return CompletedProcess(cmd, 0, "https://github.com/test/pr/9", "")
        return CompletedProcess(cmd, 0, "", "")

    # ruff + gh present; pre-commit absent so the verify loop is skipped.
    def fake_which(name):
        return None if name == "pre-commit" else f"/usr/bin/{name}"

    with (
        patch.object(pipeline_module.subprocess, "run", fake_run),
        patch.object(pipeline_module.shutil, "which", fake_which),
    ):
        pipeline_module.create_skill_pr(
            tmp_path, "x", {"id": "x", "title": "X"}, {"auto_review": {"score": 90}}, "feat/x"
        )

    assert any("ruff check --fix --unsafe-fixes" in c for c in call_log)


def test_rollback_restores_tracked_despite_untracked_pathspec(pipeline_module, tmp_path: Path):
    """A failed checkout of the untracked skill dir must not block other restores.

    Asserts the new per-path behavior: tracked paths (e.g. index.md) are still
    restored individually, and the final clean-tree assertion force-cleans any
    leftover (here index.md reported still dirty -> git restore issued).
    """
    call_log = []

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        call_log.append(cmd_str)
        # The brand-new untracked skill dir has no tracked version -> checkout fails.
        if cmd[:3] == ["git", "checkout", "--"] and cmd[-1] == "skills/x/":
            return CompletedProcess(cmd, 1, "", "error: pathspec 'skills/x/' did not match")
        # Clean-tree assertion: report index.md still dirty to exercise force-cleanup.
        if "status" in cmd_str and "--porcelain" in cmd_str:
            return CompletedProcess(cmd, 0, " M docs/en/skills/index.md\n", "")
        return CompletedProcess(cmd, 0, "", "")

    with patch.object(pipeline_module.subprocess, "run", fake_run):
        pipeline_module._rollback_skill(tmp_path, "x", "feat/x")

    # Per-path restore reached index.md even though skills/x/ checkout failed first.
    assert "git checkout -- docs/en/skills/index.md" in call_log
    # Final clean-tree assertion ran and force-restored the leftover tracked file.
    assert any("status --porcelain" in c for c in call_log)
    assert "git restore -- docs/en/skills/index.md" in call_log
