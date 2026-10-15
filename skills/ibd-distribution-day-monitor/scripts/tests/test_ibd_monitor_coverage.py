"""Coverage tests for the monitor CLI flow, FMP client fallbacks and helpers.

All HTTP is faked; no network, no dependence on the wall-clock date.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import _fmp_compat
import data_loader
import fmp_client
import ibd_monitor
import pytest
import report_generator
import yaml
from fmp_client import ApiCallBudgetExceeded, FMPClient
from helpers import make_bar, make_history
from models import DistributionDayRule

FAKE_KEY = "unit-test-key-123"  # pragma: allowlist secret
STABLE_URL = "https://financialmodelingprep.com/stable/historical-price-eod/full"
V3_URL = "https://financialmodelingprep.com/api/v3/historical-price"
FIXED_NOW = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Shared fakes / builders
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class ScriptedSession:
    """requests.Session stand-in that replays outcomes and records calls."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, dict(params)))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_client(*outcomes, max_api_calls=200):
    client = FMPClient(api_key=FAKE_KEY, max_api_calls=max_api_calls)
    client.RATE_LIMIT_DELAY = 0
    client.session = ScriptedSession(*outcomes)
    return client


def descending_history(n=90, start="2026-04-30", top=200.0):
    """Gently rising market in chronological order (newest-first list)."""
    closes = [top - i * 0.5 for i in range(n)]
    return make_history(closes, start=start)


def distribution_history(n=90):
    """Rising market whose last three sessions are Distribution Days."""
    hist = descending_history(n)
    # Newest 3 sessions: drop 0.5% on volume above the prior session.
    base_close = hist[3]["close"]
    c2 = base_close * 0.995
    c1 = c2 * 0.995
    c0 = c1 * 0.995
    for i, c in enumerate((c0, c1, c2)):
        hist[i] = make_bar(hist[i]["date"], c, volume=1_500_000 + (2 - i) * 100_000)
    return hist


class FakeMonitorClient:
    def __init__(self, histories):
        self.histories = histories
        self.requested = []

    def get_historical_prices(self, symbol, days):
        self.requested.append((symbol, days))
        hist = self.histories.get(symbol)
        if hist is None:
            return None
        return {"symbol": symbol, "historical": hist}


def run_main(monkeypatch, tmp_path, histories, argv=None, env_key=FAKE_KEY):
    client = FakeMonitorClient(histories)
    monkeypatch.setattr(ibd_monitor, "build_fmp_client", lambda api_key: client)
    if env_key:
        monkeypatch.setenv("FMP_API_KEY", env_key)
    else:
        monkeypatch.delenv("FMP_API_KEY", raising=False)
    out = tmp_path / "out"
    rc = ibd_monitor.main((argv or []) + ["--output-dir", str(out)])
    return rc, client, out


def read_report(out):
    files = sorted(out.glob("*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8")), files[0]


# ---------------------------------------------------------------------------
# ibd_monitor: config / key / args
# ---------------------------------------------------------------------------


def test_parse_args_defaults_and_overrides():
    defaults = ibd_monitor.parse_args([])
    assert defaults.symbols is None
    assert defaults.output_dir == "reports/"
    assert defaults.current_exposure is None
    args = ibd_monitor.parse_args(
        ["--symbols", "QQQ,SPY", "--lookback-days", "60", "--current-exposure", "40"]
    )
    assert args.symbols == "QQQ,SPY"
    assert args.lookback_days == 60
    assert args.current_exposure == 40


def test_load_config_default_has_expected_values():
    cfg = ibd_monitor.load_config(None)
    assert cfg["lookback_days"] == 80
    assert [i["symbol"] for i in cfg["indexes"]] == ["QQQ", "SPY"]
    assert cfg["risk_thresholds"]["high"]["d25_count"] == 5


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="config not found"):
        ibd_monitor.load_config(str(tmp_path / "nope.yaml"))


