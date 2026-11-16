"""The ``__main__`` entry maps a missing calendar dependency to exit 2 (#497).

The full run needs live market data, so the theme-config loader is stubbed to
raise the *real* ``CalendarDependencyMissingError`` produced by calling the
shared calendar with ``pandas_market_calendars`` blocked.
"""

import runpy
import sys
from datetime import date
from pathlib import Path

import _market_calendar
import config_loader
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "theme_detector.py"


def test_cli_missing_calendar_dependency_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.setitem(sys.modules, "pandas_market_calendars", None)  # import raises

    def _raise(*_a, **_kw):
        _market_calendar.count_sessions(
            "XNYS", date(2026, 11, 2), date(2026, 11, 6), include_start=True, include_end=True
        )

    monkeypatch.setattr(config_loader, "load_themes_config", _raise)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--output-dir", str(tmp_path / "out")])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "ERROR: pandas-market-calendars library not found" in err
    assert "requirements.txt" in err
