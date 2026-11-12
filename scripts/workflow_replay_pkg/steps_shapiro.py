"""Step adapters for the shapiro-contrarian workflow."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from .artifacts import _artifact_paths
from .common import (
    ReplayError,
    _assert_finite_json,
    _load_json,
    _repo_module,
    _require_finite_number,
    _run_cli,
    _write_json,
    load_yaml,
)
from .constants import REPO_ROOT
from .normalize import _canonicalize, _file_sha256, _safe_relative
from .steps_kanchi import _kanchi_artifact_link


def _shapiro_parameters(inputs, spec):
    data = _load_json(inputs["decision"], "Shapiro operator decision")
    schema = load_yaml(REPO_ROOT / "examples/workflows/shapiro-contrarian/decision.schema.yaml")
    errors = list(Draft202012Validator(schema).iter_errors(data))
    if errors:
        raise ReplayError(f"invalid Shapiro operator decision: {errors[0].message}")
    _assert_finite_json(data, "Shapiro operator decision")
    if data["as_of"] != datetime.fromisoformat(spec["fixed_timestamp"]).date().isoformat():
        raise ReplayError("Shapiro decision as_of differs from fixed_timestamp")
    return data


def _shapiro_logic(repo_root):
    return _repo_module(repo_root, "gate_logic", repo_root / "skills/contrarian-setup-gate/scripts")


def _shapiro_detector(logic, payload, decision):
    normalized = logic.normalize_crowding(
        payload, None, symbol=decision["symbol"], as_of=decision["as_of"], max_age_days=10
    )
    if normalized.state != logic.STATE_CONFIRMED:
        raise ReplayError(f"Shapiro crowding halted: {normalized.state}: {normalized.reason}")
    # The replay is deliberately a single-market scenario; never silently pick
    # one row from a duplicate or unrelated market universe.
    if len(payload["markets"]) != 1 or payload.get("skipped"):
        raise ReplayError("Shapiro crowding requires exactly one unambiguous market")
    if payload["markets"][0].get("data_date") != payload["run_context"].get("data_date"):
        raise ReplayError("Shapiro crowding dates disagree")
    return normalized


def _shapiro_manual(repo_root, spec, step, inputs, consumed, work, stage):
    decision = _shapiro_parameters(inputs, spec)
    number = step["step"]
    names = {1: "crowding", 2: "news", 3: "price"}
    envelope = _load_json(inputs[names[number]], "Shapiro manual report fixture")
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"human_approved", "fictional", "report"}
        or envelope["human_approved"] is not True
        or envelope["fictional"] is not True
    ):
        raise ReplayError("Shapiro reports require an approved fictional fixture envelope")
    payload = envelope["report"]
    _assert_finite_json(payload, "Shapiro report")
    logic = _shapiro_logic(repo_root)
    if number == 1:
        _shapiro_detector(logic, payload, decision)
    else:
        detector = _load_json(
            Path(consumed["cot_crowding_report"]["files"]["canonical"]), "crowding handoff"
        )
        normalized_detector = _shapiro_detector(logic, detector, decision)
        normalize = logic.normalize_news if number == 2 else logic.normalize_price_action
        normalized = normalize(
            payload,
            None,
            symbol=decision["symbol"],
            as_of=decision["as_of"],
            max_age_days=7,
            detector=normalized_detector,
        )
        if normalized.state != logic.STATE_CONFIRMED:
            raise ReplayError(
                f"Shapiro {names[number]} halted: {normalized.state}: {normalized.reason}"
            )
    if number == 3:
        stop = _require_finite_number(
            payload["swing_levels"]["stop_reference"], "Shapiro swing stop", minimum=0
        )
        handoff_stop = _require_finite_number(
            payload["handoff"]["price_action"]["stop_reference"], "Shapiro handoff stop", minimum=0
        )
        if stop <= 0 or stop != handoff_stop:
            raise ReplayError("Shapiro price-action stop fields disagree")
    artifacts = _artifact_paths(stage, step["output_files"])
    for bundle in artifacts.values():
        _write_json(Path(bundle["files"]["canonical"]), payload)
    return artifacts


def _shapiro_gate(repo_root, spec, step, inputs, consumed, work, stage):
    decision = _shapiro_parameters(inputs, spec)
    reports = work / "reports"
    command = [
        sys.executable,
        str(repo_root / "skills/contrarian-setup-gate/scripts/run_contrarian_setup_gate.py"),
        "--symbol",
        decision["symbol"],
        "--as-of",
        decision["as_of"],
        "--output-dir",
        str(reports),
        "--format",
        "json",
    ]
    sources = {}
    replacements = {}
    for artifact, flag in (
        ("cot_crowding_report", "--detector-json"),
        ("news_failure_verdict", "--news-json"),
        ("price_action_confirmation_report", "--price-action-json"),
    ):
        path = Path(consumed[artifact]["files"]["canonical"])
        link = _kanchi_artifact_link(consumed, artifact, "canonical", stage)
        command += [flag, str(path)]
        replacements[str(path)] = link
        sources[artifact] = {"file": link, "sha256": _file_sha256(path)}
    _run_cli(command, repo_root)
    files = list(reports.glob("*.json"))
    if len(files) != 1:
        raise ReplayError("Shapiro gate expected one native report")
    payload = _canonicalize(
        _load_json(files[0], "native contrarian gate"), spec["fixed_timestamp"], replacements
    )
    if payload.get("setup_status") != "READY_FOR_PLAN":
        raise ReplayError(f"Shapiro gate halted: {payload.get('setup_status')}")
    payload["replay_sources"] = sources
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["contrarian_setup_gate_report"]["files"]["canonical"]), payload)
    return artifacts


def _shapiro_size(repo_root, spec, step, inputs, consumed, work, stage):
    decision = _shapiro_parameters(inputs, spec)
    gate_path = Path(consumed["contrarian_setup_gate_report"]["files"]["canonical"])
    gate = _load_json(gate_path, "Shapiro sizing gate")
    if gate.get("symbol") != decision["symbol"] or gate.get("setup_status") != "READY_FOR_PLAN":
        raise ReplayError("Shapiro sizing requires a matching READY_FOR_PLAN gate")
    reports = work / "reports"
    _run_cli(
        [
            sys.executable,
            str(repo_root / "skills/futures-position-sizer/scripts/futures_position_sizer.py"),
            "--gate-json",
            str(gate_path),
            "--entry",
            str(decision["entry"]),
            "--account-size",
            str(decision["account_size"]),
            "--risk-pct",
            str(decision["risk_pct"]),
            "--as-of",
            decision["as_of"],
            "--output-dir",
            str(reports),
            "--format",
            "json",
        ],
        repo_root,
    )
    files = list(reports.glob("*.json"))
    if len(files) != 1:
        raise ReplayError("Shapiro sizing expected one native report")
    payload = _canonicalize(
        _load_json(files[0], "native futures sizing"),
        spec["fixed_timestamp"],
        {
            str(gate_path): _kanchi_artifact_link(
                consumed, "contrarian_setup_gate_report", "canonical", stage
            )
        },
    )
    if payload.get("sizing_status") != "SIZED":
        raise ReplayError(f"Shapiro sizing halted: {payload.get('sizing_status')}")
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["futures_position_size"]["files"]["canonical"]), payload)
    return artifacts


def _shapiro_journal(repo_root, spec, step, inputs, consumed, work, stage):
    decision = _shapiro_parameters(inputs, spec)
    gate_path = Path(consumed["contrarian_setup_gate_report"]["files"]["canonical"])
    size_path = Path(consumed["futures_position_size"]["files"]["canonical"])
    gate = _load_json(gate_path, "Shapiro journal gate")
    sizing = _load_json(size_path, "Shapiro journal sizing")
    if (
        gate.get("setup_status") != "READY_FOR_PLAN"
        or sizing.get("sizing_status") != "SIZED"
        or gate.get("symbol") != decision["symbol"]
        or sizing.get("symbol") != decision["symbol"]
        or sizing.get("direction") != gate.get("direction")
        or sizing.get("entry") != decision["entry"]
        or sizing.get("stop") != gate.get("invalidation_level")
    ):
        raise ReplayError(
            "Shapiro journal requires matching gate, symbol, direction, entry and stop"
        )
    sources = gate.get("replay_sources", {})
    expected = {"cot_crowding_report", "news_failure_verdict", "price_action_confirmation_report"}
    if set(sources) != expected:
        raise ReplayError("Shapiro journal requires the complete upstream evidence chain")
    # Resolve gate-carried lineage against the actual staging tree before any
    # native state writes. No filenames are assumed and no missing links pass.
    for source in sources.values():
        token = source.get("file", "")
        if not token.startswith("$ARTIFACT/"):
            raise ReplayError("invalid Shapiro evidence link")
        path = _safe_relative(stage, token[len("$ARTIFACT/") :], "Shapiro evidence link")
        if not path.is_file() or _file_sha256(path) != source.get("sha256"):
            raise ReplayError("Shapiro evidence hash mismatch")
    sources = dict(sources)
    for artifact, path in (
        ("contrarian_setup_gate_report", gate_path),
        ("futures_position_size", size_path),
    ):
        sources[artifact] = {
            "file": _kanchi_artifact_link(consumed, artifact, "canonical", stage),
            "sha256": _file_sha256(path),
        }
    store = _repo_module(repo_root, "thesis_store", repo_root / "skills/trader-memory-core/scripts")
    state = work / "state"
    thesis_id = store.register(
        state,
        {
            "ticker": decision["symbol"],
            "thesis_type": "mean_reversion",
            "thesis_statement": decision["thesis_statement"],
            "kill_criteria": [decision["kill_criterion"]],
            "_source_date": decision["as_of"],
            "origin": {
                "skill": "contrarian-setup-gate",
                "output_file": sources["contrarian_setup_gate_report"]["file"],
            },
        },
    )
    store.attach_futures_position(
        state,
        thesis_id,
        str(size_path),
        expected_entry=decision["entry"],
        expected_stop=gate["invalidation_level"],
    )
    producer_skills = {
        "cot_crowding_report": "cot-contrarian-detector",
        "news_failure_verdict": "news-reaction-failure-analyzer",
        "price_action_confirmation_report": "technical-analyst",
        "contrarian_setup_gate_report": "contrarian-setup-gate",
        "futures_position_size": "futures-position-sizer",
    }
    for artifact, source in sorted(sources.items()):
        store.link_report(
            state, thesis_id, producer_skills[artifact], source["file"], decision["as_of"]
        )
    thesis = store.get(state, thesis_id)
    if thesis["status"] != "IDEA" or thesis["entry"].get("actual_price") is not None:
        raise ReplayError("Shapiro replay must never record a fill or promote to ACTIVE")
    # The native store also attaches an ephemeral sizing-report path; replace
    # it with the portable link in the export, retaining the native mutation.
    payload = {
        key: thesis[key]
        for key in (
            "ticker",
            "status",
            "created_at",
            "position",
            "entry",
            "thesis_statement",
            "kill_criteria",
        )
    }
    payload["linked_reports"] = _canonicalize(
        thesis["linked_reports"],
        spec["fixed_timestamp"],
        {str(size_path): sources["futures_position_size"]["file"]},
    )
    payload["sources"] = sources
    payload["manual_review_required"] = True
    payload["execution_authorized"] = False
    payload = _canonicalize(
        payload, spec["fixed_timestamp"], {str(size_path): sources["futures_position_size"]["file"]}
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["contrarian_thesis_entry"]["files"]["canonical"]), payload)
    return artifacts
