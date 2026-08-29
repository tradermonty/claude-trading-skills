"""Tests for the shared market-calendar generator and authority contract."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def generator():
    return _load(REPO_ROOT / "scripts" / "generate_market_calendar.py", "market_cal_gen")


def test_authority_has_exact_supported_consumer_set(generator):
    config = generator.load_config()
    assert config["requirement"] == "pandas-market-calendars==5.2.2"
    assert set(config["consumers"]) == {
        "breakout-trade-planner",
        "drawdown-circuit-breaker",
        "market-environment-analysis",
        "market-top-detector",
        "parabolic-short-trade-planner",
        "theme-detector",
    }
    assert len(config["example_mirrors"]) == 2
    assert config["additional_requirements"]["drawdown-circuit-breaker"] == ["pyyaml>=6.0"]
    assert "requests>=2.31.0" in config["additional_requirements"]["parabolic-short-trade-planner"]
    assert {"finvizfinance>=1.0.0", "yfinance>=0.2.0"}.issubset(
        config["additional_requirements"]["theme-detector"]
    )


def test_targets_cover_runtime_tests_requirements_and_examples(generator):
    rendered = generator.targets(generator.load_config())
    paths = {path.relative_to(REPO_ROOT).as_posix() for path, _ in rendered}
    assert len(paths) == 25
    assert "scripts/market_calendar/consumers.txt" in paths
    for skill in generator.load_config()["consumers"]:
        assert f"skills/{skill}/scripts/_market_calendar.py" in paths
        assert f"skills/{skill}/scripts/tests/test_market_calendar_contract.py" in paths
        assert f"skills/{skill}/requirements.txt" in paths
    assert all(content.endswith("\n") for _, content in rendered)


def test_pyproject_and_ci_pins_match_authority(generator):
    assert generator.validate_integrations(generator.load_config()) == []


def test_consumer_inventory_is_generated_from_authority(generator):
    config = generator.load_config()
    rendered = dict(generator.targets(config))

    assert rendered[generator.CONSUMER_INVENTORY_PATH].splitlines() == config["consumers"]


def test_validation_rejects_smoke_inventory_drift(generator, monkeypatch):
    monkeypatch.setattr(generator, "_python_dict_keys", lambda path, variable: {"missing-skill"})

    errors = generator.validate_integrations(generator.load_config())

    assert "smoke CLI_PATHS must exactly match the authority consumer inventory" in errors


def test_validation_rejects_workflow_inventory_bypass(generator, monkeypatch):
    original_read_text = generator.Path.read_text

    def fake_read_text(path, *args, **kwargs):
        content = original_read_text(path, *args, **kwargs)
        if path == generator.REPO_ROOT / ".github" / "workflows" / "ci.yml":
            return content.replace(
                "done < scripts/market_calendar/consumers.txt",
                "done < hard-coded-consumers.txt",
            )
        return content

    monkeypatch.setattr(generator.Path, "read_text", fake_read_text)

    errors = generator.validate_integrations(generator.load_config())

    assert "Python 3.9 clean-room CI must read the generated consumer inventory" in errors


def test_requirement_name_detects_range_and_extra_syntax(generator):
    assert generator._requirement_name("Pandas_Market_Calendars>=5.2") == (
        "pandas-market-calendars"
    )
    assert generator._requirement_name("package[extra]~=1.0; python_version >= '3.9'") == "package"


def test_check_mode_passes_for_generated_tree(generator):
    assert generator.main(["--check"]) == 0


def test_check_detects_drift_without_writing(generator, monkeypatch, tmp_path):
    target = tmp_path / "generated.py"
    target.write_text("old\n", encoding="utf-8")
    monkeypatch.setattr(generator, "targets", lambda config: [(target, "new\n")])
    monkeypatch.setattr(generator, "validate_integrations", lambda config: [])
    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    assert generator.main(["--check"]) == 1
    assert target.read_text(encoding="utf-8") == "old\n"


def test_write_mode_repairs_target(generator, monkeypatch, tmp_path):
    target = tmp_path / "nested" / "generated.py"
    monkeypatch.setattr(generator, "targets", lambda config: [(target, "new\n")])
    monkeypatch.setattr(generator, "validate_integrations", lambda config: [])
    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    assert generator.main([]) == 0
    assert target.read_text(encoding="utf-8") == "new\n"


def test_invalid_authority_is_rejected(generator, monkeypatch, tmp_path):
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("schema_version: 2\n", encoding="utf-8")
    monkeypatch.setattr(generator, "CONFIG_PATH", invalid)
    with pytest.raises(ValueError, match="schema_version"):
        generator.load_config()


def test_canonical_runtime_executes_real_provider_contract_when_installed():
    # The repository-scripts row intentionally does not install this optional
    # runtime dependency. Each generated consumer contract exercises the real
    # provider in its own dependency-isolated CI row.
    pytest.importorskip("pandas_market_calendars")
    calendar = _load(
        REPO_ROOT / "scripts" / "market_calendar" / "market_calendar.py",
        "canonical_market_calendar",
    )
    jpx = calendar.session_for_date("XTKS", date(2024, 11, 5))
    nyse = calendar.session_for_date("XNYS", date(2026, 11, 27))
    assert jpx.market_close.strftime("%H:%M") == "15:30"
    assert nyse.market_close.strftime("%H:%M") == "13:00"
