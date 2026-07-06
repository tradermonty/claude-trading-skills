import json
import os
import subprocess
import sys
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from screen_exhaustion_hammer import (  # noqa: E402
    FMPClient,
    analyze_symbol,
    collect_price_data,
    generate_markdown_report,
    normalize_bars,
    read_prices_json,
    read_universe_file,
)


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        return self.responses.pop(0)


def _args(**overrides):
    base = dict(
        min_price=20.0,
        min_volume=100_000,
        min_avg_dollar_volume=20_000_000,
        min_market_cap=2_000_000_000,
        recent_high_lookback=40,
        min_days_since_high=3,
        max_days_since_high=30,
        min_pullback_pct=6.0,
        max_pullback_pct=35.0,
        undercut_lookback=5,
        require_undercut_reclaim=False,
        min_lower_wick_pct=40.0,
        max_body_pct=35.0,
        max_upper_wick_pct=35.0,
        min_close_location_pct=60.0,
        min_lower_wick_to_body=1.5,
        min_recovery_from_low_pct=2.0,
        max_risk_pct_to_stop=12.0,
        stop_buffer_pct=0.10,
        market_gate="allowed",
    )
    base.update(overrides)
    return Namespace(**base)


def _good_bars():
    start = date(2026, 6, 26)
    rows = []
    for i in range(90):
        dt = (start - timedelta(days=i)).isoformat()
        if i == 0:
            rows.append(
                {
                    "date": dt,
                    "open": 468.0,
                    "high": 480.0,
                    "low": 440.0,
                    "close": 476.0,
                    "volume": 8_500_000,
                }
            )
        elif i <= 5:
            close = 452.0 + (i - 1) * 5.0
            rows.append(
                {
                    "date": dt,
                    "open": close + 4.0,
                    "high": close + 12.0,
                    "low": 445.0 + (i - 1) * 4.0,
                    "close": close,
                    "volume": 4_000_000 + i * 100_000,
                }
            )
        elif i == 18:
            rows.append(
                {
                    "date": dt,
                    "open": 590.0,
                    "high": 610.0,
                    "low": 585.0,
                    "close": 600.0,
                    "volume": 6_500_000,
                }
            )
        elif i < 30:
            close = 590.0 - abs(18 - i) * 7.0
            rows.append(
                {
                    "date": dt,
                    "open": close - 2.0,
                    "high": close + 8.0,
                    "low": close - 8.0,
                    "close": close,
                    "volume": 5_000_000,
                }
            )
        else:
            close = 330.0 + (90 - i) * 2.0
            rows.append(
                {
                    "date": dt,
                    "open": close - 1.0,
                    "high": close + 4.0,
                    "low": close - 4.0,
                    "close": close,
                    "volume": 4_500_000,
                }
            )
    return normalize_bars(rows)


def _profile():
    return {
        "marketCap": 135_000_000_000,
        "mutualFundHolders": 3200,
        "institutionalOwnershipPct": 58.0,
    }


def test_fmp_stable_and_v3_fallback_send_apikey_query_param(monkeypatch):
    monkeypatch.setattr(FMPClient, "RATE_LIMIT_DELAY", 0)
    client = FMPClient(api_key="k", max_api_calls=10)
    fake_session = _FakeSession([_FakeResponse({}), _FakeResponse([{"symbol": "APP"}])])
    client.session = fake_session
    params = {"symbol": "APP"}

    result = client._stable_then_v3(
        "https://example.test/stable/company-screener",
        "https://example.test/api/v3/stock-screener",
        params,
    )

    assert result == [{"symbol": "APP"}]
    assert params == {"symbol": "APP"}
    assert len(fake_session.calls) == 2
    assert fake_session.calls[0]["params"] == {"symbol": "APP", "apikey": "k"}
    assert fake_session.calls[1]["params"] == {"symbol": "APP", "apikey": "k"}


def test_good_exhaustion_hammer_scores_actionable():
    result = analyze_symbol("APP", _good_bars(), _args(), profile_row=_profile())

    assert result["state"] == "ACTIONABLE_CLOSE_BUY"
    assert result["rating"] in {"A", "A-"}
    assert "undercut_reclaim" in result["trigger_tags"]
    assert "long_lower_wick" in result["trigger_tags"]
    assert result["pullback_pct_from_high"] < -20
    assert result["risk_pct_to_stop"] < 8
    assert result["reject_reasons"] == []


def test_restrictive_market_gate_blocks_actionable_state():
    result = analyze_symbol(
        "APP", _good_bars(), _args(market_gate="restrictive"), profile_row=_profile()
    )

    assert result["state"] == "MANUAL_REVIEW_ONLY"
    assert result["raw_setup_score"] >= 70
    assert result["reject_reasons"] == []
    assert "Market gate is restrictive" in result["downstream_action"]


def test_weak_hammer_geometry_is_rejected():
    bars = _good_bars()
    latest = bars[0]
    bars[0] = type(latest)(latest.date, 440.0, latest.high, latest.low, latest.close, latest.volume)

    result = analyze_symbol("BODY", bars, _args(), profile_row=_profile())

    assert result["state"] == "REJECTED"
    assert "body_too_large" in result["reject_reasons"]
    assert "lower_wick_too_small" in result["reject_reasons"]


def test_pullback_too_shallow_is_rejected():
    bars = _good_bars()
    adjusted = []
    for idx, bar in enumerate(bars):
        if idx == 0:
            adjusted.append(bar)
        else:
            high = min(bar.high, 490.0)
            close = min(bar.close, 486.0)
            adjusted.append(
                type(bar)(
                    bar.date, min(bar.open, 484.0), high, min(bar.low, 480.0), close, bar.volume
                )
            )

    result = analyze_symbol("SHALLOW", adjusted, _args(), profile_row=_profile())

    assert result["state"] == "REJECTED"
    assert "pullback_too_shallow" in result["reject_reasons"]