def test_load_config_empty_yaml_returns_empty_dict(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("", encoding="utf-8")
    assert ibd_monitor.load_config(str(p)) == {}


def test_resolve_api_key_precedence(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "env-key")
    cfg = {"data": {"api_key": "cfg-key"}}  # pragma: allowlist secret
    assert ibd_monitor.resolve_api_key("cli-key", cfg) == "cli-key"
    assert ibd_monitor.resolve_api_key(None, cfg) == "cfg-key"
    assert ibd_monitor.resolve_api_key(None, {"data": {"api_key": None}}) == "env-key"
    assert ibd_monitor.resolve_api_key(None, {}) == "env-key"


def test_resolve_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(ValueError, match="FMP API key required"):
        ibd_monitor.resolve_api_key(None, {"data": None})


def test_build_rule_defaults_and_overrides():
    default = ibd_monitor._build_rule({})
    assert default.min_decline_pct == -0.002
    assert default.expiration_sessions == 25
    assert default.invalidation_gain_pct == 0.05
    assert default.invalidation_price_source == "high"
    custom = ibd_monitor._build_rule(
        {
            "distribution_day_rule": {
                "min_decline_pct": -0.004,
                "expiration_sessions": 20,
                "invalidation_gain_pct": 0.03,
                "invalidation_price_source": "close",
            }
        }
    )
    assert (custom.min_decline_pct, custom.expiration_sessions) == (-0.004, 20)
    assert (custom.invalidation_gain_pct, custom.invalidation_price_source) == (0.03, "close")


def test_build_thresholds_defaults_and_overrides():
    t = ibd_monitor._build_thresholds({})
    assert (t.caution_d25, t.high_d25, t.high_d15, t.high_d5) == (3, 5, 3, 2)
    assert (t.severe_d25, t.severe_d15, t.severe_ma_d25) == (6, 4, 5)
    t2 = ibd_monitor._build_thresholds(
        {
            "risk_thresholds": {
                "caution": {"d25_count": 2},
                "high": {"d25_count": 4, "d15_count": 2, "d5_count": 1},
                "severe": {"d25_count": 7, "d15_count": 5, "severe_ma_d25": 6},
            }
        }
    )
    assert (t2.caution_d25, t2.high_d25, t2.high_d15, t2.high_d5) == (2, 4, 2, 1)
    assert (t2.severe_d25, t2.severe_d15, t2.severe_ma_d25) == (7, 5, 6)


def test_required_min_sessions_takes_largest_requirement():
    rule = DistributionDayRule(expiration_sessions=25)
    assert ibd_monitor._required_min_sessions({"lookback_days": 80}, rule) == 80
    cfg = {
        "lookback_days": 10,
        "moving_average_filters": {"sma_periods": [50], "ema_periods": [21]},
    }
    assert ibd_monitor._required_min_sessions(cfg, rule) == 50
    assert ibd_monitor._required_min_sessions({"lookback_days": 5}, rule) == 27


# ---------------------------------------------------------------------------
# ibd_monitor: moving-average filters and small builders
# ---------------------------------------------------------------------------


def test_compute_ma_filters_disabled_or_empty_returns_nones():
    expected = {
        "close_above_21ema": None,
        "close_above_50sma": None,
        "market_below_21ema_or_50ma": None,
    }
    assert ibd_monitor._compute_ma_filters(descending_history(60), {"enabled": False}) == (
        expected,
        [],
    )
    assert ibd_monitor._compute_ma_filters([], {"enabled": True}) == (expected, [])


def test_compute_ma_filters_close_above_both_means_not_below():
    # Newest close is highest in a rising market: above both averages.
    filters, flags = ibd_monitor._compute_ma_filters(descending_history(60), {})
    assert filters == {
        "close_above_21ema": True,
        "close_above_50sma": True,
        "market_below_21ema_or_50ma": False,
    }
    assert flags == []


def test_compute_ma_filters_below_both_flags_market_below():
    hist = descending_history(60)
    hist[0] = make_bar(hist[0]["date"], 50.0)
    filters, flags = ibd_monitor._compute_ma_filters(hist, {})
    assert filters["close_above_21ema"] is False
    assert filters["close_above_50sma"] is False
    assert filters["market_below_21ema_or_50ma"] is True
    assert flags == []


def test_compute_ma_filters_mixed_is_not_below():
    # Newest close 120 sits below EMA(3)=127.5 but above SMA(10)=114.
    closes = [120.0, 140.0, 140.0, 140.0] + [100.0] * 6
    filters, flags = ibd_monitor._compute_ma_filters(
        make_history(closes), {"ema_periods": [3], "sma_periods": [10]}
    )
    assert filters["close_above_21ema"] is False
    assert filters["close_above_50sma"] is True
    assert filters["market_below_21ema_or_50ma"] is False
    assert flags == []


def test_compute_ma_filters_insufficient_data_flags():
    filters, flags = ibd_monitor._compute_ma_filters(descending_history(30), {})
    assert filters["close_above_21ema"] is True
    assert filters["close_above_50sma"] is None
    assert filters["market_below_21ema_or_50ma"] is None
    assert flags == ["insufficient_data_for_moving_average"]


def test_compute_ma_filters_math_error_degrades_to_none():
    # period 0 makes calc_* raise ValueError, which must degrade, not crash.
    filters, flags = ibd_monitor._compute_ma_filters(
        descending_history(10), {"ema_periods": [0], "sma_periods": [0]}
    )
    assert filters["market_below_21ema_or_50ma"] is None
    assert flags == ["insufficient_data_for_moving_average"]


def test_today_dict_empty_and_single_session():
    assert ibd_monitor._today_dict([], []) == {}
    single = [make_bar("2026-04-30", 100.0, volume=500)]
    assert ibd_monitor._today_dict(single, []) == {
        "date": "2026-04-30",
        "close": 100.0,
        "previous_close": None,
        "pct_change": None,
        "volume": 500,
        "previous_volume": None,
        "volume_change_pct": None,
    }


def test_today_dict_computes_changes():
    hist = [
        make_bar("2026-04-30", 99.0, volume=1200),
        make_bar("2026-04-29", 100.0, volume=1000),
    ]
    d = ibd_monitor._today_dict(hist, [])
    assert d["pct_change"] == pytest.approx(-0.01)
    assert d["volume_change_pct"] == pytest.approx(0.2)
    assert d["previous_close"] == 100.0
    assert d["previous_volume"] == 1000


def test_build_explanation_and_cluster_state():
    text = ibd_monitor._build_explanation("QQQ", 1, 2, 3, "CAUTION", True)
    assert text.startswith("QQQは本日Distribution Day該当。")
    assert "1/2/3" in text
    assert text.endswith("リスク判定: CAUTION。")
    assert "非該当" in ibd_monitor._build_explanation("SPY", 0, 0, 0, "NORMAL", False)
    state = ibd_monitor._build_cluster_state(2, 2, 5)
    assert state["has_d5_cluster"] is True
    assert state["has_d15_cluster"] is False
    assert state["has_d25_cluster"] is True
    assert state["cluster_description"].endswith("2/2/5")
    quiet = ibd_monitor._build_cluster_state(1, 2, 4)
    assert not any(quiet[k] for k in ("has_d5_cluster", "has_d15_cluster", "has_d25_cluster"))


# ---------------------------------------------------------------------------
# analyze_index
# ---------------------------------------------------------------------------


def _analyze(history, as_of=None, config=None):
    config = config if config is not None else ibd_monitor.load_config(None)
    return ibd_monitor.analyze_index(
        symbol="QQQ",
        benchmark_name="Nasdaq Proxy",
        history=history,
        config=config,
        rule=ibd_monitor._build_rule(config),
        thresholds=ibd_monitor._build_thresholds(config),
        as_of=as_of,
    )


def test_analyze_index_quiet_market_is_normal():
    result, flags = _analyze(descending_history(90))
    assert result.symbol == "QQQ"
    assert result.benchmark_name == "Nasdaq Proxy"
    assert (result.d5_count, result.d15_count, result.d25_count) == (0, 0, 0)
    assert result.risk_level == "NORMAL"
    assert result.is_distribution_day_today is False
    assert result.active_distribution_days == []
    assert result.today["date"] == "2026-04-30"
    assert flags == []


def test_analyze_index_detects_three_recent_distribution_days():
    result, flags = _analyze(distribution_history(90))
    assert result.is_distribution_day_today is True
    assert result.d5_count == 3
    assert result.d15_count == 3
    assert result.d25_count == 3
    ages = sorted(r["dd_index"] for r in result.active_distribution_days)
    assert ages == [0, 1, 2]
    assert result.cluster_state["has_d5_cluster"] is True
    assert result.cluster_state["has_d15_cluster"] is True
    assert result.cluster_state["has_d25_cluster"] is False
    # d5=3 >= 2 (and d15=3 >= 3) with d25=3 < 5: HIGH, not SEVERE.
    assert result.risk_level == "HIGH"
    assert "リスク判定: " + result.risk_level in result.explanation
    assert flags == []


def test_analyze_index_as_of_rebases_and_flags_short_lookback():
    hist = distribution_history(90)
    result, flags = _analyze(hist, as_of=hist[10]["date"])
    assert result.today["date"] == hist[10]["date"]
    assert result.d25_count == 0  # the DDs are newer than the as-of session
    assert flags == []
    result2, flags2 = _analyze(hist, as_of=hist[40]["date"])
    assert result2.today["date"] == hist[40]["date"]
    assert flags2 == ["insufficient_lookback"]


def test_analyze_index_unknown_as_of_raises():
    with pytest.raises(ValueError, match="as_of 2020-01-01 not found"):
        _analyze(descending_history(90), as_of="2020-01-01")


def test_build_payload_primary_symbol_prefers_qqq_else_first():
    cfg = ibd_monitor.load_config(None)
    rule = ibd_monitor._build_rule(cfg)
    thr = ibd_monitor._build_thresholds(cfg)
    spy, _ = ibd_monitor.analyze_index("SPY", "S&P", descending_history(90), cfg, rule, thr, None)
    qqq, _ = _analyze(descending_history(90))
    audit = {"as_of_resolved": "2026-04-30", "generated_at": "t"}
    p1 = ibd_monitor.build_payload(cfg, rule, thr, [spy, qqq], "NORMAL", {"x": 1}, audit)
    assert p1["market_distribution_state"]["primary_signal_symbol"] == "QQQ"
    p2 = ibd_monitor.build_payload(cfg, rule, thr, [spy], "NORMAL", {"x": 1}, audit)
    assert p2["market_distribution_state"]["primary_signal_symbol"] == "SPY"
    p3 = ibd_monitor.build_payload(cfg, rule, thr, [], "NORMAL", {}, audit)
    assert p3["market_distribution_state"]["primary_signal_symbol"] is None
    assert p1["rule_evaluation"]["rule_version"] == "ibd_dd_v1.0"
    assert p1["rule_evaluation"]["thresholds_used"]["high_d25"] == 5
    assert p1["rule_evaluation"]["distribution_day_rule"]["expiration_sessions"] == 25
    assert p1["audit"] is audit


# ---------------------------------------------------------------------------
# main() end to end with a fake client
# ---------------------------------------------------------------------------


def test_main_default_run_writes_json_and_markdown(monkeypatch, tmp_path, capsys):
    hists = {"QQQ": descending_history(90), "SPY": descending_history(90)}
    rc, client, out = run_main(monkeypatch, tmp_path, hists)
    assert rc == 0
    assert client.requested == [("QQQ", 85), ("SPY", 85)]
    payload, json_path = read_report(out)
    md_files = list(out.glob("*.md"))
    assert len(md_files) == 1
    assert md_files[0].stem == json_path.stem
    assert json_path.name.startswith("ibd_distribution_day_monitor_")
    state = payload["market_distribution_state"]
    assert state["overall_risk_level"] == "NORMAL"
    assert state["primary_signal_symbol"] == "QQQ"
    assert state["as_of"] == "2026-04-30"
    assert [r["symbol"] for r in state["index_results"]] == ["QQQ", "SPY"]
    action = payload["portfolio_action"]
    assert action["instrument"] == "TQQQ"
    assert action["recommended_action"] == "HOLD_OR_FOLLOW_BASE_STRATEGY"
    audit = payload["audit"]
    assert audit["symbols_loaded"] == ["QQQ", "SPY"]
    assert audit["symbols_requested"] == ["QQQ", "SPY"]
    assert audit["audit_flags"] == []
    assert audit["lookback_days"] == 80
    md = md_files[0].read_text(encoding="utf-8")
    assert "# IBD Distribution Day Monitor Report" in md
    assert "- **Overall Risk Level:** **NORMAL**" in md
    stdout = capsys.readouterr().out
    assert f"Wrote {json_path}" in stdout
    assert f"Wrote {md_files[0]}" in stdout


def test_main_generated_at_is_utc_isoformat(monkeypatch, tmp_path):
    hists = {"QQQ": descending_history(90), "SPY": descending_history(90)}
    rc, _, out = run_main(monkeypatch, tmp_path, hists)
    assert rc == 0
    payload, _ = read_report(out)
    stamp = payload["market_distribution_state"]["generated_at"]
    parsed = datetime.fromisoformat(stamp)
    assert parsed.utcoffset().total_seconds() == 0
    assert payload["audit"]["generated_at"] == stamp


def test_main_distribution_cluster_drives_portfolio_action(monkeypatch, tmp_path):
    hists = {"QQQ": distribution_history(90), "SPY": descending_history(90)}
    argv = ["--instrument", "QQQ", "--current-exposure", "100", "--base-trailing-stop", "9"]
    rc, _, out = run_main(monkeypatch, tmp_path, hists, argv)
    assert rc == 0
    payload, _ = read_report(out)
    state = payload["market_distribution_state"]
    qqq = next(r for r in state["index_results"] if r["symbol"] == "QQQ")
    assert qqq["d5_count"] == 3
    assert state["overall_risk_level"] == "HIGH"
    action = payload["portfolio_action"]
    assert action["instrument"] == "QQQ"
    assert action["recommended_action"] == "REDUCE_EXPOSURE"
    assert action["current_exposure_pct"] == 100
    assert action["target_exposure_pct"] == 75
    assert action["exposure_delta_pct"] == action["target_exposure_pct"] - 100
    assert action["trailing_stop_pct"] == 6
    assert payload["audit"]["config_snapshot"]["strategy_context"]["instrument"] == "QQQ"
    md = list(out.glob("*.md"))[0].read_text(encoding="utf-8")
    assert "Active Distribution Days" in md


def test_main_symbols_filter_selects_configured_index(monkeypatch, tmp_path):
    hists = {"QQQ": descending_history(90), "SPY": descending_history(90)}
    rc, client, out = run_main(monkeypatch, tmp_path, hists, ["--symbols", "spy"])
    assert rc == 0
    assert client.requested == [("SPY", 85)]
    payload, _ = read_report(out)
    results = payload["market_distribution_state"]["index_results"]
    assert [r["symbol"] for r in results] == ["SPY"]
    assert results[0]["benchmark_name"] == "S&P500 Proxy"
    assert payload["market_distribution_state"]["primary_signal_symbol"] == "SPY"


def test_main_unknown_symbol_uses_synthesized_benchmark(monkeypatch, tmp_path):
    hists = {"IWM": descending_history(90)}
    rc, client, out = run_main(monkeypatch, tmp_path, hists, ["--symbols", " IWM , "])
    assert rc == 0
    assert client.requested == [("IWM", 85)]
    payload, _ = read_report(out)
    results = payload["market_distribution_state"]["index_results"]
    assert results[0]["benchmark_name"] == "IWM proxy"
    assert payload["audit"]["symbols_requested"] == ["IWM"]


def test_main_lookback_override_changes_fetch_days(monkeypatch, tmp_path):
    hists = {"QQQ": descending_history(90)}
    rc, client, out = run_main(
        monkeypatch, tmp_path, hists, ["--symbols", "QQQ", "--lookback-days", "60"]
    )
    assert rc == 0
    assert client.requested == [("QQQ", 65)]
    payload, _ = read_report(out)
    assert payload["audit"]["lookback_days"] == 60
    assert payload["audit"]["config_snapshot"]["lookback_days"] == 60


def test_main_as_of_option_pins_evaluation_session(monkeypatch, tmp_path):
    hist = descending_history(90)
    target = hist[5]["date"]
    rc, _, out = run_main(
        monkeypatch, tmp_path, {"QQQ": hist}, ["--symbols", "QQQ", "--as-of", target]
    )
    assert rc == 0
    payload, _ = read_report(out)
    assert payload["market_distribution_state"]["as_of"] == target
    assert payload["market_distribution_state"]["index_results"][0]["today"]["date"] == target


def test_main_missing_symbol_data_is_skipped_but_run_continues(monkeypatch, tmp_path):
    hists = {"QQQ": descending_history(90)}  # SPY returns None
    rc, _, out = run_main(monkeypatch, tmp_path, hists)
    assert rc == 0
    payload, _ = read_report(out)
    audit = payload["audit"]
    assert audit["symbols_requested"] == ["QQQ", "SPY"]
    assert audit["symbols_loaded"] == ["QQQ"]
    assert audit["audit_flags"] == ["no_data_returned"]


def test_main_returns_1_when_no_symbol_loads(monkeypatch, tmp_path, capsys):
    rc, _, out = run_main(monkeypatch, tmp_path, {})
    assert rc == 1
    assert "ERROR: no symbols loaded" in capsys.readouterr().err
    assert not out.exists()


def test_main_data_quality_issues_surface_in_audit(monkeypatch, tmp_path):
    hist = descending_history(90)
    hist[20] = dict(hist[20], volume=0)
    rc, _, out = run_main(monkeypatch, tmp_path, {"QQQ": hist}, ["--symbols", "QQQ"])
    assert rc == 0
    payload, _ = read_report(out)
    audit = payload["audit"]
    assert "data_quality_warnings" in audit["audit_flags"]
    assert {"date": hist[20]["date"], "reason": "invalid_volume"} in audit["skipped_sessions"]


def test_main_short_history_flags_insufficient_lookback_and_ma(monkeypatch, tmp_path):
    hist = descending_history(30)
    rc, _, out = run_main(monkeypatch, tmp_path, {"QQQ": hist}, ["--symbols", "QQQ"])
    assert rc == 0
    payload, _ = read_report(out)
    flags = payload["audit"]["audit_flags"]
    assert "insufficient_lookback" in flags
    assert "insufficient_data_for_moving_average" in flags
    assert flags == sorted(flags)


def test_main_missing_api_key_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(ValueError, match="FMP API key required"):
        ibd_monitor.main(["--output-dir", str(tmp_path / "o")])
    assert not (tmp_path / "o").exists()


def test_main_cli_api_key_is_passed_to_client_builder(monkeypatch, tmp_path):
    seen = {}
    client = FakeMonitorClient({"QQQ": descending_history(90)})

    def builder(api_key):
        seen["key"] = api_key
        return client

    monkeypatch.setattr(ibd_monitor, "build_fmp_client", builder)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    rc = ibd_monitor.main(
        ["--symbols", "QQQ", "--api-key", FAKE_KEY, "--output-dir", str(tmp_path / "o")]
    )
    assert rc == 0
    assert seen["key"] == FAKE_KEY


def test_main_config_file_override_and_key_redacted_in_report(monkeypatch, tmp_path):
    cfg = {
        "indexes": [{"symbol": "QQQ", "benchmark_name": "Custom Bench"}],
        "lookback_days": 70,
        "data": {"provider": "fmp", "api_key": FAKE_KEY},
        "strategy_context": {"instrument": "QQQ", "current_exposure_pct": 80},
    }
    cfg_path = tmp_path / "custom.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    rc, client, out = run_main(
        monkeypatch, tmp_path, {"QQQ": descending_history(90)}, ["--config", str(cfg_path)], None
    )
    assert rc == 0
    assert client.requested == [("QQQ", 75)]
    payload, json_path = read_report(out)
    assert (
        payload["market_distribution_state"]["index_results"][0]["benchmark_name"] == "Custom Bench"
    )
    assert payload["portfolio_action"]["current_exposure_pct"] == 80
    # config-supplied key must never reach the written artifacts
    assert FAKE_KEY not in json_path.read_text(encoding="utf-8")
    assert FAKE_KEY not in list(out.glob("*.md"))[0].read_text(encoding="utf-8")
    assert payload["audit"]["config_snapshot"]["data"]["api_key"] == "***REDACTED***"


