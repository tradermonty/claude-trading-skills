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


def test_build_entry_row_attaches_ws2_payout_safety_and_blockers() -> None:
    # WS-2 integration: financials -> payout_safety + pre_order_blockers.
    row = build_entry_row(
        ticker="MKC",
        alpha_pp=0.5,
        quote={"price": 46.35},
        profile={"lastDiv": 1.92, "sector": "Consumer Staples"},
        key_metrics=[{"dividendYield": 0.04}],
        financials={
            "sector": "Consumer Staples",
            "gaap_eps": 12.9,
            "adjusted_eps": 3.09,
            "adjusted_eps_source": "MANUAL",
        },
    )
    assert row["payout_safety"]["one_off_flag"] is True
    assert "gaap_one_off" in row["notes"]
    assert "gaap_adjusted_divergence_gt_25pct" in row["pre_order_blockers"]


def test_build_entry_row_applies_ws3_event_cap() -> None:
    from event_scanner import MAJOR_EVENT, ScanResult

    row = build_entry_row(
        ticker="MKC",
        alpha_pp=0.5,
        quote={"price": 46.0},
        profile={"lastDiv": 1.92},
        key_metrics=[{"dividendYield": 0.04}],
        event_scan=ScanResult(
            ticker="MKC", result=MAJOR_EVENT, pending_mna=True, reasons=["tx_value_280pct_mcap"]
        ),
    )
    assert row["verdict_cap"] == "HOLD-REVIEW"
    assert row["t1_blocked"] is True
    assert "major_structural_event" in row["pre_order_blockers"]
    assert row["event_scan"]["pending_mna"] is True


def test_build_entry_row_ws5_verdict_and_provenance() -> None:
    from datetime import date, timedelta

    # CFR D5: latest declared raise -> near-floor -> STEP1-RECHECK verdict.
    hist = [
        {
            "date": (date(2023, 5, 30) + timedelta(days=91 * i)).isoformat(),
            "dividend": (1.00 if i < 12 else 1.03),
            "label": "cash",
        }
        for i in range(13)
    ]
    row = build_entry_row(
        ticker="CFR",
        alpha_pp=0.5,
        quote={"price": 134.70},
        profile={"lastDiv": 4.12, "sector": "Financial Services"},
        key_metrics=[{"dividendYield": 0.031}],
        dividend_history=hist,
        floor_pct=3.0,
    )
    assert row["verdict"] == "STEP1-RECHECK"
    assert row["t1_blocked"] is True
    assert row["provenance"]["dividend_source"] == "fmp_stock_dividend"
    assert "evidence_refs" in row["provenance"]
