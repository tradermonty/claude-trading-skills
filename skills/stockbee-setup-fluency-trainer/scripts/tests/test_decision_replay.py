"""Offline tests for decision_replay.py (blind replay of the user's own VCP decisions, #710).

All data is fictional. Time is injected by monkeypatching ``decision_replay._now`` with
timezone-aware datetimes and ``decision_replay._local_tz``; nothing touches the network.
"""

import copy
import inspect
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import decision_replay as dr  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "decision_replay"
ET = ZoneInfo("America/New_York")
# 2026-11-06 is a Friday; 23:40 UTC is 18:40 EST.
FRI_EVENING = datetime(2026, 11, 6, 23, 40, tzinfo=timezone.utc)
QUADRANTS = ["followed_favorable", "followed_adverse", "deviated_favorable", "deviated_adverse"]
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
ANSWERS_QUAD = {"ZZEN": "enter", "ZZWT": "pass", "ZZDV": "pass", "ZZST": "enter"}


def _fx(name):
    return name if isinstance(name, Path) else FIX / name


def _load(name):
    return json.loads(_fx(name).read_text())


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return path


class Env:
    def __init__(self, tmp_path, monkeypatch, capsys):
        self.tmp = tmp_path
        self.store = tmp_path / "store"
        self.out = tmp_path / "reports"
        self.mp = monkeypatch
        self.capsys = capsys
        self.set_now(FRI_EVENING)
        monkeypatch.setattr(dr, "_local_tz", lambda: ET)

    def set_now(self, dt):
        self.mp.setattr(dr, "_now", lambda: dt)

    def run(self, *args):
        self.capsys.readouterr()
        code = dr.main([str(a) for a in args])
        cap = self.capsys.readouterr()
        return code, cap.out, cap.err

    def report(self, name="r.json", mutate=None):
        payload = _load("vcp_report_fictional.json")
        if mutate:
            mutate(payload)
        return _write(self.tmp / name, payload)

    def decisions(self, mapping, name="d.json"):
        rows = [{"symbol": s, "decision": d, "reason": f"reason {s}"} for s, d in mapping.items()]
        return _write(self.tmp / name, rows)

    def capture(
        self, report=None, decisions="decisions_quadrants.json", gate="open", limit=4, extra=()
    ):
        args = [
            "capture",
            "--screener-json",
            report or FIX / "vcp_report_fictional.json",
            "--decisions",
            _fx(decisions),
            "--market-gate",
            gate,
            "--store-dir",
            self.store,
        ]
        if limit:
            args += ["--limit", limit]
        return self.run(*args, *extra)

    def replay(self, size=10, seed=7, extra=()):
        code, out, err = self.run(
            "replay",
            "--sample-size",
            size,
            "--seed",
            seed,
            "--store-dir",
            self.store,
            "--output-dir",
            self.out,
            *extra,
        )
        match = re.search(r"session_id: (replay-[0-9a-f]{12})", out)
        return code, out, err, (match.group(1) if match else None)

    def blind(self, sid):
        return _load(self.out / f"stockbee_setup_fluency_replay_blind_{sid}.json")

    def answers(self, blind, mapping, name="a.json"):
        rows = [
            {
                "case_id": c["case_id"],
                "decision": mapping[c["symbol"]],
                "reason": f"replay {c['symbol']}",
            }
            for c in blind["cases"]
        ]
        return _write(self.tmp / name, rows)

    def reveal(self, sid, answers, prices="prices_bull.json"):
        return self.run(
            "reveal",
            "--session-id",
            sid,
            "--answers",
            answers,
            "--prices-json",
            _fx(prices),
            "--store-dir",
            self.store,
            "--output-dir",
            self.out,
        )

    def reveal_payload(self):
        files = sorted(
            self.out.glob("stockbee_setup_fluency_replay_reveal_*.json"),
            key=lambda p: p.stat().st_mtime_ns,
        )
        return json.loads(files[-1].read_text())

    def full_cycle(self, prices="prices_bull.json", answers=ANSWERS_QUAD, **cap):
        assert self.capture(**cap)[0] == 0
        code, _out, _err, sid = self.replay()
        assert code == 0 and sid
        blind = self.blind(sid)
        code, _out, err = self.reveal(sid, self.answers(blind, answers), prices)
        assert code == 0, err
        payload = self.reveal_payload()
        return sid, blind, payload, {c["symbol"]: c for c in payload["cases"]}


@pytest.fixture
def env(tmp_path, monkeypatch, capsys):
    return Env(tmp_path, monkeypatch, capsys)


def assert_clean_failure(result):
    code, out, err = result[:3]
    assert code == 1
    assert out == ""
    assert err.startswith("ERROR:") or "\nERROR:" in err


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


# ---------------------------------------------------------------------------
# Pure functions (sequencing step 1)
# ---------------------------------------------------------------------------


def test_select_cases_signature_is_outcome_free():
    assert list(inspect.signature(dr.select_cases).parameters) == [
        "population_ids",
        "sample_size",
        "seed",
    ]


def test_select_cases_is_deterministic_and_seed_sensitive():
    ids = [f"c{i}" for i in range(8)]
    assert dr.select_cases(ids, 8, 1) == dr.select_cases(list(reversed(ids)), 8, 1)
    assert dr.select_cases(ids, 8, 1) != dr.select_cases(ids, 8, 2)
    assert sorted(dr.select_cases(ids, 100, 3)) == ids
    assert len(dr.select_cases(ids, 3, 3)) == 3


def test_population_and_selection_never_touch_prices(env, monkeypatch):
    assert env.capture()[0] == 0

    def boom(*_a, **_k):
        raise AssertionError("population/selection must not read prices or outcomes")

    monkeypatch.setattr(dr, "load_prices_json", boom)
    monkeypatch.setattr(dr, "calculate_window_outcome", boom)
    monkeypatch.setattr(dr, "future_bars_after_setup", boom)
    ids = [c["case_id"] for c in dr.load_population(env.store)]
    assert len(dr.select_cases(ids, 2, 5)) == 2


def _good_snapshot():
    return {
        "valid_vcp": True,
        "execution_state": "Pre-breakout",
        "distance_from_pivot_pct": -1.5,
        "risk_pct": 5.0,
        "dry_up_ratio": 0.6,
    }


def test_evaluate_rule_all_pass_and_gate_closed():
    items = dr.get_rule("vcp-checklist-v1")
    ok = dr.evaluate_rule(items, _good_snapshot(), "open")
    assert ok["expected"] == "enter"
    assert all(i["status"] == "pass" for i in ok["items"])
    closed = dr.evaluate_rule(items, _good_snapshot(), "closed")
    assert closed["expected"] == "not_enter"
    assert [i["id"] for i in closed["items"] if i["status"] == "fail"] == ["market_gate_open"]


def test_evaluate_rule_missing_field_fails_item():
    snap = _good_snapshot()
    del snap["dry_up_ratio"]
    res = dr.evaluate_rule(dr.get_rule("vcp-checklist-v1"), snap, "open")
    assert res["expected"] == "not_enter"
    status = {i["id"]: i["status"] for i in res["items"]}
    assert status["volume_dry_up"] == "missing"


@pytest.mark.parametrize(
    "mutation,failed",
    [
        ({"valid_vcp": False}, "valid_vcp"),
        ({"execution_state": "Extended"}, "execution_state"),
        ({"execution_state": None}, "execution_state"),
        ({"distance_from_pivot_pct": 3.1}, "pivot_distance"),
        ({"distance_from_pivot_pct": -8.1}, "pivot_distance"),
        ({"risk_pct": 0}, "risk"),
        ({"risk_pct": 15.1}, "risk"),
        ({"dry_up_ratio": 1.01}, "volume_dry_up"),
    ],
)
def test_evaluate_rule_each_item_can_fail(mutation, failed):
    snap = {**_good_snapshot(), **mutation}
    res = dr.evaluate_rule(dr.get_rule("vcp-checklist-v1"), snap, "open")
    assert res["expected"] == "not_enter"
    assert [i["id"] for i in res["items"] if i["status"] != "pass"] == [failed]


def test_evaluate_rule_boundaries_inclusive():
    snap = {
        **_good_snapshot(),
        "distance_from_pivot_pct": 3.0,
        "risk_pct": 15.0,
        "dry_up_ratio": 1.0,
    }
    assert dr.evaluate_rule(dr.get_rule("vcp-checklist-v1"), snap, "open")["expected"] == "enter"
    snap["distance_from_pivot_pct"] = -8.0
    assert dr.evaluate_rule(dr.get_rule("vcp-checklist-v1"), snap, "open")["expected"] == "enter"