def test_main_empty_config_falls_back_to_default_indexes_and_policy(monkeypatch, tmp_path):
    cfg_path = tmp_path / "empty.yaml"
    cfg_path.write_text("", encoding="utf-8")
    hists = {"QQQ": descending_history(90), "SPY": descending_history(90)}
    rc, client, out = run_main(monkeypatch, tmp_path, hists, ["--config", str(cfg_path)])
    assert rc == 0
    assert client.requested == [("QQQ", 85), ("SPY", 85)]
    payload, _ = read_report(out)
    assert payload["portfolio_action"]["instrument"] == "TQQQ"
    assert payload["portfolio_action"]["current_exposure_pct"] == 100
    assert payload["portfolio_action"]["trailing_stop_pct"] == 10


# ---------------------------------------------------------------------------
# data_loader
# ---------------------------------------------------------------------------


def test_normalize_history_shapes():
    rows = [{"date": "2026-04-30"}]
    assert data_loader.normalize_history(None) == []
    assert data_loader.normalize_history({"historical": rows}) == rows
    assert data_loader.normalize_history({"historical": None}) == []
    assert data_loader.normalize_history(rows) == rows
    assert data_loader.normalize_history("garbage") == []


def test_validate_history_quality_flags_all_problem_kinds():
    history = [
        {"date": "d1", "close": None, "volume": 1},
        {"date": "d2", "close": -1, "volume": None},
        {"date": "d3", "close": 5, "volume": 0},
        {"date": "d4", "close": 5, "volume": 5},
    ]
    flags, skipped = data_loader.validate_history_quality(history)
    assert flags == ["data_quality_warnings"]
    assert skipped == [
        {"date": "d1", "reason": "missing_close"},
        {"date": "d2", "reason": "invalid_close"},
        {"date": "d2", "reason": "missing_volume"},
        {"date": "d3", "reason": "invalid_volume"},
    ]


