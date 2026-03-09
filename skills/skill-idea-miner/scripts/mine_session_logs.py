#!/usr/bin/env python3
"""Mine Claude Code session logs for skill idea candidates."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

logger = logging.getLogger("skill_idea_miner")

PROJECT_ALLOWLIST = [
    "claude-trading-skills",
    "claude-market-agents",
    "trade-edge-finder",
    "trade-strategy-pipeline",
    "weekly-trade-strategy",
]

CLAUDE_TIMEOUT = 600
CLAUDE_BUDGET_MINE = 1.00
LOOKBACK_DAYS = 7
MAX_USER_MESSAGES_PER_SESSION = 5
MAX_ERROR_OUTPUT_LEN = 500

# Categories rejected by the deterministic post-LLM filter.
# Broad denylist covering non-trading domains.
REJECTED_CATEGORIES = {
    "developer-tooling",
    "developer-productivity",
    "code-navigation",
    "documentation-generation",
    "skill-development",
    "devops",
    "ci-cd",
    "testing",
    "communication",
    "project-management",
    "customer-support",
    "hr",
    "meeting",
    "email",
    "calendar",
    "general-productivity",
}

# Keywords in title/description that indicate a non-trading skill.
REJECTED_KEYWORDS = [
    "codebase-navigator",
    "code-navigation",
    "doc-generator",
    "doc-site",
    "git-bulk",
    "skill-score",
    "batch-patcher",
    "meeting-scheduler",
    "email-",
    "slack-",
    "jira-",
    "confluence-",
]

AUTOMATED_PROMPT_PREFIXES = [
    "# LLM Skill Review Request",
    "Improve the skill '",
    "Implement the following plan:",
    "Score each skill idea candidate",
]


# ── Project discovery ──


def find_project_dirs(
    base_dir: Path,
    allowlist: list[str] | None = None,
) -> list[tuple[str, Path]]:
    """Scan ~/.claude/projects/ for directories matching allowlist.

    Directory encoding: `-Users-username-PycharmProjects-{project}` maps to
    the last path segment as the project name.

    Returns list of (project_name, dir_path) tuples.
    """
    if allowlist is None:
        allowlist = PROJECT_ALLOWLIST

    if not base_dir.is_dir():
        return []

    matches: list[tuple[str, Path]] = []
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir():
            continue
        # Directory name is encoded as dash-separated absolute path segments.
        # The project name is the last segment.
        for proj in allowlist:
            # Project name may itself contain dashes, so check if the dir name
            # ends with the project name (after the path encoding).
            if child.name.endswith(f"-{proj}") or child.name == proj:
                matches.append((proj, child))
                break

    return matches


# ── Session log listing ──


def list_session_logs(
    project_dirs: list[tuple[str, Path]],
    lookback_days: int = LOOKBACK_DAYS,
) -> list[tuple[str, Path]]:
    """Find *.jsonl files in each project dir, filtered by mtime.

    Returns list of (project_name, log_path) tuples.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
    cutoff_ts = cutoff.timestamp()

    results: list[tuple[str, Path]] = []
    for project_name, dir_path in project_dirs:
        if not dir_path.is_dir():
            continue
        for jsonl_file in sorted(dir_path.glob("*.jsonl")):
            if not jsonl_file.is_file():
                continue
            try:
                mtime = jsonl_file.stat().st_mtime
                if mtime >= cutoff_ts:
                    results.append((project_name, jsonl_file))
            except OSError:
                logger.warning("Could not stat %s", jsonl_file)

    return results


# ── Session parsing ──


