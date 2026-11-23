"""Issue #845: dated close gaps remain gaps through the real monitor pipeline."""

import json
from copy import deepcopy
from dataclasses import asdict

import ibd_monitor
import pytest
import yaml
from data_loader import fetch_ohlcv, normalize_history, validate_history_quality
from test_ibd_monitor_coverage import (
    FakeResponse,
    _analyze,
    descending_history,
    distribution_history,
    make_client,
    read_report,
    run_main,
)

BAD_CLOSES = [
    None,
    "bad",
    "NaN",
    "Infinity",
    float("nan"),
    float("inf"),
    -float("inf"),
    True,
    False,
    0,
    -1,
    "1e400",
    10**400,
]


@pytest.mark.parametrize("value", BAD_CLOSES)
def test_normalization_keeps_bad_session_and_audits_date(value):
    history = descending_history()
    history[1]["close"] = value
    dates = [r["date"] for r in history]
    normalized = normalize_history({"historical": history})
    assert len(normalized) == len(history)
    assert [r["date"] for r in normalized] == dates
    assert normalized[1]["close"] is None
    assert normalized[1] is not history[1]
    flags, skipped = validate_history_quality(history)
    assert "data_quality_warnings" in flags
    assert {
        "date": dates[1],
        "reason": "missing_close" if value is None else "invalid_close",
    } in skipped


def test_numeric_strings_coerce_without_mutating_payload():
    history = descending_history()
    for row in history:
        row["close"] = str(row["close"])
    original = deepcopy(history)
    normalized = normalize_history(history)
    assert normalized[0]["close"] == 200.0
    assert history == original
    assert _analyze(history) == _analyze(descending_history())


@pytest.mark.parametrize("value", BAD_CLOSES)
@pytest.mark.parametrize("offset", [0, 1, 30, 70])
def test_real_fmp_fetch_and_analysis_reject_bad_close(value, offset):
    history = descending_history()
    history[offset]["close"] = value
    client = make_client(FakeResponse(payload=history))
    normalized, audit = fetch_ohlcv(client, "QQQ", 90)
    result, flags = _analyze(normalized)
    assert "data_quality_warnings" in audit["audit_flags"]
    assert "invalid_close_data" in flags
    assert result.trend_filters["close_above_21ema"] is None
    assert result.trend_filters["market_below_21ema_or_50ma"] is None
    assert result.trend_filters["close_above_50sma"] is (True if offset >= 50 else None)
    assert result.today["date"] == history[0]["date"]
    json.dumps(asdict(result), allow_nan=False)


def test_missing_close_direct_analysis_does_not_crash():
    history = descending_history()
    del history[0]["close"]
    result, flags = _analyze(history)
    assert result.today["close"] is None
    assert result.today["pct_change"] is None
    assert "invalid_close_data" in flags


def test_no_cross_gap_dd_and_session_ages_preserved():
    history = distribution_history()
    history[1]["close"] = None
    result, _ = _analyze(history)
    # DD age 0 and 1 both touch the gap. Age 2 remains age 2, not 1.
    assert [r["age_sessions"] for r in result.active_distribution_days] == [2]
    assert result.is_distribution_day_today is False
    assert result.d5_count == 1


def test_close_gap_cannot_invalidate_record():
    history = distribution_history()
    history[0]["close"] = float("inf")
    cfg = ibd_monitor.load_config(None)
    cfg.setdefault("distribution_day_rule", {})
    rule = ibd_monitor._build_rule(cfg)
    rule.invalidation_price_source = "close"
    result, _ = ibd_monitor.analyze_index(
        "QQQ", "QQQ", history, cfg, rule, ibd_monitor._build_thresholds(cfg), None
    )
    assert all(r["invalidation_date"] is None for r in result.active_distribution_days)
    assert result.d5_count == 2


@pytest.mark.parametrize("symbol", ["QQQ", "SPY"])
def test_cli_bad_effective_close_caps_additions(monkeypatch, tmp_path, symbol):
    hists = {"QQQ": descending_history(), "SPY": descending_history()}
    hists[symbol][0]["close"] = float("nan")
    cfg = {"strategy_context": {"current_exposure_pct": 20}}
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(cfg))
    rc, _, out = run_main(monkeypatch, tmp_path, hists, ["--config", str(config_path)])
    assert rc == 0
    report, path = read_report(out)
    json.dumps(report, allow_nan=False)
    action = report["portfolio_action"]
    assert action["target_exposure_pct"] == 20
    assert action["exposure_delta_pct"] == 0
    assert action["recommended_action"] == "AVOID_NEW_ADDS"
    assert "incomplete" in action["rationale"].lower()
    assert "invalid_close_data" in report["audit"]["audit_flags"]
    assert "invalid_close_data" in path.with_suffix(".md").read_text()


