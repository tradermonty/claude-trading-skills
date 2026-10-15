"""Additional behavior tests: FMP client, normalizers, scoring helpers, CLI main()."""

import json
import sys
from pathlib import Path

import pytest
import screen_exhaustion_hammer as mod
from screen_exhaustion_hammer import (
    ApiCallBudgetExceeded,
    Bar,
    FMPClient,
    analyze_symbol,
    collect_price_data,
    consecutive_down_closes_before_latest,
    detect_hammer_profile,
    detect_pullback_profile,
    detect_soft_failure_tags,
    downstream_action,
    format_candidate_md,
    generate_json_report,
    generate_markdown_report,
    hammer_geometry_score,
    market_gate_score,
    merge_quote_bar,
    normalize_bars,
    normalize_fmp_historical_response,
    normalize_symbol,
    prior_momentum_score,
    quality_score,
    read_profiles_json,
    read_universe_file,
    risk_distance_score,
    score_to_rating,
    score_to_state,
    sort_results,
    to_float,
    to_int,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_screen_exhaustion_hammer import (  # noqa: E402
    _args,
    _FakeResponse,
    _FakeSession,
    _good_bars,
    _profile,
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(FMPClient, "RATE_LIMIT_DELAY", 0)


def _client(responses, max_calls=50):
    client = FMPClient(api_key="k", max_api_calls=max_calls)
    client.session = _FakeSession(responses)
    return client


def _bar_dict(date, close=100.0, volume=1000):
    return {
        "date": date,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": volume,
    }


# ---------------------------------------------------------------- FMPClient


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(ValueError, match="FMP API key required"):
        FMPClient(api_key=None)


def test_client_reads_key_from_env(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "envkey")
    assert FMPClient().api_key == "envkey"  # pragma: allowlist secret


def test_request_budget_exhausted_raises():
    client = _client([], max_calls=1)
    client.api_calls_made = 1
    with pytest.raises(ApiCallBudgetExceeded):
        client._request("https://example.test/x")


def test_request_429_sets_rate_limit_and_short_circuits(capsys):
    client = _client([_FakeResponse({}, status_code=429)])
    assert client._request("https://example.test/x") is None
    assert client.rate_limit_reached is True
    assert "rate limit" in capsys.readouterr().err
    # Subsequent calls make no HTTP request.
    assert client._request("https://example.test/y") is None
    assert len(client.session.calls) == 1


def test_request_http_error_logs_unless_quiet(capsys):
    client = _client([_FakeResponse({"e": 1}, 500), _FakeResponse({"e": 1}, 500)])
    assert client._request("https://example.test/x") is None
    assert "HTTP 500" in capsys.readouterr().err
    assert client._request("https://example.test/x", quiet=True) is None
    assert capsys.readouterr().err == ""
    assert client.api_calls_made == 2


def test_request_exception_returns_none(capsys):
    class Boom:
        def get(self, *a, **k):
            raise mod.requests.exceptions.ConnectionError("down")

    client = FMPClient(api_key="k")
    client.session = Boom()
    assert client._request("https://example.test/x") is None
    assert "down" in capsys.readouterr().err
    assert client._request("https://example.test/x", quiet=True) is None


def test_request_sleeps_when_within_rate_limit_delay(monkeypatch):
    slept = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(FMPClient, "RATE_LIMIT_DELAY", 100.0)
    client = _client([_FakeResponse({"ok": 1})])
    client.last_call_time = mod.time.time()
    assert client._request("https://example.test/x") == {"ok": 1}
    assert slept and slept[0] > 0


def test_stable_then_v3_prefers_stable_when_present():
    client = _client([_FakeResponse([{"a": 1}])])
    assert client._stable_then_v3("s", "v", {}) == [{"a": 1}]
    assert len(client.session.calls) == 1


def test_get_universe_filters_sorts_caps_and_caches():
    rows = [
        {"symbol": "small", "marketCap": 5},
        {"symbol": "big.b", "mktCap": 100},
        {"symbol": "etf", "marketCap": 999, "isEtf": True},
        {"symbol": "fund", "marketCap": 999, "isFund": True},
        {"symbol": "", "marketCap": 1},
        "junk",
        {"symbol": "mid", "marketCap": 50},
    ]
    client = _client([_FakeResponse(rows)])
    universe = client.get_universe(1e9, 20.0, 100000, max_symbols=2)
    assert [r["symbol"] for r in universe] == ["BIG-B", "MID"]
    again = client.get_universe(1e9, 20.0, 100000, max_symbols=2)
    assert again is universe
    assert len(client.session.calls) == 1


def test_get_universe_non_list_returns_empty():
    client = _client([_FakeResponse({"error": "x"}), _FakeResponse({"error": "x"})])
    assert client.get_universe(1e9, 20.0, 1000, 10) == []


def test_get_historical_prices_stable_then_cache():
    stable = [dict(_bar_dict("2026-06-26"), symbol="APP")]
    client = _client([_FakeResponse(stable)])
    bars = client.get_historical_prices("app", days=5)
    assert bars[0]["date"] == "2026-06-26" and "symbol" not in bars[0]
    assert client.get_historical_prices("APP", days=5) is bars
    assert len(client.session.calls) == 1
    assert "historical-price-eod/full" in client.session.calls[0]["url"]


def test_get_historical_prices_falls_back_to_v3():
    v3 = {"historical": [_bar_dict("2026-06-25"), _bar_dict("2026-06-24")]}
    client = _client([_FakeResponse([]), _FakeResponse(v3)])
    bars = client.get_historical_prices("APP", days=1)
    assert [b["date"] for b in bars] == ["2026-06-25"]
    assert "historical-price-full/APP" in client.session.calls[1]["url"]


def test_get_quote_bar_parses_and_caches():
    quote = [{"price": 10, "open": 9, "dayHigh": 11, "dayLow": 8, "volume": "500"}]
    client = _client([_FakeResponse(quote)])
    bar = client.get_quote_bar("app", asof_date="2026-06-26")
    assert bar == {
        "date": "2026-06-26",
        "open": 9.0,
        "high": 11.0,
        "low": 8.0,
        "close": 10.0,
        "volume": 500,
    }
    assert client.get_quote_bar("APP", asof_date="2026-06-26") is bar
    assert len(client.session.calls) == 1


def test_get_quote_bar_defaults_from_price_only():
    client = _client([_FakeResponse([{"price": 10}])])
    bar = client.get_quote_bar("APP")
    assert (bar["open"], bar["high"], bar["low"]) == (10.0, 10.0, 10.0)
    assert bar["date"] == mod.date.today().isoformat()


@pytest.mark.parametrize(
    "payload",
    [{}, [], ["notadict"], [{"price": 0}], [{"price": 10, "dayHigh": 5, "dayLow": 9}]],
)
def test_get_quote_bar_invalid_returns_none(payload):
    client = _client([_FakeResponse(payload)])
    assert client.get_quote_bar("APP") is None


def test_get_api_stats_reports_budget():
    client = _client([_FakeResponse({"x": 1})], max_calls=5)
    client._request("https://example.test/x")
    stats = client.get_api_stats()
    assert stats["api_calls_made"] == 1
    assert stats["budget_remaining"] == 4
    assert stats["rate_limit_reached"] is False


# ------------------------------------------------------------- normalizers


def test_symbol_and_number_coercion():
    assert normalize_symbol(None) == ""
    assert normalize_symbol(" nan ") == ""
    assert normalize_symbol("brk.b") == "BRK-B"
    assert to_float("abc", 3.0) == 3.0
    assert to_float(float("nan"), 1.0) == 1.0
    assert to_float(float("inf"), 2.0) == 2.0
    assert to_float("", 4.0) == 4.0
    assert to_float("2.5") == 2.5
    assert to_int("7.9") == 7
    assert to_int(None, 5) == 5
    assert to_int("x", 6) == 6


def test_normalize_bars_filters_dedups_sorts_and_limits():
    rows = [
        _bar_dict("2026-06-01"),
        _bar_dict("2026-06-03", close=103),
        _bar_dict("2026-06-03", close=104),  # duplicate date: last wins
        "junk",
        {"date": "", "close": 5},
        {"date": "2026-06-04", "close": 0},
        {"date": "2026-06-05", "open": 5, "high": 4, "low": 6, "close": 5},
        {"timestamp": "2026-06-06T00:00:00", "adjClose": 50},
    ]
    bars = normalize_bars(rows)
    assert [b.date for b in bars] == ["2026-06-06", "2026-06-03", "2026-06-01"]
    assert bars[1].close == 104
    assert bars[0].close == 50 and bars[0].high == 50  # defaults from close
    assert len(normalize_bars(rows, limit=2)) == 2
    assert normalize_bars(None) == []


def test_normalize_fmp_historical_response_shapes():
    assert normalize_fmp_historical_response(None, "A", 5) == []
    listing = [{"symbol": "A", "date": "d1"}, {"symbol": "B", "date": "d2"}, "x", {"date": "d3"}]
    rows = normalize_fmp_historical_response(listing, "A", 5)
    assert [r["date"] for r in rows] == ["d1", "d3"]
    hist = {"historical": [1, 2, 3]}
    assert normalize_fmp_historical_response(hist, "A", 2) == [1, 2]
    multi = {
        "historicalStockList": [
            {"symbol": "B", "historical": [9]},
            {"symbol": "A", "historical": [1, 2, 3]},
        ]
    }
    assert normalize_fmp_historical_response(multi, "A", 2) == [1, 2]
    assert (
        normalize_fmp_historical_response({"historicalStockList": [{"symbol": "Z"}]}, "A", 2) == []
    )
    assert normalize_fmp_historical_response({"other": 1}, "A", 2) == []


def test_merge_quote_bar_replaces_same_date_and_inserts_new():
    bars = normalize_bars([_bar_dict("2026-06-25", 100), _bar_dict("2026-06-24", 99)])
    assert merge_quote_bar(bars, None, 10) is bars
    assert merge_quote_bar(bars, {"date": "", "close": 0}, 10) is bars
    replaced = merge_quote_bar(bars, _bar_dict("2026-06-25", 120), 10)
    assert [b.date for b in replaced] == ["2026-06-25", "2026-06-24"]
    assert replaced[0].close == 120
    inserted = merge_quote_bar(bars, _bar_dict("2026-06-26", 130), 2)
    assert [b.date for b in inserted] == ["2026-06-26", "2026-06-25"]


# ---------------------------------------------------------------- file I/O


def test_read_universe_file_variants(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_universe_file(str(tmp_path / "missing.txt"))

    j1 = tmp_path / "a.json"
    j1.write_text(json.dumps(["app", "enph", "app"]))
    assert read_universe_file(str(j1)) == ["APP", "ENPH"]

    j2 = tmp_path / "b.json"
    j2.write_text(json.dumps({"symbols": [{"symbol": "nvda"}, {"ticker": "amd"}, "brk.b"]}))
    assert read_universe_file(str(j2)) == ["AMD", "BRK-B", "NVDA"]

    j3 = tmp_path / "c.json"
    j3.write_text(json.dumps("scalar"))
    assert read_universe_file(str(j3)) == []

    c = tmp_path / "d.csv"
    c.write_text("Ticker,x\nmsft,1\naapl,2\n")
    assert read_universe_file(str(c)) == ["AAPL", "MSFT"]

    c2 = tmp_path / "e.csv"
    c2.write_text("foo,bar\nzzz,1\n")
    assert read_universe_file(str(c2)) == ["ZZZ"]

    t = tmp_path / "f.txt"
    t.write_text("# comment\nlrcx,extra\n\ncrm\n")
    assert read_universe_file(str(t)) == ["CRM", "LRCX"]


def test_read_prices_json_shapes(tmp_path):
    rows = [_bar_dict("2026-06-26", 10)]

    def load(payload):
        p = tmp_path / "p.json"
        p.write_text(json.dumps(payload))
        return mod.read_prices_json(str(p))

    assert set(load({"symbols": {"a": {"historical": rows}}})) == {"A"}
    assert set(load({"prices": {"b": {"bars": rows}}})) == {"B"}
    assert set(load({"c": rows, "d": "bad", "e": []})) == {"C"}
    listed = load(
        [
            {"symbol": "f", "historical": rows},
            {"ticker": "g", "bars": rows},
            {"symbol": "h", "prices": rows},
            {"symbol": "i"},
            "junk",
        ]
    )
    assert set(listed) == {"F", "G", "H"}
    assert load(42) == {}


def test_read_profiles_json_shapes(tmp_path):
    assert read_profiles_json(None) == {}
    with pytest.raises(FileNotFoundError):
        read_profiles_json(str(tmp_path / "nope.json"))

    p = tmp_path / "p.json"
    p.write_text(json.dumps({"profiles": {"app": {"marketCap": 1}, "bad": 3}}))
    assert read_profiles_json(str(p)) == {"APP": {"marketCap": 1}}

    p.write_text(json.dumps([{"symbol": "enph", "marketCap": 2}, {"ticker": "x"}, "j", {"a": 1}]))
    result = read_profiles_json(str(p))
    assert result["ENPH"]["marketCap"] == 2 and result["X"] == {"ticker": "x"}
    assert len(result) == 2


# ------------------------------------------------------- scoring helpers


def test_risk_distance_score_tiers():
    cases = [(0, 0), (-1, 0), (2, 15), (4, 12), (7, 9), (9, 6), (11, 3), (13, 0)]
    for risk, expected in cases:
        assert risk_distance_score(risk) == expected


def test_market_gate_rating_state_mapping():
    assert [market_gate_score(g) for g in ("allowed", "neutral", "restrictive")] == [5, 3, 0]
    assert [score_to_rating(s) for s in (95, 85, 75, 60, 10)] == ["A", "A-", "B", "Watch", "Reject"]
    assert score_to_state(99, "allowed", True) == "REJECTED"
    assert score_to_state(75, "restrictive", False) == "MANUAL_REVIEW_ONLY"
    assert score_to_state(60, "restrictive", False) == "WATCH_TOMORROW"
    assert score_to_state(85, "allowed", False) == "ACTIONABLE_CLOSE_BUY"
    assert score_to_state(75, "allowed", False) == "MANUAL_REVIEW"
    assert score_to_state(60, "neutral", False) == "WATCH_TOMORROW"
    assert score_to_state(10, "neutral", False) == "REJECTED"


def test_downstream_action_text_per_state():
    assert "Near-close candidate" in downstream_action("ACTIONABLE_CLOSE_BUY", "A")
    assert "chart review" in downstream_action("MANUAL_REVIEW", "B")
    assert "restrictive" in downstream_action("MANUAL_REVIEW_ONLY", "B")
    assert "next-day" in downstream_action("WATCH_TOMORROW", "Watch")
    assert "Do not trade" in downstream_action("REJECTED", "Reject")


def test_quality_score_tiers():
    args = _args()
    latest = Bar("d", 50, 51, 49, 50, 50_000)
    q = mod.QualityProfile(0, 0, 0, 0, 0, 0, 0, 0)
    # price>=2x min (4) + volume below min (0) + unknown market cap (2)
    assert quality_score(q, latest, args) == 6
    # Latest volume >= min but no avg dollar volume: +2 fallback tier
    assert quality_score(q, Bar("d", 50, 51, 49, 50, 150_000), args) == 8
    big = mod.QualityProfile(5_000_000, 100_000_000, 1, 1, 50_000_000_000, 0, 2000, 0)
    # 4 + 6 + 5 + 3 + 2 = 20
    assert quality_score(big, Bar("d", 50, 51, 49, 50, 1), args) == 20
    mid = mod.QualityProfile(200_000, 25_000_000, 1, 1, 3_000_000_000, 45.0, 0, 0)
    # 3 (price 25>=20) + 5 + 4 + 2 + 2
    assert quality_score(mid, Bar("d", 25, 26, 24, 25, 1), args) == 16


def test_prior_momentum_score_branches():
    args = _args()
    base = dict(
        recent_high=100,
        recent_high_date="d",
        days_since_recent_high=10,
        pullback_pct_from_high=-10,
        prior_low=1,
        prior_low_date="d",
        undercut_reclaim=False,
        low_undercut_pct=0,
        down_days_10=0,
        lower_closes_5=0,
        consecutive_down_closes=0,
        below_10dma_pct=0,
        above_50dma=False,
        return_20d_pct=0,
        return_60d_pct=0,
    )

    def pb(**kw):
        return mod.PullbackProfile(**{**base, **kw})

    assert prior_momentum_score(pb(), args) == 5 + 2
    assert prior_momentum_score(pb(days_since_recent_high=35), args) == 2 + 2
    assert prior_momentum_score(pb(days_since_recent_high=50), args) == 2
    assert prior_momentum_score(pb(return_60d_pct=40, above_50dma=True), args) == 15
    assert prior_momentum_score(pb(return_60d_pct=20), args) == 5 + 4 + 2
    assert prior_momentum_score(pb(return_20d_pct=12), args) == 5 + 3 + 2


def test_pullback_exhaustion_score_branches():
    args = _args()
    pb = detect_pullback_profile(_good_bars(), args)
    q = mod.QualityProfile(0, 0, 1, 1.6, 0, 0, 0, 0)
    score = mod.pullback_exhaustion_score(pb, q, args)
    assert pb.undercut_reclaim and score >= 6 + 6 + 3  # depth + reclaim + volume shock
    shallow = mod.PullbackProfile(1, "d", 5, -30, 1, "d", False, -1.0, 5, 3, 0, 0, False, 0, 0)
    q2 = mod.QualityProfile(0, 0, 1, 1.0, 0, 0, 0, 0)
    # depth 30 (<=35 but >25 -> 4) + undercut no reclaim (3) + down_days 5 (3) + closes (2) + vol (2)
    assert mod.pullback_exhaustion_score(shallow, q2, args) == 14
    # Depth beyond max_pullback_pct, no undercut, no down days, no volume: zero.
    none = mod.PullbackProfile(1, "d", 5, -50, 1, "d", False, 1.0, 0, 0, 0, 0, False, 0, 0)
    assert (
        mod.pullback_exhaustion_score(none, mod.QualityProfile(0, 0, 0, 0, 0, 0, 0, 0), args) == 0
    )


def test_hammer_geometry_score_extremes_and_floor():
    args = _args()
    perfect = mod.HammerProfile(
        1, 1, 0.1, 10, 0.8, 80, 0.1, 10, 8.0, 90, 5.0, 3.0, 1, True, [], "x"
    )
    # 8 + 5 + 5 + 3 + 2 + 1 + 1 = 25
    assert hammer_geometry_score(perfect, args) == 25
    weak = mod.HammerProfile(1, 1, 0.9, 90, 0.0, 0, 0.5, 50, 0.0, 10, 0.0, -1.0, -1, False, [], "x")
    assert hammer_geometry_score(weak, args) == 0
    mid = mod.HammerProfile(1, 1, 0.3, 30, 0.45, 45, 0.25, 25, 1.6, 65, 2.5, 1.0, 1, True, [], "x")
    # 6 + 4 + 4 + 2 + 1 + 1 + 1
    assert hammer_geometry_score(mid, args) == 19


def test_consecutive_down_closes_stops_at_first_up_close():
    bars = [
        Bar("d0", 10, 10, 10, 10, 1),
        Bar("d1", 10, 10, 10, 9, 1),
        Bar("d2", 10, 10, 10, 10, 1),
        Bar("d3", 10, 10, 10, 11, 1),
        Bar("d4", 10, 10, 10, 8, 1),
    ]
    assert consecutive_down_closes_before_latest(bars) == 2


def test_detect_soft_failure_tags_collects_each_weakness():
    args = _args()
    hammer = detect_hammer_profile(_good_bars(), args)
    pullback = detect_pullback_profile(_good_bars(), args)
    quality = mod.QualityProfile(1, 1, 1, 1.0, 0, 0, 0, 0)
    assert detect_soft_failure_tags(hammer, pullback, quality, 2.0, args) == []

    bad_pullback = mod.PullbackProfile(1, "d", 40, -30, 1, "d", False, 0, 0, 0, 0, 0, False, 0, 0)
    bad_hammer = mod.HammerProfile(1, 1, 1, 1, 0, 0, 0, 0, 0, 50.0, 0, -5.0, 0, False, [], "x")
    weak_q = mod.QualityProfile(1, 1, 1, 0.5, 0, 0, 0, 0)
    tags = detect_soft_failure_tags(bad_hammer, bad_pullback, weak_q, 9.0, args)
    assert tags == [
        "no_undercut_reclaim",
        "deep_pullback",
        "stale_high",
        "weak_volume_confirmation",
        "moderate_close_location",
        "still_down_big_on_day",
        "wide_risk",
    ]


def test_hammer_profile_flat_bar_edge_case():
    bars = [Bar("d0", 10, 10, 10, 10, 1), Bar("d1", 10, 10, 10, 10, 1)]
    h = detect_hammer_profile(bars, _args())
    assert h.day_range > 0
    assert h.lower_wick_to_body == 999.0
    assert h.close_location_pct == 50.0


def test_confirmed_primary_trigger_for_good_hammer():
    h = detect_hammer_profile(_good_bars(), _args())
    assert h.primary_trigger == "confirmed_exhaustion_hammer"
    assert h.green_close is True


def test_pullback_profile_no_prior_window_is_zeroed():
    pb = detect_pullback_profile(_good_bars()[:1], _args())
    assert pb.recent_high == 0 and pb.recent_high_date == ""


def test_analyze_symbol_rejection_reasons_and_flags():
    bars = _good_bars()
    result = analyze_symbol(
        "APP",
        bars,
        _args(require_undercut_reclaim=True, min_days_since_high=30, max_days_since_high=10),
        profile_row={"marketCap": 1_000_000},
    )
    reasons = set(result["reject_reasons"])
    assert "below_min_market_cap" in reasons
    assert "too_close_to_recent_high" in reasons or "recent_high_too_stale" in reasons
    assert result["state"] == "REJECTED"
    assert result["setup_score"] == 0 and result["rating"] == "Reject"
    assert result["raw_setup_score"] > 0

    deep = analyze_symbol("APP", bars, _args(max_pullback_pct=5.0), profile_row=_profile())
    assert "pullback_too_deep" in deep["reject_reasons"]

    cheap = analyze_symbol("APP", bars, _args(min_price=1000.0), profile_row=_profile())
    assert "below_min_price" in cheap["reject_reasons"]


def test_analyze_symbol_volume_shock_tag():
    bars = _good_bars()
    result = analyze_symbol("APP", bars, _args(), profile_row=_profile())
    assert result["volume_ratio_20d"] >= 1.5
    assert "volume_shock" in result["trigger_tags"]
    assert result["exit_template"].startswith("low_of_day_stop")


# ------------------------------------------------------ sorting / reports


def test_sort_results_orders_by_state_then_score():
    rows = [
        {"symbol": "R", "state": "REJECTED", "setup_score": 0},
        {"symbol": "W", "state": "WATCH_TOMORROW", "setup_score": 60},
        {"symbol": "A1", "state": "ACTIONABLE_CLOSE_BUY", "setup_score": 85},
        {"symbol": "A2", "state": "ACTIONABLE_CLOSE_BUY", "setup_score": 92},
        {"symbol": "M", "state": "MANUAL_REVIEW", "setup_score": 75},
        {"symbol": "O", "state": "MANUAL_REVIEW_ONLY", "setup_score": 72},
        {"symbol": "U", "state": "WEIRD", "setup_score": 99},
    ]
    assert [r["symbol"] for r in sort_results(rows)] == ["A2", "A1", "M", "O", "W", "R", "U"]


def test_generate_json_report_payload(tmp_path):
    out = tmp_path / "r.json"
    generate_json_report([{"symbol": "APP"}], {"market_gate": "allowed"}, str(out))
    payload = json.loads(out.read_text())
    assert payload["skill"] == "stockbee-exhaustion-hammer-screener"
    assert payload["schema_version"] == "1.0"
    assert payload["candidates"] == [{"symbol": "APP"}]
    assert payload["metadata"] == {"market_gate": "allowed"}


def test_format_candidate_md_content():
    row = analyze_symbol("APP", _good_bars(), _args(), profile_row=_profile())
    text = format_candidate_md(row)
    assert text.startswith("### APP")
    assert "State: `ACTIONABLE_CLOSE_BUY`" in text
    assert "Volume: 8,500,000" in text
    assert "Reject reasons: none" in text
    assert "undercut reclaim = True" in text


def test_markdown_report_no_candidates_and_rejected_section(tmp_path):
    meta = {
        "generated_at": "t",
        "market_gate": "allowed",
        "input_mode": "symbols",
        "symbols_processed": 1,
    }
    rejected = analyze_symbol("APP", _good_bars(), _args(min_price=1000.0), profile_row=_profile())
    out = tmp_path / "r.md"
    generate_markdown_report([rejected], meta, str(out), top=5, include_rejected=False)
    text = out.read_text()
    assert "No non-rejected candidates found." in text
    assert "## Rejected" not in text
    assert "| REJECTED | 1 |" in text
    generate_markdown_report([rejected], meta, str(out), top=5, include_rejected=True)
    text = out.read_text()
    assert "## Rejected" in text and "below_min_price" in text


# ------------------------------------------------------ collect_price_data


def _fmp_args(**kw):
    base = dict(
        prices_json=None,
        profiles_json=None,
        symbols=[],
        universe_file=None,
        max_symbols=10,
        api_key="k",
        max_api_calls=50,
        fmp_universe=False,
        history_days=5,
        use_quote_latest=False,
        asof_date=None,
    )
    base.update(kw)
    return _args(**base)


def test_collect_price_data_offline_filters_explicit_symbols(tmp_path):
    rows = [_bar_dict("2026-06-26", 10)]
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"AAA": rows, "BBB": rows}))
    args = _fmp_args(prices_json=str(p), symbols=["bbb"])
    data, _, stats = collect_price_data(args)
    assert list(data) == ["BBB"] and stats is None


