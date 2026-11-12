"""The ``__main__`` entry maps a missing calendar dependency to exit 2 (#497).

Driving the full detector needs live FMP data, so the FMP client is stubbed to
raise the *real* ``CalendarDependencyMissingError`` produced by calling the
skill's shared calendar with ``pandas_market_calendars`` blocked.
"""

import importlib.util
import runpy
import sys
import types
from datetime import date
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "market_top_detector.py"


def _load_calendar(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "_market_calendar", SCRIPTS / "_market_calendar.py"
    )
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "_market_calendar", mod)  # dataclasses needs registration
    spec.loader.exec_module(mod)
    return mod


def test_cli_missing_calendar_dependency_exits_2(monkeypatch, capsys):
    calendar = _load_calendar(monkeypatch)
    monkeypatch.setitem(sys.modules, "pandas_market_calendars", None)  # import raises

    class _Client:
        def __init__(self, *_a, **_kw):
            calendar.count_sessions(
                "XNYS", date(2026, 11, 2), date(2026, 11, 6), include_start=True, include_end=True
            )

    stub = types.ModuleType("fmp_client")
    stub.FMPClient = _Client
    monkeypatch.setitem(sys.modules, "fmp_client", stub)
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--api-key", "x"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "ERROR: pandas-market-calendars library not found" in err
    assert "requirements.txt" in err