def test_fetch_ohlcv_no_data_and_clean_data():
    empty = FakeMonitorClient({})
    hist, audit = data_loader.fetch_ohlcv(empty, "QQQ", days=10)
    assert hist == []
    assert audit["audit_flags"] == ["no_data_returned"]
    assert audit["sessions_loaded"] == 0
    good = FakeMonitorClient({"QQQ": descending_history(5)})
    hist, audit = data_loader.fetch_ohlcv(good, "QQQ", days=10)
    assert len(hist) == 5
    assert audit["sessions_loaded"] == 5
    assert audit["days_requested"] == 10
    assert audit["audit_flags"] == []
    assert audit["data_source"] == "fmp"


def test_build_fmp_client_returns_configured_client():
    client = data_loader.build_fmp_client(api_key=FAKE_KEY, max_api_calls=7)
    assert isinstance(client, FMPClient)
    assert client.api_key == FAKE_KEY
    assert client.max_api_calls == 7


# ---------------------------------------------------------------------------
# report_generator
# ---------------------------------------------------------------------------


def _full_payload():
    return {
        "market_distribution_state": {
            "as_of": "2026-04-30",
            "overall_risk_level": "HIGH",
            "primary_signal_symbol": "QQQ",
            "generated_at": "2026-04-30T12:00:00+00:00",
            "index_results": [
                {
                    "symbol": "QQQ",
                    "risk_level": "HIGH",
                    "is_distribution_day_today": True,
                    "d5_count": 2,
                    "d15_count": 3,
                    "d25_count": 4,
                    "cluster_state": {"cluster_description": "clustered"},
                    "trend_filters": {
                        "close_above_21ema": False,
                        "close_above_50sma": True,
                        "market_below_21ema_or_50ma": False,
                    },
                    "explanation": "explained",
                    "active_distribution_days": [
                        {
                            "date": "2026-04-29",
                            "close": 99.5,
                            "pct_change": -0.0075,
                            "volume_change_pct": None,
                            "age_sessions": 1,
                            "expires_in_sessions": 24,
                            "high_since": 100.1,
                            "invalidation_price": 104.5,
                        }
                    ],
                }
            ],
        },
        "portfolio_action": {
            "instrument": "TQQQ",
            "recommended_action": "REDUCE_EXPOSURE",
            "current_exposure_pct": 100,
            "target_exposure_pct": 50,
            "exposure_delta_pct": -50,
            "trailing_stop_pct": 6,
            "alternative_action": "SWITCH_PARTIAL_TO_QQQ",
            "rationale": "because",
        },
        "audit": {
            "data_source": "fmp",
            "symbols_loaded": ["QQQ", "SPY"],
            "audit_flags": ["x"],
            "rule_version": "ibd_dd_v1.0",
            "api_key": "should-vanish",  # pragma: allowlist secret
        },
    }