def test_cli_as_of_excludes_future_close_defect(monkeypatch, tmp_path):
    history = descending_history(100)
    history[0]["close"] = float("nan")
    as_of = history[5]["date"]
    rc, _, out = run_main(
        monkeypatch, tmp_path, {"QQQ": history}, ["--symbols", "QQQ", "--as-of", as_of]
    )
    assert rc == 0
    report, _ = read_report(out)
    assert "invalid_close_data" not in report["audit"]["audit_flags"]
    assert "data_quality_warnings" not in report["audit"]["audit_flags"]
    assert all(r["date"] != history[0]["date"] for r in report["audit"]["skipped_sessions"])
    assert report["portfolio_action"]["recommended_action"] == "HOLD_OR_FOLLOW_BASE_STRATEGY"


def test_extreme_finite_return_is_unavailable_not_infinite():
    history = descending_history()
    history[0]["close"] = 1e308
    history[1]["close"] = 1e-308
    result, flags = _analyze(history)
    assert result.today["pct_change"] is None
    assert "non_finite_price_arithmetic" in flags
    json.dumps(asdict(result), allow_nan=False)


def test_extreme_dd_threshold_and_ma_sum_are_unavailable():
    history = descending_history()
    for row in history:
        row["close"] = 1.79e308
    history[0]["close"] = 1.75e308
    history[0]["volume"] = 2_000_000
    result, flags = _analyze(history)
    assert result.active_distribution_days[0]["invalidation_price"] is None
    assert result.trend_filters["market_below_21ema_or_50ma"] is None
    assert "non_finite_price_arithmetic" in flags
    assert "non_finite_moving_average" in flags
    json.dumps(asdict(result), allow_nan=False)


@pytest.mark.parametrize("value", [None, "200", "bad", float("nan"), "1e400"])
def test_cli_through_real_client_with_fake_http(monkeypatch, tmp_path, value):
    history = descending_history()
    history[0]["close"] = value
    client = make_client(FakeResponse(payload=history))
    monkeypatch.setattr(ibd_monitor, "build_fmp_client", lambda api_key: client)
    monkeypatch.setenv("FMP_API_KEY", "offline-test-value")
    assert ibd_monitor.main(["--symbols", "QQQ", "--output-dir", str(tmp_path)]) == 0
    report, _ = read_report(tmp_path)
    json.dumps(report, allow_nan=False)
    index = report["market_distribution_state"]["index_results"][0]
    assert index["trend_filters"]["market_below_21ema_or_50ma"] is (
        False if value == "200" else None
    )
    assert len(client.session.calls) == 1
    if value != "200":
        expected = "missing_close" if value is None else "invalid_close"
        quality = [
            r
            for r in index["skipped_sessions"]
            if r["date"] == history[0]["date"] and r["reason"] in {"missing_close", "invalid_close"}
        ]
        assert quality == [{"date": history[0]["date"], "reason": expected}]
        assert quality[0] in report["audit"]["skipped_sessions"]


def test_bad_close_preserves_policy_reduction(monkeypatch, tmp_path):
    history = distribution_history()
    history[70]["close"] = None
    rc, _, out = run_main(monkeypatch, tmp_path, {"QQQ": history}, ["--symbols", "QQQ"])
    assert rc == 0
    report, _ = read_report(out)
    action = report["portfolio_action"]
    assert action["recommended_action"] == "REDUCE_EXPOSURE"
    assert action["target_exposure_pct"] == 50
    assert action["exposure_delta_pct"] == -50
    assert action["trailing_stop_pct"] == 5


def test_disabled_ma_still_audits_invalid_close():
    history = descending_history()
    history[10]["close"] = None
    cfg = ibd_monitor.load_config(None)
    cfg["moving_average_filters"] = {"enabled": False}
    result, flags = _analyze(history, config=cfg)
    assert "invalid_close_data" in flags
    assert result.trend_filters["market_below_21ema_or_50ma"] is None