def parse_session(log_path: Path) -> dict:
    """Parse a JSONL session log file.

    Extracts user messages, tool usage, and timestamps.
    Skips malformed lines with a warning.

    Returns {"user_messages": [...], "tool_uses": [...], "timestamps": [...]}.
    """
    user_messages: list[str] = []
    tool_uses: list[dict] = []
    timestamps: list[str] = []
    timed_entries: list[dict] = []

    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Could not read %s: %s", log_path, e)
        return {"user_messages": [], "tool_uses": [], "timestamps": []}

    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Malformed JSON at %s:%d, skipping.", log_path.name, line_num)
            continue

        if not isinstance(entry, dict):
            continue

        # Extract timestamp
        ts = entry.get("timestamp")
        if ts:
            timestamps.append(ts)

        msg = entry.get("message", {})
        if not isinstance(msg, dict):
            continue
        entry_type = entry.get("type") or msg.get("type", "")

        # Skip sidechain messages (before timed_entries to avoid contamination)
        if entry.get("isSidechain") or msg.get("isSidechain"):
            continue

        # Track timed entries for unresolved request detection
        if ts and entry_type:
            timed_entries.append({"timestamp": ts, "type": entry_type})

        # User messages
        if entry_type == "user" or msg.get("role") == "user":
            user_type = entry.get("userType") or msg.get("userType", "")
            if user_type != "external":
                continue

            content = msg.get("content", "")
            if isinstance(content, str):
                if content.strip():
                    user_messages.append(content.strip())
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_val = block.get("text", "").strip()
                        if text_val:
                            user_messages.append(text_val)

        # Assistant messages → extract tool_use blocks
        elif entry_type == "assistant" or msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_uses.append(
                            {
                                "name": block.get("name", ""),
                                "input": block.get("input", {}),
                            }
                        )

        # Tool results → store for error detection
        elif entry_type == "tool_result":
            content = msg.get("content", "")
            is_error = entry.get("is_error") or msg.get("is_error", False)
            if is_error:
                raw = content if isinstance(content, str) else str(content)
                tool_uses.append(
                    {
                        "name": "__tool_result_error__",
                        "output": raw[:MAX_ERROR_OUTPUT_LEN],
                    }
                )
            elif isinstance(content, str):
                # Check for error patterns in tool output
                if _has_error_pattern(content):
                    tool_uses.append(
                        {
                            "name": "__tool_result_error__",
                            "output": content[:MAX_ERROR_OUTPUT_LEN],
                        }
                    )

    return {
        "user_messages": user_messages,
        "tool_uses": tool_uses,
        "timestamps": timestamps,
        "timed_entries": timed_entries,
    }


def _has_error_pattern(text: str) -> bool:
    """Check if text contains common error patterns."""
    error_patterns = [
        r"(?m)^Error:",
        r"(?m)^Exception:",
        r"(?m)^Traceback \(most recent call last\)",
        r"exit code[:\s]+[1-9]",
        r"non-zero exit",
    ]
    for pattern in error_patterns:
        if re.search(pattern, text):
            return True
    return False


# ── Signal detection ──


def detect_signals(parsed: dict) -> dict:
    """Deterministic signal detection (no LLM).

    Detects:
    - skill_usage: references to skills/ in tool args
    - errors: error patterns in tool results
    - repetitive_patterns: same tool sequence appearing 3+ times
    - automation_requests: keyword matches in user messages
    - unresolved_requests: user message followed by 5+ min gap without tool_use

    Returns dict with signal counts and details.
    """
    user_messages = parsed.get("user_messages", [])
    tool_uses = parsed.get("tool_uses", [])

    signals: dict = {
        "skill_usage": _detect_skill_usage(tool_uses),
        "errors": _detect_errors(tool_uses),
        "repetitive_patterns": _detect_repetitive_patterns(tool_uses),
        "automation_requests": _detect_automation_requests(user_messages),
        "unresolved_requests": _detect_unresolved_requests(parsed.get("timed_entries", [])),
    }

    return signals


def _detect_skill_usage(tool_uses: list[dict]) -> dict:
    """Count references to skills/ in tool args (file paths, commands)."""
    skill_refs: dict[str, int] = {}
    skill_pattern = re.compile(r"skills/([a-zA-Z0-9_-]+)/")

    for tool in tool_uses:
        tool_input = tool.get("input", {})
        # Search in all string values of the input dict
        search_text = json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input)
        for match in skill_pattern.finditer(search_text):
            skill_name = match.group(1)
            skill_refs[skill_name] = skill_refs.get(skill_name, 0) + 1

    return {"count": len(skill_refs), "skills": skill_refs}


def _detect_errors(tool_uses: list[dict]) -> dict:
    """Detect error patterns in tool results."""
    error_count = 0
    error_samples: list[str] = []

    for tool in tool_uses:
        if tool.get("name") == "__tool_result_error__":
            error_count += 1
            output = tool.get("output", "")
            if output and len(error_samples) < 5:
                error_samples.append(output[:200])

    return {"count": error_count, "samples": error_samples}