def test_render_markdown_full_payload_sections():
    md = report_generator.render_markdown(_full_payload())
    assert "- **As of:** 2026-04-30" in md
    assert "### QQQ — risk: **HIGH**" in md
    assert "- d5 / d15 / d25 = 2 / 3 / 4" in md
    assert "- Cluster: clustered" in md
    assert "close_above_21ema=False, close_above_50sma=True" in md
    assert "> explained" in md
    assert "| 2026-04-29 | 99.5 | -0.75% | — | 1 | 24 | 100.1 | 104.5 |" in md
    assert "- **Exposure:** current 100% → target 50% (delta -50%)" in md
    assert "- **Trailing Stop:** 6%" in md
    assert "- **Alternative:** SWITCH_PARTIAL_TO_QQQ" in md
    assert "> because" in md
    assert "- **Symbols:** QQQ, SPY" in md
    assert "- **Rule Version:** ibd_dd_v1.0" in md
    assert md.endswith("\n")


def test_render_markdown_empty_payload_uses_na_defaults():
    md = report_generator.render_markdown({})
    assert "- **As of:** N/A" in md
    assert "- **Overall Risk Level:** **N/A**" in md
    assert "- **Data Source:** N/A" in md
    assert "- **Symbols:** " in md
    assert "Recommended Action" not in md


def test_render_markdown_omits_optional_action_lines():
    payload = _full_payload()
    payload["portfolio_action"]["alternative_action"] = None
    payload["portfolio_action"]["rationale"] = ""
    md = report_generator.render_markdown(payload)
    assert "**Alternative:**" not in md
    assert "> because" not in md


def test_fmt_pct_handles_none_numbers_and_strings():
    assert report_generator._fmt_pct(None) == "—"
    assert report_generator._fmt_pct(0.1234) == "12.34%"
    assert report_generator._fmt_pct("n/a") == "n/a"


def test_write_json_and_markdown_redact_and_create_dirs(tmp_path):
    payload = _full_payload()
    jpath = tmp_path / "a" / "b" / "r.json"
    mpath = tmp_path / "c" / "r.md"
    report_generator.write_json(payload, jpath)
    report_generator.write_markdown(payload, mpath)
    saved = json.loads(jpath.read_text(encoding="utf-8"))
    assert saved["audit"]["api_key"] == "***REDACTED***"
    assert saved["market_distribution_state"]["index_results"][0]["explanation"] == "explained"
    assert mpath.read_text(encoding="utf-8").startswith("# IBD Distribution Day Monitor Report")


def test_redact_walks_lists_and_ignores_case():
    out = report_generator._redact(
        [{"Authorization": "Bearer x", "nested": [{"TOKEN": "t", "ok": 1}]}, 5]
    )
    assert out == [
        {"Authorization": "***REDACTED***", "nested": [{"TOKEN": "***REDACTED***", "ok": 1}]},
        5,
    ]


# ---------------------------------------------------------------------------
# _fmp_compat
# ---------------------------------------------------------------------------


def test_compat_et_today_converts_explicit_now():
    # 03:00 UTC on Apr 30 is still Apr 29 in New York (EDT, UTC-4).
    now = datetime(2026, 4, 30, 3, 0, tzinfo=timezone.utc)
    assert _fmp_compat._et_today(now).isoformat() == "2026-04-29"
    assert fmp_client._et_today(now).isoformat() == "2026-04-29"


def test_compat_et_today_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        _fmp_compat._et_today(datetime(2026, 4, 30, 3, 0))
    with pytest.raises(ValueError, match="timezone-aware"):
        fmp_client._et_today(datetime(2026, 4, 30, 3, 0))


def test_compat_et_today_without_now_returns_new_york_date(monkeypatch):
    class FakeDT:
        @staticmethod
        def now(tz):
            return datetime(2026, 7, 4, 23, 30, tzinfo=tz)

    monkeypatch.setattr(_fmp_compat, "datetime", FakeDT)
    assert _fmp_compat._et_today().isoformat() == "2026-07-04"


