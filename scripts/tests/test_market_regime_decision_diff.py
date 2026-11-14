"""Pure-logic tests for the market-regime-daily decision diff (Issue #709)."""

import copy
import itertools
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import market_regime_decision_diff as dd  # noqa: E402

PREV_EVAL = "2026-01-15T13:08:00+00:00"
TODAY_EVAL = "2026-01-16T13:08:00+00:00"
PREV_AS_OF = "2026-01-14T21:00:00+00:00"
TODAY_AS_OF = "2026-01-15T21:00:00+00:00"


def condition(metric="breadth.composite_score", comparator="lt", threshold=60, **extra):
    base = {
        "id": "c1",
        "label": "Breadth falls below 60",
        "metric": metric,
        "comparator": comparator,
        "threshold": threshold,
    }
    base.update(extra)
    return base


def recorded(value=66.1, **kwargs):
    cond = condition(**kwargs)
    cond["value_at_decision"] = value
    cond["holds_at_decision"] = (
        None if value is None else dd.holds(value, cond["comparator"], cond["threshold"])
    )
    return cond


def prev_ctx(kinds=("breadth", "uptrend"), as_of=PREV_AS_OF, inputs=None):
    return {
        "data_as_of": {"evaluation_at": PREV_EVAL, "inputs": {k: as_of for k in kinds}},
        "exposure_inputs_provided": inputs if inputs is not None else ["breadth", "uptrend"],
    }


def today_side(values=None, kinds=("breadth", "uptrend"), as_of=TODAY_AS_OF, **overrides):
    base_values = {
        "breadth.composite_score": 49.0,
        "uptrend.composite_score": 70.0,
        "top_risk.composite_score": None,
        "exposure.recommendation": "REDUCE_ONLY",
    }
    base_values.update(values or {})
    side = {
        "evaluation_at": TODAY_EVAL,
        "values": base_values,
        "as_of": {k: as_of for k in kinds},
        "max_age_days": {k: 2 for k in kinds},
        "exposure_inputs": ["breadth", "uptrend"],
        "skipped": [k for k in dd.KINDS if k not in kinds],
        "unevaluated": [],
    }
    side.update(overrides)
    return side


# ---------------------------------------------------------------- holds


@pytest.mark.parametrize(
    "value,cmp,threshold,expected",
    [
        (59, "lt", 60, True),
        (60, "lt", 60, False),
        (60, "le", 60, True),
        (61, "gt", 60, True),
        (60, "ge", 60, True),
        (59.9, "ge", 60, False),
        ("REDUCE_ONLY", "eq", "REDUCE_ONLY", True),
        ("REDUCE_ONLY", "ne", "REDUCE_ONLY", False),
        ("NEW_ENTRY_ALLOWED", "ne", "REDUCE_ONLY", True),
    ],
)
def test_holds(value, cmp, threshold, expected):
    assert dd.holds(value, cmp, threshold) is expected


# ------------------------------------------------------- classify: changed


@pytest.mark.parametrize(
    "prev_value,today_value,comparator,threshold",
    [
        (66.1, 49.0, "lt", 60),  # crossing downwards into the condition
        (49.0, 66.1, "lt", 60),  # crossing back out of the condition
        (38.0, 52.0, "ge", 50),
        (52.0, 38.0, "ge", 50),
    ],
)
def test_classify_changed_in_both_directions(prev_value, today_value, comparator, threshold):
    metric = "top_risk.composite_score"
    kinds = ("breadth", "uptrend", "top_risk")
    out = dd.classify(
        recorded(prev_value, metric=metric, comparator=comparator, threshold=threshold),
        prev_ctx(kinds, inputs=["breadth", "uptrend", "top_risk"]),
        today_side({metric: today_value}, kinds=kinds),
    )
    assert out["status"] == "changed"
    assert out["reason"] is None
    assert out["previous"]["value"] == prev_value
    assert out["today"]["value"] == today_value
    assert out["delta"] == pytest.approx(today_value - prev_value)


