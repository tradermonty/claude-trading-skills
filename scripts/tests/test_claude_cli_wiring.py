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

    def fake_run(project_root, dry_run=False, force=False):
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


@pytest.mark.parametrize("selection", ["newest", "pin"])
def test_weekly_children_execute_selected_cli(pipeline, tmp_path, monkeypatch, selection):
    """Run real Python children and real LLM functions, with fake CLIs only."""
    import os

    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    trace = tmp_path / "calls.jsonl"

    def executable(path, version):
        path.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            f"version = {version!r}\n"
            "if '--version' in sys.argv:\n"
            "    print(version)\n"
            "else:\n"
            "    assert 'CLAUDECODE' not in os.environ\n"
            "    with Path(os.environ['CLI_TRACE']).open('a') as stream:\n"
            "        stream.write(json.dumps(sys.argv[0]) + '\\n')\n"
            "    print(json.dumps({'candidates': [{'id': 'idea', 'title': 'Test', "
            "'novelty': 80, 'feasibility': 80, 'trading_value': 80}]}))\n",
            encoding="utf-8",
        )
        path.chmod(0o755)

    old = old_dir / "claude"
    newest = new_dir / "claude"
    executable(old, "2.0.69")
    executable(newest, "2.1.332")
    monkeypatch.setenv("PATH", os.pathsep.join([str(old_dir), str(new_dir)]))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLI_TRACE", str(trace))
    monkeypatch.setenv("CLAUDECODE", "nested-terminal")
    monkeypatch.delenv("SKILL_LOOP_CLAUDE_BIN", raising=False)
    selected = newest
    if selection == "pin":
        selected = new_dir / "pinned-cli"
        executable(selected, "1.0.0")
        monkeypatch.setenv("SKILL_LOOP_CLAUDE_BIN", str(selected))

    assert pipeline.configure_claude_cli()
    assert pipeline.CLAUDE_BIN == str(selected)

    # Tiny child entrypoints call the real packaged skill functions. They avoid
    # touching the maintainer's sessions, backlog or paid Claude installation.
    skill_scripts = SCRIPTS.parent / "skills" / "skill-idea-miner" / "scripts"
    mine = tmp_path / pipeline.MINE_SCRIPT
    mine.parent.mkdir(parents=True)
    mine.write_text(
        "import json, runpy, sys\nfrom pathlib import Path\n"
        f"module = runpy.run_path({str(skill_scripts / 'mine_session_logs.py')!r})\n"
        "candidates = module['abstract_with_llm']({}, [], 'fixture')\n"
        "assert candidates and candidates[0]['id'] == 'idea'\n"
        "out = Path(sys.argv[sys.argv.index('--output-dir') + 1])\n"
        "(out / 'raw_candidates.yaml').write_text(json.dumps({'candidates': candidates}))\n",
        encoding="utf-8",
    )
    score = tmp_path / pipeline.SCORE_SCRIPT
    score.write_text(
        "import json, runpy, sys\nfrom pathlib import Path\n"
        f"module = runpy.run_path({str(skill_scripts / 'score_ideas.py')!r})\n"
        "source = Path(sys.argv[sys.argv.index('--candidates') + 1])\n"
        "result = module['score_with_llm'](json.loads(source.read_text())['candidates'])\n"
        "assert result[0]['scores']['composite'] == 80\n",
        encoding="utf-8",
    )

    candidates = pipeline.run_mine(tmp_path)
    assert candidates is not None
    assert pipeline.run_score(tmp_path, candidates)
    assert [json.loads(line) for line in trace.read_text().splitlines()] == [
        str(selected),
        str(selected),
    ]
    assert os.environ["PATH"].split(os.pathsep)[0] == str(old_dir)