def test_collect_price_data_no_symbols_raises(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "k")
    with pytest.raises(ValueError, match="No symbols to process"):
        collect_price_data(_fmp_args())


def test_collect_price_data_fmp_symbols_with_quote_merge():
    hist = [dict(_bar_dict("2026-06-25", 100), symbol="APP")]
    quote = [{"price": 105, "open": 101, "dayHigh": 106, "dayLow": 100, "volume": 10}]
    sessions = [_FakeResponse(hist), _FakeResponse(quote)]
    original_init = FMPClient.__init__

    def init(self, *a, **k):
        original_init(self, *a, **k)
        self.session = _FakeSession(sessions)

    FMPClient.__init__ = init
    try:
        args = _fmp_args(symbols=["app"], use_quote_latest=True, asof_date="2026-06-26")
        data, profiles, stats = collect_price_data(args)
    finally:
        FMPClient.__init__ = original_init
    assert [b.date for b in data["APP"]] == ["2026-06-26", "2026-06-25"]
    assert data["APP"][0].close == 105.0
    assert stats["api_calls_made"] == 2


def test_collect_price_data_fmp_universe_populates_profiles(monkeypatch):
    universe = [{"symbol": "APP", "marketCap": 5}]
    hist = [dict(_bar_dict("2026-06-25", 100), symbol="APP")]
    session = _FakeSession([_FakeResponse(universe), _FakeResponse(hist)])
    original_init = FMPClient.__init__

    def init(self, *a, **k):
        original_init(self, *a, **k)
        self.session = session

    monkeypatch.setattr(FMPClient, "__init__", init)
    data, profiles, _ = collect_price_data(_fmp_args(fmp_universe=True))
    assert list(data) == ["APP"]
    assert profiles["APP"]["marketCap"] == 5


