"""Additional coverage tests for build_model_book (Issue #293). No network access."""

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import build_model_book as bmb  # noqa: E402
from build_model_book import Bar  # noqa: E402


def cand(**over):
    base = {
        "symbol": "TEST",
        "date": "2026-06-20",
        "state": "ACTIONABLE_DAY1",
        "rating": "A",
        "primary_trigger": "4pct_breakout",
        "entry_reference": 100.0,
        "stop_reference": 95.0,
    }
    base.update(over)
    return base


def bars_up(start="2026-06-22", n=6, base=100.0):
    out = []
    d = date.fromisoformat(start)
    for i in range(n):
        px = base + i
        out.append(Bar(d.isoformat(), px, px + 1, px - 0.5, px + 0.5, 1000))
        d += timedelta(days=1)
    return out


# ---------------------------------------------------------------- FMP client


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return self.responses.pop(0)


def make_client(monkeypatch, responses, **kwargs):
    session = FakeSession(responses)
    monkeypatch.setattr(bmb, "requests", SimpleNamespace(Session=lambda: session))
    monkeypatch.setattr(bmb.time, "sleep", lambda s: None)
    client = bmb.FMPClient(api_key="k", **kwargs)
    return client, session


def test_client_requires_requests(monkeypatch):
    monkeypatch.setattr(bmb, "requests", None)
    with pytest.raises(RuntimeError, match="requests is not installed"):
        bmb.FMPClient(api_key="k")


def test_client_requires_api_key(monkeypatch):
    monkeypatch.setattr(bmb, "requests", SimpleNamespace(Session=lambda: FakeSession([])))
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(ValueError, match="FMP API key required"):
        bmb.FMPClient()


def test_client_reads_key_from_env_and_sets_header(monkeypatch):
    session = FakeSession([])
    monkeypatch.setattr(bmb, "requests", SimpleNamespace(Session=lambda: session))
    monkeypatch.setenv("FMP_API_KEY", "envkey")
    client = bmb.FMPClient()
    assert client.api_key == "envkey"  # pragma: allowlist secret
    assert session.headers == {"apikey": "envkey"}  # pragma: allowlist secret


def test_get_stable_success_and_stats(monkeypatch):
    rows = [
        {"date": "2026-06-22", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"date": "2026-06-23", "open": 1, "high": 2, "low": 0.5, "close": 1.8, "volume": 10},
    ]
    client, session = make_client(monkeypatch, [FakeResponse(200, rows)])
    out = client.get_historical_prices("brk.b", days=1)
    assert [r["date"] for r in out] == ["2026-06-23"]
    url, params, timeout = session.calls[0]
    assert url.endswith("/stable/historical-price-eod/full")
    assert params["symbol"] == "BRK-B"
    assert timeout == 30
    span = date.fromisoformat(params["to"]) - date.fromisoformat(params["from"])
    assert span.days == 1 * 2 + 10
    assert client.stats() == {"api_calls_made": 1, "max_api_calls": 200, "budget_remaining": 199}


def test_get_historical_prices_caches(monkeypatch):
    rows = [{"date": "2026-06-22", "close": 5}]
    client, session = make_client(monkeypatch, [FakeResponse(200, rows)])
    first = client.get_historical_prices("AAA")
    second = client.get_historical_prices("AAA")
    assert first is second
    assert len(session.calls) == 1


def test_get_historical_prices_falls_back_to_v3(monkeypatch, capsys):
    v3 = {"historical": [{"date": "2026-06-22", "close": 7}, {"date": "2026-06-23", "close": 8}]}
    client, session = make_client(
        monkeypatch, [FakeResponse(404, None, "nope"), FakeResponse(200, v3)]
    )
    out = client.get_historical_prices("AAA", days=80)
    assert [r["close"] for r in out] == [7.0, 8.0]
    assert "/api/v3/historical-price-full/AAA" in session.calls[1][0]
    assert session.calls[1][1] == {"timeseries": 80}
    assert capsys.readouterr().err == ""


def test_v3_failure_prints_error_and_returns_empty(monkeypatch, capsys):
    client, _ = make_client(
        monkeypatch, [FakeResponse(500, None, "x"), FakeResponse(429, None, "slow down")]
    )
    assert client.get_historical_prices("AAA") == []
    err = capsys.readouterr().err
    assert "HTTP 429" in err
    assert "slow down" in err
    assert "HTTP 500" not in err  # first call is quiet


def test_budget_exhausted_raises(monkeypatch):
    client, session = make_client(monkeypatch, [], max_api_calls=0)
    with pytest.raises(bmb.ApiCallBudgetExceeded, match="0/0"):
        client.get_historical_prices("AAA")
    assert session.calls == []


def test_rate_limit_sleeps_when_called_quickly(monkeypatch):
    client, _ = make_client(monkeypatch, [FakeResponse(200, [])])
    slept = []
    monkeypatch.setattr(bmb.time, "sleep", slept.append)
    monkeypatch.setattr(bmb.time, "time", lambda: 1000.0)
    client.last_call_time = 999.9
    client._get("http://x")
    assert len(slept) == 1
    assert slept[0] == pytest.approx(0.2)