def test_classify_unchanged_requires_same_truth_value_and_fresh_inputs():
    out = dd.classify(recorded(70.0), prev_ctx(), today_side({"breadth.composite_score": 65.0}))
    assert out["status"] == "unchanged"
    assert out["previous"]["holds"] is False and out["today"]["holds"] is False


def test_classify_recommendation_eq_ne():
    cond = recorded(
        "REDUCE_ONLY", metric="exposure.recommendation", comparator="eq", threshold="REDUCE_ONLY"
    )
    changed = dd.classify(
        cond, prev_ctx(), today_side({"exposure.recommendation": "NEW_ENTRY_ALLOWED"})
    )
    same = dd.classify(cond, prev_ctx(), today_side({"exposure.recommendation": "REDUCE_ONLY"}))
    assert changed["status"] == "changed"
    assert same["status"] == "unchanged"
    assert changed["delta"] is None


# -------------------------------------- classify: never unchanged when unsure

STALE_CASES = {
    "no_baseline_value": lambda: (recorded(None), prev_ctx(), today_side()),
    "input_missing_today": lambda: (
        recorded(38.0, metric="top_risk.composite_score", comparator="ge", threshold=50),
        prev_ctx(("breadth", "uptrend", "top_risk"), inputs=["breadth", "uptrend", "top_risk"]),
        today_side(),
    ),
    "input_as_of_unknown_prev": lambda: (
        recorded(),
        {"data_as_of": {"evaluation_at": PREV_EVAL, "inputs": {}}, "exposure_inputs_provided": []},
        today_side(),
    ),
    "input_as_of_unknown_today": lambda: (recorded(), prev_ctx(), today_side() | {"as_of": {}}),
    "input_not_refreshed_equal": lambda: (recorded(), prev_ctx(), today_side(as_of=PREV_AS_OF)),
    "input_not_refreshed_older": lambda: (
        recorded(),
        prev_ctx(),
        today_side(as_of="2026-01-13T21:00:00+00:00"),
    ),
    "input_stale": lambda: (
        recorded(),
        prev_ctx(),
        today_side(max_age_days={"breadth": 0, "uptrend": 0}),
    ),
    "input_set_changed": lambda: (
        recorded(
            "REDUCE_ONLY",
            metric="exposure.recommendation",
            comparator="eq",
            threshold="REDUCE_ONLY",
        ),
        prev_ctx(("breadth", "uptrend", "top_risk"), inputs=["breadth", "uptrend", "top_risk"]),
        today_side(),
    ),
    "invalid_value_nan": lambda: (
        recorded(),
        prev_ctx(),
        today_side({"breadth.composite_score": math.nan}),
    ),
    "invalid_value_type": lambda: (
        recorded(),
        prev_ctx(),
        today_side({"breadth.composite_score": "49"}),
    ),
}


EXPECTED_REASON = {
    "input_as_of_unknown_prev": "input_as_of_unknown",
    "input_as_of_unknown_today": "input_as_of_unknown",
    "input_not_refreshed_equal": "input_not_refreshed",
    "input_not_refreshed_older": "input_not_refreshed",
    "invalid_value_nan": "invalid_value",
    "invalid_value_type": "invalid_value",
}


@pytest.mark.parametrize("case", sorted(STALE_CASES))
def test_missing_or_stale_input_is_never_unchanged(case):
    cond, previous, side = STALE_CASES[case]()
    out = dd.classify(cond, previous, side)
    assert out["status"] == "not_evaluable"
    assert out["reason"] == EXPECTED_REASON.get(case, case)
    assert out["delta"] is None


def test_missing_optional_step_carries_detail():
    cond, previous, side = STALE_CASES["input_missing_today"]()
    out = dd.classify(cond, previous, side)
    assert out["reason"] == "input_missing_today"
    assert out["detail"] == "optional_step_not_selected"