def test_compat_et_today_missing_tzdata_raises(monkeypatch):
    def boom(_name):
        raise _fmp_compat.ZoneInfoNotFoundError("x")

    monkeypatch.setattr(_fmp_compat, "ZoneInfo", boom)
    with pytest.raises(RuntimeError, match="tzdata"):
        _fmp_compat._et_today()


def test_v3_to_stable_passthrough_for_non_v3_url():
    url = "https://financialmodelingprep.com/stable/quote"
    assert _fmp_compat.v3_to_stable(url, {"a": 1}) == (url, {"a": 1})
    assert _fmp_compat.v3_to_stable(url) == (url, {})


def test_v3_to_stable_historical_price_with_timeseries(monkeypatch):
    monkeypatch.setattr(_fmp_compat, "_et_today", lambda now=None: datetime(2026, 4, 30).date())
    url, params = _fmp_compat.v3_to_stable(
        "https://financialmodelingprep.com/api/v3/historical-price-full/SPY",
        {"timeseries": 10},
    )
    assert url == "https://financialmodelingprep.com/stable/historical-price-eod/full"
    assert params == {"symbol": "SPY", "from": "2026-04-10", "to": "2026-04-30"}


def test_v3_to_stable_historical_price_without_timeseries_keeps_params():
    url, params = _fmp_compat.v3_to_stable(
        "https://financialmodelingprep.com/api/v3/historical-price-full/SPY", {"from": "a"}
    )
    assert url.endswith("/stable/historical-price-eod/full")
    assert params == {"from": "a", "symbol": "SPY"}


def test_v3_to_stable_dividend_and_earnings_history_subpaths():
    base = "https://financialmodelingprep.com/api/v3/"
    url, params = _fmp_compat.v3_to_stable(base + "historical-price-full/stock_dividend/AAPL")
    assert url.endswith("/stable/dividends")
    assert params == {"symbol": "AAPL"}
    url, params = _fmp_compat.v3_to_stable(base + "historical/earning_calendar/MSFT")
    assert url.endswith("/stable/earnings")
    assert params == {"symbol": "MSFT"}


def test_v3_to_stable_symbol_in_path_and_bare_endpoints():
    base = "https://financialmodelingprep.com/api/v3/"
    url, params = _fmp_compat.v3_to_stable(base + "profile/AAPL")
    assert url.endswith("/stable/profile")
    assert params == {"symbol": "AAPL"}
    url, params = _fmp_compat.v3_to_stable(base + "etf-holder/SPY/", {"k": "v"})
    assert url.endswith("/stable/etf-holdings")
    assert params == {"k": "v", "symbol": "SPY"}
    url, params = _fmp_compat.v3_to_stable(base + "quote", {"symbol": "X"})
    assert url.endswith("/stable/quote")
    assert params == {"symbol": "X"}


def test_v3_to_stable_hyphen_renames_and_underscore_fallthrough():
    base = "https://financialmodelingprep.com/api/v3/"
    url, _ = _fmp_compat.v3_to_stable(base + "sp500_constituent")
    assert url.endswith("/stable/sp500-constituent")
    url, params = _fmp_compat.v3_to_stable(
        base + "earning_calendar", {"from": "2026-01-01", "to": "2026-01-02"}
    )
    assert url.endswith("/stable/earnings-calendar")
    assert params == {"from": "2026-01-01", "to": "2026-01-02"}
    url, _ = _fmp_compat.v3_to_stable(base + "some_unmapped_thing")
    assert url.endswith("/stable/some_unmapped_thing")


def test_v3_to_stable_does_not_mutate_input_params():
    original = {"timeseries": 5}
    _fmp_compat.v3_to_stable(
        "https://financialmodelingprep.com/api/v3/historical-price-full/SPY", original
    )
    assert original == {"timeseries": 5}


# ---------------------------------------------------------------------------
# fmp_client: construction, URL builders, normalizer
# ---------------------------------------------------------------------------


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(ValueError, match="FMP API key required"):
        FMPClient()
    with pytest.raises(ValueError, match="FMP API key required"):
        FMPClient(api_key="   ")


def test_client_reads_key_from_env_and_strips(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "  env-key-9  ")
    client = FMPClient()
    assert client.api_key == "env-key-9"  # pragma: allowlist secret
    assert client.session.headers["apikey"] == "env-key-9"  # pragma: allowlist secret


def test_redact_key_masks_query_values_case_insensitively():
    assert fmp_client._redact_key("u?APIKEY=abc&x=1") == "u?APIKEY=REDACTED&x=1"
    assert fmp_client._redact_key("u?x=1&api_key=zzz") == "u?x=1&api_key=REDACTED"


def test_redact_secret_masks_url_encoded_key():
    client = FMPClient(api_key="a b/c")
    text = client._redact_secret("echo a%20b%2fc and a+b%2Fc and a b/c")
    assert "a%20b" not in text
    assert "a+b" not in text
    assert "a b/c" not in text
    assert text.count("***REDACTED***") == 3


def test_stable_hist_url_converts_timeseries_to_date_range(monkeypatch):
    monkeypatch.setattr(fmp_client, "_et_today", lambda now=None: datetime(2026, 4, 30).date())
    base, params = fmp_client._stable_hist_url(STABLE_URL, "QQQ", {"timeseries": 10})
    assert base == STABLE_URL
    assert params == {"symbol": "QQQ", "from": "2026-04-10", "to": "2026-04-30"}


def test_stable_hist_url_without_timeseries_only_sets_symbol():
    base, params = fmp_client._stable_hist_url(STABLE_URL, "QQQ", {})
    assert (base, params) == (STABLE_URL, {"symbol": "QQQ"})


def test_v3_hist_url_puts_symbol_in_path():
    assert fmp_client._v3_hist_url("https://h/v3", "SPY", {"timeseries": 5}) == (
        "https://h/v3/SPY",
        {"timeseries": 5},
    )


def test_normalize_eod_flat_list_variants():
    norm = fmp_client._normalize_eod_flat_list
    as_dict = {"historical": []}
    assert norm(as_dict, "SPY") is as_dict
    assert norm([], "SPY") is None
    rows = [
        {"symbol": "SPY", "date": "d3", "close": 3},
        {"date": "d2", "close": 2},
        {"symbol": "QQQ", "date": "dx", "close": 9},
        "junk",
        {"symbol": "SPY", "date": "d1", "close": 1},
    ]
    assert norm(rows, "SPY") == {
        "symbol": "SPY",
        "historical": [
            {"date": "d3", "close": 3},
            {"date": "d2", "close": 2},
            {"date": "d1", "close": 1},
        ],
    }
    assert norm(rows, "SPY", limit=2)["historical"] == [
        {"date": "d3", "close": 3},
        {"date": "d2", "close": 2},
    ]
    assert norm(rows, "SPY", limit=0)["historical"][-1] == {"date": "d1", "close": 1}
    # Rows lacking a symbol are attributed to whatever was requested (lenient),
    # but rows explicitly labelled with other symbols never match.
    assert norm(rows, "IWM") == {"symbol": "IWM", "historical": [{"date": "d2", "close": 2}]}
    assert norm([r for r in rows if r != rows[1]], "IWM") is None
    assert norm([{"symbol": "BRK.B", "date": "d"}], "BRK-B") == {
        "symbol": "BRK.B",
        "historical": [{"date": "d"}],
    }


