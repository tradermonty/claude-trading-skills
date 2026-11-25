"""The scheduled jobs run the claude CLI chosen by scripts/claude_cli.py (#652)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scripts import claude_cli

SCRIPTS = Path(__file__).resolve().parents[1]
NEW = "/opt/native/bin/claude"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_wiring", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def loop():
    return _load("run_skill_improvement_loop")


@pytest.fixture
def pipeline():
    return _load("run_skill_generation_pipeline")


def _choice():
    return claude_cli.ClaudeChoice(
        path=NEW,
        version=(2, 1, 332),
        source="path",
        candidates=[("/opt/homebrew/bin/claude", (2, 0, 69)), (NEW, (2, 1, 332))],
    )


def test_review_runs_the_configured_cli(loop, tmp_path, monkeypatch):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review", encoding="utf-8")
    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd[0])
        body = {"is_error": False, "structured_output": {"score": 80, "findings": []}}
        return CompletedProcess(cmd, 0, json.dumps(body), "")

    monkeypatch.setattr(loop, "CLAUDE_BIN", NEW)
    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    monkeypatch.setattr(loop.shutil, "which", lambda name: name if name == NEW else None)

    assert loop.run_llm_review(tmp_path, "s", str(prompt))["score"] == 80
    assert seen == [NEW]


def test_loop_main_picks_the_newest_cli_and_logs_it(loop, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(loop.claude_cli, "resolve_claude_bin", lambda: _choice())
    seen = {}

    def fake_run(project_root, dry_run=False):
        seen["bin"] = loop.CLAUDE_BIN
        loop.log_claude_choice()
        return 0

    monkeypatch.setattr(loop, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["loop", "--project-root", str(tmp_path)])
    caplog.set_level("INFO")

    assert loop.main() == 0
    assert seen["bin"] == NEW
    assert NEW in caplog.text and "2.0.69" in caplog.text


def test_loop_main_fails_on_an_unusable_pin(loop, tmp_path, monkeypatch, capsys):
    def bad():
        raise claude_cli.ClaudeBinError("SKILL_LOOP_CLAUDE_BIN is not an executable file: x")

    monkeypatch.setattr(loop.claude_cli, "resolve_claude_bin", bad)
    monkeypatch.setattr(loop, "run", lambda *a, **kw: pytest.fail("must not run"))
    monkeypatch.setattr(sys, "argv", ["loop", "--project-root", str(tmp_path)])

    assert loop.main() == 1
    assert "SKILL_LOOP_CLAUDE_BIN" in capsys.readouterr().err


def test_loop_without_any_cli_keeps_the_existing_not_found_path(loop, tmp_path, monkeypatch):
    monkeypatch.setattr(loop.claude_cli, "resolve_claude_bin", lambda: None)
    seen = {}
    monkeypatch.setattr(loop, "run", lambda *a, **kw: seen.setdefault("bin", loop.CLAUDE_BIN) and 0)
    monkeypatch.setattr(sys, "argv", ["loop", "--project-root", str(tmp_path)])

    loop.main()
    assert seen["bin"] == "claude"


@pytest.mark.parametrize("mode", ["daily", "weekly"])
def test_pipeline_main_picks_the_newest_cli(pipeline, tmp_path, monkeypatch, mode):
    monkeypatch.setattr(pipeline.claude_cli, "resolve_claude_bin", lambda: _choice())
    seen = {}

    def fake(project_root, dry_run=False):
        seen["bin"] = pipeline.CLAUDE_BIN
        return 0

    monkeypatch.setattr(pipeline, f"run_{mode}", fake)
    monkeypatch.setattr(sys, "argv", ["p", "--mode", mode, "--project-root", str(tmp_path)])

    assert pipeline.main() == 0
    assert seen["bin"] == NEW


def test_pipeline_main_fails_on_an_unusable_pin(pipeline, tmp_path, monkeypatch, capsys):
    def bad():
        raise claude_cli.ClaudeBinError("SKILL_LOOP_CLAUDE_BIN is not an executable file: x")

    monkeypatch.setattr(pipeline.claude_cli, "resolve_claude_bin", bad)
    monkeypatch.setattr(pipeline, "run_daily", lambda *a, **kw: pytest.fail("must not run"))
    monkeypatch.setattr(sys, "argv", ["p", "--mode", "daily", "--project-root", str(tmp_path)])

    assert pipeline.main() == 1
    assert "SKILL_LOOP_CLAUDE_BIN" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["run_skill_improvement_loop", "run_skill_generation_pipeline"])
def test_no_call_site_hardcodes_the_bare_command(name):
    source = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
    assert '"claude",' not in source
    assert 'shutil.which("claude")' not in source