def test_property_unchanged_only_when_every_predicate_holds():
    """Grid over presence, freshness and value validity: unchanged needs all of them."""
    seen_unchanged = 0
    for prev_present, today_present, as_of_known, fresh, in_age, value_ok in itertools.product(
        [True, False], repeat=6
    ):
        cond = recorded(70.0 if prev_present else None)
        previous = prev_ctx()
        side = today_side(
            {
                "breadth.composite_score": (65.0 if value_ok else math.inf)
                if today_present
                else None
            },
            as_of=TODAY_AS_OF if fresh else PREV_AS_OF,
            max_age_days={"breadth": 2 if in_age else 0, "uptrend": 2 if in_age else 0},
        )
        if not as_of_known:
            side["as_of"] = {}
        out = dd.classify(cond, previous, side)
        everything = (
            prev_present and today_present and as_of_known and fresh and in_age and value_ok
        )
        if out["status"] == "unchanged":
            seen_unchanged += 1
            assert everything
        if everything:
            assert out["status"] == "unchanged"
    assert seen_unchanged == 1


# ------------------------------------------------------ conditions validator


def payload(*conditions):
    return {"schema_version": 1, "conditions": list(conditions)}


def test_valid_conditions_round_trip():
    parsed = dd.validate_conditions(
        payload(
            condition(),
            condition(
                id="c2", metric="exposure.recommendation", comparator="eq", threshold="REDUCE_ONLY"
            ),
        )
    )
    assert [c["id"] for c in parsed] == ["c1", "c2"]


def test_empty_conditions_list_is_explicit_and_valid():
    assert dd.validate_conditions(payload()) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(metric="breadth.components.momentum"),
        lambda c: c.update(metric="unknown.metric"),
        lambda c: c.update(comparator="between"),
        lambda c: c.update(comparator="eq"),
        lambda c: c.update(threshold=True),
        lambda c: c.update(threshold=math.nan),
        lambda c: c.update(threshold="60"),
        lambda c: c.update(id="Bad Id"),
        lambda c: c.update(id=""),
        lambda c: c.update(label=""),
        lambda c: c.update(label="x" * 201),
        lambda c: c.update(label="tab\tinside"),
        lambda c: c.update(extra=1),
        lambda c: c.pop("label"),
    ],
)
def test_invalid_condition_is_rejected_with_fixed_message(mutate):
    bad = condition()
    mutate(bad)
    with pytest.raises(dd.ConditionsError) as err:
        dd.validate_conditions(payload(bad))
    assert "Bad Id" not in str(err.value) and "tab" not in str(err.value)


def test_recommendation_threshold_rules():
    ok = condition(metric="exposure.recommendation", comparator="ne", threshold="CASH_PRIORITY")
    assert dd.validate_conditions(payload(ok))
    for bad in (
        condition(metric="exposure.recommendation", comparator="eq", threshold=5),
        condition(metric="exposure.recommendation", comparator="lt", threshold="REDUCE_ONLY"),
        condition(metric="exposure.recommendation", comparator="eq", threshold="MAYBE"),
    ):
        with pytest.raises(dd.ConditionsError):
            dd.validate_conditions(payload(bad))


def test_duplicate_ids_too_many_and_envelope_rules():
    with pytest.raises(dd.ConditionsError):
        dd.validate_conditions(payload(condition(), condition()))
    with pytest.raises(dd.ConditionsError):
        dd.validate_conditions(payload(*[condition(id=f"c{i}") for i in range(21)]))
    assert len(dd.validate_conditions(payload(*[condition(id=f"c{i}") for i in range(20)]))) == 20
    for bad in (
        {"conditions": []},
        {"schema_version": 2, "conditions": []},
        {"schema_version": 1, "conditions": [], "extra": 1},
        [],
        "x",
    ):
        with pytest.raises(dd.ConditionsError):
            dd.validate_conditions(bad)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version": 1, "conditions": [], "conditions": []}',  # duplicate key
        b'{"schema_version": 1, "conditions": [{"id": "a", "label": "x", "metric": '
        b'"breadth.composite_score", "comparator": "lt", "threshold": NaN}]}',
        b"[" * 100000,  # RecursionError
        b"\xff\xfe",
        b"not json",
    ],
)
def test_parse_conditions_rejects_malformed_bytes(raw):
    with pytest.raises(dd.ConditionsError):
        dd.parse_conditions(raw)