# ---------------------------------------------------------------------------
# fmp_client: _rate_limited_get
# ---------------------------------------------------------------------------


def test_rate_limited_get_budget_exhausted_raises_before_request():
    client = make_client(max_api_calls=0)
    with pytest.raises(ApiCallBudgetExceeded, match="0/0 calls used"):
        client._rate_limited_get("https://x/y")
    assert client.session.calls == []


def test_rate_limited_get_short_circuits_after_daily_limit():
    client = make_client()
    client.rate_limit_reached = True
    assert client._rate_limited_get("https://x/y") is None
    assert client._last_error == "daily rate limit already reached"
    assert client.session.calls == []


def test_rate_limited_get_sleeps_to_honor_rate_delay(monkeypatch):
    sleeps = []
    fake_time = SimpleNamespace(time=lambda: 1000.0, sleep=sleeps.append)
    monkeypatch.setattr(fmp_client, "time", fake_time)
    client = make_client(FakeResponse(200, {"ok": True}))
    client.RATE_LIMIT_DELAY = 0.3
    client.last_call_time = 999.9
    assert client._rate_limited_get("https://x/y") == {"ok": True}
    assert sleeps == [pytest.approx(0.2)]
    assert client.api_calls_made == 1
    assert client.last_call_time == 1000.0


def test_rate_limited_get_429_waits_then_retries(monkeypatch, capsys):
    sleeps = []
    monkeypatch.setattr(fmp_client.time, "sleep", sleeps.append)
    client = make_client(FakeResponse(429), FakeResponse(200, [1]))
    assert client._rate_limited_get("https://x/y") == [1]
    assert 60 in sleeps
    assert "Rate limit exceeded" in capsys.readouterr().err
    assert client.retry_count == 0
    assert client.api_calls_made == 2


def test_rate_limited_get_second_429_marks_daily_limit(monkeypatch, capsys):
    monkeypatch.setattr(fmp_client.time, "sleep", lambda _s: None)
    client = make_client(FakeResponse(429), FakeResponse(429))
    assert client._rate_limited_get("https://x/y") is None
    assert client.rate_limit_reached is True
    assert client._last_error == "HTTP 429 (daily rate limit)"
    assert "Daily API rate limit reached" in capsys.readouterr().err
    # Subsequent calls short-circuit without touching the session.
    assert client._rate_limited_get("https://x/y") is None
    assert len(client.session.calls) == 2


def test_rate_limited_get_http_error_quiet_vs_loud(capsys):
    client = make_client(FakeResponse(500, text="boom"), FakeResponse(500, text="boom"))
    assert client._rate_limited_get("https://x/y", quiet=True) is None
    assert capsys.readouterr().err == ""
    assert client._last_error == "HTTP 500 - boom"
    assert client._rate_limited_get("https://x/y") is None
    assert "ERROR: API request failed: HTTP 500 - boom" in capsys.readouterr().err


def test_rate_limited_get_invalid_json_loud_retry_warning(capsys):
    class BadJson(FakeResponse):
        def json(self):
            raise ValueError("nope")

    client = make_client(BadJson(200), FakeResponse(200, {"k": 1}))
    assert client._rate_limited_get("https://x/y") == {"k": 1}
    assert "retrying once" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# fmp_client: fallback chain and public methods
# ---------------------------------------------------------------------------


def eod_rows(symbol="QQQ", n=3):
    return [
        {"symbol": symbol, "date": f"2026-04-{30 - i:02d}", "close": 100.0 - i} for i in range(n)
    ]


def test_request_with_fallback_stable_success_normalizes_and_truncates(monkeypatch):
    monkeypatch.setattr(fmp_client, "_et_today", lambda now=None: datetime(2026, 4, 30).date())
    client = make_client(FakeResponse(200, eod_rows("QQQ", 5)))
    data = client._request_with_fallback("historical", "QQQ", {"timeseries": 2})
    assert [r["date"] for r in data["historical"]] == ["2026-04-30", "2026-04-29"]
    assert data["symbol"] == "QQQ"
    url, params = client.session.calls[0]
    assert url == STABLE_URL
    assert params == {"symbol": "QQQ", "from": "2026-04-26", "to": "2026-04-30"}
    assert client._endpoint_failures[STABLE_URL] == 0


def test_request_with_fallback_falls_back_to_v3_with_warning(monkeypatch, capsys):
    monkeypatch.setattr(fmp_client, "_et_today", lambda now=None: datetime(2026, 4, 30).date())
    v3_payload = {"symbol": "QQQ", "historical": [{"date": "2026-04-30", "close": 1}]}
    client = make_client(FakeResponse(403, text="Legacy"), FakeResponse(200, v3_payload))
    data = client._request_with_fallback("historical", "QQQ", {"timeseries": 5})
    assert data == v3_payload
    assert (
        client.session.calls[1][0]
        == "https://financialmodelingprep.com/api/v3/historical-price-full/QQQ"
    )
    assert client.session.calls[1][1] == {"timeseries": 5}
    err = capsys.readouterr().err
    assert "WARN: " + STABLE_URL in err
    assert "HTTP 403" in err
    assert client._endpoint_failures[STABLE_URL] == 1


def test_request_with_fallback_all_endpoints_fail_returns_none(monkeypatch):
    monkeypatch.setattr(fmp_client, "_et_today", lambda now=None: datetime(2026, 4, 30).date())
    client = make_client(FakeResponse(500, text="a"), FakeResponse(500, text="b"))
    assert client._request_with_fallback("historical", "QQQ", {"timeseries": 5}) is None
    assert client._last_error == "HTTP 500 - b"


def test_request_with_fallback_no_matching_rows_tries_next(monkeypatch, capsys):
    monkeypatch.setattr(fmp_client, "_et_today", lambda now=None: datetime(2026, 4, 30).date())
    v3 = {"symbol": "QQQ", "historical": [{"date": "x"}]}
    client = make_client(FakeResponse(200, eod_rows("SPY")), FakeResponse(200, v3))
    assert client._request_with_fallback("historical", "QQQ", {"timeseries": 5}) == v3
    assert "no rows matching 'QQQ'" in capsys.readouterr().err


