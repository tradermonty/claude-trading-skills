"""Consumed RS endpoints must never turn missing prices into performance."""

import importlib.util
from pathlib import Path

import pytest
from calculators.leadership_calculator import calculate_leadership, slice_period_return
from test_leadership_rs import _make_price_series

INVALID = [None, float("nan"), float("inf"), -float("inf"), True, False, 0, -1, "100"]


@pytest.mark.parametrize("value", INVALID)
@pytest.mark.parametrize("endpoint", [0, -1])
def test_slice_invalid_endpoint(value, endpoint):
    prices = _make_price_series(100, 0.001, 63)
    prices[endpoint]["close"] = value
    assert slice_period_return(prices, 63) is None


@pytest.mark.parametrize("role", ["stock", "benchmark"])
@pytest.mark.parametrize("index", [0, -1, 260 - 63, 260 - 126, 260 - 252])
@pytest.mark.parametrize("value", INVALID)
def test_consumed_endpoint_is_unavailable(role, index, value):
    stock = _make_price_series(100, 0.002, 260)
    benchmark = _make_price_series(100, 0.001, 260)
    prices = stock if role == "stock" else benchmark
    prices[index]["close"] = value
    result = calculate_leadership(stock, benchmark)
    assert result["data_available"] is False
    assert result["rs_rating"] == "Unavailable"
    assert result["score"] == 0
    assert prices[index]["date"] in result["data_gaps"][role]["bad_dates"]
    assert result["weighted_relative_performance"] is None


@pytest.mark.parametrize("count", [50, 62])
@pytest.mark.parametrize("role", ["stock", "benchmark"])
def test_legacy_only_endpoint_missing(count, role):
    stock = _make_price_series(100, 0.002, count)
    benchmark = _make_price_series(100, 0.001, count)
    del (stock if role == "stock" else benchmark)[-1]["close"]
    assert calculate_leadership(stock, benchmark)["data_available"] is False


def test_unconsumed_interior_does_not_change_result():
    stock = _make_price_series(100, 0.002, 260)
    benchmark = _make_price_series(100, 0.001, 260)
    expected = calculate_leadership(stock, benchmark)
    del stock[10]["close"]
    benchmark[10]["close"] = float("nan")
    assert calculate_leadership(stock, benchmark) == expected


def test_precomputed_path_does_not_consume_modern_endpoints():
    stock = _make_price_series(100, 0.002, 260)
    expected = calculate_leadership(stock, sp500_performance=10)
    stock[260 - 63]["close"] = None
    assert calculate_leadership(stock, [{"close": None}] * 260, 10) == expected


@pytest.mark.parametrize("benchmark", [None, [], [{"close": None}] * 20])
def test_absent_or_insufficient_benchmark_preserves_fallback(benchmark):
    stock = _make_price_series(100, 0.002, 260)
    result = calculate_leadership(stock, benchmark)
    assert result["error"] is None
    assert result["score"] > 0
    assert not result.get("data_gaps")


def test_descending_gaps_preserve_date():
    prices = _make_price_series(100, 0.002, 260)
    prices[-1].pop("close")
    result = calculate_leadership(list(reversed(prices)))
    assert result["data_gaps"]["stock"]["latest_bad"] == prices[-1]["date"]


def test_pure_scoring_can_load_without_skill_path():
    path = Path(__file__).parents[1] / "calculators/leadership_calculator.py"
    spec = importlib.util.spec_from_file_location("isolated_leadership", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.score_leadership(20, True)[0] > 0


def _pipeline_stock(symbol, broken=False):
    from test_canslim_coverage import strong_stock

    stock = strong_stock(symbol)
    if broken:
        stock["prices_365"]["historical"][0].pop("close")
    return stock


def test_invalid_stock_not_ranked_but_next_candidate_survives():
    import screen_canslim as sc
    from test_canslim_coverage import FakeFMP, market_result

    client = FakeFMP({"BAD": _pipeline_stock("BAD", True), "GOOD": _pipeline_stock("GOOD")})
    diagnostics = []
    assert (
        sc.analyze_stock("BAD", client, market_result(), rs_price_diagnostics=diagnostics) is None
    )
    assert sc.analyze_stock("GOOD", client, market_result(), rs_price_diagnostics=diagnostics)
    assert diagnostics[0]["symbol"] == "BAD"
    assert diagnostics[0]["data_gaps"]["stock"]["bad_bars"] == 1


def test_partial_exclusion_visible_in_both_reports(monkeypatch, tmp_path):
    from test_canslim_coverage import FakeFMP, read_reports, run_main

    client = FakeFMP({"BAD": _pipeline_stock("BAD", True), "GOOD": _pipeline_stock("GOOD")})
    run_main(monkeypatch, ["--universe", "BAD", "GOOD", "--output-dir", str(tmp_path)], client)
    report, markdown = read_reports(tmp_path)
    assert [row["symbol"] for row in report["results"]] == ["GOOD"]
    assert report["metadata"]["rs_price_gap_exclusions"][0]["symbol"] == "BAD"
    assert "incomplete screening" in markdown
    assert "BAD" in markdown


@pytest.mark.parametrize("universe", [["BAD"], ["BAD", "NO_PROFILE"]])
def test_empty_results_with_gap_exit_without_report(monkeypatch, tmp_path, universe):
    from test_canslim_coverage import FakeFMP, run_main

    with pytest.raises(SystemExit) as exc:
        run_main(
            monkeypatch,
            ["--universe", *universe, "--output-dir", str(tmp_path)],
            FakeFMP({"BAD": _pipeline_stock("BAD", True)}),
        )
    assert exc.value.code == 1
    assert not list(tmp_path.iterdir())


def test_disable_rs_preserves_neutral_score_with_broken_prices():
    import screen_canslim as sc
    from test_canslim_coverage import FakeFMP, market_result

    client = FakeFMP({"BAD": _pipeline_stock("BAD", True)})
    result = sc.analyze_stock("BAD", client, market_result(), disable_rs=True)
    assert result["l_component"]["score"] == 50
    assert ("prices", "BAD", 365) not in client.calls


def test_invalid_benchmark_excludes_candidate():
    import screen_canslim as sc
    from test_canslim_coverage import FakeFMP, market_result

    benchmark = _make_price_series(100, 0.001, 260)
    benchmark[-1].pop("close")
    diagnostics = []
    result = sc.analyze_stock(
        "GOOD",
        FakeFMP({"GOOD": _pipeline_stock("GOOD")}),
        market_result(),
        rs_benchmark_historical={"historical": benchmark},
        rs_price_diagnostics=diagnostics,
    )
    assert result is None
    assert diagnostics[0]["data_gaps"]["benchmark"]["bad_bars"] == 1


def test_multi_period_reports_gap_without_treating_as_short_history():
    from calculators.leadership_calculator import compute_multi_period_rs

    stock = _make_price_series(100, 0.002, 260)
    benchmark = _make_price_series(100, 0.001, 260)
    benchmark[260 - 63].pop("close")
    result = compute_multi_period_rs(stock, benchmark)
    assert result["rel_3m"] is None
    assert result["benchmark_3m_return"] is None
    assert result["data_gaps"]["benchmark"]["bad_dates"] == [benchmark[260 - 63]["date"]]


def test_pure_scoring_cold_process():
    import subprocess
    import sys

    path = Path(__file__).parents[1] / "calculators/leadership_calculator.py"
    code = (
        "import importlib.util; "
        f"s=importlib.util.spec_from_file_location('leadership', {str(path)!r}); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "assert m.score_leadership(20, True)[0] > 0"
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True)
