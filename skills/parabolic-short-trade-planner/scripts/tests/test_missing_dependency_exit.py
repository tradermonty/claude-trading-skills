"""Alpaca paths without ``requests`` exit 2 with a requirements.txt hint (#497)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import generate_pre_market_plan as g2
import monitor_intraday_trigger as mit
import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def no_requests(monkeypatch):
    """Make ``import requests`` fail and force the Alpaca adapters to re-import."""
    monkeypatch.setitem(sys.modules, "requests", None)
    for name in ("alpaca_inventory_adapter", "alpaca_market_data_adapter"):
        monkeypatch.delitem(sys.modules, name, raising=False)


def _plan_argv(tmp_path):
    phase1 = tmp_path / "phase1.json"
    phase1.write_text(
        json.dumps({"schema_version": "1.0", "as_of": "2026-04-30", "candidates": []}),
        encoding="utf-8",
    )
    return [
        "--candidates-json",
        str(phase1),
        "--broker",
        "alpaca",
        "--output-dir",
        str(tmp_path),
        "--ssr-state-dir",
        str(tmp_path / "ssr"),
    ]


def test_generate_plan_without_credentials_does_not_need_requests(
    no_requests, monkeypatch, tmp_path
):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    # No credentials: falls back to the manual checklist, so requests is not required.
    assert g2.main(_plan_argv(tmp_path)) == 0


def test_generate_plan_alpaca_broker_without_requests_exits_2(
    no_requests, monkeypatch, capsys, tmp_path
):
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")  # pragma: allowlist secret
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")  # pragma: allowlist secret
    rc = g2.main(_plan_argv(tmp_path))
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR: requests library not found" in captured.err
    assert "requirements.txt" in captured.err
    assert "--broker none" in captured.err
    assert captured.out == ""


@pytest.fixture
def no_calendar(monkeypatch):
    monkeypatch.setitem(sys.modules, "pandas_market_calendars", None)  # import raises


def _run_main_block(script: str, argv: list[str], monkeypatch):
    import runpy

    path = Path(__file__).resolve().parents[1] / script
    monkeypatch.setattr(sys, "argv", [str(path), *argv])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(path), run_name="__main__")
    return exc.value.code


def test_monitor_cli_without_calendar_dependency_exits_2(
    no_calendar, monkeypatch, capsys, tmp_path
):
    code = _run_main_block(
        "monitor_intraday_trigger.py",
        [
            "--plans-json",
            str(FIXTURES / "phase2_plan_smoke.json"),
            "--bars-source",
            "fixture",
            "--bars-fixture",
            str(FIXTURES / "intraday_bars" / "orl_clean_break.json"),
            "--state-dir",
            str(tmp_path / "state"),
            "--output-dir",
            str(tmp_path / "out"),
            "--as-of",
            "2026-05-05",
            "--now-et",
            "2026-05-05T10:00:00-04:00",
        ],
        monkeypatch,
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "ERROR: pandas-market-calendars library not found" in err
    assert "requirements.txt" in err


def test_plan_cli_without_calendar_dependency_exits_2(no_calendar, monkeypatch, capsys, tmp_path):
    from test_generate_pre_market_plan import _phase1_json

    code = _run_main_block(
        "generate_pre_market_plan.py",
        [
            "--candidates-json",
            _phase1_json(tmp_path),
            "--broker",
            "none",
            "--output-dir",
            str(tmp_path),
            "--ssr-state-dir",
            str(tmp_path / "ssr"),
            "--tradable-min-grade",
            "B",
        ],
        monkeypatch,
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "ERROR: pandas-market-calendars library not found" in err
    assert "requirements.txt" in err


def test_monitor_alpaca_source_without_requests_exits_2(no_requests, capsys, tmp_path):
    rc = mit.main(
        [
            "--plans-json",
            str(FIXTURES / "phase2_plan_smoke.json"),
            "--bars-source",
            "alpaca",
            "--state-dir",
            str(tmp_path / "state"),
            "--output-dir",
            str(tmp_path),
            "--now-et",
            "2026-04-30T10:00:00-04:00",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR: requests library not found" in captured.err
    assert "requirements.txt" in captured.err
    assert "--bars-source fixture" in captured.err