def test_evaluate_rule_rejects_unknown_op_and_bad_numbers():
    with pytest.raises(dr.ReplayError):
        dr.evaluate_rule([{"id": "x", "field": "a", "op": "regex", "value": 1}], {"a": 1}, "open")
    res = dr.evaluate_rule(
        [{"id": "x", "field": "a", "op": "lte", "value": 1}], {"a": True}, "open"
    )
    assert res["items"][0]["status"] == "fail"


def test_unknown_rule_version_rejected():
    with pytest.raises(dr.ReplayError):
        dr.get_rule("vcp-checklist-v9")


@pytest.mark.parametrize(
    "decision,expected,adherence",
    [
        ("enter", "enter", "followed"),
        ("wait", "not_enter", "followed"),
        ("pass", "not_enter", "followed"),
        ("pass", "enter", "deviated"),
        ("wait", "enter", "deviated"),
        ("enter", "not_enter", "deviated"),
    ],
)
def test_adherence(decision, expected, adherence):
    assert dr.adherence(decision, expected) == adherence


def test_outcome_and_quadrant_mapping():
    assert dr.decision_outcome("enter", "rallied") == "favorable"
    assert dr.decision_outcome("enter", "did_not_rally") == "adverse"
    assert dr.decision_outcome("wait", "rallied") == "adverse"
    assert dr.decision_outcome("pass", "did_not_rally") == "favorable"
    assert dr.classify_quadrant("followed", "favorable") == "followed_favorable"
    assert dr.classify_quadrant("followed", "adverse") == "followed_adverse"
    assert dr.classify_quadrant("deviated", "favorable") == "deviated_favorable"
    assert dr.classify_quadrant("deviated", "adverse") == "deviated_adverse"


def test_vcp_snapshot_whitelist_excludes_commentary_and_unknown_keys():
    result = copy.deepcopy(_load("vcp_report_fictional.json")["results"][0])
    result["brand_new_coverage_field"] = {"secret": "2099-01-01"}
    snap = dr.vcp_snapshot(result)
    for banned in (
        "guidance",
        "rating_description",
        "execution_state_reasons",
        "cap_reason",
        "company_name",
        "brand_new_coverage_field",
        "market_cap",
    ):
        assert banned not in snap
    assert snap["symbol"] == "ZZEN"
    assert snap["pivot_price"] == 101.5
    assert snap["stop_loss_price"] == 95.0
    assert snap["risk_pct"] == 5.0
    assert snap["dry_up_ratio"] == 0.6
    assert snap["rs_rank_estimate"] == 88
    assert snap["trend_template_score"] == 92.0
    assert snap["num_contractions"] == 3
    assert snap["contractions"][0]["label"] == "T1"
    assert snap["entry_ready"] is True


def test_assert_no_future_dates():
    snap = {
        "contractions": [{"low_date": "2026-11-06"}, {"low_date": "N/A"}, {"low_date": "day-3"}]
    }
    dr.assert_no_future_dates(snap, "2026-11-06")
    snap["contractions"].append({"low_date": "2026-11-09"})
    with pytest.raises(dr.ReplayError):
        dr.assert_no_future_dates(snap, "2026-11-06")
    with pytest.raises(dr.ReplayError):
        dr.assert_no_future_dates({"x": "2026-11-09T10:00:00"}, "2026-11-06")


def test_check_capture_lag_rules():
    fri = date(2026, 11, 6)
    thu = date(2026, 11, 5)
    utc = timezone.utc
    dr.check_capture_lag(fri, datetime(2026, 11, 6, 23, 0, tzinfo=utc))  # Fri 18:00 ET
    dr.check_capture_lag(fri, datetime(2026, 11, 8, 15, 0, tzinfo=utc))  # Sunday
    with pytest.raises(dr.ReplayError):
        dr.check_capture_lag(fri, datetime(2026, 11, 9, 15, 0, tzinfo=utc))  # Monday
    with pytest.raises(dr.ReplayError):
        dr.check_capture_lag(thu, datetime(2026, 11, 6, 15, 0, tzinfo=utc))  # next day
    with pytest.raises(dr.ReplayError):
        dr.check_capture_lag(fri, datetime(2026, 11, 5, 15, 0, tzinfo=utc))  # before decision
    # judged on the ET calendar: 03:00 UTC on Nov 6 is still Nov 5 in New York
    dr.check_capture_lag(thu, datetime(2026, 11, 6, 3, 0, tzinfo=utc))
    with pytest.raises(dr.ReplayError):
        dr.check_capture_lag(fri, datetime(2026, 11, 6, 3, 0, tzinfo=utc))


def test_missing_tzdata_is_fail_closed(monkeypatch):
    from zoneinfo import ZoneInfoNotFoundError

    def boom(_name):
        raise ZoneInfoNotFoundError("America/New_York")

    monkeypatch.setattr(dr, "ZoneInfo", boom)
    with pytest.raises(dr.ReplayError, match="tzdata"):
        dr.check_capture_lag(date(2026, 11, 6), FRI_EVENING)


# ---------------------------------------------------------------------------
# Capture (step 2)
# ---------------------------------------------------------------------------


def test_capture_writes_record_with_hashes_and_ledger(env):
    code, out, err = env.capture()
    assert code == 0, err
    assert "vcp-2026-11-06-" in out
    files = list((env.store / "captures").glob("vcp-*.json"))
    assert len(files) == 1
    rec = json.loads(files[0].read_text())
    assert rec["decision_date"] == "2026-11-06"
    assert rec["market_gate"] == "open"
    assert rec["evaluation"]["horizon_days"] == 5
    assert rec["evaluation"]["rally_threshold_pct"] == 5.0
    assert rec["rule"]["version"] == "vcp-checklist-v1"
    assert [c["symbol"] for c in rec["cases"]] == ["ZZEN", "ZZWT", "ZZDV", "ZZST"]
    assert rec["cases"][0]["decision"] == "enter"
    assert rec["capture_sha256"] == dr.capture_hash(rec)
    assert rec["captured_at"].endswith("+00:00")
    ledger = [
        json.loads(x) for x in (env.store / "captures" / "ledger.jsonl").read_text().splitlines()
    ]
    assert ledger == [
        {
            "capture_id": rec["capture_id"],
            "capture_sha256": rec["capture_sha256"],
            "captured_at": rec["captured_at"],
        }
    ]
    # screener free text never enters the record
    text = files[0].read_text()
    assert "Fictional guidance" not in text and "Fictional commentary" not in text


def test_capture_limit_takes_report_order_prefix(env):
    dec = env.decisions({"ZZEN": "enter", "ZZWT": "wait"})
    assert env.capture(decisions=dec, limit=2)[0] == 0
    rec = json.loads(next((env.store / "captures").glob("vcp-*.json")).read_text())
    assert [c["symbol"] for c in rec["cases"]] == ["ZZEN", "ZZWT"]
    # a decision for a symbol outside the limited set is an unknown symbol
    env2 = Env(env.tmp / "x", env.mp, env.capsys)
    assert_clean_failure(env2.capture(decisions="decisions_quadrants.json", limit=2))


def test_capture_same_report_twice_fails(env):
    assert env.capture()[0] == 0
    result = env.capture()
    assert_clean_failure(result)
    assert "already exists" in result[2]


def test_capture_rejects_snapshot_dated_after_decision_date(env):
    def mutate(p):
        p["results"][0]["vcp_pattern"]["contractions"][0]["low_date"] = "2026-11-09"

    result = env.capture(report=env.report(mutate=mutate))
    assert_clean_failure(result)
    assert not (env.store / "captures").exists()


def test_capture_rejects_nan_in_snapshot(env):
    def mutate(p):
        p["results"][0]["pivot_proximity"]["risk_pct"] = float("nan")

    assert_clean_failure(env.capture(report=env.report(mutate=mutate)))


@pytest.mark.parametrize(
    "rows",
    [
        [{"symbol": "ZZEN", "decision": "enter", "reason": "r"}],  # missing candidates
        [
            {"symbol": s, "decision": "enter", "reason": "r"}
            for s in ("ZZEN", "ZZEN", "ZZWT", "ZZDV", "ZZST")
        ],
        [
            {"symbol": s, "decision": "enter", "reason": "r"}
            for s in ("ZZEN", "ZZWT", "ZZDV", "NOPE")
        ],
        [{"symbol": s, "decision": "buy", "reason": "r"} for s in ("ZZEN", "ZZWT", "ZZDV", "ZZST")],
        [
            {"symbol": s, "decision": "enter", "reason": ""}
            for s in ("ZZEN", "ZZWT", "ZZDV", "ZZST")
        ],
        [
            {"symbol": s, "decision": "enter", "reason": "a\nb"}
            for s in ("ZZEN", "ZZWT", "ZZDV", "ZZST")
        ],
        [
            {"symbol": s, "decision": "enter", "reason": "x" * 201}
            for s in ("ZZEN", "ZZWT", "ZZDV", "ZZST")
        ],
        {"not": "a list"},
    ],
)
def test_invalid_decisions_rejected_and_nothing_written(env, rows):
    path = _write(env.tmp / "bad.json", rows)
    assert_clean_failure(env.capture(decisions=path))
    assert not (env.store / "captures").exists()