def test_recorded_conditions_validator_rechecks_extras_and_printable_labels():
    good = [recorded()]
    assert dd.validate_recorded_conditions(good) == good
    assert dd.validate_recorded_conditions(None) is None
    forged = copy.deepcopy(good)
    forged[0]["label"] = "bad\x07label"
    with pytest.raises(dd.ConditionsError):
        dd.validate_recorded_conditions(forged)
    forged = copy.deepcopy(good)
    forged[0]["value_at_decision"] = "oops"
    with pytest.raises(dd.ConditionsError):
        dd.validate_recorded_conditions(forged)
    forged = copy.deepcopy(good)
    del forged[0]["holds_at_decision"]
    with pytest.raises(dd.ConditionsError):
        dd.validate_recorded_conditions(forged)


# ------------------------------------------------------- decision record


def test_record_conditions_stamps_value_and_holds_at_decision():
    side = today_side({"breadth.composite_score": 52.0})
    rec = dd.decision_record([condition()], side)
    assert rec["revisit_conditions"][0]["value_at_decision"] == 52.0
    assert rec["revisit_conditions"][0]["holds_at_decision"] is True
    assert rec["data_as_of"] == {
        "evaluation_at": TODAY_EVAL,
        "inputs": {"breadth": TODAY_AS_OF, "uptrend": TODAY_AS_OF},
    }
    assert rec["unevaluated"] == side["unevaluated"]


def test_decision_record_without_conditions_is_null_and_empty_list_is_kept():
    side = today_side()
    assert dd.decision_record(None, side)["revisit_conditions"] is None
    assert dd.decision_record([], side)["revisit_conditions"] == []


def test_skipped_metric_records_none_baseline():
    rec = dd.decision_record(
        [condition(id="t", metric="top_risk.composite_score", comparator="ge", threshold=50)],
        today_side(),
    )
    assert rec["revisit_conditions"][0]["value_at_decision"] is None
    assert rec["revisit_conditions"][0]["holds_at_decision"] is None


def test_make_side_derives_unevaluated_and_as_of():
    by_kind = {
        "breadth": {"composite": {"composite_score": 49.0}},
        "uptrend": {"composite": {"composite_score": 70.0}},
    }
    fixtures = {
        "breadth": {"as_of": TODAY_AS_OF, "max_age_days": 2},
        "uptrend": {"as_of": TODAY_AS_OF, "max_age_days": 2},
        "top_risk": {"as_of": TODAY_AS_OF, "max_age_days": 2},
    }
    result = {
        "recommendation": "REDUCE_ONLY",
        "inputs_provided": ["breadth", "uptrend"],
        "inputs_missing": ["top_risk", "regime", "ftd"],
    }
    side = dd.make_side(TODAY_EVAL, fixtures, by_kind, result)
    assert side["skipped"] == ["top_risk"]
    assert side["as_of"] == {"breadth": TODAY_AS_OF, "uptrend": TODAY_AS_OF}
    assert side["values"]["top_risk.composite_score"] is None
    assert side["unevaluated"] == [
        {"input": "ftd", "reason": "not_provided_by_this_workflow"},
        {"input": "regime", "reason": "not_provided_by_this_workflow"},
        {"input": "top_risk", "reason": "optional_step_not_selected"},
    ]


# --------------------------------------------------------- snapshot + diff


