"""Guard root collection coverage and cross-skill import identity."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from scripts.ci_test_matrix import discover

ROOT = Path(__file__).resolve().parents[2]


def test_root_testpaths_cover_matrix(pytestconfig):
    expected = {path for entry in discover(ROOT).values() for path in entry.test_paths}
    assert set(pytestconfig.getini("testpaths")) == expected


@pytest.mark.parametrize("fails", [False, True])
def test_shared_scenarios_restore_foreign_imports(tmp_path, monkeypatch, fails):
    spec = importlib.util.spec_from_file_location(
        "dividend_isolation", ROOT / "scripts/tests/_dividend_fmp_scenarios.py"
    )
    scenarios = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scenarios)
    (tmp_path / "fmp_client.py").write_text("class FMPClient: pass\n")
    (tmp_path / "consumer.py").write_text("from fmp_client import FMPClient\n")
    foreign = ModuleType("fmp_client")
    consumer = ModuleType("consumer")
    monkeypatch.setitem(sys.modules, "fmp_client", foreign)
    monkeypatch.setitem(sys.modules, "consumer", consumer)
    before = sys.path[:]

    def check_imports(folder, module_name):
        import importlib

        sys.path.insert(0, str(folder))
        loaded = importlib.import_module(module_name)
        transport = importlib.import_module("fmp_client")
        assert loaded is not consumer and transport is not foreign
        assert loaded.FMPClient is transport.FMPClient
        if fails:
            raise AssertionError("scenario failure")

    with patch.object(scenarios, "_run_scenarios", check_imports):
        if fails:
            with pytest.raises(AssertionError, match="scenario failure"):
                scenarios.run_scenarios(tmp_path, "consumer")
        else:
            scenarios.run_scenarios(tmp_path, "consumer")
    assert sys.path == before
    assert sys.modules["fmp_client"] is foreign
    assert sys.modules["consumer"] is consumer


def test_skill_switch_restores_original_class_identity(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("root_isolation", ROOT / "conftest.py")
    isolation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(isolation)
    monkeypatch.setattr(isolation, "_SKILLS_MARKER", str(tmp_path) + "/")
    monkeypatch.setattr(isolation, "_CONFLICTING_BASENAMES", {"shared"})
    modules = []
    skills = []
    for name in ("a", "b"):
        skill = tmp_path / name
        (skill / "scripts").mkdir(parents=True)
        (skill / "SKILL.md").touch()
        module = ModuleType("shared")
        module.__file__ = str(skill / "scripts/shared.py")
        module.Client = type("Client", (), {})
        modules.append(module)
        skills.append(skill)
    monkeypatch.setattr(sys, "path", sys.path[:])
    monkeypatch.setitem(sys.modules, "shared", modules[0])
    isolation._activate_skill(skills[0], str(skills[0] / "scripts/tests"))
    custom_path = str(skills[0] / "scripts/calculators")
    sys.path.insert(0, custom_path)
    original_class = sys.modules["shared"].Client
    isolation._activate_skill(skills[1], str(skills[1] / "scripts/tests"))
    assert "shared" not in sys.modules
    assert custom_path not in sys.path
    sys.modules["shared"] = modules[1]
    isolation._activate_skill(skills[0], str(skills[0] / "scripts/tests"))
    assert custom_path in sys.path
    assert sys.modules["shared"] is modules[0]
    assert sys.modules["shared"].Client is original_class
    isolation._activate_skill(skills[1], str(skills[1] / "scripts/tests"))
    assert sys.modules["shared"] is modules[1]


def test_namespace_package_isolated_from_foreign_regular_package(tmp_path, monkeypatch):
    import importlib

    spec = importlib.util.spec_from_file_location("root_namespace", ROOT / "conftest.py")
    isolation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(isolation)
    monkeypatch.setattr(isolation, "_SKILLS_MARKER", str(tmp_path) + "/")
    monkeypatch.setattr(isolation, "_CONFLICTING_BASENAMES", {"shared_namespace"})
    skills = [tmp_path / name for name in ("namespace", "regular")]
    for skill in skills:
        package = skill / "scripts/shared_namespace"
        package.mkdir(parents=True)
        (skill / "SKILL.md").touch()
        (package / "child.py").write_text("class Client: pass\n")
    (skills[1] / "scripts/shared_namespace/__init__.py").touch()
    monkeypatch.setattr(sys, "path", [str(s / "scripts") for s in skills] + sys.path)
    monkeypatch.delitem(sys.modules, "shared_namespace", raising=False)
    monkeypatch.delitem(sys.modules, "shared_namespace.child", raising=False)
    try:
        isolation._activate_skill(skills[0], str(skills[0] / "scripts/tests"))
        original = importlib.import_module("shared_namespace.child")
        assert str(skills[0]) in original.__file__
        isolation._activate_skill(skills[1], str(skills[1] / "scripts/tests"))
        other = importlib.import_module("shared_namespace.child")
        assert str(skills[1]) in other.__file__
        isolation._activate_skill(skills[0], str(skills[0] / "scripts/tests"))
        assert importlib.import_module("shared_namespace.child") is original
    finally:
        sys.modules.pop("shared_namespace.child", None)
        sys.modules.pop("shared_namespace", None)


def test_runbook_full_suite_command_includes_ci_extra():
    """The documented full root run must install and use the ci extra (PIL, statsmodels)."""
    text = (ROOT / "docs/dev/maintenance-runbook.md").read_text(encoding="utf-8")
    assert "uv sync --extra dev --extra ci" in text
    assert "uv run --extra dev --extra ci pytest -q" in text
    stripped = text.replace("uv sync --extra dev --extra ci", "")
    assert "uv sync --extra dev" not in stripped
    assert "uv run pytest -q" not in text


def test_activate_skill_does_not_touch_unrelated_modules(monkeypatch):
    """_activate_skill must check the module name before reading attributes."""
    spec = importlib.util.spec_from_file_location("conftest_under_test", ROOT / "conftest.py")
    conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conf)
    touched = []

    class Lazy(ModuleType):
        def __getattr__(self, attr):
            touched.append(attr)
            raise RuntimeError("lazy module attribute access")

    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(sys.modules, "unrelated_lazy_module_xyz", Lazy("unrelated_lazy_module_xyz"))
    skill = ROOT / "skills" / "position-sizer"
    conf._activate_skill(skill, str(skill / "scripts" / "tests"))
    assert touched == []
