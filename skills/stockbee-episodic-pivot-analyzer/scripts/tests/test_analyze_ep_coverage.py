"""Additional coverage: scoring, FMP fallbacks, loaders, reports, and CLI."""

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_ep  # noqa: E402
from analyze_ep import (  # noqa: E402
    FMPClient,
    analyze_candidate,
    classify_catalyst,
    dedupe_events,
    determine_state,
    events_from_earnings_json,
    events_from_events_json,
    find_event_index,
    format_num,
    infer_event_date,
    load_momentum_enrichment,
    load_prices_json,
    merge_price_fields,
    normalize_catalyst_type,
    normalize_date,
    normalize_event_record,
    parse_date,
    price_stats_from_bars,
    rating_from_score,
    safe_float,
    score_catalyst,
    score_liquidity,
    score_price_action,
    score_revaluation,
    score_risk,
    score_volume,
    sort_results,
    write_json_report,
    write_markdown_report,
)


def make_bars(n=55, event_date="2026-04-25", volume=300000):
    bars = []
    close = 50.0
    for i in range(n):
        day = f"2026-03-{i + 1:02d}" if i < 31 else f"2026-04-{i - 30:02d}"
        bars.append(
            {
                "date": day,
                "open": close - 0.2,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": volume,
            }
        )
        close += 0.05
    bars.append(
        {
            "date": event_date,
            "open": 54.0,
            "high": 58.0,
            "low": 53.0,
            "close": 57.6,
            "volume": 3500000,
        }
    )
    return bars


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class ScriptedSession:
    """Returns queued responses (or raises) per call; records URLs."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []
        self.headers = {}

    def get(self, url, params, timeout):  # noqa: ARG002
        self.urls.append(url)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(analyze_ep.time, "sleep", lambda *_a, **_k: None)


def make_client(monkeypatch, responses, max_calls=10):
    monkeypatch.setenv("FMP_API_KEY", "test-key")
    client = FMPClient(api_key=None, max_api_calls=max_calls)
    client.session = ScriptedSession(responses)
    return client


# ---------------------------------------------------------------- FMP client


def test_fmp_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(ValueError):
        FMPClient(api_key=None)


def test_fmp_client_requires_requests(monkeypatch):
    monkeypatch.setattr(analyze_ep, "requests", None)
    with pytest.raises(RuntimeError):
        FMPClient(api_key="k")


def test_fmp_get_respects_call_budget(monkeypatch):
    client = make_client(monkeypatch, [FakeResponse([{"x": 1}])], max_calls=1)
    assert client._get("u", {}) == [{"x": 1}]
    assert client._get("u", {}) is None  # budget exhausted, no session call
    assert client.stats() == {"api_calls_made": 1, "max_api_calls": 1}


def test_fmp_get_returns_none_on_non_200_and_request_error(monkeypatch):
    client = make_client(
        monkeypatch,
        [FakeResponse({}, status_code=429), analyze_ep.requests.RequestException("boom")],
    )
    assert client._get("u", {}) is None
    assert client._get("u", {}) is None
    assert client.api_calls == 2


def test_fmp_historical_prices_falls_back_to_v3(monkeypatch):
    hist = [
        {"date": f"2026-01-{d:02d}", "close": d, "open": d, "high": d, "low": d} for d in (3, 1, 2)
    ]
    client = make_client(monkeypatch, [FakeResponse([]), FakeResponse({"historical": hist})])
    bars = client.get_historical_prices("ABC", days=2)
    assert [b["date"] for b in bars] == ["2026-01-02", "2026-01-03"]
    assert "api/v3/historical-price-full/ABC" in client.session.urls[1]


def test_fmp_historical_prices_empty_when_both_fail(monkeypatch):
    client = make_client(monkeypatch, [FakeResponse({}, 500), FakeResponse({"historical": None})])
    assert client.get_historical_prices("ABC") == []


def test_fmp_profile_stable_then_v3_then_empty(monkeypatch):
    client = make_client(monkeypatch, [FakeResponse([{"symbol": "ABC", "mktCap": 5}])])
    assert client.get_profile("ABC")["mktCap"] == 5

    client = make_client(monkeypatch, [FakeResponse([]), FakeResponse([{"symbol": "ABC"}])])
    assert client.get_profile("ABC") == {"symbol": "ABC"}
    assert "api/v3/profile/ABC" in client.session.urls[1]

    client = make_client(monkeypatch, [FakeResponse({}), FakeResponse({})])
    assert client.get_profile("ABC") == {}


# ------------------------------------------------------------- small helpers


def test_safe_float_handles_bad_values():
    assert safe_float(None, 1.0) == 1.0
    assert safe_float("", 2.0) == 2.0
    assert safe_float("abc") is None
    assert safe_float(float("nan"), 0.0) == 0.0
    assert safe_float(float("inf")) is None
    assert safe_float("3.5") == 3.5


def test_date_helpers():
    assert normalize_date("2026-04-25T09:30:00") == "2026-04-25"
    assert normalize_date("   ") is None
    assert normalize_date("04/25/2026") is None
    assert normalize_date(None) is None
    assert parse_date("2026-04-25").isoformat() == "2026-04-25"
    assert parse_date("bad") is None
    assert parse_date(None) is None


def test_infer_event_date_prefers_keys_then_fallback():
    assert infer_event_date({"signal_date": "2026-05-01"}) == "2026-05-01"
    assert infer_event_date({}, fallback="2026-05-02T10:00") == "2026-05-02"
    assert infer_event_date({}) is None


def test_normalize_catalyst_type_aliases():
    assert normalize_catalyst_type("Beat-and-Raise") == "guidance_raise"
    assert normalize_catalyst_type("M&A") == "m_and_a"
    assert normalize_catalyst_type("unknown") == "unknown"
    assert normalize_catalyst_type("gibberish") == "unknown"
    assert normalize_catalyst_type(None) == "unknown"


def test_classify_catalyst_explicit_keyword_and_unknown():
    assert classify_catalyst({"catalyst_type": "fda"}) == (
        "fda_approval",
        ["explicit:fda_approval"],
    )
    assert classify_catalyst({"headline": "Firm to be acquired in buyout"})[0] == "m_and_a"
    assert classify_catalyst({"summary": "New product launch announced"})[0] == "product_launch"
    assert classify_catalyst({"headline": "Quiet day"}) == (
        "unknown",
        ["no_clear_catalyst_keyword"],
    )


def test_normalize_event_record_requires_symbol():
    assert normalize_event_record({"headline": "x"}, source="s") is None
    event = normalize_event_record(
        {"ticker": " abc ", "headline": "raises guidance"}, source="s", fallback_date="2026-04-25"
    )
    assert event["symbol"] == "ABC"
    assert event["event_date"] == "2026-04-25"
    assert event["source_input"] == "s"


# ----------------------------------------------------------------- loaders


def test_events_from_events_json_shapes():
    assert events_from_events_json(None) == []
    assert events_from_events_json("string") == []
    as_list = events_from_events_json(
        [{"symbol": "A", "headline": "contract award"}, "junk", {"headline": "no symbol"}]
    )
    assert [e["symbol"] for e in as_list] == ["A"]
    wrapped = events_from_events_json(
        {"as_of": "2026-04-25", "candidates": [{"symbol": "B", "catalyst_type": "earnings"}]}
    )
    assert wrapped[0]["event_date"] == "2026-04-25"
    assert wrapped[0]["catalyst_type"] == "earnings"


def test_events_from_earnings_json_edge_cases():
    assert events_from_earnings_json([]) == []
    data = {
        "candidates": [
            "junk",
            {"headline": "no symbol"},
            {"ticker": "xyz", "gap_pct": 6, "change_pct": 9.0, "timing": "amc", "score": "81"},
            {"symbol": "NOGAP"},
        ]
    }
    events = events_from_earnings_json(data)
    assert [e["symbol"] for e in events] == ["XYZ", "NOGAP"]
    assert events[0]["day_gain_pct"] == 9.0
    assert events[0]["source_score"] == 81.0
    assert events[0]["earnings_timing"] == "amc"
    assert events[1]["gap_pct"] is None
    assert events[1]["day_gain_pct"] is None


def test_load_momentum_enrichment(tmp_path):
    assert load_momentum_enrichment(None) == {}
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    assert load_momentum_enrichment(str(empty)) == {}
    path = tmp_path / "mom.json"
    path.write_text(
        json.dumps(
            {
                "candidates": [
                    "junk",
                    {"volume": 1},
                    {"symbol": "abc", "setup_date": "2026-04-25T00:00", "close": 10},
                ]
            }
        )
    )
    enrichment = load_momentum_enrichment(str(path))
    assert set(enrichment) == {("ABC", "2026-04-25"), ("ABC", None)}
    assert enrichment[("ABC", None)]["close"] == 10


def test_load_prices_json_shapes(tmp_path):
    assert load_prices_json(None) == {}
    bars = [{"date": "2026-01-02", "close": 2}, {"date": "2026-01-01", "adjClose": 1}, "junk"]

    p = tmp_path / "ohlcv.json"
    p.write_text(json.dumps({"ohlcv": {"abc": bars, "EMPTY": [], "BAD": 5}}))
    out = load_prices_json(str(p))
    assert list(out) == ["ABC"]
    assert [b["date"] for b in out["ABC"]] == ["2026-01-01", "2026-01-02"]
    assert out["ABC"][0]["close"] == 1.0  # adjClose fallback

    p.write_text(json.dumps({"XYZ": {"historical": bars}}))
    assert "XYZ" in load_prices_json(str(p))

    p.write_text(
        json.dumps(
            [
                {"symbol": "ab", "date": "2026-01-01", "close": 1},
                {"ticker": "ab", "date": "2026-01-02", "close": 2},
                {"date": "2026-01-03", "close": 3},
                "junk",
            ]
        )
    )
    flat = load_prices_json(str(p))
    assert list(flat) == ["AB"]
    assert len(flat["AB"]) == 2

    p.write_text(json.dumps(42))
    assert load_prices_json(str(p)) == {}


# --------------------------------------------------------------- price stats


def test_find_event_index_exact_next_and_default():
    bars = [{"date": "2026-04-20"}, {"date": "2026-04-22"}, {"date": "2026-04-24"}]
    assert find_event_index([], "2026-04-20") is None
    assert find_event_index(bars, "2026-04-22") == 1
    assert find_event_index(bars, "2026-04-23") == 2  # next trading bar
    assert find_event_index(bars, "2026-05-30") == 2  # beyond range: latest bar
    assert find_event_index(bars, None) == 2


def test_price_stats_insufficient_history_returns_empty_stats():
    single = [{"date": "2026-04-25", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]
    stats = price_stats_from_bars("ABC", single, "2026-04-25")
    assert stats.symbol == "ABC"
    assert stats.close is None
    assert stats.gap_pct is None


def test_price_stats_prior_returns_and_gap():
    stats = price_stats_from_bars("ABC", make_bars(), "2026-04-25")
    assert stats.gap_pct == pytest.approx((54.0 / stats.prev_close - 1) * 100)
    assert stats.prior_5d_return_pct is not None and stats.prior_5d_return_pct > 0
    assert stats.prior_20d_return_pct is not None
    assert stats.avg_volume_20 == 300000
    assert stats.dollar_volume == pytest.approx(57.6 * 3500000)
    assert stats.event_date == "2026-04-25"


# ------------------------------------------------------------- merge fields


def test_merge_price_fields_momentum_fills_only_missing():
    stats = analyze_ep.PriceStats(symbol="ABC", event_date="2026-04-25", close=55.0, gap_pct=5.0)
    momentum = {
        "day_gain_pct": 9.0,
        "volume_ratio_1d": 4.0,
        "risk_pct_to_stop": 3.0,
        "stop_reference": 52.0,
        "close": 99.0,
        "trigger_types": ["range_expansion", "x"],
    }
    merged = merge_price_fields({"close": 60.0}, stats, momentum)
    assert merged["close"] == 60.0  # event value wins
    assert merged["day_gain_pct"] == 9.0
    assert merged["risk_pct_to_low"] == 3.0
    assert merged["low"] == 52.0
    assert merged["gap_pct"] == 5.0  # from stats
    assert merged["momentum_trigger_type"] == "range_expansion"
    assert merged["price_event_date"] == "2026-04-25"


def test_merge_price_fields_single_trigger_type_and_existing_value():
    stats = analyze_ep.PriceStats(symbol="ABC")
    merged = merge_price_fields({}, stats, {"trigger_type": "gap_up"})
    assert merged["momentum_trigger_type"] == "gap_up"
    assert "price_event_date" not in merged
    keep = merge_price_fields({"momentum_trigger_type": "mine"}, stats, {"trigger_type": "gap_up"})
    assert keep["momentum_trigger_type"] == "mine"


# ------------------------------------------------------------------ scorers


def test_score_catalyst_grade_bonus_and_language():
    score, reasons = score_catalyst(
        {"catalyst_type": "earnings", "grade": "a", "headline": "Record results"}
    )
    assert score == pytest.approx(min(100, 88 + 8 + 6) * 0.35)
    assert "earnings_grade_A:+8" in reasons
    assert "game_change_language:+6" in reasons

    score, reasons = score_catalyst(
        {"catalyst_type": "analyst_upgrade", "summary": "secondary offering and downgrade"}
    )
    assert score == pytest.approx((54 - 12) * 0.35)
    assert "negative_or_dilutive_language:-12" in reasons


@pytest.mark.parametrize(
    "record,expected_reason",
    [
        ({}, "missing_move:0"),
        ({"day_gain_pct": 15}, "move_12pct_plus:+12"),
        ({"day_gain_pct": 9}, "move_8pct_plus:+10"),
        ({"day_gain_pct": 5}, "move_4pct_plus:+8"),
        ({"day_gain_pct": 2.5}, "move_2pct_plus:+4"),
        ({"day_gain_pct": 0.5}, "weak_move:0"),
        ({"gap_pct": 3}, "small_gap_confirmation:+2"),
        ({"gap_pct": 5}, "gap_confirmation:+4"),
        ({"day_gain_pct": 5, "close_location_pct": 65}, "close_upper_range:+2"),
        ({"day_gain_pct": 5, "close_location_pct": 90}, "close_near_high:+4"),
        ({"day_gain_pct": 5, "close_location_pct": 10}, "weak_close_location:-4"),
        ({"day_gain_pct": 5, "range_pct": 7}, "range_expansion:+2"),
    ],
)
def test_score_price_action_reasons(record, expected_reason):
    _score, reasons = score_price_action(record)
    assert expected_reason in reasons


def test_score_price_action_clamps_to_range():
    score, _ = score_price_action(
        {"day_gain_pct": 20, "gap_pct": 10, "close_location_pct": 95, "range_pct": 12}
    )
    assert score == 20.0  # 12+4+4+2 clamped to 20
    score, _ = score_price_action({"day_gain_pct": 0.5, "close_location_pct": 5})
    assert score == 0.0


@pytest.mark.parametrize(
    "record,expected",
    [
        ({"volume_ratio_50": 12}, 20.0),
        ({"volume_ratio_20": 6}, 17.0),
        ({"volume_ratio_1d": 3.5}, 14.0),
        ({"volume_ratio_50": 2}, 8.0),
        ({"volume_ratio_50": 1.1}, 2.0),
        ({"volume": 9_500_000}, 17.0),  # 14 + 3 bonus
        ({"volume": 1_500_000}, 8.0),
        ({"volume": 400_000}, 4.0),
        ({"volume": 1000}, 0.0),
        ({}, 3.0),
    ],
)
def test_score_volume_tiers(record, expected):
    score, reasons = score_volume(record)
    assert score == expected
    assert reasons


def test_score_volume_nine_million_bonus_with_ratio():
    score, reasons = score_volume({"volume_ratio_50": 2, "volume": 9_000_000})
    assert score == 11.0
    assert "9m_ep_bonus:+3" in reasons


@pytest.mark.parametrize(
    "record,expected",
    [
        ({}, 5.0),
        ({"prior_20d_return_pct": 0}, 8.0),
        ({"prior_20d_return_pct": 10}, 6.0),
        ({"prior_20d_return_pct": 25}, 3.0),
        ({"prior_20d_return_pct": 50}, 1.0),
        ({"prior_20d_return_pct": 0, "market_cap": 5e9}, 10.0),
        ({"prior_20d_return_pct": 50, "mktCap": 5e11}, 0.0),
        ({"market_cap": 5e10}, 5.0),
    ],
)
def test_score_revaluation(record, expected):
    score, reasons = score_revaluation(record)
    assert score == expected
    assert reasons


@pytest.mark.parametrize(
    "record,expected",
    [
        ({"close": 100, "volume": 600_000}, 10),  # 60M dollar volume
        ({"dollar_volume": 12_000_000}, 8),
        ({"dollar_volume": 3_000_000}, 4),
        ({"dollar_volume": 100_000}, 1),
        ({"volume": 2_000_000}, 7),
        ({"volume": 400_000}, 5),
        ({"volume": 1000}, 1),
        ({}, 3),
        ({"close": 3, "volume": 20_000_000}, 3),  # low price cap
    ],
)
def test_score_liquidity(record, expected):
    score, reasons = score_liquidity(record)
    assert score == expected
    assert reasons


@pytest.mark.parametrize(
    "risk,expected",
    [(None, 2.0), (3, 5.0), (6, 3.5), (9, 1.5), (15, 0.0)],
)
def test_score_risk_bands(risk, expected):
    record = {} if risk is None else {"risk_pct_to_low": risk}
    assert score_risk(record)[0] == expected
    assert score_risk({"risk_pct_to_stop": 3})[0] == 5.0


@pytest.mark.parametrize(
    "score,rating",
    [(95, "A"), (85, "A-"), (75, "B"), (60, "C"), (10, "D")],
)
def test_rating_from_score(score, rating):
    assert rating_from_score(score) == rating


# -------------------------------------------------------------- state logic


def _record(**kw):
    base = {
        "catalyst_type": "earnings",
        "day_gain_pct": 6,
        "volume_ratio_50": 4,
        "close_location_pct": 80,
        "risk_pct_to_low": 5,
    }
    base.update(kw)
    return base


def test_determine_state_transitions():
    assert determine_state(_record(), 90, 10)[0] == "ACTIONABLE_DAY1"
    assert determine_state(_record(), 78, 10)[0] == "DAY1_WATCH"
    state, reasons = determine_state(_record(close_location_pct=20), 80, 10)
    assert state == "DELAYED_EP_WATCH"
    assert "weak_close_location" in reasons
    state, reasons = determine_state(_record(day_gain_pct=1, gap_pct=None), 60, 10)
    assert state == "CATALYST_WATCH"
    assert "price_move_not_confirmed" in reasons
    state, reasons = determine_state(
        _record(volume_ratio_50=None, volume_ratio_20=1.0, volume=1000), 90, 10
    )
    assert state == "REJECT"
    assert "volume_not_confirmed" in reasons
    assert determine_state(_record(catalyst_type="unknown", day_gain_pct=0), 60, 10)[0] == "REJECT"


def test_determine_state_gap_alone_confirms_move():
    state, reasons = determine_state(_record(day_gain_pct=None, gap_pct=5), 90, 10)
    assert state == "ACTIONABLE_DAY1"
    assert "price_move_not_confirmed" not in reasons


# ---------------------------------------------------------- analyze_candidate


def test_analyze_candidate_fetches_from_fmp_and_caches():
    calls = []

    class StubFMP:
        def get_historical_prices(self, symbol, days):
            calls.append((symbol, days))
            return make_bars()

    prices = {}
    event = {
        "symbol": "abc",
        "event_date": "2026-04-25",
        "headline": "ABC raises guidance after record demand",
        "catalyst_type": "guidance_raise",
        "market_cap": 5e9,
    }
    result = analyze_candidate(event, prices, {}, StubFMP(), max_risk_pct=10.0)
    assert calls == [("ABC", 100)]
    assert "ABC" in prices  # cached for later events
    assert result["state"] == "ACTIONABLE_DAY1"
    assert result["pead_handoff"] is True
    assert result["trade_plan_inputs"]["stop_reference"] == 53.0
    assert result["trade_plan_inputs"]["stop_basis"] == "ep_day_low"


def test_analyze_candidate_fmp_returns_no_bars_degrades_gracefully():
    class EmptyFMP:
        def get_historical_prices(self, symbol, days):  # noqa: ARG002
            return []

    prices = {}
    event = {"symbol": "ZZZ", "event_date": "2026-04-25", "catalyst_type": "earnings"}
    result = analyze_candidate(event, prices, {}, EmptyFMP(), max_risk_pct=10.0)
    assert "ZZZ" not in prices
    assert result["close"] is None
    assert result["state"] == "REJECT"
    assert result["momentum_handoff"] is False


def test_analyze_candidate_uses_momentum_enrichment_without_prices():
    event = {
        "symbol": "MOM",
        "event_date": "2026-04-25",
        "catalyst_type": "earnings",
        "market_cap": 2e9,
    }
    momentum = {
        ("MOM", None): {
            "day_gain_pct": 9.0,
            "volume_ratio_50": 6.0,
            "close_location_pct": 90.0,
            "risk_pct_to_stop": 3.0,
            "close": 40.0,
            "volume": 2_000_000,
            "stop_reference": 38.8,
            "trigger_types": ["gap_up"],
        }
    }
    result = analyze_candidate(event, {}, momentum, None, max_risk_pct=10.0)
    assert result["day_gain_pct"] == 9.0
    assert result["risk_pct_to_low"] == 3.0
    assert result["state"] in {"ACTIONABLE_DAY1", "DAY1_WATCH"}
    assert result["momentum_handoff"] is True


def test_analyze_candidate_fade_deduction_downgrades_state():
    bars = make_bars()
    bars[-1].update({"open": 54.0, "high": 60.0, "low": 53.0, "close": 53.5})
    event = {
        "symbol": "FADE",
        "event_date": "2026-04-25",
        "catalyst_type": "guidance_raise",
        "headline": "FADE raises guidance with record results",
        "market_cap": 5e9,
    }
    result = analyze_candidate(event, {"FADE": bars}, {}, None, max_risk_pct=10.0)
    assert result["close_location_pct"] < 30
    assert "fade_deduction_applied" in result["state_reasons"]
    assert result["state"] != "ACTIONABLE_DAY1"


# ------------------------------------------------------------ dedupe / sort


def test_dedupe_events_collapses_identical_keys():
    a = {"symbol": "A", "event_date": "2026-04-25", "catalyst_type": "earnings", "headline": "h"}
    b = dict(a, symbol="a")
    c = dict(a, headline="different")
    assert dedupe_events([a, b, c]) == [a, c]


def test_sort_results_breaks_ties_by_score():
    rows = [
        {"symbol": "LOW", "state": "REJECT", "composite_score": 10},
        {"symbol": "HI", "state": "REJECT", "composite_score": 50},
        {"symbol": "ODD", "state": "WEIRD", "composite_score": 99},
    ]
    assert [r["symbol"] for r in sort_results(rows)] == ["HI", "LOW", "ODD"]


# ------------------------------------------------------------------ reports


def _results():
    rows = []
    for sym, ctype in (("AAA", "guidance_raise"), ("BBB", "unknown")):
        event = {"symbol": sym, "event_date": "2026-04-25", "catalyst_type": ctype}
        rows.append(analyze_candidate(event, {sym: make_bars()}, {}, None, max_risk_pct=10.0))
    rows.append(
        {"symbol": "REJ", "state": "REJECT", "composite_score": 1, "rating": "D", "ep_type": "X"}
    )
    return sort_results(rows)


def test_format_num():
    assert format_num(None) == "n/a"
    assert format_num("abc", "%") == "n/a"
    assert format_num(5.5, "%") == "5.50%"
    assert format_num(2_500_000) == "2.5M"
    assert format_num(2_500_000, "x") == "2500000.00x"


def test_write_json_report_structure(tmp_path):
    results = _results()
    out = tmp_path / "r.json"
    write_json_report(results, {"event_count": 3}, str(out))
    payload = json.loads(out.read_text())
    assert payload["skill"] == "stockbee-episodic-pivot-analyzer"
    assert payload["schema_version"] == "1.0"
    assert payload["metadata"] == {"event_count": 3}
    assert len(payload["results"]) == 3
    assert all(r["state"] != "REJECT" for r in payload["episodic_pivot_candidates"])
    assert len(payload["episodic_pivot_candidates"]) < 3
    assert all(r["pead_handoff"] for r in payload["pead_handoff_candidates"])
    assert all(r["delayed_ep_watch"] for r in payload["delayed_ep_watchlist"])


def test_write_markdown_report_content(tmp_path):
    results = _results()
    out = tmp_path / "r.md"
    write_markdown_report(results, {"event_count": 3, "max_risk_pct": 10.0, "top": 30}, str(out))
    text = out.read_text()
    assert "# Stockbee Episodic Pivot Analyzer Report" in text
    assert "Input events: 3" in text
    assert "Max Day 1 risk: 10.0%" in text
    assert "| ACTIONABLE_DAY1 | 1 |" in text
    assert "| REJECT | 2 |" in text
    assert "| AAA | ACTIONABLE_DAY1 | GUIDANCE_EP" in text
    assert "### AAA" in text
    assert "EP type: `GUIDANCE_EP`" in text
    assert "### REJ" not in text  # rejects get no detail section
    assert "State reasons:" in text


def test_write_markdown_report_respects_top_limit(tmp_path):
    results = _results()
    out = tmp_path / "r.md"
    write_markdown_report(results, {"event_count": 3, "top": 1}, str(out))
    text = out.read_text()
    assert "| AAA |" in text
    assert "| BBB |" not in text
    assert "| REJ |" not in text


# --------------------------------------------------------------------- CLI


def _write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def test_main_exits_1_when_no_events(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    events = _write(tmp_path / "e.json", {"events": []})
    monkeypatch.setattr(sys, "argv", ["analyze_ep.py", "--events-json", events])
    with pytest.raises(SystemExit) as exc:
        analyze_ep.main()
    assert exc.value.code == 1
    assert "Provide at least one valid event" in capsys.readouterr().err


def test_main_offline_writes_reports(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    events = _write(
        tmp_path / "e.json",
        {
            "events": [
                {"symbol": "ABC", "event_date": "2026-04-25", "headline": "ABC raises guidance"},
                {"symbol": "ABC", "event_date": "2026-04-25", "headline": "ABC raises guidance"},
            ]
        },
    )
    earnings = _write(
        tmp_path / "earn.json",
        {"results": [{"symbol": "DEF", "earnings_date": "2026-04-25", "gap_pct": 6.0}]},
    )
    prices = _write(tmp_path / "p.json", {"prices": {"ABC": make_bars()}})
    out_dir = tmp_path / "out" / "nested"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze_ep.py",
            "--events-json",
            events,
            "--earnings-json",
            earnings,
            "--prices-json",
            prices,
            "--output-dir",
            str(out_dir),
            "--top",
            "5",
        ],
    )
    analyze_ep.main()
    stdout = capsys.readouterr().out
    assert "Events loaded: 2" in stdout  # duplicate ABC removed
    assert "Offline price symbols: 1" in stdout

    json_files = list(out_dir.glob("stockbee_episodic_pivot_*.json"))
    md_files = list(out_dir.glob("stockbee_episodic_pivot_*.md"))
    assert len(json_files) == 1 and len(md_files) == 1
    payload = json.loads(json_files[0].read_text())
    assert payload["metadata"]["api_stats"] is None
    assert payload["metadata"]["max_risk_pct"] == 10.0
    assert payload["results"][0]["symbol"] == "ABC"
    assert payload["results"][0]["state"] == "ACTIONABLE_DAY1"
    assert "ABC" in md_files[0].read_text()


def test_main_with_fmp_records_api_stats(monkeypatch, tmp_path):
    created = {}

    class StubFMP:
        def __init__(self, api_key, max_api_calls=200):
            created["key"] = api_key
            created["max"] = max_api_calls

        def get_historical_prices(self, symbol, days):  # noqa: ARG002
            return make_bars()

        def stats(self):
            return {"api_calls_made": 1, "max_api_calls": created["max"]}

    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(analyze_ep, "FMPClient", StubFMP)
    events = _write(
        tmp_path / "e.json",
        {"events": [{"symbol": "ABC", "event_date": "2026-04-25", "headline": "raises guidance"}]},
    )
    momentum = _write(
        tmp_path / "m.json", {"candidates": [{"symbol": "ABC", "trigger_type": "gap_up"}]}
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze_ep.py",
            "--events-json",
            events,
            "--momentum-json",
            momentum,
            "--api-key",
            "fake-key",
            "--max-api-calls",
            "7",
            "--output-dir",
            str(tmp_path / "o"),
        ],
    )
    analyze_ep.main()
    assert created == {"key": "fake-key", "max": 7}
    payload = json.loads(next((tmp_path / "o").glob("*.json")).read_text())
    assert payload["metadata"]["api_stats"] == {"api_calls_made": 1, "max_api_calls": 7}
    assert payload["results"][0]["state"] == "ACTIONABLE_DAY1"


def test_main_warns_and_continues_when_fmp_init_fails(monkeypatch, tmp_path, capsys):
    def boom(*_a, **_k):
        raise ValueError("FMP API key required")

    monkeypatch.setattr(analyze_ep, "FMPClient", boom)
    monkeypatch.setenv("FMP_API_KEY", "x")
    events = _write(
        tmp_path / "e.json",
        {"events": [{"symbol": "ABC", "event_date": "2026-04-25", "headline": "contract award"}]},
    )
    monkeypatch.setattr(
        sys, "argv", ["analyze_ep.py", "--events-json", events, "--output-dir", str(tmp_path / "o")]
    )
    analyze_ep.main()
    captured = capsys.readouterr()
    assert "FMP enrichment disabled" in captured.err
    payload = json.loads(next((tmp_path / "o").glob("*.json")).read_text())
    assert payload["metadata"]["api_stats"] is None