def loaded_snapshot(conditions=None):
    return {
        "run_id": "00000000-0000-4000-8000-000000000002",
        "selection": {"mode": "explicit", "candidates": 1, "skipped_unreadable": 0},
        "previous": {
            "status": "loaded",
            "message": dd.STATUS_MESSAGES["loaded"][0],
            "run_id": "00000000-0000-4000-8000-000000000001",
            "fixture_set": "day-1",
            "evaluation_at": PREV_EVAL,
            "decision": "restrict",
            "decision_at": "2026-01-15T13:30:00+00:00",
            "journal_schema_version": 2,
            "manifest_sha256": "a" * 64,
            "journal_sha256": "b" * 64,
            "data_as_of": {
                "evaluation_at": PREV_EVAL,
                "inputs": {"breadth": PREV_AS_OF, "uptrend": PREV_AS_OF},
            },
            "exposure_inputs_provided": ["breadth", "uptrend"],
            "revisit_conditions": conditions,
        },
    }


def test_build_diff_summary_columns_and_first_run_shape():
    conds = [
        recorded(66.1, id="breadth-weakens"),
        recorded(70.0, id="uptrend-weakens", metric="uptrend.composite_score"),
        recorded(
            38.0,
            id="top-risk-rises",
            metric="top_risk.composite_score",
            comparator="ge",
            threshold=50,
        ),
    ]
    side = today_side({"breadth.composite_score": 49.0, "uptrend.composite_score": 71.0})
    diff = dd.build_decision_diff(loaded_snapshot(conds)["run_id"], loaded_snapshot(conds), side)
    assert diff["first_run"] is False and diff["read_only"] is True and diff["fictional"] is True
    assert diff["summary"] == {"changed": 1, "unchanged": 1, "not_evaluable": 1}
    by_id = {c["id"]: c for c in diff["conditions"]}
    assert by_id["breadth-weakens"]["status"] == "changed"
    assert by_id["uptrend-weakens"]["status"] == "unchanged"
    assert by_id["top-risk-rises"]["reason"] == "input_missing_today"
    assert diff["columns"]["previous_decision"]["decision"] == "restrict"
    assert diff["columns"]["changed_today"] == ["breadth-weakens"]
    items = diff["columns"]["confirm"]
    assert {"item": "condition", "id": "breadth-weakens", "why": "changed"} in items
    assert any(i.get("id") == "top-risk-rises" and i["why"] == "not_evaluable" for i in items)
    assert items[-1]["item"] == "posture"
    json.dumps(diff, allow_nan=False)


@pytest.mark.parametrize("conds", [None, []])
def test_build_diff_notes_missing_revisit_conditions(conds):
    diff = dd.build_decision_diff("r", loaded_snapshot(conds), today_side())
    assert diff["conditions"] == []
    assert any(i["item"] == "no_revisit_conditions" for i in diff["columns"]["confirm"])


def test_build_diff_flags_condition_already_met_at_decision():
    diff = dd.build_decision_diff("r", loaded_snapshot([recorded(50.0, id="met")]), today_side())
    assert {"item": "condition_already_met_at_decision", "id": "met"} in diff["columns"]["confirm"]


def test_build_diff_first_run_for_unusable_previous():
    snapshot = {
        "run_id": "r",
        "selection": {"mode": "explicit", "candidates": 1, "skipped_unreadable": 0},
        "previous": {"status": "not_found", "message": dd.STATUS_MESSAGES["not_found"][0]},
    }
    diff = dd.build_decision_diff("r", snapshot, today_side())
    assert diff["first_run"] is True
    assert diff["conditions"] == [] and diff["columns"]["previous_decision"] is None
    assert diff["columns"]["confirm"][0] == {
        "item": "first_run",
        "why": dd.STATUS_MESSAGES["not_found"][0],
    }
    assert diff["columns"]["confirm"][-1]["item"] == "posture"


