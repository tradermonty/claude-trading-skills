"""Offline CLI regressions using fictional sessions and Claude responses."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import mine_session_logs as miner
import pytest
import score_ideas as scorer
import yaml

NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    home = tmp_path / "fictional-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(miner, "datetime", FixedDatetime)
    monkeypatch.setattr(scorer, "datetime", FixedDatetime)
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected external operation")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    from requests.sessions import Session

    monkeypatch.setattr(Session, "request", forbidden)
    return home


def session(home, project="claude-trading-skills", name="recent", age_days=1):
    directory = home / ".claude" / "projects" / f"-Users-fictional-Projects-{project}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.jsonl"
    entries = [
        {
            "type": "user",
            "userType": "external",
            "timestamp": "2026-10-03T10:00:00Z",
            "message": {"content": "Please automate portfolio risk monitoring"},
        },
        {
            "type": "assistant",
            "timestamp": "2026-10-03T10:01:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "skills/position-sizer/SKILL.md"},
                    }
                ]
            },
        },
    ]
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    stamp = NOW.timestamp() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def cli(monkeypatch, module, *args):
    monkeypatch.setattr(sys, "argv", [module.__file__, *map(str, args)])
    return module.main()


def write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def fake_claude(monkeypatch, *responses):
    remaining = iter(responses)
    calls = []
    monkeypatch.setattr(miner.shutil, "which", lambda name: "claude" if name == "claude" else None)

    def invoke(command, **kwargs):
        assert command[:4] == ["claude", "-p", "--output-format", "json"]
        assert kwargs["timeout"] == 600
        assert "CLAUDECODE" not in kwargs["env"]
        calls.append(kwargs["input"])
        return SimpleNamespace(
            returncode=0, stdout=json.dumps({"result": json.dumps(next(remaining))}), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", invoke)
    return calls


def test_mining_to_scoring_preserves_existing_backlog(monkeypatch, tmp_path, isolated_runtime):
    session(isolated_runtime)
    session(isolated_runtime, name="old", age_days=8)
    session(isolated_runtime, project="unrelated-project")
    monkeypatch.setenv("CLAUDECODE", "fictional-test-marker")
    calls = fake_claude(
        monkeypatch,
        {
            "candidates": [
                {
                    "name": "Risk budget monitor",
                    "description": "Track portfolio drawdown",
                    "category": "risk-management",
                },
                {"title": "Build tooling", "category": "developer-tooling"},
                {
                    "title": "Momentum watch",
                    "description": "Track equity breakouts",
                    "category": "trading",
                },
            ]
        },
        {
            "candidates": [
                {"id": "raw_20261004_001", "novelty": 80, "feasibility": 60, "trading_value": 90},
                {"id": "raw_20261004_003", "novelty": 40, "feasibility": 80, "trading_value": 50},
            ]
        },
    )
    output = tmp_path / "reports"
    assert cli(monkeypatch, miner, "--output-dir", output, "--lookback-days", 7) == 0
    raw = read_yaml(output / "raw_candidates.yaml")
    assert raw["generated_at_utc"] == "2026-10-04T12:00:00+00:00"
    assert raw["sessions_analyzed"] == 1
    assert raw["session_details"][0]["session"] == "recent.jsonl"
    assert raw["session_details"][0]["user_message_count"] == 1
    assert raw["aggregated_signals"]["skill_usage"]["skills"] == {"position-sizer": 1}
    assert [c["id"] for c in raw["candidates"]] == ["raw_20261004_001", "raw_20261004_003"]
    assert raw["candidates"][0]["title"] == "Risk budget monitor"
    assert "name" not in raw["candidates"][0]
    previous = {
        "id": "approved",
        "title": "Tax lot harvest",
        "description": "Realize losses",
        "status": "accepted",
        "pr_url": "https://example.invalid/pr/1",
    }
    backlog = output / "backlog.yaml"
    write_yaml(backlog, {"ideas": [previous]})
    assert (
        cli(
            monkeypatch,
            scorer,
            "--project-root",
            tmp_path,
            "--candidates",
            "reports/raw_candidates.yaml",
            "--backlog",
            "reports/backlog.yaml",
        )
        == 0
    )
    saved = read_yaml(backlog)
    assert saved["ideas"][0] == previous
    assert [i["scores"]["composite"] for i in saved["ideas"][1:]] == [78.0, 56.0]
    assert all(i["status"] == "pending" for i in saved["ideas"][1:])
    assert saved["updated_at_utc"] == "2026-10-04T12:00:00Z"
    assert not list(output.glob(".backlog_*.tmp"))
    assert len(calls) == 2
    assert "Please automate portfolio risk monitoring" in calls[0]
    assert "Build tooling" not in calls[1]


def test_duplicate_cli_and_rerun_preserve_status(monkeypatch, tmp_path):
    write_yaml(
        tmp_path / "input.yaml",
        {
            "candidates": [
                {"id": "skill-copy", "title": "risk monitor", "description": "portfolio drawdown"},
                {"id": "backlog-copy", "title": "dividend tracker", "description": "income yield"},
                {"id": "new", "title": "momentum breakout", "description": "equity volume"},
            ]
        },
    )
    skill = tmp_path / "skills" / "risk" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: risk monitor\ndescription: portfolio drawdown\n---\n", encoding="utf-8"
    )
    existing = {
        "id": "existing",
        "title": "dividend tracker",
        "description": "income yield",
        "status": "accepted",
    }
    write_yaml(tmp_path / "backlog.yaml", {"ideas": [existing]})
    calls = fake_claude(
        monkeypatch,
        {"candidates": [{"id": "new", "novelty": 70, "feasibility": 80, "trading_value": 90}]},
    )
    args = ("--project-root", tmp_path, "--candidates", "input.yaml", "--backlog", "backlog.yaml")
    assert cli(monkeypatch, scorer, *args) == 0
    before = (tmp_path / "backlog.yaml").read_bytes()
    saved = read_yaml(tmp_path / "backlog.yaml")
    assert saved["ideas"][0] == existing
    assert [i["status"] for i in saved["ideas"][1:]] == ["duplicate", "duplicate", "pending"]
    assert saved["ideas"][-1]["scores"]["composite"] == 81.0
    assert "ID: skill-copy" not in calls[0]
    assert "ID: backlog-copy" not in calls[0]
    assert "ID: new" in calls[0]
    assert cli(monkeypatch, scorer, *args) == 0
    assert (tmp_path / "backlog.yaml").read_bytes() == before
    assert len(calls) == 1


def test_mining_dry_run_keeps_real_signals(monkeypatch, tmp_path, isolated_runtime):
    session(isolated_runtime)
    output = tmp_path / "output"
    assert cli(monkeypatch, miner, "--output-dir", output, "--dry-run") == 0
    raw = read_yaml(output / "raw_candidates.yaml")
    assert raw["sessions_analyzed"] == 1
    assert raw["candidates"] == []
    assert raw["aggregated_signals"]["skill_usage"]["count"] == 1


def test_custom_project_allows_nontrading_ideas(monkeypatch, tmp_path, isolated_runtime):
    session(isolated_runtime)
    session(isolated_runtime, project="custom-research")
    calls = fake_claude(
        monkeypatch, {"candidates": [{"title": "Build tooling", "category": "developer-tooling"}]}
    )
    output = tmp_path / "output"
    assert cli(monkeypatch, miner, "--output-dir", output, "--project", "custom-research") == 0
    raw = read_yaml(output / "raw_candidates.yaml")
    assert raw["sessions_analyzed"] == 1
    assert raw["session_details"][0]["project"] == "custom-research"
    assert raw["candidates"][0]["title"] == "Build tooling"
    assert len(calls) == 1


@pytest.mark.parametrize("stale", [False, True])
def test_empty_mining_writes_empty_report(monkeypatch, tmp_path, isolated_runtime, stale):
    if stale:
        session(isolated_runtime, age_days=8)
    output = tmp_path / "output"
    assert cli(monkeypatch, miner, "--output-dir", output, "--lookback-days", 7) == 0
    assert read_yaml(output / "raw_candidates.yaml") == {
        "generated_at_utc": "2026-10-04T12:00:00+00:00",
        "lookback_days": 7,
        "sessions_analyzed": 0,
        "aggregated_signals": {},
        "session_details": [],
        "candidates": [],
    }


def test_scoring_dry_run_writes_zero_scores(monkeypatch, tmp_path):
    write_yaml(tmp_path / "input.yaml", {"candidates": [{"id": "new", "title": "risk monitor"}]})
    assert (
        cli(
            monkeypatch,
            scorer,
            "--project-root",
            tmp_path,
            "--candidates",
            "input.yaml",
            "--backlog",
            "output/backlog.yaml",
            "--dry-run",
        )
        == 0
    )
    idea = read_yaml(tmp_path / "output/backlog.yaml")["ideas"][0]
    assert idea["scores"] == {"novelty": 0, "feasibility": 0, "trading_value": 0, "composite": 0}
    assert idea["status"] == "pending"


@pytest.mark.parametrize(
    "content,exit_code", [(None, 1), ("candidates: [", 1), ("candidates: []", 0)]
)
def test_invalid_or_empty_candidates_preserve_backlog(monkeypatch, tmp_path, content, exit_code):
    if content is not None:
        (tmp_path / "input.yaml").write_text(content, encoding="utf-8")
    backlog = tmp_path / "backlog.yaml"
    write_yaml(backlog, {"ideas": [{"id": "existing", "status": "accepted"}]})
    before = backlog.read_bytes()
    assert (
        cli(
            monkeypatch,
            scorer,
            "--project-root",
            tmp_path,
            "--candidates",
            "input.yaml",
            "--backlog",
            "backlog.yaml",
        )
        == exit_code
    )
    assert backlog.read_bytes() == before
    assert not list(tmp_path.glob(".backlog_*.tmp"))