def test_non_vcp_report_shape_rejected(env):
    path = _write(
        env.tmp / "hist.json",
        {"detections": [], "metadata": {"generated_at": "2026-11-06 18:30:00"}},
    )
    assert_clean_failure(env.capture(report=path))


def test_unreadable_json_rejected(env):
    bad = env.tmp / "bad.json"
    bad.write_text("{not json")
    assert_clean_failure(env.capture(report=bad))


def test_decision_date_defaults_from_generated_at_and_no_warning_after_close(env):
    code, _out, err = env.capture()
    assert code == 0
    assert "WARNING" not in err


def test_missing_generated_at_without_flag_fails(env):
    def mutate(p):
        del p["metadata"]["generated_at"]

    assert_clean_failure(env.capture(report=env.report(mutate=mutate)))


def test_missing_generated_at_with_flag_ok_without_warning(env):
    def mutate(p):
        del p["metadata"]["generated_at"]

    code, _out, err = env.capture(
        report=env.report(mutate=mutate), extra=["--decision-date", "2026-11-06"]
    )
    assert code == 0, err
    assert "WARNING" not in err


def test_decision_date_override_range(env):
    far = env.capture(extra=["--decision-date", "2026-11-07"])  # after generated date
    assert_clean_failure(far)
    older = env.capture(extra=["--decision-date", "2026-11-04"])  # two days before
    assert_clean_failure(older)
    env.set_now(datetime(2026, 11, 5, 23, 0, tzinfo=timezone.utc))
    ok = env.capture(extra=["--decision-date", "2026-11-05"])  # one day of slack
    assert ok[0] == 0, ok[2]


def test_capture_lag_and_future_date_rejected(env):
    env.set_now(datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc))  # Monday after a Friday report
    assert_clean_failure(env.capture())
    env.set_now(datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc))  # Sunday is fine
    assert env.capture()[0] == 0
    env2 = Env(env.tmp / "y", env.mp, env.capsys)
    env2.set_now(datetime(2026, 11, 5, 15, 0, tzinfo=timezone.utc))  # before the decision date
    assert_clean_failure(env2.capture())


def test_jst_generated_at_is_interpreted_in_new_york(env):
    env.mp.setattr(dr, "_local_tz", lambda: ZoneInfo("Asia/Tokyo"))

    def thu_morning_jst(p):
        p["metadata"]["generated_at"] = "2026-11-05 08:00:00"  # = Wed 18:00 EST

    env.set_now(datetime(2026, 11, 5, 0, 30, tzinfo=timezone.utc))  # Wed 19:30 EST
    code, _out, err = env.capture(report=env.report(mutate=thu_morning_jst))
    assert code == 0, err
    assert "WARNING" not in err
    rec = json.loads(next((env.store / "captures").glob("vcp-*.json")).read_text())
    assert rec["decision_date"] == "2026-11-04"


def test_before_close_report_warns_but_proceeds(env):
    env.mp.setattr(dr, "_local_tz", lambda: ZoneInfo("Asia/Tokyo"))

    def early(p):
        p["metadata"]["generated_at"] = "2026-11-05 20:00:00"  # = Thu 06:00 EST

    env.set_now(datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc))
    code, _out, err = env.capture(report=env.report(mutate=early))
    assert code == 0, err
    assert "WARNING: report generated before the close" in err
    rec = json.loads(next((env.store / "captures").glob("vcp-*.json")).read_text())
    assert rec["decision_date"] == "2026-11-05"


def test_lag_is_judged_on_the_et_calendar(env):
    # Thursday decision, captured 22:00 ET Thursday = 03:00 UTC Friday.
    def thursday(p):
        p["metadata"]["generated_at"] = "2026-11-05 18:30:00"

    env.set_now(datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc))
    code, _out, err = env.capture(report=env.report(mutate=thursday))
    assert code == 0, err


def test_rule_mismatch_recorded_when_screener_disagrees(env):
    def mutate(p):
        p["results"][0]["pivot_proximity"]["risk_pct"] = 18.0  # entry_ready stays true

    assert env.capture(report=env.report(mutate=mutate))[0] == 0
    rec = json.loads(next((env.store / "captures").glob("vcp-*.json")).read_text())
    flags = {c["symbol"]: c["rule_mismatch"] for c in rec["cases"]}
    assert flags == {"ZZEN": True, "ZZWT": False, "ZZDV": False, "ZZST": False}
    assert rec["cases"][0]["screener_entry_ready"] is True
    assert rec["cases"][0]["v1_structural_pass"] is False


def test_missing_execution_state_is_always_mismatch(env):
    def mutate(p):
        del p["results"][3]["execution_state"]  # ZZST

    assert env.capture(report=env.report(mutate=mutate))[0] == 0
    rec = json.loads(next((env.store / "captures").glob("vcp-*.json")).read_text())
    assert {c["symbol"]: c["rule_mismatch"] for c in rec["cases"]}["ZZST"] is True


# ---------------------------------------------------------------------------
# Replay (step 3)
# ---------------------------------------------------------------------------


def test_blind_view_omits_decision_rule_and_outcome_fields(env):
    assert env.capture()[0] == 0
    _code, _out, _err, sid = env.replay()
    blind = env.blind(sid)
    assert set(blind) == {
        "schema_version",
        "record_type",
        "session_id",
        "case_count",
        "instructions",
        "cases",
    }
    assert blind["record_type"] == "replay_blind_view"
    assert set(blind["cases"][0]) == {
        "case_number",
        "case_id",
        "symbol",
        "setup_type",
        "decision_date",
        "market_gate",
        "snapshot",
    }
    forbidden = {
        "decision",
        "reason",
        "rule",
        "rule_expected",
        "evaluation",
        "forward_return_pct",
        "path",
        "outcome",
        "guidance",
        "rating_description",
        "adherence",
        "quadrant",
    }
    assert not forbidden & set(walk_keys(blind))
    md = (env.out / f"stockbee_setup_fluency_replay_blind_{sid}.md").read_text()
    assert "Fictional guidance" not in md and "Fictional commentary" not in md


def test_blind_view_contains_no_date_after_decision_date_or_price_data(env):
    assert env.capture()[0] == 0
    _code, _out, _err, sid = env.replay()
    blind_json = (env.out / f"stockbee_setup_fluency_replay_blind_{sid}.json").read_text()
    blind_md = (env.out / f"stockbee_setup_fluency_replay_blind_{sid}.md").read_text()
    for text in (blind_json, blind_md):
        dates = ISO_DATE.findall(text)
        assert dates and max(dates) <= "2026-11-06"
        assert "2026-11-09" not in text
        for later_close in ("102.0", "104.0", "105.0", "106.0"):
            assert not re.search(rf"\b{re.escape(later_close)}\b", text)
    assert "2026-11-06" in blind_json
    # no wall-clock time, seed or hash leaks into the blind view
    assert "seed" not in blind_json and "population" not in blind_json
    assert "captured_at" not in blind_json


def test_blind_view_is_scanned_by_the_guard_too(env, monkeypatch):
    assert env.capture()[0] == 0
    calls = []
    real = dr.assert_no_future_dates
    monkeypatch.setattr(dr, "assert_no_future_dates", lambda o, d: (calls.append(d), real(o, d))[1])
    assert env.replay()[0] == 0
    assert calls  # defense in depth: the view is re-checked


def test_replay_never_loads_prices(env, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("replay must not load prices")

    monkeypatch.setattr(dr, "load_prices_json", boom)
    assert env.capture()[0] == 0
    code, _out, err, _sid = env.replay()
    assert code == 0, err


def test_replay_rejects_prices_flag(env):
    with pytest.raises(SystemExit) as exc:
        dr.main(
            [
                "replay",
                "--sample-size",
                "2",
                "--prices-json",
                "x.json",
                "--store-dir",
                str(env.store),
            ]
        )
    assert exc.value.code == 2


def test_session_record_and_population(env):
    assert env.capture()[0] == 0
    other = env.report("r2.json", mutate=lambda p: p["metadata"].update(universe="other"))
    assert env.capture(report=other)[0] == 0
    code, _out, _err, sid = env.replay(size=100, seed=11)
    assert code == 0
    session = _load(env.store / "sessions" / f"{sid}.json")
    assert session["population_size"] == 8
    assert session["seed"] == 11
    assert session["sample_size"] == 100
    assert len(session["selected_case_ids"]) == 8
    assert env.blind(sid)["case_count"] == 8
    ids = sorted(session["selected_case_ids"])
    assert session["selected_case_ids"] == dr.select_cases(ids, 100, 11)
    assert session["population_sha256"] == dr.population_hash(ids)


def test_seed_is_generated_and_recorded_when_omitted(env):
    assert env.capture()[0] == 0
    code, out, _err = env.run(
        "replay", "--sample-size", "2", "--store-dir", env.store, "--output-dir", env.out
    )
    assert code == 0
    sid = re.search(r"session_id: (replay-[0-9a-f]{12})", out).group(1)
    session = _load(env.store / "sessions" / f"{sid}.json")
    assert isinstance(session["seed"], int) and 0 <= session["seed"] < 2**31


def test_load_population_is_independent_of_reveal_and_prices(env, monkeypatch):
    assert env.capture()[0] == 0
    before = [c["case_id"] for c in dr.load_population(env.store, include_seen=True)]
    _code, _out, _err, sid = env.replay()
    blind = env.blind(sid)
    assert env.reveal(sid, env.answers(blind, ANSWERS_QUAD))[0] == 0
    monkeypatch.setattr(
        dr, "load_prices_json", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError)
    )
    after = [c["case_id"] for c in dr.load_population(env.store, include_seen=True)]
    assert before == after and len(before) == 4


