"""Tests for the explicit clean-environment import smoke."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import scripts.check_isolated_skill_imports as smoke

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_fixture(
    root: Path,
    *,
    requirements: str = "# stdlib-only\n",
    modules: tuple[str, ...] = ("entry",),
    timeout: int = 600,
) -> Path:
    scripts_dir = root / "skills" / "demo-skill" / "scripts"
    scripts_dir.mkdir(parents=True)
    for module in modules:
        (scripts_dir / f"{module}.py").write_text("VALUE = 1\n", encoding="utf-8")
    (scripts_dir.parent / "requirements.txt").write_text(requirements, encoding="utf-8")
    config = root / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "timeout_seconds": timeout,
                "skills": {"demo-skill": {"modules": list(modules)}},
            }
        ),
        encoding="utf-8",
    )
    return config


def test_repository_inventory_is_explicit_and_complete():
    plan, errors = smoke.load_plan(REPO_ROOT)
    assert errors == []
    assert plan is not None
    assert plan.timeout_seconds == 600
    assert plan.skills == {
        "position-sizer": ("position_sizer",),
        "futures-position-sizer": ("futures_position_sizer", "futures_sizing"),
        "trader-memory-core": (
            "trader_memory_cli",
            "thesis_store",
            "thesis_ingest",
            "thesis_review",
        ),
        "drawdown-circuit-breaker": ("check_circuit_breaker",),
        "trading-skills-navigator": ("recommend", "build_snapshot", "intent_benchmark"),
    }
    for skill_id, modules in plan.skills.items():
        for module in modules:
            assert (REPO_ROOT / "skills" / skill_id / "scripts" / f"{module}.py").is_file()


def test_stdlib_only_skill_is_still_imported_in_isolated_uv(tmp_path: Path):
    config = _write_fixture(tmp_path)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    assert smoke.check(root=tmp_path, config_path=config, run=fake_run) == 0
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:4] == ["uv", "run", "--isolated", "--no-project"]
    assert "--with" not in command
    assert "importlib.import_module('entry')" in command[-1]
    assert kwargs["timeout"] == 600


def test_each_module_gets_an_independent_process_with_declared_dependencies(tmp_path: Path):
    config = _write_fixture(
        tmp_path,
        requirements="requests>=2.31.0\n",
        modules=("entry", "worker"),
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    assert smoke.check(root=tmp_path, config_path=config, run=fake_run) == 0
    assert len(calls) == 2
    assert all(command[4:6] == ["--with", "requests>=2.31.0"] for command in calls)
    assert "importlib.import_module('entry')" in calls[0][-1]
    assert "importlib.import_module('worker')" in calls[1][-1]


def test_timeout_is_reported_as_failure(tmp_path: Path, capsys):
    config = _write_fixture(tmp_path)

    def timeout_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    assert smoke.check(root=tmp_path, config_path=config, run=timeout_run) == 1
    assert "timed out after 600 seconds" in capsys.readouterr().out


def test_missing_configured_module_fails_before_starting_uv(tmp_path: Path):
    config = _write_fixture(tmp_path)
    (tmp_path / "skills/demo-skill/scripts/entry.py").unlink()
    called = False

    def fake_run(command, **kwargs):
        nonlocal called
        called = True
        return subprocess.CompletedProcess(command, 0, "", "")

    assert smoke.check(root=tmp_path, config_path=config, run=fake_run) == 1
    assert called is False


def test_invalid_config_fails_closed(tmp_path: Path, capsys):
    config = tmp_path / "bad.json"
    config.write_text(
        '{"schema_version":2,"timeout_seconds":0,"skills":{"Bad Skill":{"modules":[]}}}',
        encoding="utf-8",
    )
    assert smoke.check(root=tmp_path, config_path=config) == 1
    output = capsys.readouterr().out
    assert "schema_version must be 1" in output
    assert "timeout_seconds" in output
    assert "invalid skill id" in output


def test_root_schema_rejects_non_integer_version_and_unknown_keys(tmp_path: Path):
    for index, payload in enumerate(
        (
            {
                "schema_version": True,
                "timeout_seconds": 600,
                "skills": {"demo-skill": {"modules": ["entry"]}},
            },
            {
                "schema_version": 1.0,
                "timeout_seconds": 600,
                "skills": {"demo-skill": {"modules": ["entry"]}},
            },
            {
                "schema_version": 1,
                "timeout_seconds": 600,
                "skills": {"demo-skill": {"modules": ["entry"]}},
                "timeout_second": 600,
            },
        )
    ):
        config = tmp_path / f"bad-{index}.json"
        config.write_text(json.dumps(payload), encoding="utf-8")
        plan, errors = smoke.load_plan(tmp_path, config)
        assert plan is None
        assert errors
