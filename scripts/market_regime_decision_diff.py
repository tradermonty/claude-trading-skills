"""Pure decision-diff logic for the guided market-regime-daily runner (Issue #709).

Standard library only and no I/O: callers pass in plain data. Everything here is
fictional-fixture bookkeeping, never a trading signal. Error messages are fixed
strings and never echo untrusted input.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime

KINDS = ("breadth", "uptrend", "top_risk")
RECOMMENDATIONS = ("CASH_PRIORITY", "REDUCE_ONLY", "NEW_ENTRY_ALLOWED")
NUMERIC_METRICS = ("breadth.composite_score", "uptrend.composite_score", "top_risk.composite_score")
RECOMMENDATION_METRIC = "exposure.recommendation"
METRICS = (*NUMERIC_METRICS, RECOMMENDATION_METRIC)
NUMERIC_COMPARATORS = ("lt", "le", "gt", "ge")
RECOMMENDATION_COMPARATORS = ("eq", "ne")
MAX_CONDITIONS = 20
ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
DECISIONS = ("allow", "restrict", "cash-priority")
FIXTURE_SETS = ("day-1", "day-2")
SELECTION_MODES = ("explicit", "root")
SNAPSHOT_STATUSES = (
    "not_found",
    "unavailable",
    "invalid",
    "other_workflow",
    "incomplete",
    "source_changed",
    "integrity_mismatch",
    "not_earlier",
    "ambiguous",
    "loaded",
)
STATUS_MESSAGES = {
    "not_found": (
        "No previous run found at the given path; continuing as a first run.",
        "previous runs root not found",
        "no completed earlier run found under the root",
    ),
    "unavailable": (
        "Previous run is unavailable (locked, symlinked, or unreadable); continuing as a first run.",
        "too many run directories under the root; use a dedicated root such as "
        "reports/market-regime-daily/",
    ),
    "invalid": ("Previous run directory is not a readable run; continuing as a first run.",),
    "other_workflow": ("Previous run belongs to another workflow; continuing as a first run.",),
    "incomplete": ("Previous run has no recorded decision; continuing as a first run.",),
    "source_changed": (
        "Runner, workflow, or fixture sources changed since the previous run; "
        "continuing as a first run.",
    ),
    "integrity_mismatch": (
        "Previous run failed integrity verification; continuing as a first run.",
    ),
    "not_earlier": (
        "Previous run is later than this run's evaluation time; continuing as a first run.",
    ),
    "ambiguous": ("Several previous runs tie for most recent; continuing as a first run.",),
    "loaded": ("Previous decision loaded.",),
}
LIMITATIONS = [
    "Fictional fixtures at fixed historical times; never current market data.",
    "The previous run is named explicitly or chosen from one root by recorded times only.",
    "Snapshot hashes detect edits but are not tamper-proof or signed.",
    "The diff is read-only evidence; it never records or implies a posture decision.",
]
NOT_EVALUABLE_REASONS = (
    "no_baseline_value",
    "input_missing_today",
    "input_as_of_unknown",
    "input_not_refreshed",
    "input_stale",
    "input_set_changed",
    "invalid_value",
)
POSTURE_ITEM = {
    "item": "posture",
    "why": "record today's posture at the gate; the diff never decides",
}


class ConditionsError(ValueError):
    """Revisit conditions are invalid. The message never echoes the input."""


class SnapshotError(ValueError):
    """The frozen previous-run snapshot is malformed. The message never echoes it."""


# ----------------------------------------------------------------- helpers


def _finite_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an int too large to convert is not a usable threshold
        return False


def _parse_aware(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def holds(value, comparator, threshold):
    """Evaluate one predicate. The caller guarantees comparable, valid operands."""
    return {
        "lt": lambda: value < threshold,
        "le": lambda: value <= threshold,
        "gt": lambda: value > threshold,
        "ge": lambda: value >= threshold,
        "eq": lambda: value == threshold,
        "ne": lambda: value != threshold,
    }[comparator]()


def _reject_constant(_name):
    raise ConditionsError("Revisit conditions file is invalid.")


def _unique_pairs(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ConditionsError("Revisit conditions file is invalid.")
    return dict(pairs)


# ------------------------------------------------------ conditions validator


def _validate_threshold(metric, comparator, threshold):
    if metric == RECOMMENDATION_METRIC:
        if comparator not in RECOMMENDATION_COMPARATORS or threshold not in RECOMMENDATIONS:
            raise ConditionsError("Revisit condition comparator or threshold is invalid.")
        return
    if comparator not in NUMERIC_COMPARATORS or not _finite_number(threshold):
        raise ConditionsError("Revisit condition comparator or threshold is invalid.")


def _validate_condition(cond, extra=()):
    keys = {"id", "label", "metric", "comparator", "threshold", *extra}
    if not isinstance(cond, dict) or set(cond) != keys:
        raise ConditionsError("Revisit condition has unexpected or missing fields.")
    ident, label = cond["id"], cond["label"]
    if not isinstance(ident, str) or not ID_PATTERN.fullmatch(ident):
        raise ConditionsError("Revisit condition id is invalid.")
    if not isinstance(label, str) or not 1 <= len(label) <= 200 or not label.isprintable():
        raise ConditionsError("Revisit condition label is invalid.")
    if cond["metric"] not in METRICS:
        raise ConditionsError("Revisit condition metric is not allowed.")
    _validate_threshold(cond["metric"], cond["comparator"], cond["threshold"])


def _validate_list(conditions, extra=()):
    if not isinstance(conditions, list) or len(conditions) > MAX_CONDITIONS:
        raise ConditionsError("Revisit conditions list is invalid or too long.")
    for cond in conditions:
        _validate_condition(cond, extra)
    if len({c["id"] for c in conditions}) != len(conditions):
        raise ConditionsError("Revisit condition ids must be unique.")
    return conditions


def validate_conditions(payload):
    """Validate a user-authored conditions document and return its condition list."""
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "conditions"}
        or type(payload["schema_version"]) is not int
        or payload["schema_version"] != 1
    ):
        raise ConditionsError("Revisit conditions file is invalid.")
    return _validate_list(payload["conditions"])


def parse_conditions(data):
    """Parse raw bytes, rejecting NaN, duplicate keys and pathological nesting."""
    try:
        payload = json.loads(
            data.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_pairs,
        )
    except ConditionsError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ConditionsError("Revisit conditions file is invalid.") from exc
    return validate_conditions(payload)


def validate_recorded_conditions(conditions):
    """Re-apply the full validator to conditions stored with their baseline values."""
    if conditions is None:
        return None
    _validate_list(conditions, extra=("value_at_decision", "holds_at_decision"))
    for cond in conditions:
        value, held = cond["value_at_decision"], cond["holds_at_decision"]
        if value is None:
            ok = held is None
        elif cond["metric"] == RECOMMENDATION_METRIC:
            ok = value in RECOMMENDATIONS and held is holds(
                value, cond["comparator"], cond["threshold"]
            )
        else:
            ok = _finite_number(value) and held is holds(
                value, cond["comparator"], cond["threshold"]
            )
        if not ok:
            raise ConditionsError("Recorded revisit condition baseline is invalid.")
    return conditions


# --------------------------------------------------- today's evidence side


def make_side(evaluation_at, fixtures, by_kind, proposal_result):
    """Collect today's verified values, input dates and unevaluated inputs."""
    completed = [kind for kind in KINDS if kind in by_kind]
    values = {
        f"{kind}.composite_score": (
            by_kind[kind]["composite"]["composite_score"] if kind in by_kind else None
        )
        for kind in KINDS
    }
    values[RECOMMENDATION_METRIC] = proposal_result["recommendation"]
    skipped = [kind for kind in KINDS if kind not in by_kind]
    unevaluated = [{"input": kind, "reason": "optional_step_not_selected"} for kind in skipped]
    unevaluated += [
        {"input": name, "reason": "not_provided_by_this_workflow"}
        for name in proposal_result["inputs_missing"]
        if name not in KINDS
    ]
    return {
        "evaluation_at": evaluation_at,
        "values": values,
        "as_of": {kind: fixtures[kind]["as_of"] for kind in completed},
        "max_age_days": {kind: fixtures[kind]["max_age_days"] for kind in completed},
        "exposure_inputs": sorted(proposal_result["inputs_provided"]),
        "skipped": skipped,
        "unevaluated": sorted(unevaluated, key=lambda item: item["input"]),
    }