def test_empty_store_replay_exits_0_no_files(env):
    code, out, err, _sid = env.replay()
    assert code == 0, err
    assert "No captured cases" in out
    assert not env.out.exists()
    assert not (env.store / "sessions").exists()


def test_replay_requires_positive_sample_size(env):
    assert env.capture()[0] == 0
    for argv in (
        ["replay", "--sample-size", "0", "--store-dir", str(env.store)],
        ["replay", "--store-dir", str(env.store)],
    ):
        with pytest.raises(SystemExit) as exc:
            dr.main(argv)
        assert exc.value.code == 2


def test_decided_on_or_before_filter_is_date_only(env):
    assert env.capture()[0] == 0
    code, out, _err, _sid = env.replay(extra=["--decided-on-or-before", "2026-11-05"])
    assert code == 0 and "No captured cases" in out
    code, _out, _err, sid = env.replay(extra=["--decided-on-or-before", "2026-11-06"])
    assert code == 0 and env.blind(sid)["case_count"] == 4


def test_pending_session_blocks_new_replay_until_abandoned(env):
    assert env.capture()[0] == 0
    _c, _o, _e, sid = env.replay(seed=1)
    blocked = env.replay(seed=2)
    assert blocked[0] == 1 and "pending" in blocked[2]
    assert blocked[1] == ""
    code, out, err = env.run(
        "replay",
        "--abandon",
        sid,
        "--reason",
        "ran out of time",
        "--store-dir",
        env.store,
        "--output-dir",
        env.out,
    )
    assert code == 0, err
    assert (env.store / "sessions" / f"{sid}.abandoned.json").exists()
    again = env.replay(seed=2)
    assert again[0] == 0
    # abandoned cases were never revealed, so they stay unseen
    assert env.blind(again[3])["case_count"] == 4
    dup = env.run(
        "replay",
        "--abandon",
        sid,
        "--reason",
        "again",
        "--store-dir",
        env.store,
        "--output-dir",
        env.out,
    )
    assert_clean_failure(dup)


def test_revealed_cases_are_not_offered_again_unless_include_seen(env):
    assert env.capture()[0] == 0
    _c, _o, _e, sid = env.replay()
    assert env.reveal(sid, env.answers(env.blind(sid), ANSWERS_QUAD))[0] == 0
    other = env.report("r2.json", mutate=lambda p: p["metadata"].update(universe="other"))
    assert env.capture(report=other)[0] == 0
    _c, _o, _e, sid2 = env.replay(size=100, seed=3)
    assert env.blind(sid2)["case_count"] == 4  # only the new capture
    # include-seen on a fresh seed readmits everything and marks the seen ones
    assert env.reveal(sid2, env.answers(env.blind(sid2), ANSWERS_QUAD, "a2.json"))[0] == 0
    _c, _o, _e, sid3 = env.replay(size=100, seed=4, extra=["--include-seen"])
    session = _load(env.store / "sessions" / f"{sid3}.json")
    assert len(session["selected_case_ids"]) == 8
    assert len(session["seen_before_case_ids"]) == 8
    assert env.reveal(sid3, env.answers(env.blind(sid3), ANSWERS_QUAD, "a3.json"))[0] == 0
    payload = env.reveal_payload()
    assert all(c["seen_before"] for c in payload["cases"])
    assert payload["summary"]["replay"]["adherence_rate_pct"] is None
    assert payload["summary"]["consistency_rate_pct"] is None
    assert payload["summary"]["prior_sessions"] == 2


def test_ledger_detects_deleted_capture_file(env):
    assert env.capture()[0] == 0
    next((env.store / "captures").glob("vcp-*.json")).unlink()
    result = env.replay()
    assert result[0] == 1 and "ledger" in result[2]


def test_capture_missing_from_ledger_names_reconcile_and_reconcile_fixes_it(env):
    assert env.capture()[0] == 0
    (env.store / "captures" / "ledger.jsonl").write_text("")
    result = env.replay()
    assert result[0] == 1 and "reconcile-ledger" in result[2]
    code, out, err = env.run("reconcile-ledger", "--store-dir", env.store)
    assert code == 0, err
    assert "1" in out
    assert env.replay()[0] == 0
    # reconciling again is a no-op, never a rewrite
    before = (env.store / "captures" / "ledger.jsonl").read_text()
    assert env.run("reconcile-ledger", "--store-dir", env.store)[0] == 0
    assert (env.store / "captures" / "ledger.jsonl").read_text() == before


def test_reconcile_cannot_bypass_the_lag_guard(env):
    assert env.capture()[0] == 0
    cap = next((env.store / "captures").glob("vcp-*.json"))
    rec = json.loads(cap.read_text())
    rec["captured_at"] = "2026-11-09T15:00:00+00:00"
    rec["capture_sha256"] = dr.capture_hash(rec)
    cap.write_text(json.dumps(rec))
    (env.store / "captures" / "ledger.jsonl").write_text("")
    assert_clean_failure(env.run("reconcile-ledger", "--store-dir", env.store))


def test_tampered_capture_fails_integrity(env):
    assert env.capture()[0] == 0
    cap = next((env.store / "captures").glob("vcp-*.json"))
    rec = json.loads(cap.read_text())
    rec["cases"][0]["snapshot"]["price"] = 1.0
    cap.write_text(json.dumps(rec))
    result = env.replay()
    assert result[0] == 1 and "integrity" in result[2]
    # snapshot-only tamper with a recomputed capture hash is still caught by the snapshot hash
    rec["capture_sha256"] = dr.capture_hash(rec)
    cap.write_text(json.dumps(rec))
    result = env.replay()
    assert result[0] == 1 and "integrity" in result[2]


def test_write_once_helper_never_overwrites(tmp_path):
    target = tmp_path / "a.json"
    dr._write_once(target, {"x": 1})
    with pytest.raises(dr.ReplayError, match="already exists"):
        dr._write_once(target, {"x": 2})
    assert json.loads(target.read_text()) == {"x": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]  # temp file cleaned up


def test_write_once_falls_back_when_hard_links_are_unsupported(tmp_path, monkeypatch):
    def nolink(*_a, **_k):
        raise PermissionError("no hard links here")

    monkeypatch.setattr(dr.os, "link", nolink)
    target = tmp_path / "b.json"
    dr._write_once(target, {"y": 1})
    assert json.loads(target.read_text()) == {"y": 1}
    with pytest.raises(dr.ReplayError, match="already exists"):
        dr._write_once(target, {"y": 2})


# ---------------------------------------------------------------------------
# Reveal (step 4)
# ---------------------------------------------------------------------------


def test_e2e_capture_replay_reveal_entered_and_passed(env):
    sid, blind, payload, cases = env.full_cycle()
    assert blind["case_count"] == 4
    zzen, zzwt = cases["ZZEN"], cases["ZZWT"]
    assert zzen["original"]["decision"] == "enter"
    assert zzen["original"]["reason"] == "Tight T3, at pivot, volume dry-up."
    assert zzen["replay"]["decision"] == "enter"
    assert zzen["replay"]["reason"] == "replay ZZEN"
    assert zzen["rule_version"] == "vcp-checklist-v1"
    assert [i["id"] for i in zzen["rule_items"]][0] == "market_gate_open"
    assert zzen["rule_expected"] == "enter"
    assert [p["date"] for p in zzen["path"]["closes"]] == [
        "2026-11-09",
        "2026-11-10",
        "2026-11-11",
        "2026-11-12",
        "2026-11-13",
    ]
    assert zzen["path"]["closes"][-1]["close"] == 106.0
    assert zzen["path"]["forward_return_pct"] == 6.0
    assert zzen["path_class"] == "rallied"
    assert zzen["original"]["quadrant"] == "followed_favorable"
    assert zzwt["original"]["decision"] == "pass"
    assert zzwt["original"]["quadrant"] == "followed_adverse"
    assert payload["record_type"] == "replay_reveal"
    assert payload["session_id"] == sid
    # reports exist as JSON and Markdown
    assert list(env.out.glob("stockbee_setup_fluency_replay_reveal_*.md"))


