#!/usr/bin/env python3
"""Skill auto-generation pipeline orchestrator.

Mines session logs for skill ideas (weekly) and designs,
reviews, creates skills, and opens PRs (daily).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import yaml

logger = logging.getLogger("skill_generation")

# Script paths (relative to project root)
MINE_SCRIPT = "skills/skill-idea-miner/scripts/mine_session_logs.py"
SCORE_SCRIPT = "skills/skill-idea-miner/scripts/score_ideas.py"
DESIGN_SCRIPT = "skills/skill-designer/scripts/build_design_prompt.py"
REVIEWER_SCRIPT = "skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py"

# File paths (relative to project root)
LOCK_FILE = "logs/.skill_generation.lock"
STATE_FILE = "logs/.skill_generation_state.json"
BACKLOG_FILE = "logs/.skill_generation_backlog.yaml"
SUMMARY_DIR = "reports/skill-generation-log"
LOG_DIR = "logs"

# Limits
CLAUDE_TIMEOUT = 600
CLAUDE_BUDGET_MINE = 1.00
CLAUDE_BUDGET_SCORE = 0.50
HISTORY_LIMIT = 60
LOG_RETENTION_DAYS = 30

# Daily flow constants
DESIGN_SCORE_THRESHOLD = 70
MAX_DESIGN_ITERATIONS = 2  # initial review + 1 improvement pass
MAX_RETRIES = 1  # retry count for design_failed/pr_failed
MIN_TRADING_VALUE = 15  # skip ideas with trading_value below this threshold
CLAUDE_BUDGET_DESIGN = 3.00
CLAUDE_BUDGET_REVISE = 2.00
DESIGN_TIMEOUT = 1200


# -- Lock --


def acquire_lock(project_root: Path) -> bool:
    """Acquire a PID-based lock file. Returns True if acquired."""
    lock_path = project_root / LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text().strip())
            os.kill(old_pid, 0)
            logger.info("Another instance (PID %d) is running. Exiting.", old_pid)
            return False
        except (ValueError, OSError):
            logger.info("Stale lock found, removing.")
            lock_path.unlink(missing_ok=True)

    lock_path.write_text(str(os.getpid()))
    return True


def release_lock(project_root: Path) -> None:
    lock_path = project_root / LOCK_FILE
    lock_path.unlink(missing_ok=True)


# -- State management --


def load_state(project_root: Path) -> dict:
    state_path = project_root / STATE_FILE
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt state file, starting fresh.")
    return {"last_run": None, "history": []}


def save_state(project_root: Path, state: dict) -> None:
    state_path = project_root / STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["history"] = state["history"][-HISTORY_LIMIT:]
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


# -- Backlog --


def load_backlog(project_root: Path) -> dict:
    """Load the skill ideas backlog YAML. Returns empty structure if missing or corrupt."""
    backlog_path = project_root / BACKLOG_FILE
    if not backlog_path.exists():
        return {"ideas": []}
    try:
        data = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"ideas": []}
        return data
    except (yaml.YAMLError, OSError):
        logger.warning("Corrupt backlog file, returning empty.")
        return {"ideas": []}


# -- Mining --


def run_mine(project_root: Path, dry_run: bool = False) -> Path | None:
    """Execute mine_session_logs.py as subprocess.

    Returns path to raw_candidates.yaml on success, None on failure.
    """
    script = project_root / MINE_SCRIPT
    if not script.exists():
        logger.error("Mine script not found: %s", script)
        return None

    output_dir = project_root / SUMMARY_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(script),
        "--output-dir",
        str(output_dir),
    ]
    if dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=CLAUDE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.error("Mine script timed out after %d seconds.", CLAUDE_TIMEOUT)
        return None

    if result.returncode != 0:
        logger.error(
            "Mine script failed (rc=%d): %s", result.returncode, result.stderr.strip()[:500]
        )
        return None

    # Log mine script's stderr for diagnostics (warnings about LLM failures etc.)
    if result.stderr and result.stderr.strip():
        for line in result.stderr.strip().splitlines()[-5:]:
            logger.info("[mine] %s", line.strip())

    # Find the output file
    candidates_files = sorted(output_dir.glob("raw_candidates*.yaml"), reverse=True)
    if not candidates_files:
        # Also check for .yml extension
        candidates_files = sorted(output_dir.glob("raw_candidates*.yml"), reverse=True)
    if not candidates_files:
        logger.error("No raw_candidates file found after mining.")
        return None

    return candidates_files[0]


# -- Scoring --


def run_score(
    project_root: Path,
    candidates_path: Path,
    dry_run: bool = False,
) -> bool:
    """Execute score_ideas.py as subprocess. Returns True on success."""
    script = project_root / SCORE_SCRIPT
    if not script.exists():
        logger.error("Score script not found: %s", script)
        return False

    backlog_path = project_root / BACKLOG_FILE

    cmd = [
        sys.executable,
        str(script),
        "--candidates",
        str(candidates_path),
        "--project-root",
        str(project_root),
        "--backlog",
        str(backlog_path),
    ]
    if dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=CLAUDE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.error("Score script timed out after %d seconds.", CLAUDE_TIMEOUT)
        return False

    if result.returncode != 0:
        logger.error(
            "Score script failed (rc=%d): %s", result.returncode, result.stderr.strip()[:500]
        )
        return False

    # Log score script's stderr for diagnostics
    if result.stderr and result.stderr.strip():
        for line in result.stderr.strip().splitlines()[-5:]:
            logger.info("[score] %s", line.strip())

    return True


# -- Summary --


def write_weekly_summary(
    project_root: Path,
    candidates_path: Path | None,
    backlog: dict,
) -> None:
    """Write markdown summary to SUMMARY_DIR/YYYY-MM-DD_summary.md."""
    summary_dir = project_root / SUMMARY_DIR
    summary_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    summary_path = summary_dir / f"{today}_summary.md"

    ideas = backlog.get("ideas", [])
    total_ideas = len(ideas)

    # Top scored ideas (up to 5)
    sorted_ideas = sorted(
        ideas, key=lambda x: x.get("scores", {}).get("composite", 0), reverse=True
    )
    top_ideas = sorted_ideas[:5]

    entry = (
        f"\n## Weekly Mining Summary\n"
        f"- Date: {today}\n"
        f"- Candidates file: {candidates_path.name if candidates_path else 'N/A'}\n"
        f"- Total backlog ideas: {total_ideas}\n"
    )
    if top_ideas:
        entry += "- Top scored ideas:\n"
        for idea in top_ideas:
            name = idea.get("title", "unnamed")
            score = idea.get("scores", {}).get("composite", 0)
            entry += f"  - {name} (score: {score})\n"

    if summary_path.exists():
        existing = summary_path.read_text(encoding="utf-8")
        summary_path.write_text(existing + entry, encoding="utf-8")
    else:
        header = f"# Skill Generation Summary - {today}\n"
        summary_path.write_text(header + entry, encoding="utf-8")


# -- Log rotation --


def rotate_logs(project_root: Path) -> None:
    """Remove log files older than LOG_RETENTION_DAYS."""
    log_dir = project_root / LOG_DIR
    if not log_dir.is_dir():
        return
    cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    for f in log_dir.iterdir():
        if f.is_file() and f.suffix == ".log":
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    f.unlink()
                    logger.info("Rotated old log: %s", f.name)
            except OSError:
                pass


# -- Git safety --


_SAFE_DIRTY_PREFIXES = ("reports/", "logs/", "state/")

_GIT_NETWORK_RETRY_WAIT = 30
_GIT_NETWORK_MAX_RETRIES = 1


def _git_network_cmd_with_retry(
    cmd: list[str],
    cwd: Path,
    label: str,
) -> subprocess.CompletedProcess | None:
    """Run a git network command with retry on transient SSH/network errors.

    Returns the CompletedProcess on success, or None on final failure.
    """
    import time

    transient_patterns = [
        "ssh: connect to host",
        "Could not read from remote repository",
        "Connection refused",
        "Connection reset by peer",
        "Connection timed out",
    ]
    for attempt in range(_GIT_NETWORK_MAX_RETRIES + 1):
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result
        stderr = result.stderr.strip()
        is_transient = any(p in stderr for p in transient_patterns)
        if is_transient and attempt < _GIT_NETWORK_MAX_RETRIES:
            logger.warning(
                "%s failed (transient, attempt %d/%d): %s. Retrying in %ds.",
                label,
                attempt + 1,
                _GIT_NETWORK_MAX_RETRIES + 1,
                stderr[:200],
                _GIT_NETWORK_RETRY_WAIT,
            )
            time.sleep(_GIT_NETWORK_RETRY_WAIT)
            continue
        logger.error("%s failed: %s", label, stderr[:300])
        return None
    return None


def _is_safe_dirty_tree(porcelain_output: str) -> bool:
    """Return True when all dirty files are in safe (non-source) directories.

    Untracked files (??) are always blocked regardless of path.
    Tracked changes (M/A/D/R etc.) are allowed only under reports/ or logs/.
    """
    for line in porcelain_output.splitlines():
        if not line.strip():
            continue
        status_code = line[:2]
        filepath = line[3:].strip().split(" -> ")[-1]  # handle renames
        if status_code == "??":
            # Allow untracked files under state/ (new thesis/journal files)
            if not filepath.startswith("state/"):
                logger.warning("Blocked: untracked file: %s", filepath)
                return False
        elif not filepath.startswith(_SAFE_DIRTY_PREFIXES):
            logger.warning("Blocked: non-safe dirty file: %s", filepath)
            return False
    return True


def git_safe_check(project_root: Path) -> bool:
    """Verify working tree on main branch and pull latest.

    Allows tracked changes in reports/ and logs/ to avoid blocking the
    pipeline when only output files are dirty.
    """
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        if status.stdout.strip():
            if not _is_safe_dirty_tree(status.stdout):
                logger.error("Working tree has non-safe dirty files. Aborting.")
                return False
            logger.info(
                "Dirty tree contains only safe files, proceeding: %s",
                [line[3:].strip() for line in status.stdout.strip().splitlines()],
            )

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        if branch.stdout.strip() != "main":
            logger.error("Not on main branch (on '%s'). Aborting.", branch.stdout.strip())
            return False

        pull = _git_network_cmd_with_retry(
            ["git", "pull", "--ff-only"], cwd=project_root, label="git pull"
        )
        if pull is None:
            return False

    except FileNotFoundError:
        logger.error("git not found.")
        return False

    return True


# -- PR checks --


def check_existing_pr(project_root: Path, branch_name: str) -> str | None:
    """Check if an open PR already exists for this branch.

    Returns the PR URL if found, None otherwise.
    """
    if not shutil.which("gh"):
        return None
    result = subprocess.run(
        ["gh", "pr", "list", "--head", branch_name, "--state", "open", "--json", "number,url"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        prs = json.loads(result.stdout)
        if prs:
            url = prs[0].get("url")
            return url or None
        return None
    except json.JSONDecodeError:
        return None


# -- Branch cleanup --


def cleanup_merged_branches(project_root: Path, prefix: str = "skill-improvement/") -> None:
    """Delete local branches whose PRs are merged or closed."""
    if not shutil.which("gh"):
        return

    result = subprocess.run(
        ["git", "branch", "--list", f"{prefix}*"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return

    for line in result.stdout.strip().splitlines():
        branch = line.strip().lstrip("* ")
        if not branch:
            continue
        pr_state = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "state"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if pr_state.returncode != 0:
            continue
        try:
            data = json.loads(pr_state.stdout)
            state_val = data.get("state", "").upper()
            if state_val in ("MERGED", "CLOSED"):
                subprocess.run(
                    ["git", "branch", "-D", branch],
                    cwd=project_root,
                    capture_output=True,
                    check=False,
                )
                logger.info("Deleted merged/closed branch: %s", branch)
        except json.JSONDecodeError:
            pass


# -- Auto scoring --


def _build_reviewer_cmd(project_root: Path) -> list[str]:
    """Return command prefix for invoking the reviewer script."""
    if shutil.which("uv"):
        return ["uv", "run", "--extra", "dev", "python", str(project_root / REVIEWER_SCRIPT)]
    return [sys.executable, str(project_root / REVIEWER_SCRIPT)]


def run_auto_score(
    project_root: Path,
    skill_name: str,
    skip_tests: bool = True,
) -> dict | None:
    """Run the auto reviewer and return its JSON report."""
    script = str(project_root / REVIEWER_SCRIPT)
    extra_args: list[str] = [
        "--project-root",
        str(project_root),
        "--skill",
        skill_name,
        "--output-dir",
        "reports",
    ]
    if skip_tests:
        extra_args.append("--skip-tests")

    cmd = [*_build_reviewer_cmd(project_root), *extra_args]

    result = subprocess.run(
        cmd, cwd=project_root, capture_output=True, text=True, check=False, timeout=120
    )

    # Fallback: if uv failed, retry with sys.executable
    if result.returncode != 0 and cmd[0] == "uv":
        logger.warning("uv run failed for %s; falling back to %s.", skill_name, sys.executable)
        cmd = [sys.executable, script, *extra_args]
        result = subprocess.run(
            cmd, cwd=project_root, capture_output=True, text=True, check=False, timeout=120
        )

    if result.returncode != 0:
        logger.error("Auto score failed for %s: %s", skill_name, result.stderr.strip()[:500])
        return None

    report_files = sorted(
        (project_root / "reports").glob(f"skill_review_{skill_name}_*.json"), reverse=True
    )
    if not report_files:
        logger.error("No report JSON found for %s.", skill_name)
        return None

    return json.loads(report_files[0].read_text(encoding="utf-8"))


# -- Claude output helpers --


def _extract_json_from_claude(output: str, required_keys: list[str]) -> dict | None:
    """Extract JSON from claude CLI --output-format json envelope."""
    try:
        wrapper = json.loads(output)
        text = ""
        if isinstance(wrapper, dict):
            text = wrapper.get("result", "") or ""
            if not text:
                content = wrapper.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text += block.get("text", "")
        if not text:
            text = output
    except json.JSONDecodeError:
        text = output

    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        pos = text.find("{", idx)
        if pos == -1:
            break
        try:
            obj, _end_idx = decoder.raw_decode(text, pos)
            if isinstance(obj, dict) and any(k in obj for k in required_keys):
                return obj
            idx = pos + 1
        except json.JSONDecodeError:
            idx = pos + 1
    return None


def _is_nothing_to_commit_output(output: str) -> bool:
    """Return True when git commit output indicates no staged changes."""
    text = output.lower()
    return (
        "nothing to commit" in text
        or "no changes added to commit" in text
        or "nothing added to commit" in text
    )


def register_testpaths(project_root: Path, skill_name: str) -> bool:
    """Add skill test directory to pyproject.toml testpaths if tests exist.

    Returns True if pyproject.toml was modified, False otherwise.
    Skips if: no tests/ dir, no test_*.py files, or already registered.
    """
    test_dir = project_root / "skills" / skill_name / "scripts" / "tests"
    if not test_dir.is_dir():
        return False
    test_files = list(test_dir.glob("test_*.py"))
    if not test_files:
        return False
    pyproject = project_root / "pyproject.toml"
    content = pyproject.read_text()
    if f"skills/{skill_name}/scripts/tests" in content:
        return False
    marker = '    "scripts/tests",'
    if marker not in content:
        logger.warning("Cannot find testpaths marker in pyproject.toml")
        return False
    entry = f'    "skills/{skill_name}/scripts/tests",'
    content = content.replace(marker, f"{entry}\n{marker}")
    pyproject.write_text(content)
    return True


def _get_staged_files(project_root: Path, skill_name: str) -> list[str]:
    """Return list of staged files under the skill directory, docs, and pyproject.toml."""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--name-only",
            "--",
            f"skills/{skill_name}/",
            "pyproject.toml",
            f"docs/en/skills/{skill_name}.md",
            f"docs/ja/skills/{skill_name}.md",
            "docs/en/skills/index.md",
            "docs/ja/skills/index.md",
            "docs/en/skill-catalog.md",
            "docs/ja/skill-catalog.md",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]


def _extract_failed_hooks(output: str) -> str:
    """Extract hook names that show 'Failed' from pre-commit output."""
    failed = []
    for line in output.splitlines():
        # pre-commit output format: "hook-name...Failed" or "hook-name...Passed"
        if "Failed" in line:
            hook_name = line.split("...")[0].strip().split()[-1] if "..." in line else ""
            if hook_name:
                failed.append(hook_name)
    return ", ".join(failed) if failed else ""


# -- Daily flow: idea selection --


def idea_to_skill_name(idea: dict) -> str:
    """Convert an idea title to a normalized skill directory name."""
    title = idea.get("title", idea.get("id", "unnamed"))
    # Lowercase and replace non-alphanumeric with hyphens
    name = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not name or not any(c.isalpha() for c in name):
        # Fallback to idea id if title produces no alpha chars
        name = re.sub(r"[^a-z0-9]+", "-", idea.get("id", "unnamed").lower()).strip("-")
    return name or "unnamed-skill"


def select_next_idea(backlog: dict, project_root: Path) -> dict | None:
    """Pick the highest composite-score idea that is eligible for processing.

    Eligible = trading_value >= MIN_TRADING_VALUE AND
    (status is 'pending' OR (status in RETRYABLE and retry_count <= MAX_RETRIES)).
    Additionally, skip ideas whose skill directory already exists (runtime dedup).
    """
    RETRYABLE = {"design_failed", "pr_failed"}
    eligible = []
    for idea in backlog.get("ideas", []):
        status = idea.get("status", "pending")
        retry_count = idea.get("retry_count", 0)
        trading_value = idea.get("scores", {}).get("trading_value", 0)
        if trading_value < MIN_TRADING_VALUE:
            logger.info(
                "Skipping %s: trading_value=%s < %s",
                idea.get("id"),
                trading_value,
                MIN_TRADING_VALUE,
            )
            continue
        if status == "pending":
            eligible.append(idea)
        elif status in RETRYABLE and retry_count <= MAX_RETRIES:
            eligible.append(idea)

    if not eligible:
        return None

    # Sort: pending first, then retryable; within each group by composite score descending
    eligible.sort(
        key=lambda i: (
            0 if i.get("status", "pending") == "pending" else 1,
            -(i.get("scores", {}).get("composite", 0)),
        )
    )

    # Runtime dedup: skip ideas whose skill already exists on disk
    for idea in eligible:
        skill_name = idea_to_skill_name(idea)
        skill_dir = project_root / "skills" / skill_name
        if not (skill_dir / "SKILL.md").exists():
            return idea
        logger.info("Skipping '%s': skills/%s/ already exists.", idea.get("title"), skill_name)

    return None


# -- Daily flow: backlog updates --


def update_backlog_status(
    project_root: Path, idea_id: str, status: str, pr_url: str | None = None
) -> None:
    """Update the status of an idea in the backlog using atomic write."""
    backlog_path = project_root / BACKLOG_FILE
    backlog = load_backlog(project_root)

    for idea in backlog.get("ideas", []):
        if idea.get("id") == idea_id:
            idea["status"] = status
            idea["attempted_at"] = datetime.now().isoformat()
            if pr_url:
                idea["pr_url"] = pr_url
            # Increment retry_count for retryable failures
            if status in {"design_failed", "pr_failed"}:
                idea["retry_count"] = idea.get("retry_count", 0) + 1
            break

    # Atomic write: write to temp file then rename
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(backlog_path.parent), suffix=".yaml", prefix=".backlog_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(backlog, f, default_flow_style=False, allow_unicode=True)
        os.replace(tmp_path, str(backlog_path))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# -- Daily flow: unexpected changes check --


def _check_unexpected_changes(project_root: Path, skill_name: str) -> bool:
    """Check if files outside allowed paths were modified. Returns True if clean."""
    # Get all modified/untracked files
    diff_result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    ls_result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    all_changes = []
    if diff_result.stdout.strip():
        all_changes.extend(diff_result.stdout.strip().splitlines())
    if ls_result.stdout.strip():
        all_changes.extend(ls_result.stdout.strip().splitlines())

    if not all_changes:
        return True

    allowed_prefixes = [
        f"skills/{skill_name}/",
        "reports/",
    ]
    allowed_exact = [
        "pyproject.toml",
        f"docs/en/skills/{skill_name}.md",
        f"docs/ja/skills/{skill_name}.md",
        "docs/en/skills/index.md",
        "docs/ja/skills/index.md",
        "docs/en/skill-catalog.md",
        "docs/ja/skill-catalog.md",
    ]
    unexpected = [
        f.strip()
        for f in all_changes
        if f.strip()
        and not any(f.strip().startswith(p) for p in allowed_prefixes)
        and f.strip() not in allowed_exact
    ]

    if unexpected:
        logger.error(
            "Unexpected file changes outside allowed paths: %s",
            unexpected[:5],
        )
        return False
    return True


# -- Daily flow: design and improve --


def design_skill(project_root: Path, idea: dict, skill_name: str, dry_run: bool = False) -> bool:
    """Build design prompt and invoke claude -p to create the skill.

    Returns True on success (SKILL.md exists), False on failure.
    """
    if dry_run:
        logger.info("[dry-run] Would design skill '%s'.", skill_name)
        return True

    if not shutil.which("claude"):
        logger.error("claude CLI not found; cannot design skill.")
        return False

    design_script = project_root / DESIGN_SCRIPT
    if not design_script.exists():
        logger.error("Design script not found: %s", design_script)
        return False

    # Write idea JSON to temp file
    fd, idea_json_path = tempfile.mkstemp(suffix=".json", prefix="idea_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(idea, f)

        # Build the design prompt
        prompt_result = subprocess.run(
            [
                sys.executable,
                str(design_script),
                "--idea-json",
                idea_json_path,
                "--skill-name",
                skill_name,
                "--project-root",
                str(project_root),
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if prompt_result.returncode != 0:
            logger.error("build_design_prompt failed: %s", prompt_result.stderr.strip()[:300])
            return False

        prompt_text = prompt_result.stdout
        if not prompt_text.strip():
            logger.error("build_design_prompt produced empty output.")
            return False

        # Invoke claude -p with the design prompt
        # Remove CLAUDECODE env var to allow claude -p from within Claude Code terminals
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            [
                "claude",
                "-p",
                "--allowedTools",
                "Read,Edit,Write,Glob,Grep",
                f"--max-budget-usd={CLAUDE_BUDGET_DESIGN}",
            ],
            input=prompt_text,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=DESIGN_TIMEOUT,
            env=env,
        )
        if result.returncode != 0:
            logger.error("claude -p design failed: %s", result.stderr.strip()[:300])
            return False

        # Gap A: Verify SKILL.md was actually created
        skill_md = project_root / "skills" / skill_name / "SKILL.md"
        if not skill_md.exists():
            logger.error("claude -p exited 0 but SKILL.md not created at %s.", skill_md)
            return False

        return True

    except subprocess.TimeoutExpired:
        logger.error("Design step timed out after %d seconds.", DESIGN_TIMEOUT)
        return False
    finally:
        try:
            os.unlink(idea_json_path)
        except OSError:
            pass


def improve_skill(project_root: Path, skill_name: str, findings: list[str]) -> bool:
    """Invoke claude -p to improve a skill based on review findings.

    Returns True on success, False on failure.
    """
    if not shutil.which("claude"):
        logger.error("claude CLI not found; cannot improve skill.")
        return False

    prompt = (
        f"Improve the skill '{skill_name}' in skills/{skill_name}/ based on these findings:\n\n"
        + "\n".join(f"- {item}" for item in findings[:10])
        + "\n\nMake minimal, targeted edits to address the findings. Do not change unrelated code."
    )

    try:
        # Remove CLAUDECODE env var to allow claude -p from within Claude Code terminals
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            [
                "claude",
                "-p",
                "--allowedTools",
                "Read,Edit,Write,Glob,Grep",
                f"--max-budget-usd={CLAUDE_BUDGET_REVISE}",
            ],
            input=prompt,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=DESIGN_TIMEOUT,
            env=env,
        )
        if result.returncode != 0:
            logger.error("claude -p improve failed: %s", result.stderr.strip()[:300])
            return False
        return True

    except subprocess.TimeoutExpired:
        logger.error("Improve step timed out after %d seconds.", DESIGN_TIMEOUT)
        return False


# -- Daily flow: review and improve loop --


def review_and_improve(
    project_root: Path, skill_name: str, dry_run: bool = False
) -> tuple[bool, dict | None]:
    """Score the skill, optionally improve, and return (passed, report).

    Iteration 0: score with skip_tests=True
      >= threshold: final score with skip_tests=False
      < threshold: improve, then iteration 1
    Iteration 1 (final): score with skip_tests=False
      >= threshold: pass
      < threshold: fail
    """
    if dry_run:
        return True, None

    for iteration in range(MAX_DESIGN_ITERATIONS):
        is_final = iteration == MAX_DESIGN_ITERATIONS - 1
        skip_tests = not is_final and iteration == 0

        report = run_auto_score(project_root, skill_name, skip_tests=skip_tests)
        if not report:
            logger.error("Auto scoring failed on iteration %d.", iteration)
            return False, None

        score = report.get("auto_review", {}).get("score", 0)
        logger.info(
            "Review iteration %d: score=%d (threshold=%d, skip_tests=%s).",
            iteration,
            score,
            DESIGN_SCORE_THRESHOLD,
            skip_tests,
        )

        if score >= DESIGN_SCORE_THRESHOLD:
            if skip_tests:
                # Run final pass with tests enabled
                final_report = run_auto_score(project_root, skill_name, skip_tests=False)
                if final_report:
                    final_score = final_report.get("auto_review", {}).get("score", 0)
                    if final_score >= DESIGN_SCORE_THRESHOLD:
                        return True, final_report
                    # Final with tests failed; try improvement
                    report = final_report
                    score = final_score
                else:
                    return False, report
            else:
                return True, report

        # Below threshold: attempt improvement (not on final iteration)
        if is_final:
            logger.warning(
                "Final iteration score %d below threshold %d.", score, DESIGN_SCORE_THRESHOLD
            )
            return False, report

        # Extract improvement items
        findings = report.get("auto_review", {}).get("improvement_items", [])
        if not findings:
            findings = [f"Score {score} below {DESIGN_SCORE_THRESHOLD}; improve skill quality."]

        ok = improve_skill(project_root, skill_name, findings)
        if not ok:
            return False, report

        # Check for unexpected changes after improvement
        if not _check_unexpected_changes(project_root, skill_name):
            return False, report

    return False, None


# -- Daily flow: rollback --


def _rollback_skill(project_root: Path, skill_name: str, branch_name: str) -> None:
    """Roll back ALL changes and return to main."""
    rollback_paths = [
        f"skills/{skill_name}/",
        "pyproject.toml",
        f"docs/en/skills/{skill_name}.md",
        f"docs/ja/skills/{skill_name}.md",
        "docs/en/skills/index.md",
        "docs/ja/skills/index.md",
        "docs/en/skill-catalog.md",
        "docs/ja/skill-catalog.md",
    ]
    # Unstage any staged changes
    subprocess.run(
        ["git", "reset", "HEAD", "--"] + rollback_paths,
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    # Restore modified tracked files
    restore = subprocess.run(
        ["git", "checkout", "--"] + rollback_paths,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    # Fallback: git restore for files that git checkout missed
    if restore.returncode != 0:
        logger.info("git checkout restore failed; trying git restore fallback.")
        subprocess.run(
            ["git", "restore", "--"] + rollback_paths,
            cwd=project_root,
            capture_output=True,
            check=False,
        )
    # Remove untracked files/dirs under the skill and generated docs
    for clean_path in [
        f"skills/{skill_name}/",
        f"docs/en/skills/{skill_name}.md",
        f"docs/ja/skills/{skill_name}.md",
    ]:
        subprocess.run(
            ["git", "clean", "-fd", clean_path],
            cwd=project_root,
            capture_output=True,
            check=False,
        )
    # Verify pyproject.toml is clean
    verify = subprocess.run(
        ["git", "diff", "--name-only", "--", "pyproject.toml"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if verify.stdout.strip():
        logger.warning("pyproject.toml still dirty after rollback; forcing restore.")
        subprocess.run(
            ["git", "restore", "pyproject.toml"],
            cwd=project_root,
            capture_output=True,
            check=False,
        )
    # Return to main
    subprocess.run(
        ["git", "checkout", "main"],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    # Delete the feature branch
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        cwd=project_root,
        capture_output=True,
        check=False,
    )


# -- Daily flow: PR creation --


def create_skill_pr(
    project_root: Path,
    skill_name: str,
    idea: dict,
    report: dict | None,
    branch_name: str,
) -> str | None:
    """Lint, commit, push, and create a PR. Returns PR URL or None."""
    if not shutil.which("gh"):
        logger.error("gh CLI not found; cannot create PR.")
        return None
    # Auto-fix lint issues
    if shutil.which("ruff"):
        subprocess.run(
            ["ruff", "check", "--fix", f"skills/{skill_name}/"],
            cwd=project_root,
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["ruff", "format", f"skills/{skill_name}/"],
            cwd=project_root,
            capture_output=True,
            check=False,
        )

    # Register testpaths if tests exist
    testpaths_modified = register_testpaths(project_root, skill_name)
    if testpaths_modified:
        logger.info("Registered %s in pyproject.toml testpaths", skill_name)

    # Stage files (skill dir + pyproject.toml if modified)
    stage_paths = [f"skills/{skill_name}/"]
    if testpaths_modified:
        stage_paths.append("pyproject.toml")
    result = subprocess.run(
        ["git", "add"] + stage_paths,
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("git add failed: %s", result.stderr.strip()[:300])
        return None

    # Generate doc pages (satisfies docs-completeness hook)
    doc_gen_script = project_root / "scripts" / "generate_skill_docs.py"
    if doc_gen_script.exists():
        doc_result = subprocess.run(
            [sys.executable, str(doc_gen_script), "--skill", skill_name],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if doc_result.returncode == 0:
            # Stage generated doc files
            doc_paths = [f"docs/en/skills/{skill_name}.md", f"docs/ja/skills/{skill_name}.md"]
            for dp in doc_paths:
                if (project_root / dp).exists():
                    stage_paths.append(dp)
            # Also stage updated index and catalog files
            for idx in [
                "docs/en/skills/index.md",
                "docs/ja/skills/index.md",
                "docs/en/skill-catalog.md",
                "docs/ja/skill-catalog.md",
            ]:
                if (project_root / idx).exists():
                    stage_paths.append(idx)
            subprocess.run(
                ["git", "add"] + stage_paths,
                cwd=project_root,
                capture_output=True,
                check=False,
            )
            logger.info("Generated and staged doc pages for %s.", skill_name)
        else:
            logger.warning(
                "generate_skill_docs.py failed (non-fatal): %s",
                doc_result.stderr.strip()[:200],
            )

    # Run pre-commit hooks (up to 3 fix-and-restage cycles)
    max_precommit_attempts = 3
    if shutil.which("pre-commit"):
        for attempt in range(1, max_precommit_attempts + 1):
            staged = _get_staged_files(project_root, skill_name)
            if not staged:
                break
            pc_result = subprocess.run(
                ["pre-commit", "run", "--files"] + staged,
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if pc_result.returncode == 0:
                break
            # Log which hooks failed for debugging
            pc_output = (pc_result.stdout or "") + "\n" + (pc_result.stderr or "")
            failed_hooks = _extract_failed_hooks(pc_output)
            logger.info(
                "pre-commit attempt %d/%d failed (hooks: %s); re-staging.",
                attempt,
                max_precommit_attempts,
                failed_hooks or "unknown",
            )
            if attempt == max_precommit_attempts:
                logger.error(
                    "pre-commit still failing after %d attempts. Failed hooks: %s. Output: %s",
                    max_precommit_attempts,
                    failed_hooks,
                    pc_output.strip()[:500],
                )
                return None
            restage = subprocess.run(
                ["git", "add"] + stage_paths,
                cwd=project_root,
                check=False,
                capture_output=True,
                text=True,
            )
            if restage.returncode != 0:
                logger.error("git re-add failed: %s", restage.stderr.strip()[:300])
                return None

    score = 0
    if report:
        score = report.get("auto_review", {}).get("score", 0)

    commit_msg = f"Add {skill_name} skill (auto-generated, score {score})"
    commit = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        commit_output = ((commit.stderr or "") + "\n" + (commit.stdout or "")).strip()
        if _is_nothing_to_commit_output(commit_output):
            logger.info("No staged changes to commit for %s.", skill_name)
            return None
        logger.error("git commit failed: %s", commit_output[:500])
        return None

    push = _git_network_cmd_with_retry(
        ["git", "push", "-u", "origin", branch_name],
        cwd=project_root,
        label="git push",
    )
    if push is None:
        return None

    title_text = idea.get("title", skill_name)
    pr_body = (
        f"## Summary\n"
        f"- Skill: `{skill_name}`\n"
        f"- Idea: {title_text}\n"
        f"- Auto-review score: {score}/100\n\n"
        f"## Description\n"
        f"{idea.get('description', 'N/A')}\n\n"
        f"## Post-merge TODO\n"
        f"- [ ] Add skill to README.md and README.ja.md\n"
        f"- [ ] Update CLAUDE.md if needed\n"
        f"- [ ] Confirm testpaths entry is correct if tests were skipped\n\n"
        f"Generated by skill auto-generation pipeline."
    )
    pr = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--head",
            branch_name,
            "--title",
            f"Add {skill_name} skill (auto-generated)",
            "--body",
            pr_body,
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if pr.returncode != 0:
        logger.error("gh pr create failed: %s", pr.stderr.strip()[:300])
        return None

    pr_url = pr.stdout.strip()
    # Gap B: verify URL
    if not pr_url.startswith("http"):
        logger.warning("gh pr create output is not a URL: %s", pr_url[:200])
        return None

    return pr_url


# -- Daily flow: summary --


def write_daily_generation_summary(
    project_root: Path,
    idea: dict | None,
    skill_name: str,
    report: dict | None,
    pr_url: str | None,
    dry_run: bool = False,
) -> None:
    """Write markdown summary for daily generation run."""
    summary_dir = project_root / SUMMARY_DIR
    summary_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    summary_path = summary_dir / f"{today}_daily.md"

    score = 0
    if report:
        score = report.get("auto_review", {}).get("score", 0)

    idea_title = idea.get("title", "N/A") if idea else "N/A"
    dry_tag = " (dry-run)" if dry_run else ""
    entry = (
        f"\n## Daily Generation{dry_tag}\n"
        f"- Date: {today}\n"
        f"- Idea: {idea_title}\n"
        f"- Skill: {skill_name}\n"
        f"- Score: {score}/100\n"
        f"- PR: {pr_url or 'N/A'}\n"
    )

    if summary_path.exists():
        existing = summary_path.read_text(encoding="utf-8")
        summary_path.write_text(existing + entry, encoding="utf-8")
    else:
        header = f"# Skill Generation Daily Summary - {today}\n"
        summary_path.write_text(header + entry, encoding="utf-8")


def _record_daily_state(
    project_root: Path,
    idea: dict | None,
    skill_name: str | None,
    idea_id: str | None,
    score: int,
    pr_url: str | None,
    outcome: str,
    dry_run: bool = False,
) -> None:
    """Record state and summary for any daily flow exit path (success or failure)."""
    try:
        write_daily_generation_summary(
            project_root, idea, skill_name or "unknown", None, pr_url, dry_run=dry_run
        )
    except Exception:
        logger.warning("Failed to write daily summary.", exc_info=True)

    try:
        state = load_state(project_root)
        state["last_run"] = datetime.now().isoformat()
        state["history"].append(
            {
                "mode": "daily",
                "idea": idea.get("title") if idea else None,
                "idea_id": idea_id,
                "skill": skill_name,
                "score": score,
                "pr_url": pr_url,
                "outcome": outcome,
                "dry_run": dry_run,
                "timestamp": datetime.now().isoformat(),
            }
        )
        save_state(project_root, state)
    except Exception:
        logger.warning("Failed to save daily state.", exc_info=True)


# -- Daily flow: main orchestrator --


def run_daily(project_root: Path, dry_run: bool = False) -> int:
    """Main daily flow: select idea, design skill, review, improve, create PR.

    Returns 0 on success (or no-op), 1 on failure.
    """
    log_dir = project_root / LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "skill_generation.log"),
        ],
    )

    if not acquire_lock(project_root):
        return 0

    created_branch = False

    try:
        # Select idea (read-only, safe for dry-run)
        backlog = load_backlog(project_root)
        idea = select_next_idea(backlog, project_root)
        if not idea:
            logger.info("No eligible ideas in backlog.")
            _record_daily_state(
                project_root,
                idea=None,
                skill_name=None,
                idea_id=None,
                score=0,
                pr_url=None,
                outcome="no_ideas",
                dry_run=dry_run,
            )
            return 0

        skill_name = idea_to_skill_name(idea)
        idea_id = idea.get("id", "unknown")
        logger.info(
            "Selected: %s (id=%s) -> skill: %s",
            idea.get("title"),
            idea_id,
            skill_name,
        )

        if dry_run:
            logger.info(
                "[dry-run] Would design skill '%s' from idea '%s'.",
                skill_name,
                idea.get("title"),
            )
            _record_daily_state(
                project_root,
                idea=idea,
                skill_name=skill_name,
                idea_id=idea_id,
                score=0,
                pr_url=None,
                outcome="dry_run",
                dry_run=True,
            )
            return 0

        # Non-dry-run: full flow
        if not git_safe_check(project_root):
            _record_daily_state(
                project_root, idea, skill_name, idea_id, 0, None, "git_check_failed"
            )
            return 1

        branch_name = f"skill-generation/{idea_id}-{skill_name}"

        # Fix V3#1: existing PR -> mark as pr_open
        existing_pr_url = check_existing_pr(project_root, branch_name)
        if existing_pr_url is not None:
            logger.info("Open PR already exists for %s: %s", branch_name, existing_pr_url)
            update_backlog_status(project_root, idea_id, "pr_open", pr_url=existing_pr_url)
            _record_daily_state(
                project_root, idea, skill_name, idea_id, 0, existing_pr_url, "pr_already_open"
            )
            return 0

        # Fix #3: delete stale local branch if present
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=project_root,
            capture_output=True,
            check=False,
        )

        # Create branch
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.error("git checkout -b failed: %s", result.stderr.strip()[:200])
            _record_daily_state(
                project_root, idea, skill_name, idea_id, 0, None, "branch_create_failed"
            )
            return 1

        created_branch = True

        # Step 10: Design the skill
        if not design_skill(project_root, idea, skill_name):
            _rollback_skill(project_root, skill_name, branch_name)
            created_branch = False
            update_backlog_status(project_root, idea_id, "design_failed")
            _record_daily_state(project_root, idea, skill_name, idea_id, 0, None, "design_failed")
            return 1

        # Step 11: Check for unexpected changes
        if not _check_unexpected_changes(project_root, skill_name):
            logger.error(
                "Unexpected changes detected. Branch '%s' preserved for manual inspection. "
                "Run 'git diff' and 'git status' to review, then "
                "'git checkout main && git branch -D %s' to clean up.",
                branch_name,
                branch_name,
            )
            update_backlog_status(project_root, idea_id, "unexpected_changes")
            _record_daily_state(
                project_root, idea, skill_name, idea_id, 0, None, "unexpected_changes"
            )
            return 1

        # Step 12: Review and improve
        passed, report = review_and_improve(project_root, skill_name)
        if not passed:
            _rollback_skill(project_root, skill_name, branch_name)
            created_branch = False
            update_backlog_status(project_root, idea_id, "review_failed")
            _record_daily_state(project_root, idea, skill_name, idea_id, 0, None, "review_failed")
            return 1

        # Step 13: Check for unexpected changes after improvement
        if not _check_unexpected_changes(project_root, skill_name):
            logger.error(
                "Unexpected changes after improvement. Branch '%s' preserved.",
                branch_name,
            )
            update_backlog_status(project_root, idea_id, "unexpected_changes")
            _record_daily_state(
                project_root, idea, skill_name, idea_id, 0, None, "unexpected_changes_post_improve"
            )
            return 1

        # Step 14: Create PR
        pr_url = create_skill_pr(project_root, skill_name, idea, report, branch_name)
        if not pr_url:
            _rollback_skill(project_root, skill_name, branch_name)
            created_branch = False
            update_backlog_status(project_root, idea_id, "pr_failed")
            _record_daily_state(project_root, idea, skill_name, idea_id, 0, None, "pr_failed")
            return 1

        # Step 15: Return to main (before marking completed)
        checkout_main = subprocess.run(
            ["git", "checkout", "main"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if checkout_main.returncode != 0:
            logger.warning(
                "git checkout main failed after PR creation (PR %s still valid): %s",
                pr_url,
                checkout_main.stderr.strip()[:200],
            )
        else:
            created_branch = False

        # Step 16: Mark as completed (after successful return to main)
        update_backlog_status(project_root, idea_id, "completed", pr_url=pr_url)

        # Step 17: Summary and state
        score = 0
        if report:
            score = report.get("auto_review", {}).get("score", 0)

        write_daily_generation_summary(project_root, idea, skill_name, report, pr_url)

        state = load_state(project_root)
        state["last_run"] = datetime.now().isoformat()
        state["history"].append(
            {
                "mode": "daily",
                "idea": idea.get("title"),
                "idea_id": idea_id,
                "skill": skill_name,
                "score": score,
                "pr_url": pr_url,
                "dry_run": False,
                "timestamp": datetime.now().isoformat(),
            }
        )
        save_state(project_root, state)

        # Step 18: Cleanup
        cleanup_merged_branches(project_root, prefix="skill-generation/")
        rotate_logs(project_root)

        logger.info("Daily run complete. PR: %s", pr_url)
        return 0

    finally:
        # Fix R#2: only checkout main if we created a branch and haven't returned to main yet
        if created_branch:
            subprocess.run(
                ["git", "checkout", "main"],
                cwd=project_root,
                capture_output=True,
                check=False,
            )
        release_lock(project_root)


# -- Weekly flow --


def run_weekly(project_root: Path, dry_run: bool = False) -> int:
    """Main weekly flow: mine ideas, score them, update backlog.

    Returns 0 on success, 1 on failure.
    """
    log_dir = project_root / LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "skill_generation.log"),
        ],
    )

    if not acquire_lock(project_root):
        return 0

    try:
        # Mine session logs
        logger.info("Starting weekly mining run (dry_run=%s).", dry_run)
        candidates_path = run_mine(project_root, dry_run=dry_run)
        if candidates_path is None:
            logger.error("Mining failed; aborting weekly run.")
            return 1

        logger.info("Mining produced: %s", candidates_path.name)

        # Score and update backlog
        score_ok = run_score(project_root, candidates_path, dry_run=dry_run)
        if not score_ok:
            logger.error("Scoring failed; writing partial summary.")

        # Load backlog for summary
        backlog = load_backlog(project_root)

        # Write summary
        write_weekly_summary(project_root, candidates_path, backlog)

        # Update state
        state = load_state(project_root)
        state["last_run"] = datetime.now().isoformat()
        state["history"].append(
            {
                "mode": "weekly",
                "candidates_file": candidates_path.name if candidates_path else None,
                "score_ok": score_ok,
                "backlog_size": len(backlog.get("ideas", [])),
                "timestamp": datetime.now().isoformat(),
            }
        )
        save_state(project_root, state)

        # Rotate old logs
        rotate_logs(project_root)

        if not score_ok:
            logger.info("Weekly run complete (with scoring failure).")
            return 1

        logger.info("Weekly run complete.")
        return 0

    finally:
        release_lock(project_root)


# -- CLI --


def parse_args():
    parser = argparse.ArgumentParser(description="Skill auto-generation pipeline orchestrator")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["weekly", "daily"],
        help="Pipeline mode (weekly: mine + score, daily: design + review + PR)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Pass --dry-run to subscripts")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()

    if args.mode == "weekly":
        return run_weekly(project_root, dry_run=args.dry_run)
    elif args.mode == "daily":
        return run_daily(project_root, dry_run=args.dry_run)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
