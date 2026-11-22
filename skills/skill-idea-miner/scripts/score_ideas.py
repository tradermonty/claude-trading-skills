#!/usr/bin/env python3
"""Score and deduplicate skill idea candidates."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

logger = logging.getLogger("skill_idea_scorer")

CLAUDE_TIMEOUT = 600
CLAUDE_BUDGET_SCORE = 0.50
JACCARD_THRESHOLD = 0.5


# ── Existing skill discovery ──


def list_existing_skills(project_root: Path) -> list[dict]:
    """Discover existing skills by globbing skills/*/SKILL.md (single level only).

    Returns list of {"name": str, "description": str}.
    """
    skills_dir = project_root / "skills"
    if not skills_dir.is_dir():
        return []

    results = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
            fm = _parse_yaml_frontmatter(text)
            if fm and "name" in fm:
                results.append(
                    {
                        "name": fm.get("name", child.name),
                        "description": fm.get("description", ""),
                    }
                )
        except (OSError, yaml.YAMLError):
            logger.debug("Skipping %s: invalid YAML frontmatter.", skill_md)
    return results


def _parse_yaml_frontmatter(text: str) -> dict | None:
    """Extract YAML frontmatter between --- markers."""
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    try:
        return yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None


# ── Text similarity ──


def normalize_text(text: str) -> set[str]:
    """Lowercase, remove punctuation, split into word set."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    return set(cleaned.split())


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard coefficient between word sets of two texts."""
    set_a = normalize_text(text_a)
    set_b = normalize_text(text_b)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


# ── Deduplication ──


def find_duplicates(
    candidates: list[dict],
    existing_skills: list[dict],
    backlog_ideas: list[dict],
) -> list[dict]:
    """Check candidates against existing skills and backlog ideas for duplicates.

    Annotates each candidate with status="duplicate" and duplicate_of if
    Jaccard similarity exceeds JACCARD_THRESHOLD.
    """
    for candidate in candidates:
        cand_text = f"{candidate.get('title', '')} {candidate.get('description', '')}"

        # Check against existing skills
        for skill in existing_skills:
            ref_text = f"{skill.get('name', '')} {skill.get('description', '')}"
            sim = jaccard_similarity(cand_text, ref_text)
            if sim > JACCARD_THRESHOLD:
                candidate["status"] = "duplicate"
                candidate["duplicate_of"] = f"skill:{skill.get('name', '')}"
                candidate["jaccard_score"] = round(sim, 3)
                break

        if candidate.get("status") == "duplicate":
            continue

        # Check against backlog ideas
        for idea in backlog_ideas:
            ref_text = f"{idea.get('title', '')} {idea.get('description', '')}"
            sim = jaccard_similarity(cand_text, ref_text)
            if sim > JACCARD_THRESHOLD:
                candidate["status"] = "duplicate"
                candidate["duplicate_of"] = f"backlog:{idea.get('id', '')}"
                candidate["jaccard_score"] = round(sim, 3)
                break

    return candidates


# ── LLM scoring ──


def score_with_llm(candidates: list[dict], dry_run: bool = False) -> list[dict]:
    """Score non-duplicate candidates using Claude CLI.

    Scores each candidate on novelty, feasibility, and trading_value (0-100).
    Composite = 0.3 * novelty + 0.3 * feasibility + 0.4 * trading_value.
    """
    scorable = [c for c in candidates if c.get("status") != "duplicate"]

    if not scorable:
        logger.info("No candidates to score (all duplicates or empty).")
        return candidates

    if dry_run:
        for c in scorable:
            c["scores"] = {
                "novelty": 0,
                "feasibility": 0,
                "trading_value": 0,
                "composite": 0,
            }
        return candidates

    if not shutil.which("claude"):
        logger.warning("claude CLI not found; setting zero scores.")
        for c in scorable:
            c["scores"] = {
                "novelty": 0,
                "feasibility": 0,
                "trading_value": 0,
                "composite": 0,
            }
        return candidates

    # Build scoring prompt
    candidate_descriptions = []
    for i, c in enumerate(scorable):
        candidate_descriptions.append(
            f"{i + 1}. ID: {c.get('id', f'unknown_{i}')}\n"
            f"   Title: {c.get('title', 'N/A')}\n"
            f"   Description: {c.get('description', 'N/A')}\n"
            f"   Category: {c.get('category', 'N/A')}"
        )

    prompt = (
        "Score each skill idea candidate on three dimensions (0-100 each):\n"
        "- novelty: How unique is this idea compared to typical trading tools?\n"
        "- feasibility: How practical is it to implement as a Claude skill?\n"
        "- trading_value: How useful is this for equity traders/investors?\n\n"
        "Candidates:\n" + "\n".join(candidate_descriptions) + "\n\n"
        "Return scores for ALL candidates as a single JSON object. "
        "Do NOT use markdown or natural language. Output ONLY valid JSON.\n"
        "Required format:\n"
        '{"candidates": [{"id": "...", "novelty": 0, "feasibility": 0, "trading_value": 0}]}'
    )

    # Remove CLAUDECODE env var to allow claude -p from within Claude Code terminals
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(  # nosec B607 – claude CLI is an expected dependency
            [
                "claude",
                "-p",
                # ponytail: pin sonnet — session default (Fable) costs ~$0.64/call
                # in fixed overhead and blows the budget before answering
                "--model",
                "sonnet",
                "--output-format",
                "json",
                "--max-turns",
                "3",
                f"--max-budget-usd={CLAUDE_BUDGET_SCORE}",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            timeout=CLAUDE_TIMEOUT,
            env=env,
        )

        if result.returncode != 0:
            logger.warning("claude scoring failed: %s", result.stderr.strip()[:200])
            for c in scorable:
                c["scores"] = {
                    "novelty": 0,
                    "feasibility": 0,
                    "trading_value": 0,
                    "composite": 0,
                }
            return candidates

        parsed = _extract_json_from_claude(result.stdout, ["scores", "candidates"])
        if parsed and "candidates" in parsed:
            score_map = {s.get("id", ""): s for s in parsed.get("candidates", [])}
            for c in scorable:
                cid = c.get("id", "")
                if cid in score_map:
                    s = score_map[cid]
                    n = s.get("novelty", 0)
                    f = s.get("feasibility", 0)
                    t = s.get("trading_value", 0)
                    c["scores"] = {
                        "novelty": n,
                        "feasibility": f,
                        "trading_value": t,
                        "composite": round(0.3 * n + 0.3 * f + 0.4 * t, 1),
                    }
                else:
                    c["scores"] = {
                        "novelty": 0,
                        "feasibility": 0,
                        "trading_value": 0,
                        "composite": 0,
                    }
        else:
            logger.warning("Could not parse LLM scoring output.")
            for c in scorable:
                c["scores"] = {
                    "novelty": 0,
                    "feasibility": 0,
                    "trading_value": 0,
                    "composite": 0,
                }

    except subprocess.TimeoutExpired:
        logger.warning("claude scoring timed out.")
        for c in scorable:
            c["scores"] = {"novelty": 0, "feasibility": 0, "trading_value": 0, "composite": 0}
    except FileNotFoundError:
        logger.warning("claude CLI not found during execution.")
        for c in scorable:
            c["scores"] = {"novelty": 0, "feasibility": 0, "trading_value": 0, "composite": 0}

    return candidates


def _extract_json_from_claude(output: str, required_keys: list[str]) -> dict | None:
    """Extract JSON from claude CLI --output-format json envelope.

    Unwraps the envelope (result or content[].text), then scans for
    the first JSON object containing any of the required_keys.
    """
    # Try parsing the wrapper envelope first
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

    # Find JSON block using raw_decode
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        pos = text.find("{", idx)
        if pos == -1:
            break
        try:
            obj, end_idx = decoder.raw_decode(text, pos)
            if isinstance(obj, dict) and any(k in obj for k in required_keys):
                return obj
            idx = pos + 1
        except json.JSONDecodeError:
            idx = pos + 1
    return None


# ── Backlog management ──


def load_backlog(backlog_path: Path) -> dict:
    """Load existing backlog YAML or return empty structure."""
    if backlog_path.exists():
        try:
            data = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "ideas" in data:
                return data
        except (OSError, yaml.YAMLError):
            logger.warning("Failed to load backlog from %s; starting fresh.", backlog_path)
    return {"updated_at_utc": "", "ideas": []}


def merge_into_backlog(backlog: dict, scored_candidates: list[dict]) -> dict:
    """Add new ideas to backlog, preserving existing statuses.

    Candidates with matching id are skipped (not duplicated).
    Existing idea fields (especially status) are never overwritten.
    """
    existing_ids = {idea.get("id") for idea in backlog.get("ideas", [])}

    for candidate in scored_candidates:
        cid = candidate.get("id")
        if not cid or cid in existing_ids:
            continue

        idea = {
            "id": cid,
            "title": candidate.get("title", ""),
            "description": candidate.get("description", ""),
            "category": candidate.get("category", ""),
            "source_project": candidate.get("source_project", ""),
            "source_raw_ids": candidate.get("source_raw_ids", []),
            "scores": candidate.get("scores", {}),
            "status": candidate.get("status", "pending"),
            "created_at": candidate.get(
                "created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")
            ),
            "attempted_at": None,
            "pr_url": None,
        }
        backlog["ideas"].append(idea)
        existing_ids.add(cid)

    backlog["updated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return backlog


def save_backlog(backlog_path: Path, backlog: dict) -> None:
    """Save backlog to YAML atomically via tempfile + os.replace."""
    backlog_path.parent.mkdir(parents=True, exist_ok=True)

    content = yaml.safe_dump(backlog, default_flow_style=False, sort_keys=False, allow_unicode=True)
    fd, tmp_path = tempfile.mkstemp(dir=backlog_path.parent, suffix=".tmp", prefix=".backlog_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, backlog_path)
    except BaseException:
        os.unlink(tmp_path)
        raise
    logger.info("Backlog saved to %s (%d ideas).", backlog_path, len(backlog.get("ideas", [])))


# ── Main ──


def run(args) -> int:
    """Main entry point for scoring and deduplication."""
    project_root = Path(args.project_root).resolve()
    candidates_path = Path(args.candidates)
    if not candidates_path.is_absolute():
        candidates_path = project_root / candidates_path
    backlog_path = Path(args.backlog)
    if not backlog_path.is_absolute():
        backlog_path = project_root / backlog_path

    # Load candidates
    if not candidates_path.exists():
        logger.error("Candidates file not found: %s", candidates_path)
        return 1

    try:
        raw = yaml.safe_load(candidates_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.error("Failed to load candidates: %s", exc)
        return 1

    candidates = raw.get("candidates", []) if isinstance(raw, dict) else []
    if not candidates:
        logger.info("No candidates to process.")
        return 0

    logger.info("Loaded %d candidates from %s.", len(candidates), candidates_path)

    # Discover existing skills
    existing_skills = list_existing_skills(project_root)
    logger.info("Found %d existing skills.", len(existing_skills))

    # Load backlog
    backlog = load_backlog(backlog_path)
    backlog_ideas = backlog.get("ideas", [])
    logger.info("Loaded backlog with %d existing ideas.", len(backlog_ideas))

    # Deduplication
    candidates = find_duplicates(candidates, existing_skills, backlog_ideas)
    dup_count = sum(1 for c in candidates if c.get("status") == "duplicate")
    logger.info("Marked %d candidates as duplicates.", dup_count)

    # LLM scoring
    candidates = score_with_llm(candidates, dry_run=args.dry_run)

    # Merge into backlog
    backlog = merge_into_backlog(backlog, candidates)
    save_backlog(backlog_path, backlog)

    # Summary
    scored = [c for c in candidates if c.get("scores", {}).get("composite", 0) > 0]
    logger.info(
        "Done. %d scored, %d duplicates, %d total in backlog.",
        len(scored),
        dup_count,
        len(backlog.get("ideas", [])),
    )

    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="Score and deduplicate skill idea candidates")
    parser.add_argument(
        "--candidates",
        default="reports/skill-idea-miner/raw_candidates.yaml",
        help="Path to raw_candidates.yaml",
    )
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument(
        "--backlog",
        default="reports/skill-idea-miner/idea_backlog.yaml",
        help="Path to backlog YAML file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM scoring; set zero scores",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