def test_four_quadrants_reported(env):
    _sid, _blind, payload, cases = env.full_cycle(prices="prices_mixed.json")
    original = payload["summary"]["original"]["quadrants"]
    assert original == {q: 1 for q in QUADRANTS}
    assert cases["ZZEN"]["original"]["quadrant"] == "followed_favorable"
    assert cases["ZZWT"]["original"]["quadrant"] == "followed_adverse"
    assert cases["ZZDV"]["original"]["quadrant"] == "deviated_favorable"
    assert cases["ZZST"]["original"]["quadrant"] == "deviated_adverse"
    # replay answers: ZZEN enter, ZZWT pass, ZZDV pass, ZZST enter
    assert cases["ZZDV"]["replay"]["adherence"] == "followed"
    assert cases["ZZST"]["replay"]["adherence"] == "followed"
    assert payload["summary"]["consistency_rate_pct"] == 50.0
    assert payload["summary"]["original"]["adherence_rate_pct"] == 50.0
    assert payload["summary"]["replay"]["adherence_rate_pct"] == 100.0


def test_quadrant_keys_always_present_with_zero_counts(env):
    dec = env.decisions({"ZZEN": "enter"})
    assert env.capture(decisions=dec, limit=1)[0] == 0
    _c, _o, _e, sid = env.replay()
    code, _o, err = env.reveal(sid, env.answers(env.blind(sid), {"ZZEN": "enter"}))
    assert code == 0, err
    summary = env.reveal_payload()["summary"]
    for side in ("original", "replay"):
        assert set(summary[side]["quadrants"]) == set(QUADRANTS)
    assert summary["original"]["quadrants"]["followed_favorable"] == 1
    assert sum(summary["original"]["quadrants"].values()) == 1


def test_rule_adherence_uses_recorded_spec(env, monkeypatch):
    assert env.capture()[0] == 0
    monkeypatch.setitem(dr.RULES, "vcp-checklist-v1", [])  # would make every case "enter"
    _c, _o, _e, sid = env.replay()
    assert env.reveal(sid, env.answers(env.blind(sid), ANSWERS_QUAD))[0] == 0
    cases = {c["symbol"]: c for c in env.reveal_payload()["cases"]}
    assert cases["ZZWT"]["rule_expected"] == "not_enter"
    assert cases["ZZWT"]["original"]["adherence"] == "followed"
    assert cases["ZZEN"]["rule_expected"] == "enter"


def test_market_gate_closed_makes_a_pass_followed(env):
    dec = env.decisions({"ZZEN": "pass", "ZZWT": "enter", "ZZDV": "wait", "ZZST": "enter"})
    assert env.capture(decisions=dec, gate="closed")[0] == 0
    _c, _o, _e, sid = env.replay()
    assert env.reveal(sid, env.answers(env.blind(sid), ANSWERS_QUAD))[0] == 0
    cases = {c["symbol"]: c for c in env.reveal_payload()["cases"]}
    assert cases["ZZEN"]["original"]["adherence"] == "followed"  # pass while the gate is closed
    assert cases["ZZST"]["original"]["adherence"] == "deviated"
    assert cases["ZZEN"]["market_gate"] == "closed"


def test_pending_outcome_excluded_from_quadrants(env):
    dec = env.decisions({"ZZEN": "enter"})
    assert env.capture(decisions=dec, limit=1)[0] == 0
    _c, _o, _e, sid = env.replay()
    prices = _load("prices_bull.json")
    prices["prices"]["ZZEN"] = prices["prices"]["ZZEN"][:5]  # only two future bars
    p = _write(env.tmp / "short.json", prices)
    code, _o, err = env.reveal(sid, env.answers(env.blind(sid), {"ZZEN": "enter"}), p)
    assert code == 0, err
    payload = env.reveal_payload()
    case = payload["cases"][0]
    assert case["exclusion_reason"] == "pending"
    assert case["path_class"] is None
    assert case["original"]["adherence"] == "followed"
    assert case["original"]["quadrant"] is None
    assert payload["summary"]["pending"] == 1
    assert payload["summary"]["excluded"]["pending"] == 1
    assert sum(payload["summary"]["original"]["quadrants"].values()) == 0


def test_missing_symbol_in_prices_is_pending(env):
    dec = env.decisions({"ZZEN": "enter", "ZZWT": "pass"})
    assert env.capture(decisions=dec, limit=2)[0] == 0
    _c, _o, _e, sid = env.replay()
    only_wt = {"prices": {"ZZWT": _load("prices_bull.json")["prices"]["ZZWT"]}}
    p = _write(env.tmp / "partial.json", only_wt)
    answers = env.answers(env.blind(sid), {"ZZEN": "enter", "ZZWT": "pass"})
    assert env.reveal(sid, answers, p)[0] == 0
    cases = {c["symbol"]: c for c in env.reveal_payload()["cases"]}
    assert cases["ZZEN"]["exclusion_reason"] == "pending"
    assert cases["ZZWT"]["exclusion_reason"] is None


def test_pending_case_can_be_scored_once_prices_mature(env):
    dec = env.decisions({"ZZEN": "enter"})
    assert env.capture(decisions=dec, limit=1)[0] == 0
    _c, _o, _e, sid = env.replay()
    answers = env.answers(env.blind(sid), {"ZZEN": "enter"})
    prices = _load("prices_bull.json")
    prices["prices"]["ZZEN"] = prices["prices"]["ZZEN"][:5]
    assert env.reveal(sid, answers, _write(env.tmp / "short.json", prices))[0] == 0
    assert env.reveal_payload()["cases"][0]["exclusion_reason"] == "pending"
    assert env.reveal(sid, answers)[0] == 0  # identical answers re-score
    payload = env.reveal_payload()
    assert payload["cases"][0]["exclusion_reason"] is None
    assert payload["cases"][0]["original"]["quadrant"] == "followed_favorable"
    assert payload["prices_changed_since_previous_reveal"] is True


def test_prices_hash_recorded_and_unchanged_flag(env):
    sid, _blind, payload, _cases = env.full_cycle()
    assert payload["prices_changed_since_previous_reveal"] is False
    assert re.fullmatch(r"[0-9a-f]{64}", payload["prices_json_sha256"])
    answers = env.tmp / "a.json"
    assert env.reveal(sid, answers)[0] == 0
    assert env.reveal_payload()["prices_changed_since_previous_reveal"] is False


def test_stop_hit_means_did_not_rally(env):
    dec = env.decisions({"ZZEN": "enter"})
    assert env.capture(decisions=dec, limit=1)[0] == 0
    _c, _o, _e, sid = env.replay()
    prices = _load("prices_bull.json")
    prices["prices"]["ZZEN"][4]["low"] = 94.0  # 2026-11-10 touches the 95 stop, closes still rally
    p = _write(env.tmp / "stop.json", prices)
    assert env.reveal(sid, env.answers(env.blind(sid), {"ZZEN": "enter"}), p)[0] == 0
    case = env.reveal_payload()["cases"][0]
    assert case["path"]["stop_hit"] is True
    assert case["path"]["forward_return_pct"] >= 5.0
    assert case["path_class"] == "did_not_rally"
    assert case["original"]["quadrant"] == "followed_adverse"


def test_unscorable_entry_price_excluded(env):
    def mutate(p):
        p["results"][0]["price"] = 0

    dec = env.decisions({"ZZEN": "enter"})
    assert env.capture(report=env.report(mutate=mutate), decisions=dec, limit=1)[0] == 0
    _c, _o, _e, sid = env.replay()
    assert env.reveal(sid, env.answers(env.blind(sid), {"ZZEN": "enter"}))[0] == 0
    payload = env.reveal_payload()
    assert payload["cases"][0]["exclusion_reason"] == "unscorable"
    assert payload["summary"]["excluded"]["unscorable"] == 1


def test_missing_stop_flags_and_disables_stop_check(env):
    def mutate(p):
        p["results"][0]["pivot_proximity"]["stop_loss_price"] = None

    dec = env.decisions({"ZZEN": "enter"})
    assert env.capture(report=env.report(mutate=mutate), decisions=dec, limit=1)[0] == 0
    _c, _o, _e, sid = env.replay()
    prices = _load("prices_bull.json")
    prices["prices"]["ZZEN"][4]["low"] = 50.0
    p = _write(env.tmp / "p.json", prices)
    assert env.reveal(sid, env.answers(env.blind(sid), {"ZZEN": "enter"}), p)[0] == 0
    case = env.reveal_payload()["cases"][0]
    assert case["stop_reference_missing"] is True
    assert case["path"]["stop_hit"] is False
    assert case["path_class"] == "rallied"


