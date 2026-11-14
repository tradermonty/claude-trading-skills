"""Missing pandas-market-calendars exits 2 with a requirements.txt hint (#497)."""

import sys
from unittest.mock import MagicMock

import pytest
import screen_momentum_burst as screen


def test_missing_calendar_dependency_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "pandas_market_calendars", None)  # import raises
    monkeypatch.setattr(
        screen, "collect_price_data", MagicMock(side_effect=AssertionError("HTTP before calendar"))
    )
    monkeypatch.setattr(sys, "argv", ["screen", "--symbols", "TEST", "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        screen.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "pandas-market-calendars" in err
    assert "pip install -r" in err
    assert "requirements.txt" in err
    assert list(tmp_path.iterdir()) == []


def test_missing_dependency_error_is_a_calendar_unavailable_error():
    assert issubclass(
        screen.calendar.CalendarDependencyMissingError, screen.calendar.CalendarUnavailableError
    )
