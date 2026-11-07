"""Statistical and CLI contracts for both pair-trading scripts."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

import analyze_spread
import find_pairs
import numpy as np
import pandas as pd
import pytest
import statsmodels  # noqa: F401


def _cointegrated_prices(length=320):
    rng = np.random.default_rng(7)
    index = pd.date_range("2025-01-01", periods=length, freq="D")
    stock_b = 100 + np.cumsum(rng.normal(0, 0.8, length))
    spread = np.zeros(length)
    for position in range(1, length):
        spread[position] = 0.65 * spread[position - 1] + rng.normal(0, 0.5)
    stock_a = 1.2 * stock_b + spread
    return (
        pd.Series(stock_a, index=index, name="AAA"),
        pd.Series(stock_b, index=index, name="BBB"),
    )


def _pair_result():
    return {
        "pair": "AAA/BBB",
        "stock_a": "AAA",
        "stock_b": "BBB",
        "correlation": 0.95,
        "beta": 1.2,
        "cointegration_pvalue": 0.01,
        "adf_statistic": -4.2,
        "critical_value_5pct": -2.9,
        "is_cointegrated": True,
        "half_life_days": 5.0,
        "current_zscore": 2.1,
        "signal": "SHORT",
        "strength": "★★",
        "timestamp": "2026-07-25T00:00:00",
    }


def test_find_pairs_runs_real_cointegration_and_half_life():
    prices_a, prices_b = _cointegrated_prices()
    beta = find_pairs.calculate_beta(prices_a, prices_b)["beta"]

    result = find_pairs.test_cointegration(prices_a, prices_b, beta)

    assert result is not None
    assert result["p_value"] < 0.05
    assert find_pairs.calculate_half_life(result["spread"]) > 0


def test_analyze_spread_runs_real_statistics():
    prices_a, prices_b = _cointegrated_prices()
    beta = analyze_spread.calculate_hedge_ratio(prices_a, prices_b)
    spread = beta["aligned_a"] - beta["beta"] * beta["aligned_b"]

    result = analyze_spread.test_cointegration(spread)

    assert result is not None
    assert result["p_value"] < 0.05
    assert analyze_spread.calculate_half_life(spread) > 0


@pytest.mark.parametrize("module", (find_pairs, analyze_spread))
def test_regression_rejects_constant_independent_series(module):
    index = pd.date_range("2026-01-01", periods=10, freq="D")
    varying = pd.Series(np.arange(10, dtype=float), index=index)
    constant = pd.Series(np.ones(10), index=index)
    function = module.calculate_beta if module is find_pairs else module.calculate_hedge_ratio

    with pytest.raises(ValueError, match="non-constant"):
        function(varying, constant)


def test_short_and_constant_series_are_not_actionable():
    prices_a, prices_b = _cointegrated_prices(length=20)

    assert find_pairs.calculate_correlation(prices_a, prices_b) is None
    assert find_pairs.calculate_current_zscore(pd.Series([1.0] * 20)) is None
    assert analyze_spread.test_cointegration(pd.Series([1.0, 1.0])) is None


def test_pair_statistics_drop_the_same_nonfinite_observations():
    index = pd.date_range("2026-01-01", periods=120, freq="D")
    prices_a = pd.Series(np.arange(120, dtype=float), index=index)
    prices_b = pd.Series(np.arange(120, dtype=float) * 2, index=index)
    prices_a.iloc[50] = np.nan
    prices_b.iloc[75] = np.inf

    correlation = find_pairs.calculate_correlation(prices_a, prices_b)
    beta = find_pairs.calculate_beta(prices_a, prices_b)

    assert correlation == pytest.approx(1.0)
    assert beta["beta"] == pytest.approx(0.5)
    assert np.isfinite(beta["intercept"])


def test_screen_all_pairs_skips_malformed_pair_and_keeps_valid_pair():
    prices_a, prices_b = _cointegrated_prices()
    malformed = prices_a.copy()
    malformed.iloc[20:] = np.nan

    results = find_pairs.screen_all_pairs(
        {"AAA": prices_a, "BBB": prices_b, "BAD": malformed},
        min_correlation=0.70,
    )

    assert [result["pair"] for result in results] == ["AAA/BBB"]


@pytest.mark.parametrize(("zscore", "expected"), ((None, None), (0.0, 0.0)))
def test_analyze_pair_preserves_non_actionable_zscores(monkeypatch, zscore, expected):
    prices_a, prices_b = _cointegrated_prices()
    spread = prices_a - prices_b
    monkeypatch.setattr(find_pairs, "calculate_correlation", lambda *_args: 0.9)
    monkeypatch.setattr(
        find_pairs,
        "calculate_beta",
        lambda *_args: {"beta": 1.0, "intercept": 0.0, "r_squared": 0.8},
    )
    monkeypatch.setattr(
        find_pairs,
        "test_cointegration",
        lambda *_args: {
            "is_cointegrated": True,
            "p_value": 0.01,
            "adf_statistic": -4.0,
            "critical_value_5pct": -2.9,
            "spread": spread,
        },
    )
    monkeypatch.setattr(find_pairs, "calculate_half_life", lambda _spread: 5.0)
    monkeypatch.setattr(find_pairs, "calculate_current_zscore", lambda _spread: zscore)

    result = find_pairs.analyze_pair("AAA", "BBB", prices_a, prices_b)

    assert result["current_zscore"] == expected
    assert result["signal"] == "NONE"


def test_rank_pairs_prints_na_for_missing_zscore(capsys):
    pair = _pair_result()
    pair["current_zscore"] = None

    assert find_pairs.rank_pairs([pair]) == [pair]

    assert "z=N/A" in capsys.readouterr().out


@pytest.mark.parametrize("module", (find_pairs, analyze_spread))
def test_statistical_api_reports_missing_dependency(monkeypatch, module):
    def missing_dependency():
        raise RuntimeError("statsmodels dependency missing")

    monkeypatch.setattr(module, "require_statsmodels", missing_dependency)
    prices_a, prices_b = _cointegrated_prices()

    with pytest.raises(RuntimeError, match="statsmodels dependency missing"):
        if module is find_pairs:
            module.test_cointegration(prices_a, prices_b, 1.2)
        else:
            module.test_cointegration(prices_a - prices_b)


@pytest.mark.parametrize(
    "arguments",
    (
        ["--symbols", "AAA,BBB", "--min-correlation", "nan"],
        ["--symbols", "AAA,BBB", "--min-correlation", "1.1"],
        ["--symbols", "AAA,BBB", "--lookback-days", "249"],
        ["--symbols", "AAA,AAA"],
    ),
)
def test_find_pairs_rejects_invalid_cli_values(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["find_pairs.py", *arguments])

    with pytest.raises(SystemExit, match="2"):
        find_pairs.main()


@pytest.mark.parametrize(
    "arguments",
    (
        ["--stock-a", "AAA", "--stock-b", "AAA"],
        ["--stock-a", "AAA", "--stock-b", "BBB", "--lookback-days", "89"],
        ["--stock-a", "AAA", "--stock-b", "BBB", "--entry-zscore", "nan"],
        ["--stock-a", "AAA", "--stock-b", "BBB", "--entry-zscore", "0"],
        ["--stock-a", "AAA", "--stock-b", "BBB", "--exit-zscore", "-0.1"],
        [
            "--stock-a",
            "AAA",
            "--stock-b",
            "BBB",
            "--entry-zscore",
            "2",
            "--exit-zscore",
            "2",
        ],
    ),
)
def test_analyze_spread_rejects_invalid_cli_values(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["analyze_spread.py", *arguments])

    with pytest.raises(SystemExit, match="2"):
        analyze_spread.main()


def test_find_pairs_creates_output_parent_and_writes_json(monkeypatch, tmp_path):
    prices_a, prices_b = _cointegrated_prices()
    output = tmp_path / "nested" / "pairs.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "find_pairs.py",
            "--symbols",
            "AAA,BBB",
            "--api-key",
            "key",
            "--output",
            str(output),
        ],
    )
    monkeypatch.setattr(
        find_pairs,
        "fetch_price_data_batch",
        lambda *_args: {"AAA": prices_a, "BBB": prices_b},
    )
    monkeypatch.setattr(find_pairs, "screen_all_pairs", lambda *_args: [_pair_result()])

    find_pairs.main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metadata"]["total_pairs"] == 1
    assert payload["pairs"][0]["pair"] == "AAA/BBB"


def test_find_pairs_writes_empty_json_when_no_pairs_are_found(monkeypatch, tmp_path):
    prices_a, prices_b = _cointegrated_prices()
    output = tmp_path / "nested" / "empty.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "find_pairs.py",
            "--symbols",
            "AAA,BBB",
            "--api-key",
            "key",
            "--output",
            str(output),
        ],
    )
    monkeypatch.setattr(
        find_pairs,
        "fetch_price_data_batch",
        lambda *_args: {"AAA": prices_a, "BBB": prices_b},
    )
    monkeypatch.setattr(find_pairs, "screen_all_pairs", lambda *_args: [])

    find_pairs.main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metadata"] == {
        "generated_at": payload["metadata"]["generated_at"],
        "total_pairs": 0,
        "cointegrated_pairs": 0,
        "active_signals": 0,
        "price_basis": {"AAA": "unknown", "BBB": "unknown"},
    }
    assert payload["pairs"] == []


def test_find_pairs_reports_unwritable_output_as_runtime_error(tmp_path):
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("occupied", encoding="utf-8")

    with pytest.raises(RuntimeError, match="could not write output file"):
        find_pairs.save_results([_pair_result()], parent_file / "pairs.json")


@pytest.mark.parametrize("module", (find_pairs, analyze_spread))
def test_cli_dependency_error_is_nonzero_without_traceback(monkeypatch, capsys, module):
    prices_a, prices_b = _cointegrated_prices()
    if module is find_pairs:
        monkeypatch.setattr(
            sys,
            "argv",
            ["find_pairs.py", "--symbols", "AAA,BBB", "--api-key", "key"],
        )
        monkeypatch.setattr(
            find_pairs,
            "fetch_price_data_batch",
            lambda *_args: {"AAA": prices_a, "BBB": prices_b},
        )
        monkeypatch.setattr(
            find_pairs,
            "screen_all_pairs",
            MagicMock(side_effect=RuntimeError("install statsmodels")),
        )
    else:
        monkeypatch.setattr(
            sys,
            "argv",
            ["analyze_spread.py", "--stock-a", "AAA", "--stock-b", "BBB", "--api-key", "key"],
        )
        monkeypatch.setattr(
            analyze_spread,
            "fetch_historical_prices",
            MagicMock(side_effect=(prices_a, prices_b)),
        )
        monkeypatch.setattr(
            analyze_spread,
            "test_cointegration",
            MagicMock(side_effect=RuntimeError("install statsmodels")),
        )

    assert module.cli() == 1

    captured = capsys.readouterr()
    assert "install statsmodels" in captured.err
    assert "Traceback" not in captured.err


def test_analyze_spread_main_produces_report_contract(monkeypatch):
    prices_a, prices_b = _cointegrated_prices(length=120)
    aligned = {
        "beta": 1.2,
        "intercept": 0.0,
        "r_value": 0.95,
        "r_squared": 0.9,
        "aligned_a": prices_a,
        "aligned_b": prices_b,
    }
    zscore = pd.Series(np.linspace(-1.0, 1.0, 120), index=prices_a.index)
    report = MagicMock()
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_spread.py", "--stock-a", "AAA", "--stock-b", "BBB", "--api-key", "key"],
    )
    monkeypatch.setattr(
        analyze_spread,
        "fetch_historical_prices",
        MagicMock(side_effect=(prices_a, prices_b)),
    )
    monkeypatch.setattr(analyze_spread, "calculate_hedge_ratio", lambda *_args: aligned)
    monkeypatch.setattr(
        analyze_spread,
        "test_cointegration",
        lambda _spread: {
            "adf_statistic": -4.2,
            "p_value": 0.01,
            "critical_values": {"5%": -2.9},
            "is_cointegrated": True,
        },
    )
    monkeypatch.setattr(analyze_spread, "calculate_half_life", lambda _spread: 5.0)
    monkeypatch.setattr(analyze_spread, "calculate_zscore_series", lambda *_args, **_kwargs: zscore)
    monkeypatch.setattr(analyze_spread, "print_analysis_report", report)

    analyze_spread.main()

    report.assert_called_once()
