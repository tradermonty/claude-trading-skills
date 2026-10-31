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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/workflows/market-regime-daily"
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


def regular_bytes(path):
    if any(p.is_symlink() for p in (path, *path.absolute().parents)) or not path.is_file():
        raise RunError("Required regular file missing or symlink encountered.")
    return path.read_bytes()


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
        ROOT / "scripts/validate_provenance.py",
        Path(__file__).resolve(),
        EXAMPLE / "replay.yaml",
        *sorted((EXAMPLE / "replay-inputs").glob("*.json")),
    ]
    for skill in SKILLS:
        scripts = ROOT / "skills" / skill / "scripts"
        paths.extend(p for p in sorted(scripts.rglob("*.py")) if "tests" not in p.parts)
    return {str(p.relative_to(ROOT)): digest(regular_bytes(p)) for p in paths}


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
    return {
        "schema_version": 1,
        "run_id": state["run_id"],
        "fictional": True,
        "destination": "trader-memory-core",
        "delivery": "handoff_only",
        "decision": state["steps"][3]["decision"],
        "recorded_at": state["steps"][3]["decision_at"],
        "proposal": state["steps"][3]["output"],
        "limitations": LIMITATIONS,
    }


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
                prior[KINDS[i]] = row["output"]
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
        elif "decision" in gate or "journal" in state or (directory / "journal.json").exists():
            raise RunError("A decision cannot precede its human gate.")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        if isinstance(exc, RunError):
            raise
        raise RunError("Invalid manifest schema or run contract.") from exc


def initialize(directory, include_top_risk, setup):
    _, spec, fixtures, _ = setup
    run_id = str(uuid.uuid4())
    (directory / "inputs").mkdir()
    inputs = {}
    for kind in KINDS:
        path = directory / "inputs" / f"{kind}.json"
        write_new(path, {"run_id": run_id, "fixture": fixtures[kind]})
        inputs[kind] = record(path, directory)
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


def run(directory, *, resume=False, include_top_risk=False, decision=None, status_only=False):
    directory = directory.absolute()
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise RunError("Run directory ancestry must not contain symlinks.")
    if not resume and not status_only:
        if decision is not None:
            raise RunError("A decision requires a paused existing run.")
        # Readiness is checked before allocating a run or writing any artifacts.
        setup = contract()
        directory.mkdir(parents=True, exist_ok=False)
    else:
        if not directory.is_dir():
            raise RunError("Run directory missing.")
        setup = contract()
    with locked(directory):
        if resume or status_only:
            state = load(directory / "manifest.json")
        else:
            state = initialize(directory, include_top_risk, setup)
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
            gate = state["steps"][3]
            if decision not in DECISIONS:
                raise RunError("Invalid exposure posture decision.")
            gate.update(status="COMPLETED", decision=decision, decision_at=now())
            # Treat journal publication as an execution boundary. If interrupted,
            # RUNNING blocks adoption of any partially published journal.
            state["status"] = "RUNNING"
            atomic_json(directory / "manifest.json", state)
            write_new(directory / "journal.json", journal(state))
            state["journal"] = record(directory / "journal.json", directory)
            state["status"] = "COMPLETED"
            checkpoint(directory, state)
            verify(directory, state, setup)
        return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--status", action="store_true", help="Validate and display saved status")
    parser.add_argument("--include-top-risk", action="store_true")
    parser.add_argument("--decision", choices=DECISIONS)
    args = parser.parse_args(argv)
    if args.decision and not args.resume:
        parser.error("--decision requires --resume at a paused gate")
    if args.include_top_risk and (args.resume or args.status):
        parser.error("--include-top-risk is fixed when creating a run")
    try:
        state = run(
            args.run_dir,
            resume=args.resume,
            include_top_risk=args.include_top_risk,
            decision=args.decision,
            status_only=args.status,
        )
        print(f"Fictional offline run {state['run_id']}: {state['status']}")
        for row in state["steps"]:
            print(f"  {row['step']}. {row['skill']}: {row['status']}")
        if state["status"] == "AWAITING_DECISION":
            result = load(args.run_dir / FILES[3])["result"]
            print(json.dumps(result, indent=2))
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
                print("Resume with --run-dir <same-directory> --resume --decision <posture>.")
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
