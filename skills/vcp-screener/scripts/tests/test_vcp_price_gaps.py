"""A missing VCP observation is unavailable, never an artificial zero price."""

import copy

import pytest
from calculators.vcp_pattern_calculator import calculate_vcp_pattern
from test_vcp_screener import _make_prices

MISSING = object()
INVALID = [MISSING, None, float("nan"), float("inf"), -float("inf"), True, False, 0, -1, "100"]


@pytest.mark.parametrize("field", ["high", "low", "close"])
@pytest.mark.parametrize("index", [0, 50, 119])
@pytest.mark.parametrize("value", INVALID)
def test_invalid_consumed_bar_is_unavailable(field, index, value):
    history = _make_prices(260, daily_change=0.001)
    if value is MISSING:
        history[index].pop(field)
    else:
        history[index][field] = value
    result = calculate_vcp_pattern(history)
    assert result["data_available"] is False
    assert result["score"] == 0
    assert result["valid_vcp"] is False
    assert result["contractions"] == []
    assert history[index]["date"] in result["data_gaps"]["bad_dates"]
    assert result["pivot_price"] is None
    assert result["error"]


def test_unconsumed_older_rows_and_volume_do_not_affect_pattern():
    history = _make_prices(260, daily_change=0.001)
    expected = calculate_vcp_pattern(history)
    history[120] = {"date": "bad", "close": None}
    for row in history[:120]:
        row.pop("volume")
    assert calculate_vcp_pattern(history) == expected


def test_input_rows_are_not_mutated_or_compressed():
    history = _make_prices(120)
    history[50].pop("low")
    original = copy.deepcopy(history)
    calculate_vcp_pattern(history)
    assert history == original


@pytest.mark.parametrize("field", ["close", "high", "low"])
@pytest.mark.parametrize("value", [None, "bad"])
def test_analysis_checks_vcp_before_other_calculators(field, value, monkeypatch, capsys):
    import screen_vcp

    history = _make_prices(260)
    history[0][field] = value

    def unexpected(*args, **kwargs):
        pytest.fail("Invalid VCP data must stop before RS/TT/composite calculation")

    monkeypatch.setattr(screen_vcp, "calculate_relative_strength", unexpected)
    assert screen_vcp.analyze_stock("BAD", history, {"price": 100}, history) is None
    assert "unavailable" in capsys.readouterr().err.lower()


def test_asof_ignores_future_bad_bar():
    import screen_vcp

    history = _make_prices(300, daily_change=0.001)
    benchmark = _make_prices(300, daily_change=0.0005)
    quote = {"price": 100, "yearHigh": 130, "yearLow": 60, "marketCap": 1e9}
    expected = screen_vcp.analyze_stock("OK", history, quote, benchmark, as_of_offset=40)
    history[0]["close"] = None
    assert screen_vcp.analyze_stock("OK", history, quote, benchmark, as_of_offset=40) == expected


def test_historical_scan_rejects_gap_before_quote_synthesis(monkeypatch):
    import historical_scanner

    history = _make_prices(300)
    history[-1].pop("low")

    def unexpected(*args, **kwargs):
        pytest.fail("Invalid lookback must stop before synthetic quote construction")

    monkeypatch.setattr(historical_scanner, "build_quote_from_history", unexpected)
    with pytest.raises(ValueError, match="VCP.*unavailable") as exc:
        historical_scanner.scan_history("BAD", history, history)
    assert history[-1]["date"] in exc.value.data_gaps["bad_dates"]


@pytest.mark.parametrize("field,value", [("low", MISSING), ("close", None), ("close", "bad")])
def test_historical_cli_reports_unavailable_without_writing(
    field, value, monkeypatch, tmp_path, capsys
):
    import sys

    import screen_vcp
    from test_historical_vcp import _StubFMPClient

    history = _make_prices(300)
    if value is MISSING:
        history[-1].pop(field)
    else:
        history[-1][field] = value
    monkeypatch.setattr(
        sys,
        "argv",
        ["screen_vcp.py", "--history", "--ticker", "TEST", "--output-dir", str(tmp_path)],
    )
    args = screen_vcp.parse_arguments()
    with pytest.raises(SystemExit) as exc:
        screen_vcp.run_historical(args, _StubFMPClient(history, _make_prices(300)))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "VCP price data unavailable" in captured.err
    assert "Found 0" not in captured.out
    assert not list(tmp_path.iterdir())


def test_cold_pure_atr_import():
    import subprocess
    import sys
    from pathlib import Path

    path = Path(__file__).parents[1] / "calculators/vcp_pattern_calculator.py"
    code = (
        "import importlib.util; "
        f"s=importlib.util.spec_from_file_location('vcp', {str(path)!r}); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "assert m._calculate_atr([101]*30, [99]*30, [100]*30) > 0"
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True)