def data_as_of(side):
    return {"evaluation_at": side["evaluation_at"], "inputs": dict(sorted(side["as_of"].items()))}


def record_conditions(conditions, side):
    """Stamp each condition with today's value and whether it already holds."""
    out = []
    for cond in conditions:
        value = side["values"].get(cond["metric"])
        held = None if value is None else holds(value, cond["comparator"], cond["threshold"])
        out.append({**cond, "value_at_decision": value, "holds_at_decision": held})
    return out


def decision_record(conditions, side):
    """The extended record stored on the decision gate and mirrored into the journal."""
    return {
        "revisit_conditions": None if conditions is None else record_conditions(conditions, side),
        "data_as_of": data_as_of(side),
        "unevaluated": side["unevaluated"],
    }


# ---------------------------------------------------------- classification


def _source_kinds(metric, side):
    if metric == RECOMMENDATION_METRIC:
        return sorted(side["as_of"])
    return [metric.split(".", 1)[0]]


def _valid_operands(metric, *values):
    if metric == RECOMMENDATION_METRIC:
        return all(v in RECOMMENDATIONS for v in values)
    return all(_finite_number(v) for v in values)


def _not_refreshed_or_stale(kinds, prev_as_of, side):
    for kind in kinds:
        today = _parse_aware(side["as_of"].get(kind))
        before = _parse_aware(prev_as_of.get(kind))
        if today is None or before is None:
            return "input_as_of_unknown"
    for kind in kinds:
        if not _parse_aware(side["as_of"][kind]) > _parse_aware(prev_as_of[kind]):
            return "input_not_refreshed"
    evaluated = _parse_aware(side["evaluation_at"])
    for kind in kinds:
        limit = side["max_age_days"].get(kind)
        age = None if evaluated is None else (evaluated - _parse_aware(side["as_of"][kind]))
        if age is None or not isinstance(limit, int) or age.total_seconds() > limit * 86400:
            return "input_stale"
    return None


