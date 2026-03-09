"""Tests for mine_session_logs.py."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def mine_module():
    """Load mine_session_logs.py as a module."""
    script_path = Path(__file__).resolve().parents[1] / "mine_session_logs.py"
    spec = importlib.util.spec_from_file_location("mine_session_logs", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load mine_session_logs.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ── find_project_dirs ──


def test_find_project_dirs(mine_module, tmp_path: Path):
    """Create mock dirs matching allowlist encoding, verify matches."""
    # Simulate ~/.claude/projects/ directory structure
    base = tmp_path / "projects"
    base.mkdir()

    # Directory encoding: dash-separated absolute path
    (base / "-Users-alice-PycharmProjects-claude-trading-skills").mkdir()
    (base / "-Users-bob-Code-trade-edge-finder").mkdir()
    (base / "-Users-carol-Projects-unrelated-project").mkdir()

    allowlist = ["claude-trading-skills", "trade-edge-finder"]
    result = mine_module.find_project_dirs(base, allowlist)

    assert len(result) == 2
    names = [name for name, _ in result]
    assert "claude-trading-skills" in names
    assert "trade-edge-finder" in names


def test_find_project_dirs_no_match(mine_module, tmp_path: Path):
    """No matching dirs returns empty list."""
    base = tmp_path / "projects"
    base.mkdir()
    (base / "-Users-alice-Projects-something-else").mkdir()

    result = mine_module.find_project_dirs(base, ["claude-trading-skills"])
    assert result == []


# ── list_session_logs ──


def test_list_session_logs_date_filter(mine_module, tmp_path: Path):
    """Create files with recent and old mtime, verify filter."""
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()

    # Recent file (now)
    recent = proj_dir / "recent_session.jsonl"
    recent.write_text('{"type":"user"}\n')

    # Old file (30 days ago)
    old = proj_dir / "old_session.jsonl"
    old.write_text('{"type":"user"}\n')
    old_time = time.time() - (30 * 86400)
    os.utime(old, (old_time, old_time))

    project_dirs = [("test-project", proj_dir)]
    result = mine_module.list_session_logs(project_dirs, lookback_days=7)

    assert len(result) == 1
    assert result[0][0] == "test-project"
    assert result[0][1].name == "recent_session.jsonl"


# ── parse_session ──


def test_parse_user_messages_str(mine_module, tmp_path: Path):
    """Parse JSONL with string content format."""
    log = tmp_path / "session.jsonl"
    lines = [
        json.dumps(
            {
                "type": "user",
                "message": {"type": "user", "content": "Analyze AAPL"},
                "userType": "external",
                "timestamp": "2026-02-28T10:00:00+00:00",
            }
        ),
        json.dumps(
            {
                "type": "user",
                "message": {"type": "user", "content": "Check breadth"},
                "userType": "external",
                "timestamp": "2026-02-28T10:01:00+00:00",
            }
        ),
    ]
    log.write_text("\n".join(lines))

    result = mine_module.parse_session(log)
    assert len(result["user_messages"]) == 2
    assert result["user_messages"][0] == "Analyze AAPL"
    assert result["user_messages"][1] == "Check breadth"


def test_parse_user_messages_list(mine_module, tmp_path: Path):
    """Parse JSONL with list[{type,text}] content format."""
    log = tmp_path / "session.jsonl"
    lines = [
        json.dumps(
            {
                "type": "user",
                "message": {
                    "type": "user",
                    "content": [
                        {"type": "text", "text": "Create a new skill"},
                        {"type": "text", "text": "for dividend analysis"},
                    ],
                },
                "userType": "external",
                "timestamp": "2026-02-28T10:00:00+00:00",
            }
        ),
    ]
    log.write_text("\n".join(lines))

    result = mine_module.parse_session(log)
    assert len(result["user_messages"]) == 2
    assert result["user_messages"][0] == "Create a new skill"
    assert result["user_messages"][1] == "for dividend analysis"


def test_parse_tool_usage(mine_module, tmp_path: Path):
    """Extract tool_use blocks from assistant messages."""
    log = tmp_path / "session.jsonl"
    lines = [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "type": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {
                                "command": "python3 skills/pead-screener/scripts/screen_pead.py"
                            },
                        },
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/tmp/report.md"},
                        },
                    ],
                },
                "timestamp": "2026-02-28T10:00:00+00:00",
            }
        ),
    ]
    log.write_text("\n".join(lines))

    result = mine_module.parse_session(log)
    tool_uses = [t for t in result["tool_uses"] if not t["name"].startswith("__")]
    assert len(tool_uses) == 2
    assert tool_uses[0]["name"] == "Bash"
    assert tool_uses[1]["name"] == "Read"


def test_parse_malformed_jsonl(mine_module, tmp_path: Path):
    """Bad lines are skipped, good lines parsed."""
    log = tmp_path / "session.jsonl"
    lines = [
        "this is not json",
        json.dumps(
            {
                "type": "user",
                "message": {"type": "user", "content": "Valid message"},
                "userType": "external",
                "timestamp": "2026-02-28T10:00:00+00:00",
            }
        ),
        "{broken json",
        json.dumps(
            {
                "type": "user",
                "message": {"type": "user", "content": "Another valid one"},
                "userType": "external",
                "timestamp": "2026-02-28T10:01:00+00:00",
            }
        ),
    ]
    log.write_text("\n".join(lines))

    result = mine_module.parse_session(log)
    assert len(result["user_messages"]) == 2
    assert result["user_messages"][0] == "Valid message"
    assert result["user_messages"][1] == "Another valid one"


# ── detect_signals ──


def test_detect_skill_usage(mine_module):
    """Detect skills/ references in tool args."""
    tool_uses = [
        {
            "name": "Bash",
            "input": {"command": "python3 skills/earnings-trade-analyzer/scripts/run.py"},
        },
        {
            "name": "Read",
            "input": {"file_path": "skills/pead-screener/SKILL.md"},
        },
        {
            "name": "Bash",
            "input": {"command": "ls -la"},
        },
    ]
    result = mine_module._detect_skill_usage(tool_uses)
    assert result["count"] == 2
    assert "earnings-trade-analyzer" in result["skills"]
    assert "pead-screener" in result["skills"]


def test_detect_errors(mine_module):
    """Detect error patterns in tool results."""
    tool_uses = [
        {"name": "__tool_result_error__", "output": "Error: API key missing"},
        {"name": "__tool_result_error__", "output": "Traceback (most recent call last):\n..."},
        {"name": "Bash", "input": {"command": "echo hello"}},
    ]
    result = mine_module._detect_errors(tool_uses)
    assert result["count"] == 2
    assert len(result["samples"]) == 2


def test_detect_automation_requests(mine_module):
    """Detect automation keywords in user messages."""
    messages = [
        "Can you create a skill for this?",
        "Just run the analysis",
        "I want to automate this workflow",
        "スキルを作成してほしい",
    ]
    result = mine_module._detect_automation_requests(messages)
    assert result["count"] == 3
    assert len(result["samples"]) == 3


def test_detect_automation_requests_excludes_automated_prompts(mine_module):
    """Claude -p automated prompts are excluded from automation_requests."""
    messages = [
        "# LLM Skill Review Request\nPlease review this skill...",
        "Improve the skill 'backtest-expert' using the review results below.",
        "Implement the following plan:\n1. Create skill...",
        "Score each skill idea candidate on three dimensions...",
        "Can you create a skill for this?",  # Real user request
    ]
    result = mine_module._detect_automation_requests(messages)
    assert result["count"] == 1
    assert "create a skill" in result["samples"][0].lower()


def test_is_automated_prompt(mine_module):
    """_is_automated_prompt correctly identifies automated prompts."""
    assert mine_module._is_automated_prompt("# LLM Skill Review Request\nContent...")
    assert mine_module._is_automated_prompt("Improve the skill 'x' using...")
    assert mine_module._is_automated_prompt("Implement the following plan:\n...")
    assert mine_module._is_automated_prompt("Score each skill idea candidate on...")
    assert not mine_module._is_automated_prompt("Can you create a skill?")
    assert not mine_module._is_automated_prompt("I want to automate this")


# ── _detect_unresolved_requests ──


def test_detect_unresolved_requests_no_gap(mine_module):
    """User message followed by quick assistant response is not unresolved."""
    timed_entries = [
        {"timestamp": "2026-02-28T10:00:00+00:00", "type": "user"},
        {"timestamp": "2026-02-28T10:00:30+00:00", "type": "assistant"},
    ]
    result = mine_module._detect_unresolved_requests(timed_entries)
    assert result["count"] == 0


def test_detect_unresolved_requests_with_gap(mine_module):
    """User message followed by 10-min gap before response is unresolved."""
    timed_entries = [
        {"timestamp": "2026-02-28T10:00:00+00:00", "type": "user"},
        {"timestamp": "2026-02-28T10:10:00+00:00", "type": "assistant"},
    ]
    result = mine_module._detect_unresolved_requests(timed_entries)
    assert result["count"] == 1


def test_detect_unresolved_requests_user_then_user(mine_module):
    """Consecutive user messages with gap: first is unresolved."""
    timed_entries = [
        {"timestamp": "2026-02-28T10:00:00+00:00", "type": "user"},
        {"timestamp": "2026-02-28T10:06:00+00:00", "type": "user"},
        {"timestamp": "2026-02-28T10:06:10+00:00", "type": "assistant"},
    ]
    result = mine_module._detect_unresolved_requests(timed_entries)
    # First user: next non-user is assistant at +6:10 (>5min) → unresolved
    # Second user: next non-user is assistant at +0:10 (<5min) → resolved
    assert result["count"] == 1


# ── _extract_json_from_claude ──


def test_extract_json_from_claude_candidates(mine_module):
    """JSON with candidates key is extracted."""
    raw = json.dumps(
        {
            "candidates": [
                {
                    "name": "test-skill",
                    "description": "A test",
                    "rationale": "Because",
                    "priority": "high",
                },
            ],
        }
    )
    result = mine_module._extract_json_from_claude(raw, ["candidates"])
    assert result is not None
    assert "candidates" in result
    assert len(result["candidates"]) == 1


def test_extract_json_from_claude_wrapped(mine_module):
    """JSON wrapped in claude --output-format json envelope."""
    inner = json.dumps(
        {
            "candidates": [{"name": "x", "description": "y", "rationale": "z", "priority": "low"}],
        }
    )
    wrapper = json.dumps({"result": f"Here are the ideas:\n{inner}\nDone."})
    result = mine_module._extract_json_from_claude(wrapper, ["candidates"])
    assert result is not None
    assert result["candidates"][0]["name"] == "x"


def test_extract_json_from_claude_no_candidates(mine_module):
    """JSON without 'candidates' key returns None."""
    raw = '{"score": 85, "summary": "review"}'
    result = mine_module._extract_json_from_claude(raw, ["candidates"])
    assert result is None


# ── Real session format: entry.type != msg.type ──


def test_parse_assistant_with_message_type(mine_module, tmp_path: Path):
    """Real session format: entry.type=assistant, msg.type=message, msg.role=assistant."""
    log = tmp_path / "session.jsonl"
    entry = {
        "type": "assistant",
        "message": {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Read",
                    "input": {"file_path": "skills/pead-screener/SKILL.md"},
                },
            ],
        },
        "timestamp": "2026-02-28T10:00:00+00:00",
    }
    log.write_text(json.dumps(entry))
    result = mine_module.parse_session(log)
    tool_uses = [t for t in result["tool_uses"] if not t["name"].startswith("__")]
    assert len(tool_uses) == 1
    assert tool_uses[0]["name"] == "Read"


def test_timed_entries_correct_types(mine_module, tmp_path: Path):
    """timed_entries records entry-level type, not message-level type."""
    log = tmp_path / "session.jsonl"
    lines = [
        json.dumps(
            {
                "type": "user",
                "message": {"type": "user", "content": "Hello"},
                "userType": "external",
                "timestamp": "2026-02-28T10:00:00+00:00",
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hi"}],
                },
                "timestamp": "2026-02-28T10:00:05+00:00",
            }
        ),
    ]
    log.write_text("\n".join(lines))
    result = mine_module.parse_session(log)
    assert result["timed_entries"][0]["type"] == "user"
    assert result["timed_entries"][1]["type"] == "assistant"


def test_parse_assistant_role_fallback(mine_module, tmp_path: Path):
    """When entry has no type but msg.role=assistant, tool_use blocks are extracted."""
    log = tmp_path / "session.jsonl"
    entry = {
        "message": {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "ls"},
                },
            ],
        },
        "timestamp": "2026-02-28T10:00:00+00:00",
    }
    log.write_text(json.dumps(entry))
    result = mine_module.parse_session(log)
    tool_uses = [t for t in result["tool_uses"] if not t["name"].startswith("__")]
    assert len(tool_uses) == 1
    assert tool_uses[0]["name"] == "Bash"


# ── find_project_dirs endswith fix ──


def test_find_project_dirs_no_false_positive(mine_module, tmp_path: Path):
    """Suffix match without dash boundary should not match."""
    base = tmp_path / "projects"
    base.mkdir()
    # "notclaude-trading-skills" ends with "claude-trading-skills" but lacks
    # a dash boundary separating the path segment from the project name.
    (base / "-Users-alice-notclaude-trading-skills").mkdir()
    # This SHOULD match (proper dash boundary)
    (base / "-Users-bob-PycharmProjects-claude-trading-skills").mkdir()

    result = mine_module.find_project_dirs(base, ["claude-trading-skills"])
    assert len(result) == 1
    assert result[0][1].name == "-Users-bob-PycharmProjects-claude-trading-skills"


def test_find_project_dirs_exact_name(mine_module, tmp_path: Path):
    """Directory with exact project name matches."""
    base = tmp_path / "projects"
    base.mkdir()
    (base / "claude-trading-skills").mkdir()

    result = mine_module.find_project_dirs(base, ["claude-trading-skills"])
    assert len(result) == 1
    assert result[0][0] == "claude-trading-skills"


# ── Fix A: _parse_timestamp timezone normalization ──


def test_parse_timestamp_naive_gets_utc(mine_module):
    """Naive timestamps are normalized to UTC-aware."""
    from datetime import timezone

    dt = mine_module._parse_timestamp("2026-03-01T10:00:00")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.tzinfo == timezone.utc


def test_parse_timestamp_aware_preserved(mine_module):
    """Aware timestamps keep their original tzinfo."""
    from datetime import timedelta

    dt = mine_module._parse_timestamp("2026-03-01T10:00:00+09:00")
    assert dt is not None
    assert dt.utcoffset() == timedelta(hours=9)


def test_unresolved_requests_mixed_tz(mine_module):
    """Naive and aware timestamps can be subtracted without TypeError."""
    timed_entries = [
        {"timestamp": "2026-03-01T10:00:00", "type": "user"},
        {"timestamp": "2026-03-01T10:10:00+00:00", "type": "assistant"},
    ]
    result = mine_module._detect_unresolved_requests(timed_entries)
    assert result["count"] == 1  # 10-min gap → unresolved


# ── Fix A2: sidechain contamination ──


def test_sidechain_excluded_from_timed_entries(mine_module, tmp_path: Path):
    """Sidechain messages should not appear in timed_entries."""
    log = tmp_path / "session.jsonl"
    lines = [
        json.dumps(
            {
                "type": "user",
                "message": {"type": "user", "content": "Hello"},
                "userType": "external",
                "timestamp": "2026-03-01T10:00:00+00:00",
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {"type": "assistant", "content": [{"type": "text", "text": "Hi"}]},
                "isSidechain": True,
                "timestamp": "2026-03-01T10:00:05+00:00",
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {"type": "assistant", "content": [{"type": "text", "text": "Real"}]},
                "timestamp": "2026-03-01T10:00:10+00:00",
            }
        ),
    ]
    log.write_text("\n".join(lines))
    result = mine_module.parse_session(log)
    # Sidechain entry should NOT be in timed_entries
    types = [e["type"] for e in result["timed_entries"]]
    assert len(types) == 2  # user + non-sidechain assistant
    assert types == ["user", "assistant"]


# ── Fix A3: end-of-session exclusion ──


def test_unresolved_requests_end_of_session(mine_module):
    """User message at end of session (no following non-user entry) is NOT unresolved."""
    timed_entries = [
        {"timestamp": "2026-03-01T10:00:00+00:00", "type": "user"},
        {"timestamp": "2026-03-01T10:00:05+00:00", "type": "assistant"},
        {"timestamp": "2026-03-01T10:05:00+00:00", "type": "user"},
        # No assistant response after this — end of session
    ]
    result = mine_module._detect_unresolved_requests(timed_entries)
    assert result["count"] == 0  # Last user message should not count


# ── Fix D: MAX_ERROR_OUTPUT_LEN truncation ──


def test_error_output_truncated(mine_module, tmp_path: Path):
    """Long error outputs are truncated to MAX_ERROR_OUTPUT_LEN."""
    log = tmp_path / "session.jsonl"
    long_error = "Error: " + "x" * 1000
    entry = {
        "type": "tool_result",
        "message": {"type": "tool_result", "content": long_error},
        "is_error": True,
        "timestamp": "2026-03-01T10:00:00+00:00",
    }
    log.write_text(json.dumps(entry))
    result = mine_module.parse_session(log)
    error_entries = [t for t in result["tool_uses"] if t["name"] == "__tool_result_error__"]
    assert len(error_entries) == 1
    assert len(error_entries[0]["output"]) <= mine_module.MAX_ERROR_OUTPUT_LEN


def test_error_pattern_output_truncated(mine_module, tmp_path: Path):
    """Error-pattern path (is_error=False) also truncates long output."""
    log = tmp_path / "session.jsonl"
    # Not flagged as is_error, but contains an error pattern
    long_traceback = "Traceback (most recent call last):\n" + "  File x.py\n" * 200
    entry = {
        "type": "tool_result",
        "message": {"type": "tool_result", "content": long_traceback},
        "timestamp": "2026-03-01T10:00:00+00:00",
    }
    log.write_text(json.dumps(entry))
    result = mine_module.parse_session(log)
    error_entries = [t for t in result["tool_uses"] if t["name"] == "__tool_result_error__"]
    assert len(error_entries) == 1
    assert len(error_entries[0]["output"]) <= mine_module.MAX_ERROR_OUTPUT_LEN


# ── Z-suffix timestamp handling (Python 3.10 compatibility) ──


def test_parse_timestamp_z_suffix(mine_module):
    """Timestamps ending with Z are parsed correctly on Python 3.10."""
    from datetime import timezone

    dt = mine_module._parse_timestamp("2026-03-01T10:00:00Z")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 10


def test_parse_timestamp_z_with_millis(mine_module):
    """Z-suffix with milliseconds is also handled."""
    dt = mine_module._parse_timestamp("2026-03-01T10:00:00.123Z")
    assert dt is not None
    assert dt.microsecond == 123000


def test_unresolved_requests_z_timestamps(mine_module):
    """Real session logs use Z-suffix timestamps; detection must work."""
    timed_entries = [
        {"timestamp": "2026-03-01T10:00:00Z", "type": "user"},
        {"timestamp": "2026-03-01T10:10:00Z", "type": "assistant"},
    ]
    result = mine_module._detect_unresolved_requests(timed_entries)
    assert result["count"] == 1  # 10-min gap → unresolved


# ── Response type filtering ──


def test_unresolved_requests_ignores_system_entries(mine_module):
    """system/progress/queue-operation entries do not count as a response."""
    timed_entries = [
        {"timestamp": "2026-03-01T10:00:00+00:00", "type": "user"},
        {"timestamp": "2026-03-01T10:00:01+00:00", "type": "system"},
        {"timestamp": "2026-03-01T10:00:02+00:00", "type": "progress"},
        {"timestamp": "2026-03-01T10:06:00+00:00", "type": "assistant"},
    ]
    result = mine_module._detect_unresolved_requests(timed_entries)
    # system/progress at +1s/+2s are skipped; assistant at +6min is the real response → unresolved
    assert result["count"] == 1


def test_unresolved_requests_tool_result_counts_as_response(mine_module):
    """tool_result entries count as a valid response."""
    timed_entries = [
        {"timestamp": "2026-03-01T10:00:00+00:00", "type": "user"},
        {"timestamp": "2026-03-01T10:00:30+00:00", "type": "tool_result"},
    ]
    result = mine_module._detect_unresolved_requests(timed_entries)
    assert result["count"] == 0  # tool_result within 5 min → resolved


# ── N4: C1 regression test (name→title conversion + id generation) ──


def test_run_converts_name_to_title_and_adds_id(mine_module, tmp_path: Path):
    """run() converts LLM-returned 'name' to 'title' and generates 'id' for each candidate."""
    import types
    from unittest.mock import patch

    import yaml

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    # Candidates as the LLM might return them (with 'name' instead of 'title')
    fake_candidates = [
        {"name": "Auto Reporter", "description": "Automated reports", "priority": "high"},
        {"title": "Already Titled", "description": "Has title", "priority": "low"},
    ]

    # Build minimal args namespace
    args = types.SimpleNamespace(
        output_dir=str(output_dir),
        project=None,
        lookback_days=7,
        dry_run=False,
    )

    # Patch dependencies to isolate the enrichment logic
    with (
        patch.object(mine_module, "find_project_dirs", return_value=[("proj", tmp_path)]),
        patch.object(
            mine_module,
            "list_session_logs",
            return_value=[("proj", tmp_path / "fake.jsonl")],
        ),
        patch.object(
            mine_module,
            "parse_session",
            return_value={
                "user_messages": ["hello"],
                "tool_uses": [],
                "timestamps": [],
                "timed_entries": [],
            },
        ),
        patch.object(mine_module, "abstract_with_llm", return_value=fake_candidates),
    ):
        rc = mine_module.run(args)

    assert rc == 0

    # Read the output file
    output_path = output_dir / "raw_candidates.yaml"
    assert output_path.exists()
    data = yaml.safe_load(output_path.read_text(encoding="utf-8"))

    candidates = data["candidates"]
    assert len(candidates) == 2

    # First candidate: 'name' should be converted to 'title'
    assert "title" in candidates[0]
    assert candidates[0]["title"] == "Auto Reporter"
    assert "name" not in candidates[0]  # 'name' key removed

    # Second candidate: already had 'title', should be untouched
    assert candidates[1]["title"] == "Already Titled"

    # Both should have 'id' assigned
    assert candidates[0]["id"].startswith("raw_")
    assert candidates[1]["id"].startswith("raw_")
    assert candidates[0]["id"] != candidates[1]["id"]


# ── PROJECT_ALLOWLIST ──


def test_project_allowlist_contains_trading_projects(mine_module):
    """Allowlist includes all expected trading-related projects."""
    al = mine_module.PROJECT_ALLOWLIST
    assert "claude-trading-skills" in al
    assert "weekly-trade-strategy" in al
    assert "claude-market-agents" in al
    assert "trade-edge-finder" in al
    assert "trade-strategy-pipeline" in al


# ── filter_non_trading_candidates ──


def test_filter_rejects_developer_tooling_category(mine_module):
    """Candidates with rejected categories are filtered out."""
    candidates = [
        {"title": "code-nav", "category": "developer-tooling", "description": ""},
        {"title": "trade-tool", "category": "trade-execution", "description": ""},
        {"title": "skill-opt", "category": "skill-development", "description": ""},
    ]
    result = mine_module.filter_non_trading_candidates(candidates)
    assert len(result) == 1
    assert result[0]["title"] == "trade-tool"


def test_filter_rejects_broad_off_domain_categories(mine_module):
    """Non-trading categories beyond developer-tooling are also rejected."""
    candidates = [
        {"title": "scheduler", "category": "meeting", "description": "Schedule meetings"},
        {"title": "support-bot", "category": "customer-support", "description": "Handle tickets"},
        {"title": "earnings-tool", "category": "trade-review", "description": "Review trades"},
    ]
    result = mine_module.filter_non_trading_candidates(candidates)
    assert len(result) == 1
    assert result[0]["title"] == "earnings-tool"


def test_filter_rejects_keyword_in_title(mine_module):
    """Candidates with rejected keywords in title are filtered out."""
    candidates = [
        {"title": "codebase-navigator", "category": "other", "description": ""},
        {"title": "earnings-tracker", "category": "trade-review", "description": ""},
    ]
    result = mine_module.filter_non_trading_candidates(candidates)
    assert len(result) == 1
    assert result[0]["title"] == "earnings-tracker"


def test_filter_rejects_keyword_in_description(mine_module):
    """Candidates with rejected keywords in description are filtered out."""
    candidates = [
        {
            "title": "some-tool",
            "category": "other",
            "description": "A git-bulk commit helper",
        },
        {
            "title": "watchlist",
            "category": "trading",
            "description": "Monitor stock prices",
        },
    ]
    result = mine_module.filter_non_trading_candidates(candidates)
    assert len(result) == 1
    assert result[0]["title"] == "watchlist"


def test_filter_passes_all_trading_candidates(mine_module):
    """All trading-related candidates pass through the filter."""
    candidates = [
        {"title": "earnings-reviewer", "category": "trade-review", "description": "Review trades"},
        {"title": "alert-monitor", "category": "trade-execution", "description": "Price alerts"},
    ]
    result = mine_module.filter_non_trading_candidates(candidates)
    assert len(result) == 2


# ── _build_llm_prompt trading_focus ──


def test_build_llm_prompt_trading_focus_true(mine_module):
    """With trading_focus=True, prompt includes trading constraints."""
    prompt = mine_module._build_llm_prompt({}, [], "test-project", trading_focus=True)
    assert "trading and investing skill library" in prompt
    assert "DO NOT propose developer-tooling" in prompt


def test_build_llm_prompt_trading_focus_false(mine_module):
    """With trading_focus=False, prompt is generic (no trading constraints)."""
    prompt = mine_module._build_llm_prompt({}, [], "test-project", trading_focus=False)
    assert "trading and investing skill library" not in prompt
    assert "DO NOT propose developer-tooling" not in prompt
    assert "automate or improve" in prompt


def test_filter_handles_null_fields(mine_module):
    """Filter handles None/null values in category, title, description."""
    candidates = [
        {"title": None, "category": None, "description": None},
        {"title": "valid", "category": "trading", "description": "ok"},
    ]
    result = mine_module.filter_non_trading_candidates(candidates)
    assert len(result) == 2  # None fields don't match any reject rule


def test_filter_handles_non_string_fields(mine_module):
    """Filter handles non-string values (e.g., list, int) without crashing."""
    candidates = [
        {"title": 123, "category": ["a"], "description": True},
        {"title": "valid", "category": "trading", "description": "ok"},
    ]
    result = mine_module.filter_non_trading_candidates(candidates)
    assert len(result) == 2


def test_filter_rejects_name_based_keyword_after_normalization(mine_module):
    """name->title normalization should happen before filter (tested via run)."""
    # Simulate a candidate that used 'name' instead of 'title'
    # After normalization in run(), title should be set
    candidates = [
        {"title": "codebase-navigator", "category": "other", "description": ""},
    ]
    result = mine_module.filter_non_trading_candidates(candidates)
    assert len(result) == 0
