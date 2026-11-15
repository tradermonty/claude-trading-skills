#!/usr/bin/env python3
"""Guide one fictional, offline market-regime-daily run with an explicit human gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from market_regime_decision_diff import (
    STATUS_MESSAGES,
    ConditionsError,
    SnapshotError,
    build_decision_diff,
    decision_record,
    make_side,
    parse_conditions,
    validate_recorded_conditions,
    validate_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/workflows/market-regime-daily"
DAY2 = EXAMPLE / "guided-day-2"
DAY2_KEYS = {"schema_version", "workflow_id", "fixture_set", "fixed_timestamp", "inputs"}
MAX_PREVIOUS_BYTES = 1024 * 1024
MAX_CONDITIONS_BYTES = 64 * 1024
MAX_ROOT_DIRS = 500
KINDS = ("breadth", "uptrend", "top_risk")
FILES = (
    "01_market_breadth_report.json",
    "02_uptrend_report.json",
    "03_top_risk_report.json",
    "04_exposure_proposal.json",
)
SKILLS = ("market-breadth-analyzer", "uptrend-analyzer", "market-top-detector", "exposure-coach")
DECISIONS = ("allow", "restrict", "cash-priority")
LIMITATIONS = [
    "Fictional component fixtures at a fixed historical evaluation time; never current market data.",
    "Native scorers and exposure API only; no provider fetch or individual component calculators.",
    "No network, broker, account, dotenv, or real trader-memory state access.",
    "Journal is a local handoff only; delivery to trader-memory-core is not implemented.",
]


class RunError(ValueError):
    """A run cannot safely continue. Messages contain no untrusted payloads."""


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


# Byte limit applied while inspecting an untrusted previous run. A ContextVar is
# per-thread, restored by token (so scopes nest), and never leaks into other threads.
_read_cap = ContextVar("market_regime_read_cap", default=None)
INHERIT = object()  # regular_bytes default: use the active scope's cap, if any


@contextmanager
def capped_reads(limit):
    token = _read_cap.set(limit)
    try:
        yield
    finally:
        _read_cap.reset(token)


def regular_bytes(path, cap=INHERIT):
    """Read a regular file. `cap=None` is explicitly uncapped, e.g. trusted repository sources."""
    if any(p.is_symlink() for p in (path, *path.absolute().parents)) or not path.is_file():
        raise RunError("Required regular file missing or symlink encountered.")
    cap = _read_cap.get() if cap is INHERIT else cap
    if cap is None:
        return path.read_bytes()
    with path.open("rb") as stream:
        data = stream.read(cap + 1)
    if len(data) > cap:
        raise RunError("A file exceeds the size limit.")
    return data


def load(path):
    try:
        return json.loads(regular_bytes(path))
    except (ValueError, UnicodeError) as exc:
        raise RunError("Invalid run JSON; restore the run or start a new directory.") from exc


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    # Never follow an existing temporary file after an interrupted write.
    with temporary.open("xb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def write_new(path, value):
    with path.open("xb") as stream:
        stream.write(encoded(value))


def source_fingerprint():
    paths = [
        ROOT / "workflows/market-regime-daily.yaml",
        ROOT / "scripts/workflow_replay.py",
        *sorted((ROOT / "scripts/workflow_replay_pkg").glob("*.py")),
        ROOT / "scripts/validate_provenance.py",
        ROOT / "scripts/market_regime_decision_diff.py",
        Path(__file__).resolve(),
        EXAMPLE / "replay.yaml",
        *sorted((EXAMPLE / "replay-inputs").glob("*.json")),
        DAY2 / "fixture-set.yaml",
        *sorted(DAY2.glob("*.json")),
    ]
    for skill in SKILLS:
        scripts = ROOT / "skills" / skill / "scripts"
        paths.extend(p for p in sorted(scripts.rglob("*.py")) if "tests" not in p.parts)
    return {str(p.relative_to(ROOT)): digest(regular_bytes(p, cap=None)) for p in paths}


def contract():
    # Reuse the replay's validated component contract and native scorer loaders.
    # Do not modify its global fixture run ID: this runner owns its own provenance.
    import workflow_replay as replay

    workflow = replay.load_yaml(ROOT / "workflows/market-regime-daily.yaml")
    spec = replay.load_yaml(EXAMPLE / "replay.yaml")
    if (
        workflow["id"] != "market-regime-daily"
        or [s["skill"] for s in workflow["steps"]] != list(SKILLS)
        or [s["decision_gate"] for s in workflow["steps"]] != [False, False, False, True]
        or workflow["journal_destination"] != "trader-memory-core"
    ):
        raise RunError("Workflow contract changed; this runner needs an update.")
    fixtures = replay._load_market_fixture_set(
        {name: EXAMPLE / path for name, path in spec["inputs"].items()}, spec
    )
    for kind in KINDS:
        replay._market_modules(ROOT, kind)
    exposure = replay._load_module_from_path(
        ROOT / "skills/exposure-coach/scripts/calculate_exposure.py", "guided_exposure"
    )
    return replay, spec, fixtures, exposure


def with_fixture_set(setup):
    """Swap in the fictional day-2 fixtures, validated like the default set."""
    replay, spec, _, exposure = setup
    document = replay.load_yaml(DAY2 / "fixture-set.yaml")
    inputs = document.get("inputs") if isinstance(document, dict) else None
    if (
        not isinstance(inputs, dict)
        or set(document) != DAY2_KEYS
        or document["schema_version"] != 1
        or document["workflow_id"] != "market-regime-daily"
        or document["fixture_set"] != "day-2"
        or set(inputs) != set(spec["inputs"])
        or any(
            not isinstance(v, str) or Path(v).name != v or v.startswith(".")
            for v in inputs.values()
        )
    ):
        raise RunError("Day-2 fixture set contract is invalid.")
    spec2 = {**spec, "fixed_timestamp": document["fixed_timestamp"]}
    fixtures = replay._load_market_fixture_set({k: DAY2 / v for k, v in inputs.items()}, spec2)
    return replay, spec2, fixtures, exposure


def select_setup(state, setup):
    """Choose the fixture set recorded in a manifest. Only absent or day-2 is valid."""
    if not isinstance(state, dict):
        raise RunError("Invalid manifest schema or run contract.")
    if "fixture_set" not in state:
        return setup
    if state["fixture_set"] != "day-2":
        raise RunError("Unsupported fixture set in the run manifest.")
    return with_fixture_set(setup)


def component(kind, fixture, evaluation, run_id, replay):
    scorer, _ = replay._market_modules(ROOT, kind)
    report = replay._market_analysis(scorer, kind, fixture, evaluation)
    report["provenance"]["native_surface"] = (
        "scorer.calculate_composite_score; guided runner JSON serialization"
    )
    report["run_id"] = run_id
    if "data_provenance" in report:
        report["data_provenance"]["run_id"] = run_id
    return report


def proposal(reports, state, exposure):
    scores = dict.fromkeys(exposure.WEIGHTS)
    scores.update(
        breadth=exposure.extract_breadth_score(reports[0]),
        uptrend=exposure.extract_uptrend_score(reports[1]),
        top_risk=exposure.extract_top_risk_score(reports[2]) if len(reports) == 3 else None,
    )
    lineage = exposure.validate_market_inputs(
        reports[0],
        reports[1],
        run_id=state["run_id"],
        evaluation=state["evaluation_at"],
        max_age_days=3,
    )
    score, provided, missing = exposure.calculate_composite_score(scores)
    recommendation = exposure.determine_recommendation(
        score, scores["top_risk"], len(set(missing) & exposure.CRITICAL_INPUTS)
    )
    ceiling = exposure.determine_exposure_ceiling(score)
    bias = exposure.determine_bias("Unknown", None, None, None)
    participation = exposure.determine_participation(scores["uptrend"], scores["breadth"], None)
    return {
        "schema_version": 1,
        "run_id": state["run_id"],
        "evaluation_at": state["evaluation_at"],
        "fictional": True,
        "result": {
            "composite_score": round(score, 1),
            "recommendation": recommendation,
            "exposure_ceiling_pct": ceiling,
            "bias": bias,
            "participation": participation,
            "confidence": exposure.determine_confidence(provided, missing),
            "inputs_provided": provided,
            "inputs_missing": missing,
            "component_scores": {k: v for k, v in scores.items() if v is not None},
            "input_lineage": lineage,
            "rationale": exposure.generate_rationale(
                score, recommendation, participation, bias, scores, missing, ceiling
            ),
        },
    }


def record(path, directory):
    return {"path": str(path.relative_to(directory)), "sha256": digest(regular_bytes(path))}


def verify_record(entry, expected_path, directory):
    if entry != record(directory / expected_path, directory):
        raise RunError("Run artifact path or hash mismatch; refusing stale handoff.")


def after_checkpoint(state):
    """Checkpoint boundary, also an interruption-test seam."""


def checkpoint(directory, state):
    atomic_json(directory / "manifest.json", state)
    after_checkpoint(state)


def journal(state):
    gate = state["steps"][3]
    value = {
        "schema_version": 1,
        "run_id": state["run_id"],
        "fictional": True,
        "destination": "trader-memory-core",
        "delivery": "handoff_only",
        "decision": gate["decision"],
        "recorded_at": gate["decision_at"],
        "proposal": gate["output"],
        "limitations": LIMITATIONS,
    }
    extended = gate.get("decision_record")
    if extended is not None:
        value.update(
            schema_version=2,
            revisit_conditions=extended["revisit_conditions"],
            data_as_of=extended["data_as_of"],
            unevaluated=extended["unevaluated"],
            decision_diff=state.get("decision_diff"),
        )
    return value


def today_side(state, setup, by_kind, proposal_value):
    return make_side(state["evaluation_at"], setup[2], by_kind, proposal_value["result"])


def lexists(path):
    return os.path.lexists(path)


def verify_previous_snapshot(directory, state):
    """Return the validated frozen previous-run snapshot, or None when none is allowed."""
    if "previous_run" in state:
        verify_record(state["previous_run"], "inputs/previous_run.json", directory)
        snapshot = load(directory / "inputs/previous_run.json")
        try:
            validate_snapshot(snapshot, state["run_id"])
        except SnapshotError as exc:
            raise RunError("Previous-run snapshot is invalid.") from exc
        return snapshot
    if (
        lexists(directory / "inputs/previous_run.json")
        or lexists(directory / "decision_diff.json")
        or "decision_diff" in state
    ):
        raise RunError("Decision diff artifacts exist without a previous-run record.")
    return None


def verify_decision_diff(directory, state, setup, snapshot, by_kind, proposal_value):
    if snapshot is None:
        return
    published = state["steps"][3]["status"] in {"AWAITING_DECISION", "COMPLETED"}
    if not published:
        if "decision_diff" in state or lexists(directory / "decision_diff.json"):
            raise RunError("Decision diff cannot precede the exposure proposal.")
        return
    if "decision_diff" not in state:
        raise RunError("Decision diff record missing.")
    verify_record(state["decision_diff"], "decision_diff.json", directory)
    expected = build_decision_diff(
        state["run_id"], snapshot, today_side(state, setup, by_kind, proposal_value)
    )
    if load(directory / "decision_diff.json") != expected:
        raise RunError("Decision diff differs from its recomputation.")


def verify_decision_record(state, setup, by_kind, proposal_value):
    extended = state["steps"][3].get("decision_record")
    if extended is None:
        if state["status"] == "COMPLETED" and "previous_run" in state:
            raise RunError("Decision record missing.")
        return
    if state["status"] != "COMPLETED" or set(extended) != {
        "revisit_conditions",
        "data_as_of",
        "unevaluated",
    }:
        raise RunError("Decision record is invalid.")
    recorded = validate_recorded_conditions(extended["revisit_conditions"])
    plain = None
    if recorded is not None:
        keys = ("id", "label", "metric", "comparator", "threshold")
        plain = [{key: cond[key] for key in keys} for cond in recorded]
    side = today_side(state, setup, by_kind, proposal_value)
    if extended != decision_record(plain, side):
        raise RunError("Decision record differs from its recomputation.")


def verify_extensions(directory, state, setup, by_kind, proposal_value):
    """Checks for the optional fixture-set, previous-run, diff and decision-record artifacts."""
    if state.get("fixture_set", "day-2") != "day-2":
        raise RunError("Unsupported fixture set in the run manifest.")
    snapshot = verify_previous_snapshot(directory, state)
    verify_decision_diff(directory, state, setup, snapshot, by_kind, proposal_value)
    verify_decision_record(state, setup, by_kind, proposal_value)


def verify(directory, state, setup):
    """Validate saved state and recompute values without rewriting or rerunning steps."""
    replay, spec, fixtures, exposure = setup
    try:
        if (
            state["schema_version"] != 1
            or state["workflow_id"] != "market-regime-daily"
            or str(uuid.UUID(state["run_id"])) != state["run_id"]
            or state["evaluation_at"] != spec["fixed_timestamp"]
            or type(state["include_top_risk"]) is not bool
            or state["limitations"] != LIMITATIONS
            or state["readiness"] != {"status": "PASSED", "api_environment": "not_required"}
        ):
            raise RunError("Invalid run contract.")
        if state["sources"] != source_fingerprint():
            raise RunError("Runner, workflow, fixture, or native source changed; start a new run.")
        datetime.fromisoformat(state["created_at"])
        if set(state["inputs"]) != set(KINDS) or len(state["steps"]) != 4:
            raise RunError("Incomplete run manifest.")
        for kind in KINDS:
            path = f"inputs/{kind}.json"
            verify_record(state["inputs"][kind], path, directory)
            if load(directory / path) != {"run_id": state["run_id"], "fixture": fixtures[kind]}:
                raise RunError("Fixture snapshot does not belong to this run.")
        reports, prior, pending = [], {}, False
        by_kind, proposal_value = {}, None
        for i, row in enumerate(state["steps"]):
            if row["step"] != i + 1 or row["skill"] != SKILLS[i]:
                raise RunError("Invalid step order or skill.")
            status = row["status"]
            if i == 2 and not state["include_top_risk"]:
                if row != {
                    "step": 3,
                    "skill": SKILLS[2],
                    "status": "SKIPPED",
                    "reason": "optional_not_selected",
                }:
                    raise RunError("Optional step skip must be explicit.")
                continue
            if status == "PENDING":
                if row != {"step": i + 1, "skill": SKILLS[i], "status": "PENDING"}:
                    raise RunError("Pending step has unexpected execution state.")
                pending = True
                continue
            if pending or status not in {"COMPLETED", "AWAITING_DECISION"}:
                raise RunError("Interrupted, failed, or out-of-order step; start a new run.")
            if status == "AWAITING_DECISION" and i != 3:
                raise RunError("Unexpected decision gate.")
            expected_inputs = {KINDS[i]: state["inputs"][KINDS[i]]} if i < 3 else prior
            if row["inputs"] != expected_inputs:
                raise RunError("Step dependencies do not match this run.")
            verify_record(row["output"], FILES[i], directory)
            expected = (
                component(
                    KINDS[i], fixtures[KINDS[i]], state["evaluation_at"], state["run_id"], replay
                )
                if i < 3
                else proposal(reports, state, exposure)
            )
            if load(directory / FILES[i]) != expected:
                raise RunError("Saved output differs from native calculation or run provenance.")
            datetime.fromisoformat(row["started_at"])
            datetime.fromisoformat(row["completed_at"])
            if i < 3:
                reports.append(expected)
                by_kind[KINDS[i]] = expected
                prior[KINDS[i]] = row["output"]
            else:
                proposal_value = expected
        gate = state["steps"][3]
        expected_status = "IN_PROGRESS" if pending else gate["status"]
        if state["status"] != expected_status:
            raise RunError("Run status does not match step completeness.")
        if state["status"] == "COMPLETED":
            if gate["decision"] not in DECISIONS:
                raise RunError("Decision missing or invalid.")
            datetime.fromisoformat(gate["decision_at"])
            verify_record(state["journal"], "journal.json", directory)
            if load(directory / "journal.json") != journal(state):
                raise RunError("Journal handoff does not match the decision.")
        elif (
            "decision" in gate
            or "decision_record" in gate
            or "journal" in state
            or (directory / "journal.json").exists()
        ):
            raise RunError("A decision cannot precede its human gate.")
        verify_extensions(directory, state, setup, by_kind, proposal_value)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        if isinstance(exc, RunError):
            raise
        raise RunError("Invalid manifest schema or run contract.") from exc


def initialize(directory, include_top_risk, setup, fixture_set=None, previous=None):
    _, spec, fixtures, _ = setup
    run_id = str(uuid.uuid4())
    (directory / "inputs").mkdir()
    inputs = {}
    for kind in KINDS:
        path = directory / "inputs" / f"{kind}.json"
        write_new(path, {"run_id": run_id, "fixture": fixtures[kind]})
        inputs[kind] = record(path, directory)
    state = new_state(run_id, include_top_risk, spec, inputs)
    if fixture_set == "day-2":
        state["fixture_set"] = "day-2"
    if previous is not None:
        path = directory / "inputs" / "previous_run.json"
        write_new(path, {"run_id": run_id, **previous})
        state["previous_run"] = record(path, directory)
    return state


def new_state(run_id, include_top_risk, spec, inputs):
    return {
        "schema_version": 1,
        "workflow_id": "market-regime-daily",
        "run_id": run_id,
        "created_at": now(),
        "evaluation_at": spec["fixed_timestamp"],
        "include_top_risk": include_top_risk,
        "readiness": {"status": "PASSED", "api_environment": "not_required"},
        "sources": source_fingerprint(),
        "inputs": inputs,
        "status": "IN_PROGRESS",
        "limitations": LIMITATIONS,
        "steps": [
            {"step": i + 1, "skill": skill, "status": "SKIPPED", "reason": "optional_not_selected"}
            if i == 2 and not include_top_risk
            else {"step": i + 1, "skill": skill, "status": "PENDING"}
            for i, skill in enumerate(SKILLS)
        ],
    }


def execute_step(i, directory, state, setup):
    replay, _, fixtures, exposure = setup
    if i < 3:
        return component(
            KINDS[i], fixtures[KINDS[i]], state["evaluation_at"], state["run_id"], replay
        )
    reports = [
        load(directory / FILES[j]) for j in range(3) if state["steps"][j]["status"] == "COMPLETED"
    ]
    return proposal(reports, state, exposure)


@contextmanager
def locked(directory):
    path = directory / ".lock"
    try:
        stream = path.open("x")
    except FileExistsError as exc:
        raise RunError(
            "Run is locked; inspect the owner before manual recovery. See the runbook."
        ) from exc
    try:
        with stream:
            stream.write(str(os.getpid()) + "\n")
        yield
    finally:
        path.unlink()


def after_previous_classification(directory):
    """Classification boundary, also a race-test seam. Must not write to `directory`."""


def previous_status(status, message_index=0):
    return {"status": status, "message": STATUS_MESSAGES[status][message_index]}


def screen_previous_state(state):
    """Return a non-loaded status for a manifest that cannot be a usable previous run."""
    if not isinstance(state, dict) or state.get("fixture_set", "day-2") != "day-2":
        return "invalid"
    if state.get("workflow_id") != "market-regime-daily":
        return "other_workflow"
    if state.get("status") != "COMPLETED":
        return "incomplete"
    if state.get("sources") != source_fingerprint():
        return "source_changed"
    return None


def loaded_previous(directory, state, setup, manifest_sha):
    gate = state["steps"][3]
    fixtures = setup[2]
    completed = [k for i, k in enumerate(KINDS) if state["steps"][i]["status"] == "COMPLETED"]
    journal_bytes = regular_bytes(directory / "journal.json")
    extended = gate.get("decision_record")
    return {
        **previous_status("loaded"),
        "run_id": state["run_id"],
        "fixture_set": state.get("fixture_set", "day-1"),
        "evaluation_at": state["evaluation_at"],
        "decision": gate["decision"],
        "decision_at": gate["decision_at"],
        "journal_schema_version": json.loads(journal_bytes)["schema_version"],
        "manifest_sha256": manifest_sha,
        "journal_sha256": digest(journal_bytes),
        "data_as_of": {
            "evaluation_at": state["evaluation_at"],
            "inputs": {kind: fixtures[kind]["as_of"] for kind in completed},
        },
        "exposure_inputs_provided": load(directory / FILES[3])["result"]["inputs_provided"],
        "revisit_conditions": None if extended is None else extended["revisit_conditions"],
    }


def classify_previous_inner(directory, base_setup, evaluation_at):
    if not os.path.lexists(directory):
        return previous_status("not_found")
    if (
        any(p.is_symlink() for p in (directory, *directory.parents))
        or not directory.is_dir()
        or os.path.lexists(directory / ".lock")
    ):
        return previous_status("unavailable")
    try:
        raw = regular_bytes(directory / "manifest.json")
        state = json.loads(raw)
    except (RunError, ValueError, UnicodeError):
        return previous_status("invalid")
    early = screen_previous_state(state)
    if early:
        return previous_status(early)
    setup = select_setup(state, base_setup)
    try:
        verify(directory, state, setup)
    except RunError:
        return previous_status("integrity_mismatch")
    if datetime.fromisoformat(state["evaluation_at"]) > datetime.fromisoformat(evaluation_at):
        return previous_status("not_earlier")
    loaded = loaded_previous(directory, state, setup, digest(raw))
    after_previous_classification(directory)
    # A run that started or changed while it was inspected is not a stable baseline.
    if os.path.lexists(directory / ".lock") or digest(
        regular_bytes(directory / "manifest.json")
    ) != digest(raw):
        return previous_status("unavailable")
    return loaded


def classify_previous(directory, base_setup, evaluation_at):
    """Read-only classification of one previous run directory. Never raises."""
    try:
        with capped_reads(MAX_PREVIOUS_BYTES):
            return classify_previous_inner(Path(directory).absolute(), base_setup, evaluation_at)
    except OSError:
        return previous_status("unavailable")
    except Exception:
        return previous_status("invalid")


def overlaps(first, second):
    return first == second or first in second.parents or second in first.parents


def root_candidate_key(child, evaluation_at):
    """Sort key of a completed earlier run under a root, or None when it does not qualify."""
    state = json.loads(regular_bytes(child / "manifest.json", cap=MAX_PREVIOUS_BYTES))
    if state.get("workflow_id") != "market-regime-daily" or state.get("status") != "COMPLETED":
        return None
    evaluated = datetime.fromisoformat(state["evaluation_at"])
    decided = datetime.fromisoformat(state["steps"][3]["decision_at"])
    if evaluated.tzinfo is None or decided.tzinfo is None:
        raise ValueError("naive timestamp")
    if evaluated > datetime.fromisoformat(evaluation_at):
        return None
    return evaluated, decided


def scan_root(root, own, evaluation_at):
    """Pick the latest completed earlier run directly under `root`; no recursion, no mtime."""
    root = Path(root).absolute()
    counts = {"candidates": 0, "skipped_unreadable": 0}
    if not os.path.lexists(root):
        return None, previous_status("not_found", 1), counts
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        return None, previous_status("unavailable"), counts
    with os.scandir(root) as entries:
        children = sorted(e.path for e in entries if e.is_dir(follow_symlinks=False))
    if len(children) > MAX_ROOT_DIRS:
        return None, previous_status("unavailable", 1), counts
    keyed = []
    for path in children:
        child = Path(path)
        if overlaps(child, own):
            continue
        try:
            key = root_candidate_key(child, evaluation_at)
        except Exception:
            counts["skipped_unreadable"] += 1
            continue
        if key is not None:
            keyed.append((key, child))
    counts["candidates"] = len(keyed)
    if not keyed:
        return None, previous_status("not_found", 2), counts
    best = max(key for key, _ in keyed)
    chosen = [child for key, child in keyed if key == best]
    if len(chosen) > 1:
        return None, previous_status("ambiguous"), counts
    return chosen[0], None, counts


def resolve_previous(directory, previous_run_dir, previous_runs_root, base_setup, evaluation_at):
    """Frozen previous-run evidence for a new run, or None when none was requested."""
    if previous_run_dir is None and previous_runs_root is None:
        return None
    if previous_run_dir is not None:
        selection = {"mode": "explicit", "candidates": 1, "skipped_unreadable": 0}
        previous = classify_previous(previous_run_dir, base_setup, evaluation_at)
    else:
        selection = {"mode": "root", "candidates": 0, "skipped_unreadable": 0}
        try:
            chosen, previous, counts = scan_root(previous_runs_root, directory, evaluation_at)
            selection.update(counts)
        except Exception:
            chosen, previous = None, previous_status("unavailable")
        if previous is None:
            previous = classify_previous(chosen, base_setup, evaluation_at)
    snapshot = {"selection": selection, "previous": previous}
    try:
        validate_snapshot({"run_id": "x", **snapshot}, "x")
    except SnapshotError:
        snapshot["previous"] = previous_status("invalid")
    return snapshot


def refuse_nested_run(directory, previous_run_dir):
    for parent in directory.parents:
        if os.path.lexists(parent / "manifest.json"):
            raise RunError("The run directory cannot be created inside another run.")
    if previous_run_dir is not None:
        earlier = Path(previous_run_dir).absolute().resolve()
        if overlaps(directory.resolve(), earlier):
            raise RunError("The previous run directory cannot contain or equal the new run.")


def read_conditions(path):
    try:
        return parse_conditions(regular_bytes(Path(path).absolute(), cap=MAX_CONDITIONS_BYTES))
    except ConditionsError as exc:
        raise RunError("Revisit conditions file is invalid; the run remains paused.") from exc


def publish_decision_diff(directory, state, setup, output):
    snapshot = load(directory / "inputs/previous_run.json")
    by_kind = {
        KINDS[j]: load(directory / FILES[j])
        for j in range(3)
        if state["steps"][j]["status"] == "COMPLETED"
    }
    diff = build_decision_diff(state["run_id"], snapshot, today_side(state, setup, by_kind, output))
    write_new(directory / "decision_diff.json", diff)
    state["decision_diff"] = record(directory / "decision_diff.json", directory)


def record_decision(directory, state, setup, decision, conditions):
    gate = state["steps"][3]
    if decision not in DECISIONS:
        raise RunError("Invalid exposure posture decision.")
    extra = {}
    if "previous_run" in state or conditions is not None:
        by_kind = {
            KINDS[j]: load(directory / FILES[j])
            for j in range(3)
            if state["steps"][j]["status"] == "COMPLETED"
        }
        side = today_side(state, setup, by_kind, load(directory / FILES[3]))
        extra["decision_record"] = decision_record(conditions, side)
    gate.update(status="COMPLETED", decision=decision, decision_at=now(), **extra)
    # Treat journal publication as an execution boundary. If interrupted,
    # RUNNING blocks adoption of any partially published journal.
    state["status"] = "RUNNING"
    atomic_json(directory / "manifest.json", state)
    write_new(directory / "journal.json", journal(state))
    state["journal"] = record(directory / "journal.json", directory)
    state["status"] = "COMPLETED"
    checkpoint(directory, state)
    verify(directory, state, setup)


def check_run_arguments(
    resume, status_only, decision, fixture_set, previous_run_dir, previous_runs_root, conditions
):
    creation_only = (fixture_set, previous_run_dir, previous_runs_root)
    if (resume or status_only) and any(v is not None for v in creation_only):
        raise RunError("Fixture set and previous-run options are fixed when creating a run.")
    if fixture_set not in (None, "day-1", "day-2"):
        raise RunError("Unknown fixture set.")
    if previous_run_dir is not None and previous_runs_root is not None:
        raise RunError("Choose either a previous run directory or a previous runs root.")
    if conditions is not None and decision is None:
        raise RunError("Revisit conditions are accepted only with a decision.")


def create_run(directory, fixture_set, previous_run_dir, previous_runs_root):
    """Readiness, previous-run classification and directory allocation for a new run."""
    base = contract()
    setup = with_fixture_set(base) if fixture_set == "day-2" else base
    refuse_nested_run(directory, previous_run_dir)
    # The base (day-1) setup lets each previous run pick its own recorded fixture set.
    previous = resolve_previous(
        directory, previous_run_dir, previous_runs_root, base, setup[1]["fixed_timestamp"]
    )
    directory.mkdir(parents=True, exist_ok=False)
    return setup, previous


def run(
    directory,
    *,
    resume=False,
    include_top_risk=False,
    decision=None,
    status_only=False,
    fixture_set=None,
    previous_run_dir=None,
    previous_runs_root=None,
    revisit_conditions=None,
):
    directory = directory.absolute()
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise RunError("Run directory ancestry must not contain symlinks.")
    check_run_arguments(
        resume,
        status_only,
        decision,
        fixture_set,
        previous_run_dir,
        previous_runs_root,
        revisit_conditions,
    )
    previous = None
    if not resume and not status_only:
        if decision is not None:
            raise RunError("A decision requires a paused existing run.")
        # Readiness is checked before allocating a run or writing any artifacts.
        setup, previous = create_run(directory, fixture_set, previous_run_dir, previous_runs_root)
    else:
        if not directory.is_dir():
            raise RunError("Run directory missing.")
        setup = contract()
    with locked(directory):
        if resume or status_only:
            state = load(directory / "manifest.json")
            setup = select_setup(state, setup)
        else:
            state = initialize(directory, include_top_risk, setup, fixture_set, previous)
            checkpoint(directory, state)
        verify(directory, state, setup)
        if status_only:
            return state
        if decision is not None and state["status"] != "AWAITING_DECISION":
            raise RunError("A decision is accepted only at AWAITING_DECISION.")
        if state["status"] == "COMPLETED":
            return state
        for i, row in enumerate(state["steps"]):
            if row["status"] != "PENDING":
                continue
            verify(directory, state, setup)
            row.update(status="RUNNING", started_at=now())
            checkpoint(directory, state)
            try:
                output = execute_step(i, directory, state, setup)
                write_new(directory / FILES[i], output)
                if i == 3 and "previous_run" in state:
                    publish_decision_diff(directory, state, setup, output)
                inputs = (
                    {KINDS[i]: state["inputs"][KINDS[i]]}
                    if i < 3
                    else {
                        KINDS[j]: state["steps"][j]["output"]
                        for j in range(3)
                        if state["steps"][j]["status"] == "COMPLETED"
                    }
                )
                row.update(
                    status="AWAITING_DECISION" if i == 3 else "COMPLETED",
                    completed_at=now(),
                    inputs=inputs,
                    output=record(directory / FILES[i], directory),
                )
                if i == 3:
                    state["status"] = "AWAITING_DECISION"
                checkpoint(directory, state)
            except Exception as exc:
                row["status"] = state["status"] = "FAILED"
                row["failure"] = "Step execution failed; no automatic retry. Start a new run."
                checkpoint(directory, state)
                raise RunError(
                    "Step execution failed; start a new run. See the run manifest."
                ) from exc
        verify(directory, state, setup)
        if decision is not None:
            # Validate before any state changes so a bad file leaves the run paused.
            conditions = None if revisit_conditions is None else read_conditions(revisit_conditions)
            record_decision(directory, state, setup, decision, conditions)
        return state


def print_condition_warnings(state):
    extended = state["steps"][3].get("decision_record") or {}
    for cond in extended.get("revisit_conditions") or []:
        if cond["holds_at_decision"] is True:
            print(f"WARNING: revisit condition {cond['id']} already holds at decision time.")


def condition_line(entry):
    line = (
        f"  [{entry['status']}] {entry['id']}: {entry['metric']} "
        f"{entry['comparator']} {entry['threshold']} "
        f"({entry['previous']['value']} -> {entry['today']['value']})"
    )
    return line + (f" reason: {entry['reason']}" if entry["reason"] else "")


def confirm_line(item):
    parts = [str(item[key]) for key in ("item", "id", "why", "reason") if key in item]
    return "    - " + " ".join(parts)


def print_decision_diff(diff):
    print("Decision diff (read-only; it never records a decision):")
    if diff["first_run"]:
        print(f"  First run: {diff['previous']['message']}")
    else:
        before = diff["columns"]["previous_decision"]
        print(f"  Previous decision: {before['decision']} at {before['decision_at']}")
    for entry in diff["conditions"]:
        print(condition_line(entry))
    print("  Confirm today:")
    for item in diff["columns"]["confirm"]:
        print(confirm_line(item))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--status", action="store_true", help="Validate and display saved status")
    parser.add_argument("--include-top-risk", action="store_true")
    parser.add_argument("--decision", choices=DECISIONS)
    parser.add_argument("--fixture-set", choices=("day-1", "day-2"))
    previous = parser.add_mutually_exclusive_group()
    previous.add_argument("--previous-run-dir", type=Path)
    previous.add_argument("--previous-runs-root", type=Path)
    parser.add_argument("--revisit-conditions", type=Path)
    args = parser.parse_args(argv)
    if args.decision and not args.resume:
        parser.error("--decision requires --resume at a paused gate")
    if args.include_top_risk and (args.resume or args.status):
        parser.error("--include-top-risk is fixed when creating a run")
    creation_only = (args.fixture_set, args.previous_run_dir, args.previous_runs_root)
    if (args.resume or args.status) and any(v is not None for v in creation_only):
        parser.error("--fixture-set and the previous-run options are fixed when creating a run")
    if args.revisit_conditions and not args.decision:
        parser.error("--revisit-conditions requires --decision")
    try:
        state = run(
            args.run_dir,
            resume=args.resume,
            include_top_risk=args.include_top_risk,
            decision=args.decision,
            status_only=args.status,
            fixture_set=args.fixture_set,
            previous_run_dir=args.previous_run_dir,
            previous_runs_root=args.previous_runs_root,
            revisit_conditions=args.revisit_conditions,
        )
        print(f"Fictional offline run {state['run_id']}: {state['status']}")
        for row in state["steps"]:
            print(f"  {row['step']}. {row['skill']}: {row['status']}")
        if args.decision:
            print_condition_warnings(state)
        if state["status"] == "AWAITING_DECISION":
            result = load(args.run_dir / FILES[3])["result"]
            print(json.dumps(result, indent=2))
            if "decision_diff" in state:
                print_decision_diff(load(args.run_dir / "decision_diff.json"))
            print(
                "Choose a fictional posture after reviewing the evidence; this is not a trade signal."
            )
            if not args.status and sys.stdin.isatty():
                answer = input("Posture (allow / restrict / cash-priority; blank pauses): ").strip()
                if answer:
                    if answer not in DECISIONS:
                        raise RunError("Invalid posture; run remains paused.")
                    state = run(args.run_dir, resume=True, decision=answer)
                    print(f"{state['status']}: local journal handoff recorded; not delivered.")
            if state["status"] == "AWAITING_DECISION":
                print(
                    "Resume with --run-dir <same-directory> --resume --decision <posture> "
                    "[--revisit-conditions <file>]."
                )
                return 3
        return 0
    except ImportError:
        print(
            "ERROR: missing runtime dependencies. Run uv sync --locked --extra dev.",
            file=sys.stderr,
        )
        return 2
    except RunError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Replay adapters wrap dependency/import failures in ReplayError. Keep
        # their payload-bearing messages out of CLI diagnostics, but retain the
        # missing-dependency exit contract through the exception chain.
        cause, visited = exc, set()
        while cause is not None and id(cause) not in visited:
            if isinstance(cause, ImportError):
                print(
                    "ERROR: missing runtime dependencies. Run uv sync --locked --extra dev.",
                    file=sys.stderr,
                )
                return 2
            visited.add(id(cause))
            cause = cause.__cause__ or cause.__context__
        print(
            "BLOCKED: invalid, changed, interrupted, or locked run; see the runbook and manifest.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