def _blocking_reason(cond, previous, side):
    metric = cond["metric"]
    if cond["value_at_decision"] is None:
        return "no_baseline_value", None
    if side["values"].get(metric) is None:
        detail = (
            "optional_step_not_selected" if metric.split(".", 1)[0] in side["skipped"] else None
        )
        return "input_missing_today", detail
    # A different input set makes the recommendation incomparable, so name that before
    # any per-input date check can fail for a missing kind.
    if metric == RECOMMENDATION_METRIC and sorted(previous["exposure_inputs_provided"]) != sorted(
        side["exposure_inputs"]
    ):
        return "input_set_changed", None
    kinds = _source_kinds(metric, side)
    reason = _not_refreshed_or_stale(kinds, previous["data_as_of"]["inputs"], side)
    if reason:
        return reason, None
    if not _valid_operands(metric, cond["value_at_decision"], side["values"][metric]):
        return "invalid_value", None
    return None, None


def classify(cond, previous, side):
    """Classify one recorded condition against today's evidence.

    `unchanged` is returned only after every presence, freshness and validity
    check has passed; anything else is `not_evaluable` with a reason.
    """
    metric = cond["metric"]
    before, now_value = cond["value_at_decision"], side["values"].get(metric)
    kinds = _source_kinds(metric, side)
    entry = {
        "id": cond["id"],
        "label": cond["label"],
        "metric": metric,
        "comparator": cond["comparator"],
        "threshold": cond["threshold"],
        "previous": {
            "value": before,
            "holds": cond.get("holds_at_decision"),
            "as_of": previous["data_as_of"]["inputs"].get(kinds[0]) if kinds else None,
        },
        "today": {
            "value": now_value,
            "holds": None,
            "as_of": side["as_of"].get(kinds[0]) if kinds else None,
        },
        "delta": None,
        "status": "not_evaluable",
        "reason": None,
        "detail": None,
    }
    reason, detail = _blocking_reason(cond, previous, side)
    if reason:
        entry["reason"], entry["detail"] = reason, detail
        return entry
    held_before = holds(before, cond["comparator"], cond["threshold"])
    held_now = holds(now_value, cond["comparator"], cond["threshold"])
    entry["previous"]["holds"], entry["today"]["holds"] = held_before, held_now
    entry["status"] = "changed" if held_before != held_now else "unchanged"
    if metric != RECOMMENDATION_METRIC:
        entry["delta"] = round(now_value - before, 6)
    return entry


# ------------------------------------------------------ snapshot validator


def _check_message(status, message):
    if message not in STATUS_MESSAGES[status]:
        raise SnapshotError("Previous-run snapshot is malformed.")


