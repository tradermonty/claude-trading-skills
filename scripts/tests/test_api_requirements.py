"""Offline API metadata/source/profile contracts (Issue #653)."""

from __future__ import annotations

import importlib.util
import json
import runpy
import socket
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def checker():
    spec = importlib.util.spec_from_file_location(
        "api_requirements", ROOT / "scripts/check_api_requirements.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project(tmp_path, source, integrations=None):
    scripts = tmp_path / "skills/example/scripts"
    scripts.mkdir(parents=True)
    (scripts / "main.py").write_text(source)
    (tmp_path / "skills-index.yaml").write_text(
        yaml.safe_dump(
            {
                "skills": [
                    {"id": "example", "status": "production", "integrations": integrations or []}
                ]
            }
        )
    )
    return scripts


@pytest.mark.parametrize(
    "source",
    [
        'import os\nx=os.getenv("FMP_API_KEY")',
        'import os as system\nx=system.environ.get("FMP_API_KEY")',
        'from os import getenv as read\nx=read("FMP_API_KEY")',
        'from os import environ as env\nx=env["FMP_API_KEY"]',
        'from os import environ\nx=environ.get("FMP_API_KEY")',
    ],
)
def test_literal_environment_reads_require_provider(tmp_path, source):
    project(tmp_path, source)
    errors = checker().check(tmp_path)
    assert any("API001" in e and "fmp" in e and "main.py:2" in e for e in errors)


@pytest.mark.parametrize(
    "key,provider",
    [
        ("FINVIZ_API_KEY", "finviz"),
        ("ALPACA_API_KEY", "alpaca"),
        ("ALPACA_SECRET_KEY", "alpaca"),
        ("APCA_API_KEY_ID", "alpaca"),
        ("APCA_API_SECRET_KEY", "alpaca"),
    ],
)
def test_other_paid_credentials(tmp_path, key, provider):
    project(tmp_path, f"import os\nx=os.environ.get({key!r})")
    assert any(provider in e for e in checker().check(tmp_path))


def test_documentation_constants_and_noncredential_config_are_not_reads(tmp_path):
    project(
        tmp_path,
        '''import os
"""FMP_API_KEY, FINVIZ_API_KEY"""
pattern = "ALPACA_API_KEY"
x = os.environ.get("ALPACA_PAPER")
''',
    )
    assert checker().check(tmp_path) == []


@pytest.mark.parametrize(
    "requirement", ["required", "recommended", "optional", "not_required", "unknown"]
)
def test_declared_provider_contract(tmp_path, requirement):
    project(
        tmp_path,
        'import os\nx=os.getenv("FMP_API_KEY")',
        [{"id": "fmp", "requirement": requirement}],
    )
    assert bool(checker().check(tmp_path)) == (requirement in ["not_required", "unknown"])


def test_nested_vendored_read_is_checked_but_tests_are_excluded(tmp_path):
    scripts = project(tmp_path, "pass")
    for sub in ("tests/test_fake.py", "test_fake.py"):
        p = scripts / sub
        p.parent.mkdir(exist_ok=True)
        p.write_text('import os\nos.getenv("FMP_API_KEY")')
    assert checker().check(tmp_path) == []
    p = scripts / "vendor/client.py"
    p.parent.mkdir()
    p.write_text('import os\nos.getenv("FMP_API_KEY")')
    assert any("vendor/client.py:2" in e for e in checker().check(tmp_path))


def test_syntax_error_is_a_failure(tmp_path):
    project(tmp_path, "def broken(")
    assert any("API003" in e for e in checker().check(tmp_path))


@pytest.mark.parametrize("optional", [False, True])
def test_no_api_profile_rejects_even_optional_paid_step(tmp_path, optional):
    project(tmp_path, "pass", [{"id": "fmp", "requirement": "required"}])
    (tmp_path / "workflows").mkdir()
    p = tmp_path / "workflows/flow.yaml"
    w = {
        "id": "flow",
        "api_profile": "no-api-basic",
        "steps": [{"step": 1, "skill": "example", "optional": optional}],
    }
    p.write_text(yaml.safe_dump(w))
    assert any("API002" in e for e in checker().check(tmp_path))
    w["api_profile"] = "mixed"
    p.write_text(yaml.safe_dump(w))
    assert checker().check(tmp_path) == []


def test_real_metadata_matches_all_credential_readers():
    assert checker().check(ROOT) == []


@pytest.mark.parametrize(
    "skill,filename",
    [
        ("market-top-detector", "market_top_detector.py"),
        ("downtrend-duration-analyzer", "analyze_downtrends.py"),
    ],
)
def test_required_cli_missing_key_matches_metadata_without_network(
    tmp_path, monkeypatch, capsys, skill, filename
):
    index = yaml.safe_load((ROOT / "skills-index.yaml").read_text())
    entry = next(s for s in index["skills"] if s["id"] == skill)
    assert any(i["id"] == "fmp" and i["requirement"] == "required" for i in entry["integrations"])
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    blocked = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    script = ROOT / "skills" / skill / "scripts" / filename
    monkeypatch.syspath_prepend(str(script.parent))
    # Imported sibling names are shared across skill scripts; isolate this CLI.
    for name in ("fmp_client", "utils", "calculators", "report_generator"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "argv", [str(script), "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert exc.value.code == 1
    assert "FMP" in capsys.readouterr().err
    blocked.assert_not_called()


def test_optional_postmortem_cli_without_key_is_offline(tmp_path, monkeypatch):
    entry = next(
        s
        for s in yaml.safe_load((ROOT / "skills-index.yaml").read_text())["skills"]
        if s["id"] == "signal-postmortem"
    )
    assert any(i["id"] == "fmp" and i["requirement"] == "optional" for i in entry["integrations"])
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    blocked = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(socket.socket, "connect", blocked)
    script = ROOT / "skills/signal-postmortem/scripts/postmortem_recorder.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "--signal-id",
            "manual_AAPL_2026-01-01",
            "--exit-price",
            "101",
            "--exit-date",
            "2026-01-10",
            "--output-dir",
            str(tmp_path),
        ],
    )
    runpy.run_path(str(script), run_name="__main__")
    records = list((tmp_path / "postmortems").glob("*.json"))
    assert len(records) == 1
    assert json.loads(records[0].read_text())["ticker"] == "AAPL"
    blocked.assert_not_called()


def test_gate_is_wired_to_precommit_and_ci():
    hooks = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    hook = next(
        h for repo in hooks["repos"] for h in repo["hooks"] if h["id"] == "api-requirements"
    )
    assert hook["entry"] == "python3 scripts/check_api_requirements.py"
    assert hook["always_run"] is True and hook["pass_filenames"] is False
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert any(
        step.get("run") == "python3 scripts/check_api_requirements.py"
        for job in ci["jobs"].values()
        for step in job.get("steps", [])
    )


def test_market_regime_mixed_profile_retains_key_free_base():
    workflow = yaml.safe_load((ROOT / "workflows/market-regime-daily.yaml").read_text())
    entries = {
        s["id"]: s for s in yaml.safe_load((ROOT / "skills-index.yaml").read_text())["skills"]
    }
    assert workflow["api_profile"] == "mixed"
    assert workflow["required_skills"] == [
        "market-breadth-analyzer",
        "uptrend-analyzer",
        "exposure-coach",
    ]
    for sid in workflow["required_skills"]:
        assert not any(
            i["id"] in {"fmp", "finviz", "alpaca"} and i["requirement"] == "required"
            for i in entries[sid]["integrations"]
        )
    top = next(s for s in workflow["steps"] if s["skill"] == "market-top-detector")
    assert top["step"] == 3 and top["optional"] is True and top["produces"] == ["top_risk_report"]
    assert "FMP" in top["name"] and "FMP" in top["name_ja"]


def test_market_regime_skillset_matches_mixed_workflow_without_paid_base():
    workflow = yaml.safe_load((ROOT / "workflows/market-regime-daily.yaml").read_text())
    skillset = yaml.safe_load((ROOT / "skillsets/market-regime.yaml").read_text())
    assert skillset["api_profile"] == workflow["api_profile"] == "mixed"
    assert skillset["required_skills"] == workflow["required_skills"]
    assert "market-top-detector" in skillset["recommended_skills"]
    assert "downtrend-duration-analyzer" in skillset["optional_skills"]


@pytest.mark.parametrize("skill", ["market-top-detector", "downtrend-duration-analyzer"])
@pytest.mark.parametrize("locale", ["en", "ja"])
def test_manual_required_fmp_skill_guides_match_declarations(skill, locale):
    """Manual pages are outside the doc generator; keep the reported gap guarded."""
    text = (ROOT / "docs" / locale / "skills" / f"{skill}.md").read_text(encoding="utf-8")
    expected = "FMP Required" if locale == "en" else "FMP必須"
    assert f'<span class="badge badge-api">{expected}</span>' in text
    assert 'badge-free">No API' not in text
    assert 'badge-free">API不要' not in text
    assert "**API Key:** None required" not in text
    assert "**APIキー:** 不要" not in text
    # Prose that makes the key optional contradicts a required declaration.
    assert "API なしでも" not in text and "APIなしでも" not in text
    assert "FMP API を使う場合" not in text and "FMP APIを使う場合" not in text