def _detect_repetitive_patterns(tool_uses: list[dict]) -> dict:
    """Detect same tool sequence (3+ tools) appearing 3+ times."""
    tool_names = [
        t.get("name", "") for t in tool_uses if t.get("name", "").startswith("__") is False
    ]
    # Filter out error markers
    tool_names = [n for n in tool_names if not n.startswith("__")]

    if len(tool_names) < 9:  # Need at least 3 sequences of 3
        return {"count": 0, "patterns": []}

    # Check all windows of size 3
    sequences: dict[str, int] = {}
    for i in range(len(tool_names) - 2):
        seq = tuple(tool_names[i : i + 3])
        key = " -> ".join(seq)
        sequences[key] = sequences.get(key, 0) + 1

    repeated = {k: v for k, v in sequences.items() if v >= 3}
    return {"count": len(repeated), "patterns": list(repeated.keys())}


def _is_automated_prompt(msg: str) -> bool:
    """Check if a message is an automated Claude -p prompt (not a real user request)."""
    stripped = msg.strip()
    for prefix in AUTOMATED_PROMPT_PREFIXES:
        if stripped.startswith(prefix):
            return True
    return False


def _detect_automation_requests(user_messages: list[str]) -> dict:
    """Detect automation-related keywords in user messages.

    Excludes automated prompts from Claude -p invocations (e.g., skill
    improvement loop, scoring pipelines) to avoid false positives.
    """
    keywords = [
        "skill",
        "create",
        "automate",
        "workflow",
        "pipeline",
        "スキル",
        "作成",
        "自動化",
        "ワークフロー",
    ]
    matches: list[str] = []

    for msg in user_messages:
        if _is_automated_prompt(msg):
            continue
        msg_lower = msg.lower()
        for kw in keywords:
            if kw.lower() in msg_lower:
                if msg[:100] not in matches:
                    matches.append(msg[:100])
                break

    return {"count": len(matches), "samples": matches}


_RESPONSE_TYPES = {"assistant", "tool_result", "tool_use"}


def _detect_unresolved_requests(timed_entries: list[dict]) -> dict:
    """Detect user messages followed by 5+ minutes without assistant response.

    Only ``assistant``, ``tool_result``, and ``tool_use`` entries count as
    a real response.  System/progress/queue-operation entries are ignored.
    """
    if len(timed_entries) < 2:
        return {"count": 0}

    gap_count = 0
    for i, entry in enumerate(timed_entries):
        if entry.get("type") != "user":
            continue
        t1 = _parse_timestamp(entry.get("timestamp", ""))
        if t1 is None:
            continue
        # Find the next response entry (assistant/tool_use/tool_result)
        responded = False
        found_response = False
        for j in range(i + 1, len(timed_entries)):
            next_entry = timed_entries[j]
            if next_entry.get("type") not in _RESPONSE_TYPES:
                continue  # Skip user, system, progress, etc.
            found_response = True
            t2 = _parse_timestamp(next_entry.get("timestamp", ""))
            if t2 is None:
                continue
            diff = (t2 - t1).total_seconds()
            if diff < 300:  # Response within 5 minutes
                responded = True
            break  # Found the next response entry
        if not found_response:
            continue  # End of session or no real response — not unresolved
        if not responded:
            gap_count += 1

    return {"count": gap_count}


def _parse_timestamp(ts: str) -> datetime | None:
    """Parse ISO format timestamp string, normalizing to UTC-aware.

    Handles the ``Z`` suffix that Python 3.10's fromisoformat() rejects.
    """
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


# ── LLM abstraction ──