def test_collect_price_data_budget_exhaustion_keeps_partial(monkeypatch, capsys):
    hist = [dict(_bar_dict("2026-06-25", 100), symbol="AAA")]
    session = _FakeSession([_FakeResponse(hist)])
    original_init = FMPClient.__init__

    def init(self, *a, **k):
        original_init(self, *a, **k)
        self.session = session

    monkeypatch.setattr(FMPClient, "__init__", init)
    args = _fmp_args(symbols=["AAA", "BBB"], max_api_calls=1)
    data, _, stats = collect_price_data(args)
    assert list(data) == ["AAA"]
    assert "API budget exhausted at BBB" in capsys.readouterr().out
    assert stats["budget_remaining"] == 0


# ------------------------------------------------------------------- main()


def _write_prices(tmp_path, with_good=True):
    bars = [
        {
            "date": b.date,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in _good_bars()
    ]
    short = [_bar_dict("2026-06-26", 10)]
    payload = {"SHORT": short}
    if with_good:
        payload["APP"] = bars
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(payload))
    return path


def test_main_offline_writes_reports_and_lists_top(tmp_path, monkeypatch, capsys):
    prices = _write_prices(tmp_path)
    profiles = tmp_path / "profiles.json"
    profiles.write_text(json.dumps({"APP": _profile()}))
    out = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--prices-json",
            str(prices),
            "--profiles-json",
            str(profiles),
            "--market-gate",
            "allowed",
            "--include-rejected",
            "--output-dir",
            str(out),
        ],
    )
    mod.main()
    stdout = capsys.readouterr().out
    assert "Top candidates:" in stdout
    assert "APP" in stdout and "ACTIONABLE_CLOSE_BUY" in stdout
    payload = json.loads(next(out.glob("*.json")).read_text())
    assert payload["metadata"]["input_mode"] == "prices_json"
    assert payload["metadata"]["symbols_processed"] == 2
    assert payload["metadata"]["api_stats"] is None
    assert [c["symbol"] for c in payload["candidates"]] == ["APP", "SHORT"]
    md = next(out.glob("*.md")).read_text()
    assert "## Rejected" in md and "insufficient_history" in md


