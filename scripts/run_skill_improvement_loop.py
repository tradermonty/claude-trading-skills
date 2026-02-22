#!/usr/bin/env python3
"""Skill self-improvement loop orchestrator.

Picks the next skill, scores it with run_dual_axis_review.py,
optionally invokes `claude -p` for LLM review and improvement,
and opens a PR when the score is below threshold.
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
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("skill_improvement")

REVIEWER_SCRIPT = "skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py"
SELF_SKILL_NAME = "dual-axis-skill-reviewer"
STATE_FILE = "logs/.skill_improvement_state.json"
LOCK_FILE = "logs/.skill_improvement.lock"
LOG_DIR = "logs"
SUMMARY_DIR = "reports/skill-improvement-log"
SCORE_THRESHOLD = 90
HISTORY_LIMIT = 60
LOG_RETENTION_DAYS = 30
CLAUDE_TIMEOUT = 300
CLAUDE_RETRIES = 2
CLAUDE_BUDGET_REVIEW = 0.50
CLAUDE_BUDGET_IMPROVE = 2.00
IMPROVEMENT_TIMEOUT = 600


# ── Lock ──


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


# ── Git safety ──


def git_safe_check(project_root: Path) -> bool:
    """Verify clean working tree on main branch and pull latest."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        if status.stdout.strip():
            logger.error("Working tree is dirty. Aborting.")
            return False

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

        pull = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if pull.returncode != 0:
            logger.warning(
                "git pull --ff-only failed; will retry next run. stderr: %s", pull.stderr.strip()
            )
            return False

    except FileNotFoundError:
        logger.error("git not found.")
        return False

    return True


# ── State management ──


def load_state(project_root: Path) -> dict:
    state_path = project_root / STATE_FILE
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt state file, starting fresh.")
    return {"last_skill_index": -1, "history": []}


def save_state(project_root: Path, state: dict) -> None:
    state_path = project_root / STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["history"] = state["history"][-HISTORY_LIMIT:]
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── Skill selection ──


def discover_skills(project_root: Path) -> list[str]:
    """Return sorted skill names, excluding the reviewer itself."""
    skills_dir = project_root / "skills"
    if not skills_dir.is_dir():
        return []
    names = []
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists() and child.name != SELF_SKILL_NAME:
            names.append(child.name)
    return names


def pick_next_skill(skills: list[str], state: dict) -> str | None:
    if not skills:
        return None
    idx = (state.get("last_skill_index", -1) + 1) % len(skills)
    state["last_skill_index"] = idx
    return skills[idx]


# ── Scoring ──


def _build_reviewer_cmd(project_root: Path) -> list[str]:
    """Return command prefix for invoking the reviewer script."""
    if shutil.which("uv"):
        return ["uv", "run", "--extra", "dev", "python", str(project_root / REVIEWER_SCRIPT)]
    return [sys.executable, str(project_root / REVIEWER_SCRIPT)]


def run_auto_score(
    project_root: Path,
    skill_name: str,
    emit_prompt: bool = False,
    skip_tests: bool = True,
    llm_review_json: str | None = None,
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
    if llm_review_json:
        extra_args.extend(["--llm-review-json", llm_review_json])
    if emit_prompt:
        extra_args.append("--emit-llm-prompt")

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
        logger.error("Auto score failed for %s: %s", skill_name, result.stderr.strip())
        return None

    report_files = sorted(
        (project_root / "reports").glob(f"skill_review_{skill_name}_*.json"), reverse=True
    )
    if not report_files:
        logger.error("No report JSON found for %s.", skill_name)
        return None

    return json.loads(report_files[0].read_text(encoding="utf-8"))


def run_llm_review(project_root: Path, skill_name: str, prompt_file: str) -> dict | None:
    """Invoke claude CLI for LLM review. Returns parsed JSON or None."""
    if not shutil.which("claude"):
        logger.warning("claude CLI not found; skipping LLM review.")
        return None

    prompt_path = Path(prompt_file)
    if not prompt_path.is_absolute():
        prompt_path = project_root / prompt_path
    if not prompt_path.exists():
        logger.error("LLM prompt file not found: %s", prompt_file)
        return None

    prompt_text = prompt_path.read_text(encoding="utf-8")

    # JSON Schema to force structured output from Claude CLI
    review_schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "summary": {"type": "string"},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                            "path": {"type": "string"},
                            "line": {"type": "integer"},
                            "message": {"type": "string"},
                            "improvement": {"type": "string"},
                        },
                        "required": ["severity", "message", "improvement"],
                    },
                },
            },
            "required": ["score", "summary", "findings"],
        }
    )

    for attempt in range(CLAUDE_RETRIES + 1):
        try:
            result = subprocess.run(
                [
                    "claude",
                    "-p",
                    "--output-format",
                    "json",
                    "--json-schema",
                    review_schema,
                    "--max-turns",
                    "1",
                    f"--max-budget-usd={CLAUDE_BUDGET_REVIEW}",
                ],
                input=prompt_text,
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=CLAUDE_TIMEOUT,
            )
            if result.returncode != 0:
                logger.warning(
                    "claude -p attempt %d failed: %s", attempt + 1, result.stderr.strip()[:200]
                )
                continue

            # Parse claude output to extract the review JSON
            response = _extract_json_from_claude(result.stdout)
            if response:
                return response
            logger.warning("Could not parse LLM JSON on attempt %d.", attempt + 1)

        except subprocess.TimeoutExpired:
            logger.warning("claude -p timed out on attempt %d.", attempt + 1)
        except FileNotFoundError:
            logger.warning("claude CLI disappeared; skipping LLM review.")
            return None

    return None