def test_as_of_unverified_when_close_differs_or_bar_missing(env):
    dec = env.decisions({"ZZEN": "enter"})
    assert env.capture(decisions=dec, limit=1)[0] == 0
    _c, _o, _e, sid = env.replay()
    answers = env.answers(env.blind(sid), {"ZZEN": "enter"})
    drift = _load("prices_bull.json")
    drift["prices"]["ZZEN"][2]["close"] = 104.0  # decision-day close 4% away from snapshot.price
    assert env.reveal(sid, answers, _write(env.tmp / "drift.json", drift))[0] == 0
    case = env.reveal_payload()["cases"][0]
    assert case["exclusion_reason"] == "as_of_unverified"
    assert case["original"]["quadrant"] is None
    nobar = _load("prices_bull.json")
    nobar["prices"]["ZZEN"] = nobar["prices"]["ZZEN"][3:]  # only future bars
    assert env.reveal(sid, answers, _write(env.tmp / "nobar.json", nobar))[0] == 0
    payload = env.reveal_payload()
    assert payload["cases"][0]["exclusion_reason"] == "as_of_unverified"
    assert payload["summary"]["excluded"]["as_of_unverified"] == 1


def _monday_store(env):
    """Capture on Friday, then rewrite the record as if it had been captured on Monday."""
    assert env.capture()[0] == 0
    cap = next((env.store / "captures").glob("vcp-*.json"))
    rec = json.loads(cap.read_text())
    rec["captured_at"] = "2026-11-09T15:00:00+00:00"  # Monday 10:00 ET
    rec["capture_sha256"] = dr.capture_hash(rec)
    store2 = env.tmp / "store2"
    dr.persist_capture(rec, store2)
    env.store = store2
    return rec


def test_capture_after_path_start_is_flagged_and_excluded(env):
    _monday_store(env)
    code, _o, err, sid = env.replay()
    assert code == 0, err
    assert env.reveal(sid, env.answers(env.blind(sid), ANSWERS_QUAD))[0] == 0
    payload = env.reveal_payload()
    assert all(c["exclusion_reason"] == "captured_after_path_start" for c in payload["cases"])
    assert payload["summary"]["excluded"]["captured_after_path_start"] == 4
    assert sum(payload["summary"]["original"]["quadrants"].values()) == 0


def test_capture_after_path_start_beats_maturity_pending(env):
    _monday_store(env)
    _c, _o, _e, sid = env.replay()
    prices = _load("prices_bull.json")
    for rows in prices["prices"].values():
        del rows[5:]  # a single future bar
    p = _write(env.tmp / "one.json", prices)
    assert env.reveal(sid, env.answers(env.blind(sid), ANSWERS_QUAD), p)[0] == 0
    payload = env.reveal_payload()
    assert {c["exclusion_reason"] for c in payload["cases"]} == {"captured_after_path_start"}


def test_sunday_capture_is_not_flagged(env):
    env.set_now(datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc))
    _sid, _blind, payload, _cases = env.full_cycle()
    assert all(c["exclusion_reason"] is None for c in payload["cases"])


def test_reveal_contains_disclaimer_in_json_and_markdown(env):
    env.full_cycle()
    payload = env.reveal_payload()
    assert payload["disclaimer"] == "Practice feedback, not a trade recommendation."
    md = max(
        env.out.glob("stockbee_setup_fluency_replay_reveal_*.md"),
        key=lambda p: p.stat().st_mtime_ns,
    )
    text = md.read_text()
    assert "Practice feedback, not a trade recommendation." in text
    assert "ZZEN" in text and "followed_favorable" in text


def test_reveal_summary_reports_population_and_sessions(env):
    _sid, _blind, payload, _cases = env.full_cycle()
    summary = payload["summary"]
    assert summary["population_size"] == 4
    assert summary["prior_sessions"] == 0
    assert summary["abandoned_sessions"] == 0
    assert summary["abandoned_before_this_session"] == 0


def test_abandoned_sessions_are_reported(env):
    assert env.capture()[0] == 0
    _c, _o, _e, sid1 = env.replay(seed=1)
    assert (
        env.run(
            "replay",
            "--abandon",
            sid1,
            "--reason",
            "skip",
            "--store-dir",
            env.store,
            "--output-dir",
            env.out,
        )[0]
        == 0
    )
    _c, _o, _e, sid2 = env.replay(seed=2)
    assert env.reveal(sid2, env.answers(env.blind(sid2), ANSWERS_QUAD))[0] == 0
    summary = env.reveal_payload()["summary"]
    assert summary["abandoned_sessions"] == 1
    assert summary["abandoned_before_this_session"] == 1
    assert summary["prior_sessions"] == 1


def test_reveal_with_different_answers_fails(env):
    sid, blind, _payload, _cases = env.full_cycle()
    changed = dict(ANSWERS_QUAD, ZZEN="wait")
    result = env.reveal(sid, env.answers(blind, changed, "changed.json"))
    assert_clean_failure(result)
    assert "answers already recorded" in result[2]


def test_reveal_same_answers_rescores_with_whitespace_variation(env):
    sid, blind, _payload, _cases = env.full_cycle()
    rows = json.loads((env.tmp / "a.json").read_text())
    rows.reverse()
    for row in rows:
        row["reason"] = "  " + row["reason"] + " "
    again = _write(env.tmp / "again.json", rows)
    assert env.reveal(sid, again)[0] == 0


@pytest.mark.parametrize("variant", ["missing", "unknown", "duplicate", "bad_enum", "empty_reason"])
def test_answers_must_cover_every_selected_case(env, variant):
    assert env.capture()[0] == 0
    _c, _o, _e, sid = env.replay()
    rows = json.loads(env.answers(env.blind(sid), ANSWERS_QUAD).read_text())
    if variant == "missing":
        rows = rows[:-1]
    elif variant == "unknown":
        rows[0]["case_id"] = "nope:ZZ"
    elif variant == "duplicate":
        rows[1] = dict(rows[0])
    elif variant == "bad_enum":
        rows[0]["decision"] = "buy"
    else:
        rows[0]["reason"] = " "
    bad = _write(env.tmp / "bad_answers.json", rows)
    assert_clean_failure(env.reveal(sid, bad))
    assert not (env.store / "sessions" / f"{sid}.answers.json").exists()
    assert not list(env.out.glob("stockbee_setup_fluency_replay_reveal_*"))


def test_reveal_unknown_session_and_abandoned_session_fail(env):
    assert env.capture()[0] == 0
    assert_clean_failure(env.reveal("replay-000000000000", env.tmp / "none.json"))
    _c, _o, _e, sid = env.replay()
    answers = env.answers(env.blind(sid), ANSWERS_QUAD)
    assert (
        env.run(
            "replay",
            "--abandon",
            sid,
            "--reason",
            "x",
            "--store-dir",
            env.store,
            "--output-dir",
            env.out,
        )[0]
        == 0
    )
    assert_clean_failure(env.reveal(sid, answers))


def test_abandon_unknown_session_fails(env):
    assert_clean_failure(
        env.run(
            "replay",
            "--abandon",
            "replay-123456789abc",
            "--reason",
            "x",
            "--store-dir",
            env.store,
            "--output-dir",
            env.out,
        )
    )


def test_cannot_abandon_after_reveal(env):
    sid, _b, _p, _c = env.full_cycle()
    assert_clean_failure(
        env.run(
            "replay",
            "--abandon",
            sid,
            "--reason",
            "x",
            "--store-dir",
            env.store,
            "--output-dir",
            env.out,
        )
    )


def test_identical_replay_request_collides_after_abandon(env):
    assert env.capture()[0] == 0
    _c, _o, _e, sid = env.replay(seed=5)
    assert (
        env.run(
            "replay",
            "--abandon",
            sid,
            "--reason",
            "x",
            "--store-dir",
            env.store,
            "--output-dir",
            env.out,
        )[0]
        == 0
    )
    again = env.replay(seed=5)  # same seed, size and population: same session id by design
    assert again[0] == 1 and "already exists" in again[2]


def test_selection_identical_after_reveal_with_include_seen(env):
    assert env.capture()[0] == 0
    _c, _o, _e, sid = env.replay(size=2, seed=9)
    first = _load(env.store / "sessions" / f"{sid}.json")["selected_case_ids"]
    blind = env.blind(sid)
    answers = env.answers(blind, {c["symbol"]: "pass" for c in blind["cases"]})
    assert env.reveal(sid, answers)[0] == 0
    ids = [c["case_id"] for c in dr.load_population(env.store, include_seen=True)]
    assert dr.select_cases(ids, 2, 9) == first


