import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from screen_momentum_burst import (  # noqa: E402
    FMPClient,
    analyze_symbol,
    generate_markdown_report,
    normalize_bars,
    read_prices_json,
    read_universe_file,
)


def _args(**overrides):
    base = dict(
        min_price=5.0,
        min_volume=100_000,
        four_pct_threshold=4.0,
        dollar_threshold=0.90,
        nine_million_volume=9_000_000,
        max_prev_day_gain_for_range=2.0,
        min_base_days=3,
        max_base_days=20,
        max_base_width_pct=15.0,
        max_prior_avg_range_pct=5.0,
        narrow_prior_day_range_pct=3.0,
        recent_breakdown_lookback=5,
        breakdown_threshold_pct=4.0,
        max_risk_pct_to_stop=10.0,
        market_gate="allowed",
    )
    base.update(overrides)
    return Namespace(**base)


def _good_bars():
    rows = [
        {
            "date": "2026-06-20",
            "open": 100.0,
            "high": 105.0,
            "low": 101.0,
            "close": 104.5,
            "volume": 600_000,
        },
        {
            "date": "2026-06-19",
            "open": 99.8,
            "high": 100.8,
            "low": 99.1,
            "close": 100.0,
            "volume": 120_000,
        },
        {
            "date": "2026-06-18",
            "open": 100.1,
            "high": 100.9,
            "low": 99.3,
            "close": 99.8,
            "volume": 130_000,
        },
        {
            "date": "2026-06-17",
            "open": 99.5,
            "high": 100.4,
            "low": 98.8,
            "close": 100.1,
            "volume": 125_000,
        },
        {
            "date": "2026-06-16",
            "open": 99.6,
            "high": 100.3,
            "low": 98.7,
            "close": 99.7,
            "volume": 115_000,
        },
        {
            "date": "2026-06-15",
            "open": 100.0,
            "high": 100.6,
            "low": 99.2,
            "close": 99.9,
            "volume": 118_000,
        },
    ]
    for i in range(25):
        # Older history creates enough context and slightly higher older volume for dry-up.
        rows.append(
            {
                "date": f"2026-05-{31 - i:02d}",
                "open": 98.5,
                "high": 101.0,
                "low": 97.8,
                "close": 99.0 + (i % 3) * 0.2,
                "volume": 180_000,
            }
        )
    return normalize_bars(rows)


def test_good_4pct_breakout_scores_actionable():
    result = analyze_symbol("TEST", _good_bars(), _args())

    assert result["state"] == "ACTIONABLE_DAY1"
    assert result["rating"] in {"A", "A-"}
    assert "4pct_breakout" in result["trigger_tags"]
    assert "range_expansion" in result["trigger_tags"]
    assert result["risk_pct_to_stop"] < 4.0
    assert result["reject_reasons"] == []


def test_no_trigger_is_rejected():
    bars = _good_bars()
    latest = bars[0]
    bars[0] = type(latest)(latest.date, 100.1, 100.5, 99.7, 100.2, 180_000)

    result = analyze_symbol("FLAT", bars, _args())

    assert result["state"] == "REJECTED"
    assert "no_momentum_burst_trigger" in result["reject_reasons"]


def test_risk_too_wide_is_hard_rejected():
    bars = _good_bars()
    latest = bars[0]
    bars[0] = type(latest)(latest.date, latest.open, latest.high, 80.0, latest.close, latest.volume)

    result = analyze_symbol("WIDE", bars, _args(max_risk_pct_to_stop=10.0))

    assert result["state"] == "REJECTED"
    assert "risk_too_wide" in result["reject_reasons"]


def test_read_prices_json_accepts_symbol_map(tmp_path):
    payload = {
        "TEST": [{"date": "2026-06-20", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100}]
    }
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    data = read_prices_json(str(path))

    assert "TEST" in data
    assert data["TEST"][0].close == 2.0


def test_read_universe_file_csv_symbol_column(tmp_path):
    path = tmp_path / "universe.csv"
    path.write_text("symbol,name\nAAPL,Apple\nnvda,NVIDIA\n", encoding="utf-8")

    assert read_universe_file(str(path)) == ["AAPL", "NVDA"]


def test_fmp_universe_routes_to_stable_company_screener(monkeypatch):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = [
        {"symbol": "AAPL", "marketCap": 100_000_000_000, "price": 200, "volume": 1_000_000},
        {
            "symbol": "SPY",
            "marketCap": 500_000_000_000,
            "price": 600,
            "volume": 50_000_000,
            "isEtf": True,
        },
    ]

    session = MagicMock()
    session.get.return_value = response
    client = FMPClient(api_key="test", max_api_calls=10)
    client.session = session

    universe = client.get_universe(1_000_000_000, 5.0, 100_000, 10)

    assert [row["symbol"] for row in universe] == ["AAPL"]
    assert session.get.call_args_list[0][0][0].endswith("/stable/company-screener")


def test_include_rejected_handles_insufficient_history(tmp_path):
    # A symbol with too little history returns a minimal skeleton (no volume).
    skeleton = analyze_symbol(
        "SHORT",
        normalize_bars(
            [{"date": "2026-06-20", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 500}]
        ),
        _args(),
    )
    assert skeleton["reject_reasons"] == ["insufficient_history"]
    assert "volume" not in skeleton

    metadata = {
        "generated_at": "2026-06-20 00:00:00",
        "input_mode": "prices_json",
        "symbols_processed": 1,
        "market_gate": "allowed",
    }
    out = tmp_path / "report.md"

    # Regression: --include-rejected used to crash on the skeleton row via
    # the thousands-separator format on a None volume.
    generate_markdown_report([skeleton], metadata, str(out), top=50, include_rejected=True)

    text = out.read_text(encoding="utf-8")
    assert "SHORT" in text
    assert "Volume: n/a" in text
    # Missing numeric fields render as n/a, never as a stray "None"/"Nonex".
    assert "Nonex" not in text
    assert "None" not in text