def _extract_json_from_claude(output: str) -> dict | None:
    """Extract review JSON from claude CLI output."""
    # claude --output-format json wraps response; try to extract inner JSON
    try:
        wrapper = json.loads(output)
        # The actual text is in result or content
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

    # Find JSON block in text
    match = re.search(r"\{[\s\S]*?\"score\"\s*:\s*\d+[\s\S]*?\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ── Improvement ──


def check_existing_pr(project_root: Path, branch_name: str) -> bool:
    """Check if an open PR already exists for this branch."""
    if not shutil.which("gh"):
        return False
    result = subprocess.run(
        ["gh", "pr", "list", "--head", branch_name, "--state", "open", "--json", "number"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        prs = json.loads(result.stdout)
        return len(prs) > 0
    except json.JSONDecodeError:
        return False


def apply_improvement(
    project_root: Path,
    skill_name: str,
    report: dict,
    dry_run: bool = False,
) -> dict | None:
    """Create a branch, use claude to improve the skill, and open a PR.

    Returns the post-improvement report dict on success, or None on failure/dry-run.
    """
    if dry_run:
        logger.info(
            "[dry-run] Would improve skill '%s' (score=%d).",
            skill_name,
            report["final_review"]["score"],
        )
        return None

    if not shutil.which("claude"):
        logger.warning("claude CLI not found; skipping improvement.")
        return None
    if not shutil.which("gh"):
        logger.warning("gh CLI not found; skipping PR creation.")
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    branch_name = f"skill-improvement/{today}-{skill_name}"

    if check_existing_pr(project_root, branch_name):
        logger.info("Open PR already exists for %s; skipping.", branch_name)
        return None

    # Get pre-improvement auto score (use auto_review to avoid LLM merge bias)
    pre_score = report["auto_review"]["score"]

    # Delete existing branch if present (from a previous failed run)
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        cwd=project_root,
        capture_output=True,
        check=False,
    )

    # Create branch
    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    )

    try:
        # Build improvement prompt
        improvements = report["final_review"].get("improvement_items", [])
        prompt = (
            f"Improve the skill '{skill_name}' in skills/{skill_name}/ based on these findings:\n\n"
            + "\n".join(f"- {item}" for item in improvements[:10])
            + "\n\nMake minimal, targeted edits to address the findings. Do not change unrelated code."
        )

        result = subprocess.run(
            [
                "claude",
                "-p",
                "--allowedTools",
                "Read,Edit,Write,Glob,Grep",
                f"--max-budget-usd={CLAUDE_BUDGET_IMPROVE}",
            ],
            input=prompt,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=IMPROVEMENT_TIMEOUT,
        )
        if result.returncode != 0:
            logger.error("claude improvement failed: %s", result.stderr.strip()[:200])
            _rollback(project_root, skill_name, branch_name)
            return None

        # Quality gate: re-score (with tests enabled)
        re_report = run_auto_score(project_root, skill_name, skip_tests=False)
        if not re_report:
            logger.error("Re-scoring failed after improvement; rolling back.")
            _rollback(project_root, skill_name, branch_name)
            return None

        re_score = re_report.get("auto_review", {}).get("score", 0)
        if re_score <= pre_score:
            logger.warning(
                "Re-score (%d) not better than pre-score (%d); rolling back.",
                re_score,
                pre_score,
            )
            _rollback(project_root, skill_name, branch_name)
            return None

        # Auto-fix lint issues before committing
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

        # Commit, push, create PR
        subprocess.run(
            ["git", "add", f"skills/{skill_name}/"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        commit_msg = f"Improve {skill_name} skill (score {pre_score} -> {re_score})"
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        push = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if push.returncode != 0:
            logger.error("git push failed: %s", push.stderr.strip()[:200])
            return None

        pr_body = (
            f"## Summary\n"
            f"- Skill: `{skill_name}`\n"
            f"- Score: {pre_score} -> {re_score}\n\n"
            f"## Improvements\n"
            + "\n".join(f"- {item}" for item in improvements[:10])
            + "\n\nGenerated by skill self-improvement loop."
        )
        pr = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                f"Improve {skill_name} skill (score {pre_score} -> {re_score})",
                "--body",
                pr_body,
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if pr.returncode != 0:
            logger.error("gh pr create failed: %s", pr.stderr.strip()[:200])

        return re_report

    except Exception:
        logger.exception("Unexpected error during improvement.")
        _rollback(project_root, skill_name, branch_name)
        return None

    finally:
        # Return to main
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=project_root,
            capture_output=True,
            check=False,
        )


def _rollback(project_root: Path, skill_name: str, branch_name: str) -> None:
    """Roll back changes and return to main."""
    subprocess.run(
        ["git", "reset", "HEAD", "--", f"skills/{skill_name}/"],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["git", "checkout", "--", f"skills/{skill_name}/"],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["git", "clean", "-fd", f"skills/{skill_name}/"],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["git", "checkout", "main"],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        cwd=project_root,
        capture_output=True,
        check=False,
    )


# ── Summary ──


def write_daily_summary(project_root: Path, skill_name: str, report: dict, improved: bool) -> None:
    summary_dir = project_root / SUMMARY_DIR
    summary_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    summary_path = summary_dir / f"{today}_summary.md"

    entry = (
        f"\n## {skill_name}\n"
        f"- Score: {report['final_review']['score']}/100\n"
        f"- Improved: {'Yes' if improved else 'No'}\n"
        f"- High findings: {sum(1 for f in report['final_review'].get('findings', []) if f.get('severity') == 'high')}\n"
    )

    if summary_path.exists():
        existing = summary_path.read_text(encoding="utf-8")
        summary_path.write_text(existing + entry, encoding="utf-8")
    else:
        header = f"# Skill Improvement Summary - {today}\n"
        summary_path.write_text(header + entry, encoding="utf-8")


# ── Cleanup ──


def cleanup_merged_branches(project_root: Path) -> None:
    """Delete local branches whose PRs are merged or closed."""
    if not shutil.which("gh"):
        return

    result = subprocess.run(
        ["git", "branch", "--list", "skill-improvement/*"],
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
            state = data.get("state", "").upper()
            if state in ("MERGED", "CLOSED"):
                subprocess.run(
                    ["git", "branch", "-D", branch],
                    cwd=project_root,
                    capture_output=True,
                    check=False,
                )
                logger.info("Deleted merged/closed branch: %s", branch)
        except json.JSONDecodeError:
            pass


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


# ── Main ──


def parse_args():
    parser = argparse.ArgumentParser(description="Skill self-improvement orchestration loop")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument(
        "--dry-run", action="store_true", help="Score only; skip improvement and PR creation"
    )
    return parser.parse_args()


def run(project_root: Path, dry_run: bool = False) -> int:
    """Core orchestration logic, separated from CLI for testability."""
    log_dir = project_root / LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "skill_improvement.log"),
        ],
    )

    if not acquire_lock(project_root):
        return 0

    try:
        # Git safety
        if not dry_run and not git_safe_check(project_root):
            return 1

        # Discover and pick skill
        skills = discover_skills(project_root)
        if not skills:
            logger.error("No skills found.")
            return 1

        state = load_state(project_root)
        skill_name = pick_next_skill(skills, state)
        if not skill_name:
            logger.error("No skill to review.")
            return 1

        logger.info("Selected skill: %s", skill_name)

        # Auto scoring (with LLM prompt emission)
        report = run_auto_score(project_root, skill_name, emit_prompt=True)
        if not report:
            logger.error("Auto scoring failed.")
            return 1

        auto_score = report.get("auto_review", {}).get("score", 0)
        logger.info("Auto score for %s: %d/100", skill_name, auto_score)

        # LLM review (optional)
        llm_prompt_file = report.get("llm_prompt_file")
        if llm_prompt_file and not dry_run:
            llm_result = run_llm_review(project_root, skill_name, llm_prompt_file)
            if llm_result:
                # Write LLM review JSON and re-run with --llm-review-json
                llm_json_path = project_root / "reports" / f"llm_review_{skill_name}.json"
                llm_json_path.write_text(json.dumps(llm_result, indent=2), encoding="utf-8")
                logger.info("LLM review score: %d", llm_result.get("score", 0))
                # Re-score with LLM review merged
                merged_report = run_auto_score(
                    project_root,
                    skill_name,
                    llm_review_json=str(llm_json_path),
                )
                if merged_report:
                    report = merged_report

        final_score = report.get("auto_review", {}).get("score", auto_score)
        logger.info("Auto-based score for %s: %d/100", skill_name, final_score)

        # Improvement
        improved = False
        if final_score < SCORE_THRESHOLD:
            logger.info(
                "Auto score %d below %d; attempting improvement.", final_score, SCORE_THRESHOLD
            )
            improvement_result = apply_improvement(
                project_root, skill_name, report, dry_run=dry_run
            )
            if isinstance(improvement_result, dict):
                # Use post-improvement report for summary and state
                report = improvement_result
                final_score = report.get("auto_review", {}).get("score", final_score)
                improved = True
        else:
            logger.info(
                "Auto score meets threshold (%d >= %d); no improvement needed.",
                final_score,
                SCORE_THRESHOLD,
            )

        # Summary
        write_daily_summary(project_root, skill_name, report, improved)

        # State update
        state["history"].append(
            {
                "skill": skill_name,
                "score": final_score,
                "improved": improved,
                "timestamp": datetime.now().isoformat(),
            }
        )
        save_state(project_root, state)

        # Cleanup
        if not dry_run:
            cleanup_merged_branches(project_root)
            rotate_logs(project_root)

        return 0

    finally:
        release_lock(project_root)


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    return run(project_root, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