def abstract_with_llm(
    signals: dict,
    user_samples: list[str],
    project_name: str,
    dry_run: bool = False,
    trading_focus: bool = True,
) -> list[dict] | None:
    """Use claude CLI to abstract skill idea candidates from signals.

    Returns list of candidate dicts, or None if dry_run or on failure.
    """
    if dry_run:
        return None

    if not shutil.which("claude"):
        logger.warning("claude CLI not found; skipping LLM abstraction.")
        return None

    # Build prompt
    prompt = _build_llm_prompt(signals, user_samples, project_name, trading_focus)

    # Remove CLAUDECODE env var to allow claude -p from within Claude Code terminals
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(  # nosec B607 – claude CLI is an expected dependency
            [
                "claude",
                "-p",
                "--output-format",
                "json",
                "--max-turns",
                "3",
                f"--max-budget-usd={CLAUDE_BUDGET_MINE}",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            timeout=CLAUDE_TIMEOUT,
            env=env,
        )

        if result.returncode != 0:
            logger.warning("claude -p failed: %s", result.stderr.strip()[:200])
            return None

        logger.debug("claude -p stdout (%d chars): %.500s", len(result.stdout), result.stdout)

        response = _extract_json_from_claude(result.stdout, ["candidates"])
        if response and "candidates" in response:
            return response["candidates"]

        logger.warning(
            "Could not parse LLM candidates JSON. stdout (%d chars): %.300s",
            len(result.stdout),
            result.stdout,
        )
        return None

    except subprocess.TimeoutExpired:
        logger.warning("claude -p timed out.")
        return None
    except FileNotFoundError:
        logger.warning("claude CLI not found.")
        return None


def _build_llm_prompt(
    signals: dict,
    user_samples: list[str],
    project_name: str,
    trading_focus: bool = True,
) -> str:
    """Build the LLM prompt for skill idea abstraction.

    Args:
        trading_focus: When True (default, used with PROJECT_ALLOWLIST), constrain
            candidates to trading/investing domain. When False (used with --project
            override), use a generic prompt.
    """
    parts = [f"Project: {project_name}\n"]

    if trading_focus:
        parts.extend(
            [
                "This project is a trading and investing skill library. "
                "Analyze the following session signals and user message samples to suggest "
                "new Claude skill ideas focused on TRADING, INVESTING, and MARKET ANALYSIS.\n",
                "\n## IMPORTANT CONSTRAINTS\n",
                "- ONLY propose skills directly related to: stock/options trading, market analysis, "
                "portfolio management, risk management, economic/earnings data, technical/fundamental "
                "analysis, or trade execution workflows.",
                "- DO NOT propose developer-tooling, code-navigation, documentation-generation, "
                "or general-purpose software engineering skills. Those belong to a separate project.",
                "- Each skill idea must clearly describe how it helps a trader or investor.\n",
            ]
        )
    else:
        parts.append(
            "Analyze the following session signals and user message samples to suggest "
            "new Claude skill ideas that would automate or improve the user's workflow.\n",
        )

    parts.append("\n## Signals\n")

    for signal_name, signal_data in signals.items():
        count = signal_data.get("count", 0)
        parts.append(f"- {signal_name}: {count}")
        if isinstance(signal_data, dict):
            samples = signal_data.get("samples", [])
            skills = signal_data.get("skills", {})
            patterns = signal_data.get("patterns", [])
            if skills:
                parts.append(f"  Skills referenced: {', '.join(skills.keys())}")
            if samples:
                for s in samples[:3]:
                    parts.append(f"  Sample: {s[:100]}")
            if patterns:
                for p in patterns[:3]:
                    parts.append(f"  Pattern: {p}")
        parts.append("")

    if user_samples:
        parts.append("\n## User Message Samples\n")
        for sample in user_samples[:MAX_USER_MESSAGES_PER_SESSION]:
            parts.append(f"- {sample[:200]}")

    parts.append(
        "\n\nReturn 1-5 skill idea candidates as a single JSON object. "
        "Do NOT use markdown or natural language. Output ONLY valid JSON.\n"
        "Required format:\n"
        '{"candidates": [{"title": "...", "description": "...", "category": "...", '
        '"rationale": "...", "priority": "high|medium|low", '
        '"signals_used": ["..."]}]}'
    )

    return "\n".join(parts)


def _extract_json_from_claude(output: str, required_keys: list[str]) -> dict | None:
    """Extract JSON from claude CLI --output-format json envelope.

    Unwraps the envelope (result or content[].text), then scans for
    the first JSON object containing any of the required_keys.
    """
    # claude --output-format json wraps response; try to extract inner JSON
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


def filter_non_trading_candidates(candidates: list[dict]) -> list[dict]:
    """Deterministic post-LLM filter: reject candidates outside trading domain."""
    accepted = []
    for c in candidates:
        category = str(c.get("category") or "").lower()
        title = str(c.get("title") or "").lower()
        desc = str(c.get("description") or "").lower()

        if category in REJECTED_CATEGORIES:
            logger.info("Filtered out '%s' (rejected category: %s)", c.get("title"), category)
            continue

        text = f"{title} {desc}"
        if any(kw in text for kw in REJECTED_KEYWORDS):
            logger.info("Filtered out '%s' (rejected keyword match)", c.get("title"))
            continue

        accepted.append(c)
    return accepted


# ── Output helpers ──


def _write_empty_output(output_dir: Path, lookback_days: int) -> None:
    """Write an empty raw_candidates.yaml when there are no sessions to process."""
    output = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "sessions_analyzed": 0,
        "aggregated_signals": {},
        "session_details": [],
        "candidates": [],
    }
    output_path = output_dir / "raw_candidates.yaml"
    output_path.write_text(
        yaml.safe_dump(output, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    logger.info("Wrote empty raw candidates to %s", output_path)


# ── Main entry point ──


def run(args: argparse.Namespace) -> int:
    """Main entry point for session log mining."""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine base directory for project scanning
    claude_dir = Path.home() / ".claude" / "projects"

    # Determine allowlist
    if args.project:
        allowlist = [args.project]
    else:
        allowlist = PROJECT_ALLOWLIST

    # Find project directories
    project_dirs = find_project_dirs(claude_dir, allowlist)
    if not project_dirs:
        logger.warning("No matching project directories found in %s", claude_dir)
        _write_empty_output(output_dir, args.lookback_days)
        return 0

    logger.info("Found %d project directories.", len(project_dirs))

    # List session logs
    session_logs = list_session_logs(project_dirs, lookback_days=args.lookback_days)
    if not session_logs:
        logger.info("No recent session logs found (lookback=%d days).", args.lookback_days)
        _write_empty_output(output_dir, args.lookback_days)
        return 0

    logger.info("Found %d session logs.", len(session_logs))

    # Parse and detect signals per session
    all_signals: list[dict] = []
    all_user_samples: list[str] = []

    for project_name, log_path in session_logs:
        logger.info("Parsing %s (%s)", log_path.name, project_name)
        parsed = parse_session(log_path)
        signals = detect_signals(parsed)

        # Collect user message samples
        user_samples = parsed.get("user_messages", [])[:MAX_USER_MESSAGES_PER_SESSION]
        all_user_samples.extend(user_samples)

        all_signals.append(
            {
                "project": project_name,
                "session": log_path.name,
                "signals": signals,
                "user_message_count": len(parsed.get("user_messages", [])),
                "tool_use_count": len(parsed.get("tool_uses", [])),
            }
        )

    # LLM abstraction (optional)
    # Aggregate signals across sessions
    aggregated = _aggregate_signals(all_signals)
    # --project overrides the default trading-focused allowlist
    trading_focus = args.project is None
    candidates = abstract_with_llm(
        aggregated,
        all_user_samples[:MAX_USER_MESSAGES_PER_SESSION],
        project_name=", ".join(set(p for p, _ in project_dirs)),
        dry_run=args.dry_run,
        trading_focus=trading_focus,
    )

    # Normalize candidates before filtering: name -> title, assign ids
    if candidates:
        date_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
        for i, c in enumerate(candidates):
            c["id"] = f"raw_{date_str}_{i + 1:03d}"
            # Handle backward compatibility: LLM might output 'name' instead of 'title'
            if "title" not in c and "name" in c:
                c["title"] = c.pop("name")

    # Deterministic domain filter (only when using default allowlist)
    if candidates and trading_focus:
        candidates = filter_non_trading_candidates(candidates)

    # Write output
    output = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "lookback_days": args.lookback_days,
        "sessions_analyzed": len(session_logs),
        "aggregated_signals": aggregated,
        "session_details": all_signals,
    }
    output["candidates"] = candidates if candidates else []

    output_path = output_dir / "raw_candidates.yaml"
    output_path.write_text(
        yaml.safe_dump(output, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    logger.info("Wrote raw candidates to %s", output_path)

    return 0


def _aggregate_signals(all_signals: list[dict]) -> dict:
    """Aggregate signals across multiple sessions."""
    totals: dict = {
        "skill_usage": {"count": 0, "skills": {}},
        "errors": {"count": 0, "samples": []},
        "repetitive_patterns": {"count": 0, "patterns": []},
        "automation_requests": {"count": 0, "samples": []},
        "unresolved_requests": {"count": 0},
    }

    for entry in all_signals:
        signals = entry.get("signals", {})
        for key in totals:
            sig = signals.get(key, {})
            totals[key]["count"] = totals[key].get("count", 0) + sig.get("count", 0)

            if key == "skill_usage":
                for skill, cnt in sig.get("skills", {}).items():
                    totals[key]["skills"][skill] = totals[key]["skills"].get(skill, 0) + cnt
            elif key in ("errors", "automation_requests"):
                samples = sig.get("samples", [])
                totals[key]["samples"].extend(samples[:3])
            elif key == "repetitive_patterns":
                patterns = sig.get("patterns", [])
                totals[key]["patterns"].extend(patterns[:3])

    return totals


# ── CLI ──


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mine Claude Code session logs for skill idea candidates."
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Output directory for raw_candidates.yaml (default: reports)",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Override allowlist with a single project name",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=LOOKBACK_DAYS,
        help=f"Number of days to look back for session logs (default: {LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM abstraction step",
    )
    return parser.parse_args(argv)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