# ---------------------------------------------------------------------------
# Code review round 1 (#710): clean failures, no half-written state, mutation gaps
# ---------------------------------------------------------------------------


def _single_case(env, mapping=None):
    mapping = mapping or {"ZZEN": "enter"}
    assert env.capture(decisions=env.decisions(mapping), limit=len(mapping))[0] == 0
    _c, _o, _e, sid = env.replay()
    return sid, env.answers(env.blind(sid), mapping)


def _assert_nothing_revealed(env, sid):
    assert not (env.store / "sessions" / f"{sid}.answers.json").exists()
    assert not (env.store / "sessions" / f"{sid}.reveals.jsonl").exists()
    assert not list(env.out.glob("stockbee_setup_fluency_replay_reveal_*"))


def _assert_no_traceback(result):
    assert_clean_failure(result)
    assert "Traceback" not in result[2]


def test_date_guard_catches_next_day_and_mid_string_dates():
    dr.assert_no_future_dates({"x": "2026-11-06", "y": "T1 2026-11-06"}, "2026-11-06")
    for leaked in (
        "2026-11-07",
        "2026-11-07T10:00:00",
        "Technology 2026-11-20 earnings",
        "T1 2026-12-01",
    ):
        with pytest.raises(dr.ReplayError):
            dr.assert_no_future_dates({"x": leaked}, "2026-11-06")


def test_duplicate_symbol_in_report_rejected(env):
    def mutate(p):
        p["results"].insert(1, copy.deepcopy(p["results"][0]))

    result = env.capture(report=env.report(mutate=mutate))
    assert_clean_failure(result)
    assert "duplicate" in result[2]
    assert not (env.store / "captures").exists()


def test_result_row_without_symbol_fails_instead_of_shrinking_the_set(env):
    def mutate(p):
        p["results"].insert(2, {"price": 1, "sector": "x"})

    result = env.capture(report=env.report(mutate=mutate), limit=None)
    assert_clean_failure(result)
    assert "symbol" in result[2]
    assert not (env.store / "captures").exists()


def _tamper_setup(env):
    assert env.capture()[0] == 0
    path = next((env.store / "captures").glob("vcp-*.json"))
    return path, json.loads(path.read_text())


def _write_ledger_for(env, rec):
    entry = {
        "capture_id": rec["capture_id"],
        "capture_sha256": rec["capture_sha256"],
        "captured_at": rec["captured_at"],
    }
    (env.store / "captures" / "ledger.jsonl").write_text(json.dumps(entry) + "\n")


def _assert_integrity_failure(env):
    result = env.replay()
    assert result[0] == 1 and "integrity" in result[2]


def test_snapshot_hash_layer_detects_alone(env):
    path, rec = _tamper_setup(env)
    rec["cases"][0]["snapshot"]["price"] = 1.0
    rec["capture_sha256"] = dr.capture_hash(rec)  # capture and ledger hashes stay consistent
    path.write_text(json.dumps(rec))
    _write_ledger_for(env, rec)
    _assert_integrity_failure(env)


def test_capture_hash_layer_detects_alone(env):
    path, rec = _tamper_setup(env)
    rec["cases"][0]["decision"] = "pass"  # embedded hash is now stale
    path.write_text(json.dumps(rec))
    _write_ledger_for(env, rec)  # ledger matches the stale embedded hash
    _assert_integrity_failure(env)


def test_ledger_hash_layer_detects_alone(env):
    path, rec = _tamper_setup(env)
    rec["cases"][0]["decision"] = "pass"
    rec["capture_sha256"] = dr.capture_hash(rec)  # file is self-consistent; ledger is stale
    path.write_text(json.dumps(rec))
    _assert_integrity_failure(env)


@pytest.mark.parametrize("last_close,expected", [(105.0, "rallied"), (104.99, "did_not_rally")])
def test_rally_threshold_boundary(env, last_close, expected):
    sid, answers = _single_case(env)
    prices = _load("prices_bull.json")
    prices["prices"]["ZZEN"][-1]["close"] = last_close
    p = _write(env.tmp / "edge.json", prices)
    assert env.reveal(sid, answers, p)[0] == 0
    case = env.reveal_payload()["cases"][0]
    assert case["path_class"] == expected


def test_seen_before_cases_are_excluded_from_replay_tallies(env):
    assert env.capture()[0] == 0
    _c, _o, _e, sid = env.replay(seed=1)
    assert env.reveal(sid, env.answers(env.blind(sid), ANSWERS_QUAD))[0] == 0
    _c, _o, _e, sid2 = env.replay(seed=2, extra=["--include-seen"])
    assert env.reveal(sid2, env.answers(env.blind(sid2), ANSWERS_QUAD, "a2.json"))[0] == 0
    summary = env.reveal_payload()["summary"]
    assert sum(summary["original"]["quadrants"].values()) == 4
    assert sum(summary["replay"]["quadrants"].values()) == 0


@pytest.mark.parametrize(
    "kind", ["binary", "bad_date", "slash_date", "iso_week_date", "bad_date_other_symbol"]
)
def test_reveal_bad_prices_fail_cleanly_without_writing(env, kind):
    sid, answers = _single_case(env)
    if kind == "binary":
        bad = env.tmp / "bin.json"
        bad.write_bytes(b"\xff\xfe\x00bad")
    else:
        prices = _load("prices_bull.json")
        symbol = "ZZPS" if kind == "bad_date_other_symbol" else "ZZEN"
        bad_value = {"slash_date": "2026/11/09", "iso_week_date": "2026-W45-1"}.get(
            kind, "abcdefghij"
        )
        prices["prices"][symbol][3]["date"] = bad_value
        bad = _write(env.tmp / "bad.json", prices)
    _assert_no_traceback(env.reveal(sid, answers, bad))
    _assert_nothing_revealed(env, sid)
    assert env.reveal(sid, answers)[0] == 0  # the session is still usable


@pytest.mark.parametrize("which", ["decisions", "answers"])
def test_non_utf8_inputs_fail_cleanly(env, which):
    bad = env.tmp / "bad.bin"
    bad.write_bytes(b"\xff\xfe\x00bad")
    if which == "decisions":
        _assert_no_traceback(env.capture(decisions=bad))
        return
    sid, _answers = _single_case(env)
    _assert_no_traceback(env.reveal(sid, bad))
    _assert_nothing_revealed(env, sid)


def test_lone_surrogate_in_reason_fails_cleanly(env):
    rows = [
        {"symbol": s, "decision": "enter", "reason": "\ud800 x"}
        for s in ("ZZEN", "ZZWT", "ZZDV", "ZZST")
    ]
    _assert_no_traceback(env.capture(decisions=_write(env.tmp / "sur.json", rows)))
    assert not (env.store / "captures").exists()


def test_unwritable_output_dir_leaves_no_blocking_session(env):
    assert env.capture()[0] == 0
    blocker = env.tmp / "blocker"
    blocker.write_text("not a directory")
    result = env.run(
        "replay", "--sample-size", 2, "--seed", 1, "--store-dir", env.store, "--output-dir", blocker
    )
    _assert_no_traceback(result)
    sessions = env.store / "sessions"
    assert not sessions.exists() or not list(sessions.glob("replay-*"))
    assert env.replay(seed=1)[0] == 0  # nothing is pending


def test_unwritable_output_dir_on_reveal_writes_nothing(env):
    sid, answers = _single_case(env)
    blocker = env.tmp / "blocker"
    blocker.write_text("not a directory")
    result = env.run(
        "reveal",
        "--session-id",
        sid,
        "--answers",
        answers,
        "--prices-json",
        FIX / "prices_bull.json",
        "--store-dir",
        env.store,
        "--output-dir",
        blocker,
    )
    _assert_no_traceback(result)
    assert not (env.store / "sessions" / f"{sid}.answers.json").exists()


@pytest.mark.parametrize("payload", [{}, [1, 2, 3], "hello", "foreign"])
def test_prices_without_any_session_symbol_rejected_before_writing(env, payload):
    sid, answers = _single_case(env)
    if payload == "foreign":
        payload = {"prices": {"QQQQ": _load("prices_bull.json")["prices"]["ZZEN"]}}
    foreign = _write(env.tmp / "foreign.json", payload)
    _assert_no_traceback(env.reveal(sid, answers, foreign))
    _assert_nothing_revealed(env, sid)
    assert env.reveal(sid, answers)[0] == 0  # the cases were not burned


def test_truncated_ledger_tail_is_repairable(env):
    assert env.capture()[0] == 0
    ledger = env.store / "captures" / "ledger.jsonl"
    with open(ledger, "a") as handle:
        handle.write('{"capture_id": "x')
    result = env.replay()
    assert result[0] == 1 and "reconcile-ledger" in result[2]
    code, _out, err = env.run("reconcile-ledger", "--store-dir", env.store)
    assert code == 0, err
    assert [json.loads(line) for line in ledger.read_text().splitlines()]
    assert env.replay()[0] == 0


