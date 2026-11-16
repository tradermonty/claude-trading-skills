"""Missing-dependency hint is correct for the canonical file and generated copies (#497)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path, name: str, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, mod)  # dataclasses needs the module registered
    spec.loader.exec_module(mod)
    return mod


def test_canonical_hint_is_generic_not_a_nonexistent_path(monkeypatch):
    mod = _load(
        ROOT / "scripts" / "market_calendar" / "market_calendar.py", "mc_canonical", monkeypatch
    )
    monkeypatch.setitem(sys.modules, "pandas_market_calendars", None)
    with pytest.raises(mod.CalendarDependencyMissingError) as exc:
        mod.session_for_date("XNYS", __import__("datetime").date(2026, 11, 6))
    message = str(exc.value)
    assert "<this skill's>/requirements.txt" in message
    assert not (ROOT / "scripts" / "requirements.txt").exists()


def test_generated_copy_hint_names_existing_requirements_file(monkeypatch):
    skill = ROOT / "skills" / "breakout-trade-planner"
    mod = _load(skill / "scripts" / "_market_calendar.py", "mc_generated", monkeypatch)
    monkeypatch.setitem(sys.modules, "pandas_market_calendars", None)
    with pytest.raises(mod.CalendarDependencyMissingError) as exc:
        mod.session_for_date("XNYS", __import__("datetime").date(2026, 11, 6))
    assert f"pip install -r {skill / 'requirements.txt'}" in str(exc.value)
    assert (skill / "requirements.txt").is_file()
