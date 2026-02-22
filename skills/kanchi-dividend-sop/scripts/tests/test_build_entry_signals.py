"""Tests for build_entry_signals.py."""

from build_entry_signals import (
    build_entry_row,
    load_tickers,
    normalize_metrics_yields,
    parse_ticker_csv,
)


def test_parse_ticker_csv_normalizes_and_deduplicates() -> None:
    tickers = parse_ticker_csv("aapl, MSFT, aapl, ko")
    assert tickers == ["AAPL", "MSFT", "KO"]


def test_load_tickers_from_json_candidates(tmp_path) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"candidates":[{"ticker":"jnj"},{"ticker":"pg"}]}')
    assert load_tickers(path, None) == ["JNJ", "PG"]


def test_normalize_metrics_yields_limits_to_five_points() -> None:
    metrics = [
        {"dividendYield": 0.02},
        {"dividendYield": 0.03},
        {"dividendYield": 0.04},
        {"dividendYield": 0.05},
        {"dividendYield": 0.06},
        {"dividendYield": 0.07},
    ]
    assert normalize_metrics_yields(metrics) == [2.0, 3.0, 4.0, 5.0, 6.0]


def test_build_entry_row_wait_signal() -> None:
    row = build_entry_row(
        ticker="AAPL",
        alpha_pp=0.5,
        quote={"price": 200.0},
        profile={"lastDiv": 4.0},
        key_metrics=[
            {"dividendYield": 0.02},
            {"dividendYield": 0.021},
            {"dividendYield": 0.019},
            {"dividendYield": 0.022},
            {"dividendYield": 0.018},
        ],
    )
    assert row["signal"] == "WAIT"
    assert row["target_yield_pct"] == 2.5
    assert row["buy_target_price"] == 160.0
    assert row["drop_needed_pct"] == 20.0


def test_build_entry_row_triggered_signal() -> None:
    row = build_entry_row(
        ticker="KO",
        alpha_pp=0.5,
        quote={"price": 45.0},
        profile={"lastDiv": 2.4},
        key_metrics=[
            {"dividendYield": 0.03},
            {"dividendYield": 0.032},
            {"dividendYield": 0.031},
            {"dividendYield": 0.033},
            {"dividendYield": 0.034},
        ],
    )
    assert row["signal"] == "TRIGGERED"
    assert row["buy_target_price"] == 64.86
    assert row["drop_needed_pct"] == 0.0


def test_build_entry_row_assumption_required_when_missing_data() -> None:
    row = build_entry_row(
        ticker="XXX",
        alpha_pp=0.5,
        quote=None,
        profile=None,
        key_metrics=[],
    )
    assert row["signal"] == "ASSUMPTION-REQUIRED"
    assert "quote_missing" in row["notes"]
    assert "profile_missing" in row["notes"]
