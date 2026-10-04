"""Tests for scripts/smoke_contracts_runner.py (issue #349).

Execution apparatus is isolated behind `run_command`/`create_venv` so these
unit tests monkeypatch them (no real venvs, no real processes, no network).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import check_skill_deps as deps  # noqa: E402
import smoke_contracts_runner as runner  # noqa: E402


def _fake_cmds(commands):
    """Route fake results by (code, out) when '--help' appears in the cmd;
    anything else (pip install, import probes) succeeds."""
    help_code, help_out = commands.get("help", (0, "usage: demo"))

    def run_command(cmd, timeout=120):
        if "--help" in cmd[2:]:
            return help_code, help_out
        return 0, ""

    return run_command


def _manifest(root: Path, skill_id: str, text: str) -> Path:
    skill_dir = root / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    manifest = skill_dir / "requirements.txt"
    manifest.write_text(text, encoding="utf-8")
    return manifest


def _base(root, monkeypatch, created=None):
    _manifest(root, "demo", "demothirdparty>=1.0\n")
    (root / "scripts").mkdir()
    monkeypatch.setattr(
        runner,
        "create_venv",
        (lambda path: created.append(path) or path) if created is not None else (lambda path: path),
    )
    monkeypatch.setattr(runner, "run_command", lambda cmd, timeout=120: (0, "usage: demo"))
    # Fake roots must not see the real table; tests install their own subset.
    monkeypatch.setattr(deps, "SMOKE_CONTRACTS", {})
    monkeypatch.setattr(deps, "PENDING_SMOKE_CONTRACTS", ())


def _demo_script(root: Path) -> Path:
    script = root / "skills/demo/scripts/run.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("print('demo')\n", encoding="utf-8")
    return script


def test_main_exit_zero_all_ok(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    created = []
    _base(root, monkeypatch, created)
    _demo_script(root)
    monkeypatch.setattr(
        deps,
        "SMOKE_CONTRACTS",
        {
            "demo": [
                deps.SmokeContract(
                    script="skills/demo/scripts/run.py",
                    args=("--help",),
                    expect_out=("usage:",),
                )
            ]
        },
    )
    output = tmp_path / "evidence.json"
    assert runner.main(["--output", str(output), "--root", str(root)]) == 0
    evidence = json.loads(output.read_text())
    (demo_row,) = [row for row in evidence["skills"] if row["id"] == "demo"]
    assert demo_row["ok"] is True
    (contract,) = demo_row["contracts"]
    assert contract["expect_out_match"] is True
    assert created == [root / ".venv-smoke-demo"]


def test_main_exit_one_on_contract_expectation_miss(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _base(root, monkeypatch)
    _demo_script(root)
    monkeypatch.setattr(
        deps,
        "SMOKE_CONTRACTS",
        {"demo": [deps.SmokeContract(script="skills/demo/scripts/run.py", args=("--help",))]},
    )
    monkeypatch.setattr(runner, "run_command", _fake_cmds({"help": (1, "boom")}))
    output = tmp_path / "evidence.json"
    assert runner.main(["--output", str(output), "--root", str(root)]) == 1
    evidence = json.loads(output.read_text())
    (demo_row,) = [row for row in evidence["skills"] if row["id"] == "demo"]
    assert demo_row["ok"] is False
    assert any("expect_exit" in err for err in demo_row["errors"])


def test_main_exit_one_on_harness_error(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _base(root, monkeypatch)

    def broken_create(path):
        raise RuntimeError("venv boom")

    monkeypatch.setattr(runner, "create_venv", broken_create)
    monkeypatch.setattr(deps, "PENDING_SMOKE_CONTRACTS", ("demo",))
    output = tmp_path / "evidence.json"
    assert runner.main(["--output", str(output), "--root", str(root)]) == 1
    evidence = json.loads(output.read_text())
    (demo_row,) = [row for row in evidence["skills"] if row["id"] == "demo"]
    assert demo_row["ok"] is False
    assert any("harness error" in err for err in demo_row["errors"])


def test_main_exit_one_on_expect_out_mismatch(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _base(root, monkeypatch)
    _demo_script(root)
    monkeypatch.setattr(
        deps,
        "SMOKE_CONTRACTS",
        {
            "demo": [
                deps.SmokeContract(
                    script="skills/demo/scripts/run.py",
                    args=("--help",),
                    expect_out=("usage:", "--required-flag-that-is-absent"),
                )
            ]
        },
    )
    output = tmp_path / "evidence.json"
    assert runner.main(["--output", str(output), "--root", str(root)]) == 1
    evidence = json.loads(output.read_text())
    (demo_row,) = [row for row in evidence["skills"] if row["id"] == "demo"]
    (contract,) = demo_row["contracts"]
    assert contract["expect_out_match"] is False
    assert any("missing expected output" in err for err in demo_row["errors"])


def test_main_exit_one_on_table_validation_problem(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _manifest(root, "demo", "demothirdparty>=1.0\n")
    (root / "scripts").mkdir()
    monkeypatch.setattr(
        deps,
        "SMOKE_CONTRACTS",
        {"nosuchskill": [deps.SmokeContract(script="", args=(), skip_reason="x")]},
    )
    output = tmp_path / "evidence.json"
    assert runner.main(["--output", str(output), "--root", str(root)]) == 1
    evidence = json.loads(output.read_text())
    assert any("unknown skill" in p for p in evidence["table_problems"])


def test_pending_skills_recorded_without_contract_failure(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _base(root, monkeypatch)
    monkeypatch.setattr(deps, "PENDING_SMOKE_CONTRACTS", ("demo",))
    output = tmp_path / "evidence.json"
    assert runner.main(["--output", str(output), "--root", str(root)]) == 0
    evidence = json.loads(output.read_text())
    (demo_row,) = [row for row in evidence["skills"] if row["id"] == "demo"]
    assert demo_row["contracts_status"] == "pending_wave2"
    assert demo_row["ok"] is True


def test_skip_contract_recorded_as_skipped(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _base(root, monkeypatch)
    _demo_script(root)
    monkeypatch.setattr(
        deps,
        "SMOKE_CONTRACTS",
        {"demo": [deps.SmokeContract(script="", args=(), skip_reason="windows-only MT5 terminal")]},
    )
    output = tmp_path / "evidence.json"
    assert runner.main(["--output", str(output), "--root", str(root)]) == 0
    evidence = json.loads(output.read_text())
    (demo_row,) = [row for row in evidence["skills"] if row["id"] == "demo"]
    assert demo_row["ok"] is True
    (skip,) = demo_row["contracts"]
    assert skip["skipped"] is True and skip["skip_reason"]