def test_main_missing_prices_file_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--prices-json",
            str(tmp_path / "none.json"),
            "--profiles-json",
            str(tmp_path / "np.json"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1
    assert "Profiles file not found" in capsys.readouterr().err


def test_main_no_symbols_without_key_exits_1(monkeypatch, capsys):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["x", "--symbols", "APP"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1
    assert "FMP API key required" in capsys.readouterr().err


def test_main_empty_price_data_exits_0(tmp_path, monkeypatch, capsys):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({}))
    monkeypatch.setattr(
        sys, "argv", ["x", "--prices-json", str(path), "--output-dir", str(tmp_path)]
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 0
    assert "No price data found" in capsys.readouterr().out


def test_main_fmp_symbols_mode_records_api_stats(tmp_path, monkeypatch):
    hist = [dict(b, symbol="APP") for b in json.loads(_write_prices(tmp_path).read_text())["APP"]]
    session = _FakeSession([_FakeResponse(hist)])
    original_init = FMPClient.__init__

    def init(self, *a, **k):
        original_init(self, *a, **k)
        self.session = session

    monkeypatch.setattr(FMPClient, "__init__", init)
    out = tmp_path / "fmp_out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--symbols",
            "app",
            "--api-key",
            "k",
            "--history-days",
            "90",
            "--output-dir",
            str(out),
        ],
    )
    mod.main()
    payload = json.loads(next(out.glob("*.json")).read_text())
    assert payload["metadata"]["input_mode"] == "symbols"
    assert payload["metadata"]["api_stats"]["api_calls_made"] == 1
    assert payload["candidates"][0]["symbol"] == "APP"