def test_risk_too_wide_is_hard_rejected():
    bars = _good_bars()
    latest = bars[0]
    bars[0] = type(latest)(
        latest.date, latest.open, latest.high, 395.0, latest.close, latest.volume
    )

    result = analyze_symbol("WIDE", bars, _args(max_risk_pct_to_stop=12.0), profile_row=_profile())

    assert result["state"] == "REJECTED"
    assert "risk_too_wide" in result["reject_reasons"]


def test_read_prices_json_accepts_symbol_map(tmp_path):
    payload = {
        "APP": [{"date": "2026-06-26", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100}]
    }
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    data = read_prices_json(str(path))

    assert "APP" in data
    assert data["APP"][0].close == 2.0


def test_read_universe_file_csv_symbol_column(tmp_path):
    path = tmp_path / "universe.csv"
    path.write_text("symbol,name\nAPP,AppLovin\nENPH,Enphase\n", encoding="utf-8")

    assert read_universe_file(str(path)) == ["APP", "ENPH"]


def test_prices_json_mode_honors_max_symbols_without_explicit_symbols(tmp_path):
    prices_path = tmp_path / "prices.json"
    payload = {
        "ZZZ": [{"date": "2026-06-26", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100}],
        "AAA": [{"date": "2026-06-26", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100}],
        "MMM": [{"date": "2026-06-26", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100}],
    }
    prices_path.write_text(json.dumps(payload), encoding="utf-8")
    args = _args(
        prices_json=str(prices_path),
        profiles_json=None,
        symbols=[],
        universe_file=None,
        max_symbols=2,
    )

    price_data, profiles, api_stats = collect_price_data(args)

    assert list(price_data) == ["AAA", "MMM"]
    assert profiles == {}
    assert api_stats is None


def test_include_rejected_handles_insufficient_history(tmp_path):
    skeleton = analyze_symbol(
        "SHORT",
        normalize_bars(
            [{"date": "2026-06-26", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 500}]
        ),
        _args(),
        profile_row=_profile(),
    )
    assert skeleton["reject_reasons"] == ["insufficient_history"]
    assert "volume" not in skeleton

    metadata = {
        "generated_at": "2026-06-26 00:00:00",
        "input_mode": "prices_json",
        "symbols_processed": 1,
        "market_gate": "allowed",
        "use_quote_latest": False,
    }
    out = tmp_path / "report.md"

    generate_markdown_report([skeleton], metadata, str(out), top=50, include_rejected=True)

    text = out.read_text(encoding="utf-8")
    assert "SHORT" in text
    assert "Volume: n/a" in text
    assert "None" not in text


def test_sparse_long_history_rejects_without_none_in_markdown(tmp_path):
    rows = []
    for bar in _good_bars():
        row = {"date": bar.date, "high": bar.high, "low": bar.low, "close": bar.close}
        rows.append(row)
    sparse_bars = normalize_bars(rows)

    result = analyze_symbol(
        "SPARSE", sparse_bars, _args(), profile_row={"institutionalOwnershipPct": ""}
    )

    assert len(sparse_bars) >= 40
    assert result["state"] == "REJECTED"
    assert "below_min_volume" in result["reject_reasons"]
    assert "below_min_avg_dollar_volume" in result["reject_reasons"]

    out = tmp_path / "sparse.md"
    metadata = {
        "generated_at": "2026-06-26 00:00:00",
        "input_mode": "prices_json",
        "symbols_processed": 1,
        "market_gate": "allowed",
        "use_quote_latest": False,
    }
    generate_markdown_report([result], metadata, str(out), top=50, include_rejected=True)

    text = out.read_text(encoding="utf-8")
    assert "SPARSE" in text
    assert "None" not in text


def test_markdown_summary_counts_all_non_rejected_when_top_limits_display(tmp_path):
    row_a = analyze_symbol("APP", _good_bars(), _args(), profile_row=_profile())
    row_b = dict(row_a, symbol="APP2")
    row_c = dict(row_a, symbol="APP3")
    out = tmp_path / "report.md"
    metadata = {
        "generated_at": "2026-06-26 00:00:00",
        "input_mode": "prices_json",
        "symbols_processed": 3,
        "market_gate": "allowed",
        "use_quote_latest": False,
    }

    generate_markdown_report(
        [row_a, row_b, row_c], metadata, str(out), top=1, include_rejected=False
    )

    text = out.read_text(encoding="utf-8")
    assert "- Non-rejected candidates: 3" in text
    assert text.count("### APP") == 1


def test_cli_offline_smoke_does_not_require_fmp_key(tmp_path):
    prices_path = tmp_path / "prices.json"
    profiles_path = tmp_path / "profiles.json"
    output_dir = tmp_path / "reports"
    prices_path.write_text(
        json.dumps(
            {
                "APP": [
                    {
                        "date": bar.date,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in _good_bars()
                ]
            }
        ),
        encoding="utf-8",
    )
    profiles_path.write_text(json.dumps({"APP": _profile()}), encoding="utf-8")

    env = os.environ.copy()
    env.pop("FMP_API_KEY", None)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "screen_exhaustion_hammer.py"),
            "--prices-json",
            str(prices_path),
            "--profiles-json",
            str(profiles_path),
            "--market-gate",
            "allowed",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Screening complete" in result.stdout
    assert list(output_dir.glob("stockbee_exhaustion_hammer_*.json"))
    assert list(output_dir.glob("stockbee_exhaustion_hammer_*.md"))