def _validate_loaded(prev):
    expected = {
        "status",
        "message",
        "run_id",
        "fixture_set",
        "evaluation_at",
        "decision",
        "decision_at",
        "journal_schema_version",
        "manifest_sha256",
        "journal_sha256",
        "data_as_of",
        "exposure_inputs_provided",
        "revisit_conditions",
    }
    if set(prev) != expected:
        raise SnapshotError("Previous-run snapshot is malformed.")
    sha = re.compile(r"^[0-9a-f]{64}$")
    ok = (
        isinstance(prev["run_id"], str)
        and prev["fixture_set"] in FIXTURE_SETS
        and _parse_aware(prev["evaluation_at"]) is not None
        and prev["decision"] in DECISIONS
        and _parse_aware(prev["decision_at"]) is not None
        and prev["journal_schema_version"] in (1, 2)
        and all(
            isinstance(prev[k], str) and sha.match(prev[k])
            for k in ("manifest_sha256", "journal_sha256")
        )
        and isinstance(prev["exposure_inputs_provided"], list)
        and all(isinstance(v, str) for v in prev["exposure_inputs_provided"])
    )
    data = prev["data_as_of"]
    ok = ok and isinstance(data, dict) and set(data) == {"evaluation_at", "inputs"}
    ok = ok and isinstance(data["inputs"], dict) and set(data["inputs"]) <= set(KINDS)
    ok = ok and all(_parse_aware(v) is not None for v in data["inputs"].values())
    if not ok:
        raise SnapshotError("Previous-run snapshot is malformed.")
    try:
        validate_recorded_conditions(prev["revisit_conditions"])
    except ConditionsError as exc:
        raise SnapshotError("Previous-run snapshot is malformed.") from exc


def validate_snapshot(snapshot, run_id):
    """Check the frozen previous-run snapshot's shape; raises SnapshotError."""
    selection_keys = {"mode", "candidates", "skipped_unreadable"}
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != {"run_id", "selection", "previous"}
        or snapshot["run_id"] != run_id
        or not isinstance(snapshot["selection"], dict)
        or set(snapshot["selection"]) != selection_keys
        or snapshot["selection"]["mode"] not in SELECTION_MODES
        or any(
            isinstance(snapshot["selection"][k], bool)
            or not isinstance(snapshot["selection"][k], int)
            for k in ("candidates", "skipped_unreadable")
        )
        or not isinstance(snapshot["previous"], dict)
    ):
        raise SnapshotError("Previous-run snapshot is malformed.")
    prev = snapshot["previous"]
    status = prev.get("status")
    if status not in SNAPSHOT_STATUSES:
        raise SnapshotError("Previous-run snapshot is malformed.")
    _check_message(status, prev.get("message"))
    if status == "loaded":
        _validate_loaded(prev)
    elif set(prev) != {"status", "message"}:
        raise SnapshotError("Previous-run snapshot is malformed.")


# -------------------------------------------------------------------- diff


def _confirm_items(prev, entries):
    items = []
    for entry in entries:
        if entry["status"] == "changed":
            items.append({"item": "condition", "id": entry["id"], "why": "changed"})
        elif entry["status"] == "not_evaluable":
            items.append(
                {
                    "item": "condition",
                    "id": entry["id"],
                    "why": "not_evaluable",
                    "reason": entry["reason"],
                }
            )
    for cond in prev["revisit_conditions"] or []:
        if cond["holds_at_decision"] is True:
            items.append({"item": "condition_already_met_at_decision", "id": cond["id"]})
    if not prev["revisit_conditions"]:
        items.append(
            {
                "item": "no_revisit_conditions",
                "why": "previous decision recorded no revisit conditions; "
                "review from today's evidence",
            }
        )
    return items


def build_decision_diff(run_id, snapshot, side):
    """Build the read-only decision diff from a validated snapshot and today's side."""
    prev = snapshot["previous"]
    loaded = prev["status"] == "loaded"
    entries = [classify(c, prev, side) for c in prev["revisit_conditions"] or []] if loaded else []
    summary = {
        key: sum(1 for e in entries if e["status"] == key)
        for key in ("changed", "unchanged", "not_evaluable")
    }
    if loaded:
        previous_decision = {
            "decision": prev["decision"],
            "decision_at": prev["decision_at"],
            "run_id": prev["run_id"],
        }
        confirm = _confirm_items(prev, entries)
        shown = {
            k: prev[k]
            for k in (
                "status",
                "message",
                "run_id",
                "decision",
                "decision_at",
                "evaluation_at",
                "data_as_of",
            )
        }
    else:
        previous_decision = None
        confirm = [{"item": "first_run", "why": prev["message"]}]
        shown = {"status": prev["status"], "message": prev["message"]}
    return {
        "schema_version": 1,
        "workflow_id": "market-regime-daily",
        "run_id": run_id,
        "fictional": True,
        "read_only": True,
        "evaluation_at": side["evaluation_at"],
        "first_run": not loaded,
        "previous": shown,
        "today": {"data_as_of": data_as_of(side), "unevaluated": side["unevaluated"]},
        "conditions": entries,
        "summary": summary,
        "columns": {
            "previous_decision": previous_decision,
            "changed_today": [e["id"] for e in entries if e["status"] == "changed"],
            "confirm": [*confirm, dict(POSTURE_ITEM)],
        },
        "limitations": list(LIMITATIONS),
    }