def test_truncated_real_ledger_entry_is_readded_from_the_capture(env):
    assert env.capture()[0] == 0
    ledger = env.store / "captures" / "ledger.jsonl"
    ledger.write_text(ledger.read_text()[:30])
    assert env.replay()[0] == 1
    assert env.run("reconcile-ledger", "--store-dir", env.store)[0] == 0
    assert len(ledger.read_text().splitlines()) == 1
    assert env.replay()[0] == 0


def test_corrupt_ledger_middle_line_is_not_repaired(env):
    assert env.capture()[0] == 0
    other = env.report("r2.json", mutate=lambda p: p["metadata"].update(universe="other"))
    assert env.capture(report=other)[0] == 0
    ledger = env.store / "captures" / "ledger.jsonl"
    first, second = ledger.read_text().splitlines()
    ledger.write_text(f"{first}\n{{garbage\n{second}\n")
    result = env.run("reconcile-ledger", "--store-dir", env.store)
    assert_clean_failure(result)
    assert "restore" in result[2]


def test_reconcile_will_not_drop_a_line_while_a_capture_fails_verification(env):
    path, rec = _tamper_setup(env)
    with open(env.store / "captures" / "ledger.jsonl", "a") as handle:
        handle.write('{"capture_id": "x')
    rec["cases"][0]["decision"] = "pass"
    path.write_text(json.dumps(rec))
    assert_clean_failure(env.run("reconcile-ledger", "--store-dir", env.store))
    assert (env.store / "captures" / "ledger.jsonl").read_text().endswith('{"capture_id": "x')


def test_missing_entry_ready_is_unknown_not_a_mismatch(env):
    def mutate(p):
        for row in p["results"]:
            row.pop("entry_ready", None)

    assert env.capture(report=env.report(mutate=mutate))[0] == 0
    rec = json.loads(next((env.store / "captures").glob("vcp-*.json")).read_text())
    assert all(c["rule_mismatch"] is None for c in rec["cases"])
    assert all(c["screener_entry_ready"] is None for c in rec["cases"])


def test_entry_ready_is_kept_in_capture_but_hidden_from_blind_view(env):
    assert env.capture()[0] == 0
    rec = json.loads(next((env.store / "captures").glob("vcp-*.json")).read_text())
    assert rec["cases"][0]["snapshot"]["entry_ready"] is True
    _c, _o, _e, sid = env.replay()
    for suffix in ("json", "md"):
        text = (env.out / f"stockbee_setup_fluency_replay_blind_{sid}.{suffix}").read_text()
        assert "entry_ready" not in text


def test_weekend_report_cannot_be_captured_twice_under_different_dates(env):
    def saturday(p):
        p["metadata"]["generated_at"] = "2026-11-07 12:00:00"

    env.set_now(datetime(2026, 11, 7, 18, 0, tzinfo=timezone.utc))  # Saturday 13:00 ET
    report = env.report(mutate=saturday)
    assert env.capture(report=report, extra=["--decision-date", "2026-11-07"])[0] == 0
    again = env.capture(report=report, extra=["--decision-date", "2026-11-06"])
    assert_clean_failure(again)
    assert "already exists" in again[2]
    assert len(list((env.store / "captures").glob("vcp-*.json"))) == 1


@pytest.mark.parametrize(
    "extra",
    [
        ["--abandon", "replay-0123456789ab", "--reason", "x", "--sample-size", "3"],
        ["--abandon", "replay-0123456789ab", "--reason", "x", "--seed", "1"],
        ["--abandon", "replay-0123456789ab", "--reason", "x", "--include-seen"],
        [
            "--abandon",
            "replay-0123456789ab",
            "--reason",
            "x",
            "--decided-on-or-before",
            "2026-11-06",
        ],
        ["--abandon", "replay-0123456789ab"],
        ["--sample-size", "3", "--reason", "x"],
    ],
)
def test_replay_incompatible_arguments_exit_2(tmp_path, extra):
    with pytest.raises(SystemExit) as exc:
        dr.main(["replay", "--store-dir", str(tmp_path / "s"), *extra])
    assert exc.value.code == 2


def test_naive_generated_at_without_tz_override_uses_system_zone(monkeypatch):
    monkeypatch.setattr(dr, "_local_tz", lambda: None)
    assert dr._parse_generated_at("2026-11-06 18:30:00").tzinfo is not None


# ---------------------------------------------------------------------------
# Code review round 2 (#710)
# ---------------------------------------------------------------------------


def _blind_files(env):
    return list(env.out.glob("stockbee_setup_fluency_replay_blind_*")) if env.out.exists() else []


def test_failed_session_write_removes_the_blind_files(env, monkeypatch):
    assert env.capture()[0] == 0
    real = dr._write_once

    def failing(path, payload):
        if "sessions" in Path(path).parts:
            raise PermissionError(13, "Permission denied", str(path))
        return real(path, payload)

    monkeypatch.setattr(dr, "_write_once", failing)
    result = env.replay(seed=4)
    assert result[0] == 1 and "ERROR:" in result[2] and "Traceback" not in result[2]
    assert _blind_files(env) == []


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="needs non-root POSIX")
def test_unwritable_sessions_dir_leaves_no_blind_view(env):
    assert env.capture()[0] == 0
    sessions = env.store / "sessions"
    sessions.mkdir()
    sessions.chmod(0o500)
    try:
        result = env.replay(seed=4)
    finally:
        sessions.chmod(0o700)
    assert result[0] == 1 and "ERROR:" in result[2]
    assert _blind_files(env) == []
    assert env.replay(seed=4)[0] == 0  # nothing was left behind that blocks a retry


def test_reconcile_checks_every_lag_before_touching_the_ledger(env):
    assert env.capture()[0] == 0
    other = env.report("r2.json", mutate=lambda p: p["metadata"].update(universe="other"))
    assert env.capture(report=other)[0] == 0
    ledger = env.store / "captures" / "ledger.jsonl"
    first, second = ledger.read_text().splitlines()
    # the second capture is now past its lag window, and its ledger line is cut off
    victim = env.store / "captures" / f"{json.loads(second)['capture_id']}.json"
    rec = json.loads(victim.read_text())
    rec["captured_at"] = "2026-11-09T15:00:00+00:00"
    rec["capture_sha256"] = dr.capture_hash(rec)
    victim.write_text(json.dumps(rec))
    ledger.write_text(first + "\n" + second[:25])
    before = ledger.read_bytes()
    result = env.run("reconcile-ledger", "--store-dir", env.store)
    assert_clean_failure(result)
    assert "backup" in result[2]
    assert ledger.read_bytes() == before


def test_parse_generated_at_uses_the_offset_in_force_on_that_date(monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is POSIX only")
    monkeypatch.setattr(dr, "_local_tz", lambda: None)
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    try:
        et = ZoneInfo("America/New_York")
        summer = dr._parse_generated_at("2026-07-10 20:30:00").astimezone(et)
        winter = dr._parse_generated_at("2026-12-10 21:30:00").astimezone(et)
    finally:
        monkeypatch.undo()
        time.tzset()
    assert (summer.date().isoformat(), summer.hour) == ("2026-07-10", 23)
    assert (winter.date().isoformat(), winter.hour) == ("2026-12-11", 0)


def test_partial_prices_warn_with_the_pending_case_count(env):
    dec = env.decisions({"ZZEN": "enter", "ZZWT": "pass"})
    assert env.capture(decisions=dec, limit=2)[0] == 0
    _c, _o, _e, sid = env.replay()
    only_wt = {"prices": {"ZZWT": _load("prices_bull.json")["prices"]["ZZWT"]}}
    answers = env.answers(env.blind(sid), {"ZZEN": "enter", "ZZWT": "pass"})
    code, _out, err = env.reveal(sid, answers, _write(env.tmp / "partial.json", only_wt))
    assert code == 0
    assert "WARNING: prices JSON has no bars for 1 of 2 cases" in err
    # a complete file gives no warning
    assert "WARNING" not in env.reveal(sid, answers)[2]


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def test_main_requires_a_subcommand_and_exposes_help(capsys):
    with pytest.raises(SystemExit) as exc:
        dr.main([])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        dr.main(["--help"])
    assert exc.value.code == 0
    assert "capture" in capsys.readouterr().out


def test_now_is_timezone_aware():
    assert dr._now().tzinfo is not None


def test_unexpected_os_error_is_reported_without_traceback(monkeypatch, capsys):
    def boom(_args):
        raise PermissionError(13, "Permission denied", "/some/path")

    monkeypatch.setitem(dr.COMMANDS, "reconcile-ledger", boom)
    assert dr.main(["reconcile-ledger", "--store-dir", "x"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("ERROR:") and "Traceback" not in err
