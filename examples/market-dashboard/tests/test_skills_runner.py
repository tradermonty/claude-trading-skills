# tests/test_skills_runner.py
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_run_skill_success_renames_to_fixed_path(tmp_path):
    """A successful run finds the newest timestamped JSON and renames it."""
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    # Pre-create a timestamped output file (simulating what the skill writes)
    ts_file = tmp_path / "ftd_detector_2026-03-20_120000.json"
    ts_file.write_text(json.dumps({"generated_at": "2026-03-20T12:00:00", "score": 42}))

    with patch("skills_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = runner.run_skill("ftd-detector")

    assert result is True
    fixed = tmp_path / "ftd-detector.json"
    assert fixed.exists()
    assert json.loads(fixed.read_text())["score"] == 42


def test_run_skill_failure_preserves_old_cache(tmp_path):
    """A failed run leaves the previous cache file intact."""
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    # Write existing cache
    old_cache = tmp_path / "ftd-detector.json"
    old_cache.write_text(json.dumps({"score": 99}))

    with patch("skills_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="FMP error")
        result = runner.run_skill("ftd-detector")

    assert result is False
    assert json.loads(old_cache.read_text())["score"] == 99  # unchanged


def test_run_skill_writes_stderr_log(tmp_path):
    """Stderr from a failed run is written to <skill>.stderr.log."""
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    with patch("skills_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="connection refused")
        runner.run_skill("ftd-detector")

    log = tmp_path / "ftd-detector.stderr.log"
    assert log.exists()
    assert "connection refused" in log.read_text()


def test_run_skill_substitutes_cache_dir_in_args(tmp_path):
    """Args containing {cache_dir} are substituted with the real cache path."""
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    with patch("skills_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        runner.run_skill("ftd-detector")

    call_args = mock_run.call_args[0][0]  # first positional arg = command list
    assert str(tmp_path) in call_args


def test_run_skill_no_script_returns_false(tmp_path):
    """Skills with script=None return False immediately (nothing to run)."""
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    result = runner.run_skill("market-news-analyst")
    assert result is False


def test_is_stale_returns_true_when_file_missing(tmp_path):
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))
    assert runner.is_stale("ftd-detector") is True


def test_is_stale_reads_generated_at_from_json(tmp_path):
    from skills_runner import SkillsRunner
    import datetime
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    cache = tmp_path / "ftd-detector.json"
    old_time = (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).isoformat()
    cache.write_text(json.dumps({"generated_at": old_time}))

    # cadence_min=30, threshold=60 min — 3h old is stale
    assert runner.is_stale("ftd-detector") is True


def test_is_stale_returns_false_for_fresh_file(tmp_path):
    from skills_runner import SkillsRunner
    import datetime
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    cache = tmp_path / "ftd-detector.json"
    now = datetime.datetime.utcnow().isoformat()
    cache.write_text(json.dumps({"generated_at": now}))

    assert runner.is_stale("ftd-detector") is False