def test_request_with_fallback_rejects_wrong_shapes(capsys):
    client = make_client(
        FakeResponse(200, {"symbol": "QQQ"}),
        FakeResponse(200, {"symbol": "SPY", "historical": [{"d": 1}]}),
    )
    assert client._request_with_fallback("historical", "QQQ") is None
    err = capsys.readouterr().err
    assert "missing 'historical' key" in err


def test_request_with_fallback_symbol_mismatch_in_v3_dict(capsys):
    client = make_client(
        FakeResponse(200, {"symbol": "SPY", "historical": [{"d": 1}]}),
        FakeResponse(200, {"symbol": "SPY", "historical": [{"d": 1}]}),
    )
    assert client._request_with_fallback("historical", "QQQ") is None
    assert "response symbol 'SPY' != requested 'QQQ'" in capsys.readouterr().err


def test_request_with_fallback_non_dict_after_normalizer_is_rejected():
    client = make_client(FakeResponse(200, "weird"), FakeResponse(200, "weird"))
    assert client._request_with_fallback("historical", "QQQ") is None
    assert client._endpoint_failures[STABLE_URL] == 1
    assert (
        client._endpoint_failures[V3_URL.replace("historical-price", "historical-price-full")] == 1
    )


def test_request_with_fallback_historical_stock_list_batch_format():
    batch = {
        "historicalStockList": [
            {"symbol": "SPY", "historical": [{"date": "s"}]},
            {"symbol": "BRK.B", "historical": [{"date": "b"}]},
        ]
    }
    client = make_client(FakeResponse(200, batch))
    found = client._request_with_fallback("historical", "BRK-B")
    assert found == {"symbol": "BRK.B", "historical": [{"date": "b"}]}


def test_request_with_fallback_stock_list_without_symbol_falls_through():
    batch = {"historicalStockList": [{"symbol": "SPY", "historical": []}]}
    v3 = {"symbol": "QQQ", "historical": [{"date": "q"}]}
    client = make_client(FakeResponse(200, batch), FakeResponse(200, v3))
    assert client._request_with_fallback("historical", "QQQ") == v3


def test_circuit_breaker_disables_endpoint_after_three_failures():
    client = make_client()
    for _ in range(3):
        client._record_endpoint_failure(STABLE_URL)
    assert STABLE_URL in client._disabled_endpoints
    client.session.outcomes = [FakeResponse(200, {"symbol": "QQQ", "historical": [{"date": "q"}]})]
    data = client._request_with_fallback("historical", "QQQ")
    assert data["historical"] == [{"date": "q"}]
    assert [c[0] for c in client.session.calls] == [
        "https://financialmodelingprep.com/api/v3/historical-price-full/QQQ"
    ]


def test_warn_fallback_is_silent_for_last_endpoint_or_empty_reason(capsys):
    client = make_client()
    client._warn_fallback("u", True, "reason")
    client._warn_fallback("u", False, None)
    assert capsys.readouterr().err == ""
    client._warn_fallback("u", False, "why")
    assert "WARN: u failed (why); falling back to next endpoint" in capsys.readouterr().err


def test_get_historical_prices_caches_successful_result(monkeypatch):
    monkeypatch.setattr(fmp_client, "_et_today", lambda now=None: datetime(2026, 4, 30).date())
    client = make_client(FakeResponse(200, eod_rows("QQQ", 3)))
    first = client.get_historical_prices("QQQ", days=3)
    second = client.get_historical_prices("QQQ", days=3)
    assert second is first
    assert len(client.session.calls) == 1
    assert "prices_QQQ_3" in client.cache


def test_get_historical_prices_failure_is_not_cached():
    client = make_client(FakeResponse(500), FakeResponse(500))
    assert client.get_historical_prices("QQQ", days=3) is None
    assert client.cache == {}


def test_get_earnings_calendar_uses_stable_url_and_caches():
    rows = [{"symbol": "AAPL", "date": "2026-05-01", "time": "amc"}]
    client = make_client(FakeResponse(200, rows))
    assert client.get_earnings_calendar("2026-05-01", "2026-05-07") == rows
    url, params = client.session.calls[0]
    assert url == "https://financialmodelingprep.com/stable/earnings-calendar"
    assert params == {"from": "2026-05-01", "to": "2026-05-07", "includeReportTimes": "true"}
    assert client.get_earnings_calendar("2026-05-01", "2026-05-07") == rows
    assert len(client.session.calls) == 1


def test_get_earnings_calendar_failure_returns_none_uncached():
    client = make_client(FakeResponse(500, text="x"))
    assert client.get_earnings_calendar("2026-05-01", "2026-05-07") is None
    assert client.cache == {}


def test_get_company_profiles_fetches_each_symbol_and_caches():
    client = make_client(
        FakeResponse(200, [{"symbol": "AAPL", "marketCap": 3}]),
        FakeResponse(200, [{"marketCap": 1}]),  # no "symbol": keyed by request
        FakeResponse(200, []),  # empty -> skipped
        FakeResponse(200, ["not-a-dict"]),  # wrong item type -> skipped
    )
    result = client.get_company_profiles(["AAPL", "MSFT", "EMPTY", "BAD"])
    assert result == {"AAPL": {"symbol": "AAPL", "marketCap": 3}, "MSFT": {"marketCap": 1}}
    assert [c[1]["symbol"] for c in client.session.calls] == ["AAPL", "MSFT", "EMPTY", "BAD"]
    assert client.session.calls[0][0] == "https://financialmodelingprep.com/stable/profile"
    # Second call served from cache (no new session outcomes available).
    again = client.get_company_profiles(["AAPL", "MSFT"])
    assert again == result
    assert len(client.session.calls) == 4


def test_get_company_profiles_ignores_non_dict_cache_entries():
    client = make_client()
    client.cache["profile_ZZZ"] = "stale"
    assert client.get_company_profiles(["ZZZ"]) == {}
    assert client.session.calls == []


def test_get_api_stats_reports_usage():
    client = make_client(FakeResponse(200, {"a": 1}), max_api_calls=5)
    client._rate_limited_get("https://x/y")
    client.cache["k"] = 1
    assert client.get_api_stats() == {
        "cache_entries": 1,
        "api_calls_made": 1,
        "max_api_calls": 5,
        "rate_limit_reached": False,
        "budget_remaining": 4,
    }
    client.api_calls_made = 9
    assert client.get_api_stats()["budget_remaining"] == 0


def test_budget_exceeded_propagates_through_fallback_chain():
    client = make_client(max_api_calls=0)
    with pytest.raises(ApiCallBudgetExceeded):
        client.get_historical_prices("QQQ", days=3)