# ------------------------------------------------------------- tiny helpers


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, 0.0),
        ("", 0.0),
        ("abc", 0.0),
        (float("nan"), 0.0),
        (float("inf"), 0.0),
        ("2.5", 2.5),
        (3, 3.0),
    ],
)
def test_to_float(value, expected):
    assert bmb.to_float(value) == expected


def test_to_float_custom_default():
    assert bmb.to_float(None, default=-1.0) == -1.0


@pytest.mark.parametrize(
    "value,expected", [(None, 0), ("", 0), ("x", 0), ("7.9", 7), (4, 4), ([], 0)]
)
def test_to_int(value, expected):
    assert bmb.to_int(value) == expected


def test_normalize_symbol():
    assert bmb.normalize_symbol(" brk.b ") == "BRK-B"
    assert bmb.normalize_symbol(None) == ""


def test_parse_date_truncates_timestamp():
    assert bmb.parse_date("2026-06-20T10:00:00") == date(2026, 6, 20)


# ----------------------------------------------------- normalize_price_bars


def test_normalize_bars_unsupported_payload():
    assert bmb.normalize_price_bars("junk") == []
    assert bmb.normalize_price_bars(None) == []
    assert bmb.normalize_price_bars({"other": 1}) == []


def test_normalize_bars_historical_and_bars_keys():
    rows = [{"date": "2026-06-22", "close": 10}]
    assert bmb.normalize_price_bars({"historical": rows})[0].close == 10.0
    assert bmb.normalize_price_bars({"bars": rows})[0].close == 10.0
    assert bmb.normalize_price_bars({"historical": None}) == []


def test_normalize_bars_filters_and_fills_defaults():
    rows = [
        "not-a-dict",
        {"date": "bad", "close": 10},
        {"date": "2026-06-22", "close": 0},
        {"date": "2026-06-22", "symbol": "OTHER", "close": 50},
        {"datetime": "2026-06-23 09:30:00", "close": 20},
        {"date": "2026-06-24", "close": None, "adjClose": 30},
        {"date": "2026-06-25", "open": 10, "high": 0, "low": 0, "close": 12, "symbol": "tst"},
    ]
    bars = bmb.normalize_price_bars(rows, symbol="TST")
    by_date = {b.date: b for b in bars}
    assert sorted(by_date) == ["2026-06-23", "2026-06-24", "2026-06-25"]
    b23 = by_date["2026-06-23"]
    assert (b23.open, b23.high, b23.low, b23.close) == (20.0, 20.0, 20.0, 20.0)
    # close falls back to adjClose; open/high/low defaults were derived from missing close
    assert by_date["2026-06-24"].close == 30.0
    b25 = by_date["2026-06-25"]
    assert (b25.high, b25.low) == (12.0, 12.0)  # non-positive high/low -> close


def test_normalize_bars_dedups_by_date_keeping_last():
    rows = [{"date": "2026-06-22", "close": 10}, {"date": "2026-06-22", "close": 11}]
    bars = bmb.normalize_price_bars(rows)
    assert len(bars) == 1
    assert bars[0].close == 11.0


# ----------------------------------------------------------- load_prices_json