def test_validate_snapshot_accepts_good_and_rejects_forged():
    snap = loaded_snapshot([recorded()])
    dd.validate_snapshot(snap, snap["run_id"])
    with pytest.raises(dd.SnapshotError):
        dd.validate_snapshot(snap, "another-run")
    for mutate in (
        lambda s: s["previous"].update(status="mystery"),
        lambda s: s["previous"].update(message="free text"),
        lambda s: s["previous"].update(decision="yolo"),
        lambda s: s["previous"]["revisit_conditions"][0].update(label="bad\x07"),
        lambda s: s.update(extra=1),
        lambda s: s["selection"].update(mode="scan"),
    ):
        forged = copy.deepcopy(snap)
        mutate(forged)
        with pytest.raises(dd.SnapshotError):
            dd.validate_snapshot(forged, snap["run_id"])


# ---------------------------------------------------- review round 1 additions


def test_id_with_trailing_newline_is_rejected():
    with pytest.raises(dd.ConditionsError):
        dd.validate_conditions(payload(condition(id="a\n")))


@pytest.mark.parametrize("big", [10**400, -(10**400)])
def test_huge_integer_threshold_gives_fixed_conditions_error(big):
    raw = json.dumps(payload(condition(threshold=big))).encode()
    with pytest.raises(dd.ConditionsError):
        dd.parse_conditions(raw)


@pytest.mark.parametrize("version", [1.0, True, "1", 2])
def test_schema_version_must_be_the_integer_one(version):
    with pytest.raises(dd.ConditionsError):
        dd.validate_conditions({"schema_version": version, "conditions": []})


def recommendation_condition():
    return recorded(
        "REDUCE_ONLY", metric="exposure.recommendation", comparator="eq", threshold="REDUCE_ONLY"
    )


def test_recommendation_input_set_change_reports_input_set_changed_both_ways():
    three = ("breadth", "uptrend", "top_risk")
    today_more = today_side(kinds=three, exposure_inputs=list(three))
    out = dd.classify(recommendation_condition(), prev_ctx(), today_more)
    assert out["reason"] == "input_set_changed"
    prev_more = prev_ctx(three, inputs=list(three))
    out = dd.classify(recommendation_condition(), prev_more, today_side())
    assert out["reason"] == "input_set_changed"


def test_recommendation_freshness_checks_every_input_kind():
    side = today_side()
    side["as_of"] = {"breadth": TODAY_AS_OF, "uptrend": PREV_AS_OF}  # uptrend not refreshed
    assert dd.classify(recommendation_condition(), prev_ctx(), side)["reason"] == (
        "input_not_refreshed"
    )
    side["as_of"] = {"breadth": PREV_AS_OF, "uptrend": TODAY_AS_OF}  # breadth not refreshed
    assert dd.classify(recommendation_condition(), prev_ctx(), side)["reason"] == (
        "input_not_refreshed"
    )


def test_input_stale_boundary_is_inclusive_of_max_age():
    as_of = datetime.fromisoformat(TODAY_AS_OF)
    exact = (as_of + timedelta(days=2)).isoformat()
    over = (as_of + timedelta(days=2, seconds=1)).isoformat()
    ok = dd.classify(
        recorded(70.0),
        prev_ctx(),
        today_side({"breadth.composite_score": 65.0}, evaluation_at=exact),
    )
    assert ok["status"] == "unchanged"
    late = dd.classify(
        recorded(70.0),
        prev_ctx(),
        today_side({"breadth.composite_score": 65.0}, evaluation_at=over),
    )
    assert late["reason"] == "input_stale"


def test_recorded_holds_at_decision_must_match_its_value():
    for good in (recorded(66.1), recommendation_condition()):
        forged = copy.deepcopy(good)
        forged["holds_at_decision"] = not forged["holds_at_decision"]
        with pytest.raises(dd.ConditionsError):
            dd.validate_recorded_conditions([forged])


def test_unknown_recommendation_value_today_is_invalid_value():
    cond = recommendation_condition()
    out = dd.classify(cond, prev_ctx(), today_side({"exposure.recommendation": "MAYBE"}))
    assert out["status"] == "not_evaluable" and out["reason"] == "invalid_value"