def test_load_prices_json_symbol_mapping(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(
        json.dumps(
            {
                "aaa": [{"date": "2026-06-22", "close": 5}],
                "EMPTY": [],
                "BAD": "x",
            }
        ),
        encoding="utf-8",
    )
    prices = bmb.load_prices_json(p)
    assert list(prices) == ["AAA"]
    assert prices["AAA"][0].close == 5.0


def test_load_prices_json_flat_list(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(
        json.dumps(
            [
                {"symbol": "aaa", "date": "2026-06-22", "close": 5},
                {"ticker": "bbb", "date": "2026-06-22", "close": 6},
                {"date": "2026-06-22", "close": 7},
                "junk",
                {"symbol": "ccc", "date": "bad", "close": 8},
            ]
        ),
        encoding="utf-8",
    )
    prices = bmb.load_prices_json(p)
    assert sorted(prices) == ["AAA", "BBB"]
    assert prices["BBB"][0].close == 6.0


def test_load_prices_json_scalar_returns_empty(tmp_path):
    p = tmp_path / "p.json"
    p.write_text("42", encoding="utf-8")
    assert bmb.load_prices_json(p) == {}


# -------------------------------------------------------- model book storage


def test_load_model_book_missing_file(tmp_path):
    assert bmb.load_model_book(tmp_path / "nope.jsonl") == []


def test_load_model_book_skips_blank_and_non_dict(tmp_path):
    p = tmp_path / "b.jsonl"
    p.write_text('{"a": 1}\n\n[1, 2]\n{"b": 2}\n', encoding="utf-8")
    assert bmb.load_model_book(p) == [{"a": 1}, {"b": 2}]


def test_load_model_book_invalid_json_reports_line(tmp_path):
    p = tmp_path / "b.jsonl"
    p.write_text('{"a": 1}\n{oops\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"b\.jsonl:2"):
        bmb.load_model_book(p)


def test_save_model_book_sorts_and_creates_dirs(tmp_path):
    p = tmp_path / "deep" / "dir" / "b.jsonl"
    recs = [
        {"setup_date": "2026-06-21", "symbol": "B", "record_id": "3"},
        {"setup_date": "2026-06-20", "symbol": "B", "record_id": "2"},
        {"setup_date": "2026-06-20", "symbol": "A", "record_id": "1", "note": "日本語"},
    ]
    bmb.save_model_book(p, recs)
    text = p.read_text(encoding="utf-8")
    assert "日本語" in text
    assert [r["record_id"] for r in bmb.load_model_book(p)] == ["1", "2", "3"]


# ----------------------------------------------------------- upsert_records


def test_upsert_inserts_new_and_ignores_existing_without_id():
    existing = [{"symbol": "X"}]
    new = [{"record_id": "n1", "v": 1}]
    records, stats = bmb.upsert_records(existing, new)
    assert stats == {"inserted": 1, "updated": 0, "total": 1}
    assert records == [{"record_id": "n1", "v": 1}]


def test_upsert_preserves_human_annotations():
    prev = {"record_id": "r", "human_label": "good", "human_decision": "take", "human_notes": "n"}
    fresh = {
        "record_id": "r",
        "human_label": None,
        "human_decision": "unknown",
        "human_notes": "",
        "setup_score": 9,
    }
    records, stats = bmb.upsert_records([prev], [fresh])
    assert stats == {"inserted": 0, "updated": 1, "total": 1}
    assert records[0]["human_label"] == "good"
    assert records[0]["human_decision"] == "take"
    assert records[0]["human_notes"] == "n"
    assert records[0]["setup_score"] == 9


def test_upsert_keeps_matured_outcomes_over_pending_placeholder():
    prev = {
        "record_id": "r",
        "outcomes": {"5d": {"matured": True}},
        "overall_outcome": "WORKED",
        "matured": True,
        "last_outcome_update_at": "t",
    }
    fresh = {"record_id": "r", "outcomes": {}, "overall_outcome": "PENDING", "matured": False}
    records, _ = bmb.upsert_records([prev], [fresh])
    assert records[0]["overall_outcome"] == "WORKED"
    assert records[0]["matured"] is True
    assert records[0]["last_outcome_update_at"] == "t"
    assert records[0]["outcomes"] == {"5d": {"matured": True}}


def test_upsert_new_outcomes_override_previous():
    prev = {"record_id": "r", "outcomes": {"5d": {"matured": True}}, "overall_outcome": "WORKED"}
    fresh = {
        "record_id": "r",
        "outcomes": {"5d": {"matured": True, "x": 1}},
        "overall_outcome": "X",
    }
    records, _ = bmb.upsert_records([prev], [fresh])
    assert records[0]["overall_outcome"] == "X"


# ------------------------------------------------- load_screener_candidates


def test_load_screener_rejects_non_report(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"nothing": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="does not look like"):
        bmb.load_screener_candidates([p])
    p.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(ValueError, match="does not look like"):
        bmb.load_screener_candidates([p])


def test_load_screener_filters_rejects_and_attaches_source(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(
        json.dumps(
            {
                "metadata": {"src": "x"},
                "candidates": [
                    cand(symbol="OK"),
                    cand(symbol="R1", state="reject"),
                    cand(symbol="R2", state="REJECTED"),
                    cand(symbol="R3", state="Invalid"),
                    "junk",
                ],
            }
        ),
        encoding="utf-8",
    )
    kept = bmb.load_screener_candidates([p])
    assert [c["symbol"] for c in kept] == ["OK"]
    assert kept[0]["_source_report"] == str(p)
    assert kept[0]["_source_metadata"] == {"src": "x"}
    allc = bmb.load_screener_candidates([p], include_rejects=True)
    assert [c["symbol"] for c in allc] == ["OK", "R1", "R2", "R3"]


def test_load_screener_non_dict_metadata_becomes_empty(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"metadata": "str", "candidates": [cand()]}), encoding="utf-8")
    assert bmb.load_screener_candidates([p])[0]["_source_metadata"] == {}


# --------------------------------------------------------- derive_setup_tags


def test_derive_tags_empty_candidate():
    assert bmb.derive_setup_tags({}) == ["weak_close_location"]


def test_derive_tags_low_side_branches():
    tags = bmb.derive_setup_tags(
        {
            "trigger_tags": ["t1", "", None],
            "soft_failure_tags": ["s1", ""],
            "reject_reasons": ["r1", None],
            "rating": "A+",
            "close_location_pct": 49.9,
            "volume_ratio_1d": 1.0,
            "base_width_pct": 20,
            "prior_base_days": 31,
            "risk_pct_to_stop": 6,
            "recent_4pct_breakdown": True,
            "prior_up_streak": 3,
        }
    )
    assert tags == sorted(
        [
            "t1",
            "soft_s1",
            "reject_r1",
            "rating_Aplus",
            "weak_close_location",
            "thin_volume_confirmation",
            "wide_base",
            "long_base",
            "wide_risk",
            "recent_4pct_breakdown",
            "three_days_up_before_trigger",
        ]
    )


def test_derive_tags_minus_rating_and_compact_risk():
    tags = bmb.derive_setup_tags(
        {"rating": "B-", "risk_pct_to_stop": 2.0, "close_location_pct": 60}
    )
    assert tags == ["compact_risk", "rating_Bminus"]


# ------------------------------------------------------------- make_record


def test_make_record_missing_symbol_or_date_raises():
    with pytest.raises(ValueError, match="missing symbol or setup date"):
        bmb.make_record({"date": "2026-06-20"})
    with pytest.raises(ValueError, match="missing symbol or setup date"):
        bmb.make_record({"symbol": "A", "date": "2026"})


def test_make_record_fallbacks():
    rec = bmb.make_record(
        {"symbol": "a.b", "setup_date": "2026-06-20T00:00:00", "close": 50.0, "low": 48.0}
    )
    assert rec["symbol"] == "A-B"
    assert rec["setup_date"] == "2026-06-20"
    assert rec["primary_trigger"] == "unknown"
    assert rec["record_id"] == "stockbee_mb:A-B:2026-06-20:unknown"
    assert rec["entry_reference"] == 50.0
    assert rec["stop_reference"] == 48.0
    assert rec["trigger_tags"] == []
    assert rec["human_decision"] == "unknown"
    assert rec["source_report"] is None


def test_is_studyable_candidate_reasons():
    assert bmb.is_studyable_candidate({"date": "2026-06-20"}) == (False, "missing_symbol")
    assert bmb.is_studyable_candidate({"symbol": "A"}) == (False, "missing_setup_date")
    assert bmb.is_studyable_candidate(cand()) == (True, None)


def test_make_studyable_records_counts_missing_symbol():
    records, stats = bmb.make_studyable_records([cand(), {"date": "2026-06-20"}, {"symbol": "Z"}])
    assert len(records) == 1
    assert stats == {
        "candidates_loaded": 3,
        "studyable": 1,
        "skipped": 2,
        "skipped_missing_symbol": 1,
        "skipped_missing_setup_date": 1,
    }


# ------------------------------------------------------ outcome calculation


def test_window_outcome_missing_entry():
    out = bmb.calculate_window_outcome({"setup_date": "2026-06-20"}, bars_up(), 3)
    assert out == {"horizon_days": 3, "matured": False, "reason": "missing_entry"}


def test_window_outcome_not_enough_bars():
    rec = bmb.make_record(cand())
    out = bmb.calculate_window_outcome(rec, bars_up(n=2), 3)
    assert out == {
        "horizon_days": 3,
        "matured": False,
        "available_future_bars": 2,
        "reason": "not_enough_future_bars",
    }


def test_window_outcome_excludes_setup_day_and_no_stop():
    rec = bmb.make_record(cand(stop_reference=0, entry_reference=100.0))
    rec["stop_reference"] = 0.0
    bars = [Bar("2026-06-20", 1, 500, 0.1, 100, 1)] + bars_up(n=3)
    out = bmb.calculate_window_outcome(rec, bars, 3)
    assert out["matured"] is True
    assert out["close_date"] == "2026-06-24"
    assert out["stop_hit"] is False
    assert out["stop_hit_date"] is None
    assert out["max_high"] == 103.0
    assert out["min_low"] == 99.5
    assert out["forward_return_pct"] == 2.5
    assert out["mfe_pct"] == 3.0
    assert out["mae_pct"] == -0.5
    assert out["outcome_tag"] == "NEUTRAL"


@pytest.mark.parametrize(
    "args,tag",
    [
        ((1.0, 1.0, -1.0, True), "FAILED_STOP"),
        ((0.0, 12.0, 0.0, False), "STRONG_WINNER"),
        ((8.0, 1.0, 0.0, False), "STRONG_WINNER"),
        ((0.0, 6.0, 0.0, False), "WORKED"),
        ((4.0, 1.0, 0.0, False), "WORKED"),
        ((-2.0, 1.0, 0.0, False), "FAILED_FADE"),
        ((1.0, 1.0, -5.0, False), "CHOPPY_FAILURE"),
        ((2.0, 1.0, -5.0, False), "NEUTRAL"),
    ],
)
def test_classify_outcome_branches(args, tag):
    assert bmb.classify_outcome(*args) == tag


def test_derive_overall_outcome():
    assert bmb.derive_overall_outcome({}) == "PENDING"
    assert bmb.derive_overall_outcome({"5d": {"matured": False}}) == "PENDING"
    assert bmb.derive_overall_outcome({"5d": {"matured": True}}) == "UNKNOWN"
    assert bmb.derive_overall_outcome({"3d": {"matured": True, "outcome_tag": "WORKED"}}, 3) == (
        "WORKED"
    )


def test_update_outcomes_missing_prices_pending_and_skip_matured():
    missing = bmb.make_record(cand(symbol="NOPX"))
    pending = bmb.make_record(cand(symbol="SHORT"))
    done = bmb.make_record(cand(symbol="DONE"))
    done["matured"] = True
    records, stats = bmb.update_record_outcomes(
        [missing, pending, done], {"SHORT": bars_up(n=2)}, horizons=(3, 5)
    )
    assert stats == {"updated": 1, "matured": 0, "still_pending": 1, "skipped_no_prices": 1}
    assert missing["update_error"] == "missing_prices"
    assert pending["overall_outcome"] == "PENDING"
    assert pending["matured"] is False
    assert pending["outcomes"]["5d"]["reason"] == "not_enough_future_bars"
    assert "outcomes" in done and done["outcomes"] == {}


def test_update_outcomes_only_pending_false_reprocesses_matured():
    rec = bmb.make_record(cand())
    rec["matured"] = True
    rec["overall_outcome"] = "WORKED"
    _, stats = bmb.update_record_outcomes([rec], {"TEST": bars_up(n=6)}, only_pending=False)
    assert stats["updated"] == 1
    assert stats["matured"] == 1
    assert rec["outcomes"]["5d"]["matured"] is True
    assert rec["last_outcome_update_at"] == rec["updated_at"]


# ------------------------------------------------------------- summarizing


def test_values_for_metric_nested_and_non_dict_paths():
    recs = [
        {"a": {"b": 1.5}},
        {"a": 3},
        {"a": {"b": None}},
        {"a": {"b": "x"}},
        {},
        {"a": {"b": 2}},
    ]
    assert bmb.values_for_metric(recs, "a.b") == [1.5, 2.0]


def test_group_records_untagged_and_unknown():
    recs = [
        {"setup_tags": ["x", "y"], "rating": "A"},
        {"setup_tags": [], "rating": None},
    ]
    tags = bmb.group_records(recs, "setup_tags")
    assert sorted(tags) == ["untagged", "x", "y"]
    ratings = bmb.group_records(recs, "rating")
    assert sorted(ratings) == ["A", "unknown"]


def test_summarize_group_no_matured():
    assert bmb.summarize_group([{"matured": False}, {}]) == {
        "sample_size": 0,
        "pending": 2,
        "win_rate_pct": None,
    }


def make_matured(outcome, r5=None, mae=-1.0, stop=False, r3=None):
    outcomes = {"5d": {"mae_pct": mae, "mfe_pct": 5.0, "stop_hit": stop}}
    if r5 is not None:
        outcomes["5d"]["forward_return_pct"] = r5
    if r3 is not None:
        outcomes["3d"] = {"forward_return_pct": r3}
    return {"matured": True, "overall_outcome": outcome, "outcomes": outcomes}


def test_summarize_group_rates_and_averages():
    recs = [
        make_matured("STRONG_WINNER", r5=10, r3=6),
        make_matured("WORKED", r5=4, r3=2),
        make_matured("FAILED_STOP", r5=-6, stop=True, mae=-7),
        make_matured("CHOPPY_FAILURE", r5=0, mae=-6),
        {"matured": False},
    ]
    s = bmb.summarize_group(recs)
    assert s["sample_size"] == 4
    assert s["pending"] == 1
    assert s["win_rate_pct"] == 50.0
    assert s["failure_rate_pct"] == 50.0
    assert s["strong_winner_rate_pct"] == 25.0
    assert s["stop_hit_rate_pct"] == 25.0
    assert s["avg_3d_return_pct"] == 4.0
    assert s["avg_5d_return_pct"] == 2.0
    assert s["median_5d_return_pct"] == 2.0
    assert s["avg_5d_mfe_pct"] == 5.0
    assert s["avg_5d_mae_pct"] == -3.75


def test_summarize_group_missing_metrics_are_none():
    s = bmb.summarize_group([{"matured": True, "overall_outcome": "NEUTRAL"}])
    assert s["sample_size"] == 1
    assert s["win_rate_pct"] == 0.0
    assert s["avg_3d_return_pct"] is None
    assert s["avg_5d_return_pct"] is None
    assert s["median_5d_return_pct"] is None
    assert s["avg_5d_mfe_pct"] is None
    assert s["avg_5d_mae_pct"] is None


def test_is_promote_and_downgrade_thresholds():
    good = {"sample_size": 5, "win_rate_pct": 60, "avg_5d_return_pct": 2, "avg_5d_mae_pct": -4.9}
    assert bmb.is_promote_candidate(good) is True
    assert bmb.is_promote_candidate({**good, "sample_size": 4}) is False
    assert bmb.is_promote_candidate({**good, "avg_5d_mae_pct": -5}) is False
    assert bmb.is_promote_candidate({}) is False
    assert bmb.is_downgrade_candidate({"sample_size": 5, "failure_rate_pct": 50}) is True
    assert bmb.is_downgrade_candidate({"sample_size": 5, "avg_5d_return_pct": -1}) is True
    assert bmb.is_downgrade_candidate({"sample_size": 4, "failure_rate_pct": 90}) is False
    assert bmb.is_downgrade_candidate({"sample_size": 5, "failure_rate_pct": 10}) is False


def test_summarize_model_book_downgrade_threshold_and_sorting():
    recs = []
    for i in range(5):
        r = make_matured("FAILED_FADE", r5=-3)
        r["rating"] = "C"
        recs.append(r)
    for i in range(3):
        r = make_matured("WORKED", r5=5)
        r["rating"] = "B"
        recs.append(r)
    for i in range(2):  # below min_sample -> dropped
        r = make_matured("WORKED", r5=9)
        r["rating"] = "A"
        recs.append(r)
    s = bmb.summarize_model_book(recs, ["rating"], min_sample=3)
    assert s["total_records"] == 10
    assert [row["group"] for row in s["groups"]["rating"]] == ["B", "C"]
    assert len(s["rule_candidates"]) == 1
    rule = s["rule_candidates"][0]
    assert rule["action"] == "downgrade_or_filter"
    assert rule["group"] == "C"
    assert rule["evidence"]["sample_size"] == 5


def test_summarize_model_book_empty():
    s = bmb.summarize_model_book([], ["rating"])
    assert s["total_records"] == 0
    assert s["overall"] == {"sample_size": 0, "pending": 0, "win_rate_pct": None}
    assert s["groups"] == {"rating": []}
    assert s["rule_candidates"] == []


# ------------------------------------------------------------------ reports


def test_write_json_report_creates_dir(tmp_path):
    out = tmp_path / "a" / "b"
    path = bmb.write_json_report({"k": "日本"}, out, "pre")
    assert path.parent == out
    assert path.name.startswith("pre_")
    assert path.suffix == ".json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": "日本"}


def test_markdown_report_minimal(tmp_path):
    path = bmb.write_markdown_report({"generated_at": "G"}, tmp_path / "m", "p")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Stockbee Setup Fluency Report\n\nGenerated: G\n")
    assert "## Reminder" in text
    assert "## Ingest" not in text
    assert "## Rule Candidates" not in text


def test_markdown_report_default_generated_stamp(tmp_path):
    path = bmb.write_markdown_report({"title": "T"}, tmp_path, "p")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# T"
    assert lines[2].startswith("Generated: 20")


def test_markdown_report_ingest_and_update_sections(tmp_path):
    payload = {
        "ingest": {
            "candidates_loaded": 4,
            "studyable": 2,
            "skipped": 2,
            "skipped_missing_setup_date": 1,
            "skipped_missing_symbol": 1,
            "inserted": 1,
            "updated": 1,
            "total": 9,
        },
        "update": {"updated": 3, "matured": 2, "still_pending": 1, "skipped_no_prices": 5},
    }
    text = bmb.write_markdown_report(payload, tmp_path, "p").read_text(encoding="utf-8")
    assert "- Candidates loaded: 4" in text
    assert "- Skipped missing setup date: 1" in text
    assert "- Skipped missing symbol: 1" in text
    assert "- Total model-book records: 9" in text
    assert "## Outcome Update" in text
    assert "- Matured: 2" in text
    assert "- Missing prices: 5" in text


def test_markdown_report_ingest_omits_zero_skip_lines(tmp_path):
    text = bmb.write_markdown_report({"ingest": {"studyable": 1}}, tmp_path, "p").read_text(
        encoding="utf-8"
    )
    assert "Skipped missing" not in text
    assert "- Skipped: 0" in text


def test_markdown_report_summary_groups_and_rules(tmp_path):
    row = {
        "group": "A",
        "sample_size": 6,
        "win_rate_pct": 80.0,
        "failure_rate_pct": 10.0,
        "avg_5d_return_pct": 3.0,
        "avg_5d_mfe_pct": 7.0,
        "avg_5d_mae_pct": -2.0,
    }
    payload = {
        "total_records": 6,
        "matured_records": 6,
        "pending_records": 0,
        "overall": {
            "sample_size": 6,
            "win_rate_pct": 80.0,
            "avg_5d_return_pct": 3.0,
            "avg_5d_mfe_pct": 7.0,
            "avg_5d_mae_pct": -2.0,
        },
        "groups": {"rating": [row], "primary_trigger": []},
        "rule_candidates": [
            {
                "action": "promote",
                "group_by": "rating",
                "group": "A",
                "reason": "why",
                "evidence": row,
            }
        ],
    }
    text = bmb.write_markdown_report(payload, tmp_path, "p").read_text(encoding="utf-8")
    assert "- Win rate: 80.0%" in text
    assert "- Avg 5d MFE / MAE: 7.0% / -2.0%" in text
    assert "## Cohorts by rating" in text
    assert "| A | 6 | 80.0 | 10.0 | 3.0 | 7.0 | -2.0 |" in text
    assert "## Cohorts by primary_trigger\n\nNo cohorts met the sample threshold." in text
    assert "- **promote** `rating=A`: why N=6, Win=80.0%, Avg5d=3.0%." in text


def test_markdown_report_overall_without_samples(tmp_path):
    payload = {"overall": {"sample_size": 0}, "total_records": 2, "pending_records": 2}
    text = bmb.write_markdown_report(payload, tmp_path, "p").read_text(encoding="utf-8")
    assert "- Pending records: 2" in text
    assert "Win rate" not in text


# ----------------------------------------------------------- parse_horizons


def test_parse_horizons_dedups_and_sorts():
    assert bmb.parse_horizons("5, 3,,3") == (3, 5)


def test_parse_horizons_errors():
    with pytest.raises(ValueError, match="positive integers"):
        bmb.parse_horizons("0")
    with pytest.raises(ValueError, match="positive integers"):
        bmb.parse_horizons("-2,3")
    with pytest.raises(ValueError, match="at least one horizon"):
        bmb.parse_horizons(" , ")
    with pytest.raises(ValueError):
        bmb.parse_horizons("abc")


# ----------------------------------------------------------------- commands


def write_screener(path, candidates):
    path.write_text(json.dumps({"metadata": {}, "candidates": candidates}), encoding="utf-8")
    return path


def test_main_ingest_end_to_end(tmp_path, capsys):
    screener = write_screener(
        tmp_path / "s.json", [cand(), cand(symbol="REJ", state="REJECT"), {"symbol": "NODATE"}]
    )
    book = tmp_path / "state" / "book.jsonl"
    out = tmp_path / "out"
    rc = bmb.main(
        [
            "ingest",
            "--screener-json",
            str(screener),
            "--model-book",
            str(book),
            "--output-dir",
            str(out),
        ]
    )
    assert rc == 0
    stdout = capsys.readouterr().out
    assert "Ingested 1 studyable candidates" in stdout
    assert "(1 skipped)" in stdout
    records = bmb.load_model_book(book)
    assert [r["symbol"] for r in records] == ["TEST"]
    assert records[0]["source_report"] == str(screener)
    reports = sorted(p.name for p in out.iterdir())
    assert len(reports) == 2
    jpath = next(p for p in out.iterdir() if p.suffix == ".json")
    payload = json.loads(jpath.read_text(encoding="utf-8"))
    assert payload["ingest"]["inserted"] == 1
    assert payload["candidates_loaded"] == 2
    assert payload["model_book"] == str(book)


def test_main_ingest_include_rejects_and_reingest_updates(tmp_path, capsys):
    screener = write_screener(tmp_path / "s.json", [cand(), cand(symbol="REJ", state="REJECT")])
    book = tmp_path / "book.jsonl"
    argv = ["ingest", "--screener-json", str(screener), "--model-book", str(book)]
    argv += ["--output-dir", str(tmp_path / "o"), "--include-rejects"]
    assert bmb.main(argv) == 0
    assert bmb.main(argv) == 0
    capsys.readouterr()
    records = bmb.load_model_book(book)
    assert sorted(r["symbol"] for r in records) == ["REJ", "TEST"]
    jsons = sorted((tmp_path / "o").glob("*.json"))
    assert jsons
    last = max(jsons, key=lambda p: p.stat().st_mtime_ns)
    assert json.loads(last.read_text(encoding="utf-8"))["ingest"]["total"] == 2


def test_main_update_no_records(tmp_path, capsys):
    rc = bmb.main(["update", "--model-book", str(tmp_path / "none.jsonl")])
    assert rc == 0
    assert "No records found in" in capsys.readouterr().out
    assert not (tmp_path / "none.jsonl").exists()


def test_main_update_with_prices_json(tmp_path, capsys):
    book = tmp_path / "book.jsonl"
    bmb.save_model_book(book, [bmb.make_record(cand())])
    prices = tmp_path / "prices.json"
    rows = [
        {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close}
        for b in bars_up(n=6)
    ]
    prices.write_text(json.dumps({"TEST": rows}), encoding="utf-8")
    out = tmp_path / "out"
    rc = bmb.main(
        [
            "update",
            "--model-book",
            str(book),
            "--prices-json",
            str(prices),
            "--horizons",
            "5,3",
            "--output-dir",
            str(out),
        ]
    )
    assert rc == 0
    assert "Updated outcomes in" in capsys.readouterr().out
    rec = bmb.load_model_book(book)[0]
    assert rec["matured"] is True
    assert set(rec["outcomes"]) == {"3d", "5d"}
    jpath = next(p for p in out.iterdir() if p.suffix == ".json")
    payload = json.loads(jpath.read_text(encoding="utf-8"))
    assert payload["horizons"] == [3, 5]
    assert payload["prices_source"] == str(prices)
    assert payload["api_stats"] is None
    assert payload["update"]["matured"] == 1


def test_main_update_no_only_pending_flag(tmp_path, capsys):
    book = tmp_path / "book.jsonl"
    rec = bmb.make_record(cand())
    rec["matured"] = True
    rec["overall_outcome"] = "WORKED"
    bmb.save_model_book(book, [rec])
    prices = tmp_path / "prices.json"
    rows = [{"date": b.date, "close": b.close} for b in bars_up(n=6)]
    prices.write_text(json.dumps({"TEST": rows}), encoding="utf-8")
    argv = ["update", "--model-book", str(book), "--prices-json", str(prices)]
    argv += ["--output-dir", str(tmp_path / "o"), "--no-only-pending"]
    assert bmb.main(argv) == 0
    capsys.readouterr()
    assert bmb.load_model_book(book)[0]["outcomes"]["5d"]["matured"] is True


def test_main_update_via_fmp_uses_fake_client(tmp_path, monkeypatch, capsys):
    book = tmp_path / "book.jsonl"
    bmb.save_model_book(
        book,
        [bmb.make_record(cand(symbol="aaa")), bmb.make_record(cand(symbol="bbb"))],
    )
    rows = [
        {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close}
        for b in bars_up(n=6)
    ]
    session = FakeSession([FakeResponse(200, rows), FakeResponse(200, [])])
    monkeypatch.setattr(bmb, "requests", SimpleNamespace(Session=lambda: session))
    monkeypatch.setattr(bmb.time, "sleep", lambda s: None)
    monkeypatch.setenv("FMP_API_KEY", "k")
    argv = ["update", "--model-book", str(book), "--history-days", "10", "--max-api-calls", "5"]
    argv += ["--output-dir", str(tmp_path / "o")]
    # BBB: stable returns [] -> v3 fallback; supply that response too.
    session.responses.append(FakeResponse(200, {"historical": []}))
    assert bmb.main(argv) == 0
    capsys.readouterr()
    recs = {r["symbol"]: r for r in bmb.load_model_book(book)}
    assert recs["AAA"]["matured"] is True
    assert recs["BBB"]["update_error"] == "missing_prices"
    jpath = next(p for p in (tmp_path / "o").iterdir() if p.suffix == ".json")
    payload = json.loads(jpath.read_text(encoding="utf-8"))
    assert payload["prices_source"] == "fmp"
    assert payload["api_stats"] == {
        "api_calls_made": 3,
        "max_api_calls": 5,
        "budget_remaining": 2,
    }
    assert payload["update"]["skipped_no_prices"] == 1


def test_build_prices_for_update_skips_blank_symbols(monkeypatch):
    session = FakeSession([])
    monkeypatch.setattr(bmb, "requests", SimpleNamespace(Session=lambda: session))
    monkeypatch.setenv("FMP_API_KEY", "k")
    args = SimpleNamespace(prices_json=None, api_key=None, max_api_calls=3, history_days=10)
    prices, stats = bmb.build_prices_for_update(args, [{"symbol": ""}, {}])
    assert prices == {}
    assert stats == {"api_calls_made": 0, "max_api_calls": 3, "budget_remaining": 3}
    assert session.calls == []


def test_main_summarize_end_to_end(tmp_path, capsys):
    recs = []
    for i in range(5):
        r = bmb.make_record(cand(symbol=f"S{i}"))
        r["matured"] = True
        r["overall_outcome"] = "WORKED"
        r["outcomes"] = {
            "3d": {"forward_return_pct": 3.0},
            "5d": {"forward_return_pct": 5.0, "mfe_pct": 8.0, "mae_pct": -1.0},
        }
        recs.append(r)
    book = tmp_path / "book.jsonl"
    bmb.save_model_book(book, recs)
    out = tmp_path / "out"
    rc = bmb.main(
        [
            "summarize",
            "--model-book",
            str(book),
            "--group-by",
            "rating, primary_trigger,",
            "--min-sample",
            "5",
            "--output-dir",
            str(out),
        ]
    )
    assert rc == 0
    assert "Summarized 5 records" in capsys.readouterr().out
    jpath = next(p for p in out.iterdir() if p.suffix == ".json")
    payload = json.loads(jpath.read_text(encoding="utf-8"))
    assert list(payload["groups"]) == ["rating", "primary_trigger"]
    assert payload["model_book"] == str(book)
    assert {r["group_by"] for r in payload["rule_candidates"]} == {"rating", "primary_trigger"}
    md = next(p for p in out.iterdir() if p.suffix == ".md").read_text(encoding="utf-8")
    assert "## Cohorts by rating" in md
    assert "## Rule Candidates" in md


def test_main_requires_subcommand():
    with pytest.raises(SystemExit) as exc:
        bmb.main([])
    assert exc.value.code == 2


def test_default_model_book_and_parser_defaults():
    args = bmb.build_parser().parse_args(["summarize"])
    assert args.model_book == bmb.DEFAULT_MODEL_BOOK
    assert args.group_by == "rating,primary_trigger,setup_tags"
    assert args.min_sample == 3
    args = bmb.build_parser().parse_args(["update"])
    assert args.only_pending is True
    assert args.horizons == "3,5"
    assert args.max_api_calls == 200
    assert args.history_days == 80
