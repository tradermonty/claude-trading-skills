"""Replay execution, manifest writing, and transactional publication."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from .artifacts import (
    _artifact_file_digests,
    _validate_artifact_files,
    _validate_artifact_provenance,
)
from .common import ReplayError, load_yaml
from .constants import VARIANTS
from .manifest import _validate_runtime_output, validate_spec
from .normalize import _paths_overlap
from .registry import EXECUTORS


def _prompt_text(workflow: Mapping[str, Any], variant: str) -> str:
    if variant == "required-only":
        optional_text = "Skip every optional step."
    elif workflow["id"] == "stockbee-20pct-study-daily":
        optional_text = (
            "Run the optional human-approved lessons step after reviewing the 20% mover "
            "cohort evidence."
        )
    elif workflow["id"] == "trade-memory-loop":
        optional_text = (
            "Run the optional native coaching and fixture-metric evaluation steps before "
            "recording the separately human-approved lesson."
        )
    elif workflow["id"] == "market-regime-daily":
        optional_text = (
            "Include the optional fixture-backed market-top score before running the "
            "native exposure posture CLI."
        )
    elif workflow["id"] == "core-portfolio-weekly":
        optional_text = (
            "Include the optional native dividend-rule review while keeping every "
            "rebalance action proposed, manual, and not submitted."
        )
    elif workflow["id"] == "stockbee-ep-daily":
        optional_text = "Include the fictional earnings and momentum handoffs and reviewed written plan. Keep delayed EP candidates on watch; never submit orders."
    elif workflow["id"] == "kanchi-dividend-weekly":
        optional_text = (
            "Include the optional screeners, tax/account-location advice, and "
            "existing-holding review while keeping every buy proposal manual and "
            "never activating a thesis."
        )
    elif workflow["id"] == "multi-asset-opportunity-daily":
        optional_text = (
            "Include the optional news/catalyst brief while keeping every hypothesis "
            "card manual-review-gated and never wiring forex output to a broker."
        )
    elif workflow["id"] == "earnings-weekly":
        optional_text = (
            "This workflow has no optional steps; run all seven required steps, keep the "
            "chart review and register decisions human-approved, and never submit orders."
        )
    elif workflow["id"] == "portfolio-holdings-review":
        optional_text = "This workflow has no optional steps; run its single required step."
    else:
        optional_text = (
            "Run the optional human-approved lessons step after reviewing the cohort evidence."
        )
    return (
        f"# Prompt: {variant} {workflow['id']} replay\n\n"
        "Replay this workflow with the bundled fictional input data. "
        "This is not investment advice and must not submit orders or call live APIs.\n\n"
        f"{optional_text}\n"
    )


def _write_manifest(
    stage: Path,
    workflow: Mapping[str, Any],
    variant: str,
    report: Mapping[str, Any],
    artifacts: Mapping[str, dict[str, Any]],
) -> None:
    artifact_contract = {item["id"]: item for item in workflow["artifacts"]}
    step_contract = {int(item["step"]): item for item in workflow["steps"]}
    entries = []
    for artifact_id, bundle in artifacts.items():
        contract = artifact_contract[artifact_id]
        step_number = int(contract["produced_by_step"])
        entry = {
            "step": step_number,
            "artifact_id": artifact_id,
            "skill": step_contract[step_number]["skill"],
            "execution_mode": next(
                item["executor_mode"] for item in report["steps"] if item["step"] == step_number
            ),
            "files": {
                role: Path(path).resolve().relative_to(stage.resolve()).as_posix()
                for role, path in bundle["files"].items()
            },
        }
        report_step = next(item for item in report["steps"] if item["step"] == step_number)
        if report_step.get("executor_components"):
            entry["executor_components"] = report_step["executor_components"]
        entries.append(entry)
    entries.sort(key=lambda item: (item["step"], item["artifact_id"]))
    completed_steps = [int(item["step"]) for item in report["steps"]]
    completed = set(completed_steps)
    halted_after = completed_steps[-1] if report["status"] == "halted" else None
    required_steps_not_executed = [
        {
            "step": int(step["step"]),
            "skill": step["skill"],
            "reason": (
                f"halted after step {halted_after}" if halted_after is not None else "not executed"
            ),
        }
        for step in workflow["steps"]
        if not step.get("optional") and int(step["step"]) not in completed
    ]
    skipped = [
        {
            "step": int(step["step"]),
            "skill": step["skill"],
            "reason": "required-only executable replay",
        }
        for step in workflow["steps"]
        if step.get("optional") and variant == "required-only"
    ]
    payload = {
        "workflow_id": workflow["id"],
        "sample_type": variant,
        "status": report["status"],
        "completed_steps": completed_steps,
        "required_steps_not_executed": required_steps_not_executed,
        "illustrative": True,
        "generated_by": "scripts/workflow_replay.py generate",
        "prompt": "prompt.md",
        "network_policy": report["network_policy"],
        "optional_steps_skipped": skipped,
        "artifacts": entries,
    }
    if workflow["id"] == "swing-opportunity-daily":
        payload["execution_evidence_limitations"] = [
            "When step 11 executes, the native discipline CLI consumes checklist answers synthesized from offline fixtures and plan/sizing consistency checks, not human checklist responses.",
            "No live human-approval workflow is exercised and no broker order is submitted; neither fixture GO nor NO_GO authorizes a real trade.",
            "In the bundled full-path fixture, the consistent optional written plan yields fixture GO when step 11 executes; this is not human approval."
            if variant == "full-path"
            else "In required-only replay, the optional written plan is absent, so step 11 returns NO_GO when executed.",
        ]
    if workflow["id"] == "stockbee-ep-daily":
        payload["execution_evidence_limitations"] = [
            "Native circuit breaker, EP classification and position sizing consume fictional offline inputs; live providers and news verification are not executed.",
            "Chart confirmation and execution checklist are human-approved fixtures; native trader-memory APIs persist IDEA only in disposable state, without fills or order authorization.",
            "Native discipline consumes the account history; delayed EP candidates remain non-actionable watch entries.",
            "Full path includes manual-contract earnings/momentum screens and a written plan."
            if variant == "full-path"
            else "Optional earnings/momentum screens and written plan are skipped; the absent written plan forces NO_GO.",
        ]
    if workflow["id"] == "earnings-weekly":
        payload["execution_evidence"] = {
            "native_earnings_trade_analyzer_cli_executed": True,
            "native_pead_screener_cli_executed": True,
            "native_trader_memory_register_executed": True,
            "broker_or_live_api_calls": False,
            "execution_authorized": False,
        }
        payload["execution_evidence_limitations"] = [
            "Steps 2-3 execute the real earnings-trade-analyzer and pead-screener CLIs unchanged; only their FMPClient is replaced by a read-only reader of a fictional local fixture (scripts/replay_offline_fmp_cli.py). Live FMP responses, field drift, and rate limits are not exercised.",
            "Step 4 is a human-approved fictional chart review bound to the PEAD screener output; no chart image is analyzed.",
            "Step 6 calls the native trader-memory-core pead-screener ingest and link_report APIs on disposable temporary state; the thesis stays IDEA and no fill is recorded.",
            "Step 7 consumes checklist answers synthesized from offline fixtures and plan/sizing consistency checks, not human checklist responses; a fixture GO is not an order approval.",
            "Both variants execute the same seven required steps because this workflow has no optional steps.",
            "The replay does not measure real FMP API volume: the offline fixture has five symbols, while a live 28-day window makes one calendar request per day plus one profile request per reporting symbol. The explicit --max-api-calls value is not a measured requirement.",
        ]
    if workflow["id"] == "shapiro-contrarian":
        payload["execution_evidence_limitations"] = [
            "Steps 1-3 validate human-approved fictional report contracts; no CFTC/FMP/news provider or live chart analysis is executed.",
            "Steps 4-5 execute the native contrarian gate and futures sizing CLIs on those actual handoffs.",
            "Step 6 uses native register, attach_futures_position, get and link_report APIs in disposable state. It preserves IDEA without broker fills or order authorization.",
            "Both variants execute the same six required steps because this workflow has no optional steps.",
        ]
    if workflow["id"] == "trade-memory-loop":
        payload["execution_evidence_limitations"] = [
            "Root-cause and lesson decisions are human-approved fixtures bound by SHA-256.",
            "Backtest Expert evaluates bundled aggregate metrics; it does not run a strategy backtest.",
            "Only staged temporary trader-memory state is mutated; no user state is accessed.",
        ]
    elif workflow["id"] == "market-regime-daily":
        payload["execution_evidence_limitations"] = [
            "Breadth, uptrend, and top-risk provider fetches are not executed.",
            "Individual component calculators and live API failure paths are not executed.",
            "Native scorer and JSON report APIs consume complete fictional component fixtures.",
            "INSUFFICIENT_EVIDENCE is not a literal contract for these skills; unavailable fixture components fail closed before publication.",
            "Exposure Coach runs as the native CLI against the generated artifact handoffs.",
        ]
    elif workflow["id"] == "core-portfolio-weekly":
        payload["execution_evidence"] = {
            "native_portfolio_manager_executed": False,
            "native_trader_memory_append_executed": False,
            "native_dividend_rule_api_executed": any(
                row["executor"] == "core_portfolio_dividend" for row in report["steps"]
            ),
            "broker_or_live_api_calls": False,
            "execution_authorized": False,
        }
        payload["execution_evidence_limitations"] = [
            "Holdings, target allocation, rebalance, and journal decisions are fictional manual contracts sealed to upstream artifact SHA-256 values.",
            "Allocation and projected-weight arithmetic is recomputed, but Portfolio Manager has no offline native decision API and is not claimed as executed.",
            "The optional full path calls the native Kanchi dividend rule API after joining enrichment to the step-1 snapshot identity.",
            "The journal is staged transactionally; Trader Memory Core is not mutated and no broker order is placed or authorized.",
        ]
    elif workflow["id"] == "kanchi-dividend-weekly":
        payload["execution_evidence"] = {
            "native_kanchi_verdict_api_executed": any(
                row["executor"] == "kanchi_underwrite" for row in report["steps"]
            ),
            "native_tax_planning_cli_executed": any(
                row["executor"] == "kanchi_tax_advice" for row in report["steps"]
            ),
            "native_review_queue_cli_executed": any(
                row["executor"] == "kanchi_review_queue" for row in report["steps"]
            ),
            "native_trader_memory_register_executed": any(
                row["executor"] == "kanchi_register_thesis" for row in report["steps"]
            ),
            "broker_or_live_api_calls": False,
            "execution_authorized": False,
        }
        limitations = [
            "The live kanchi_candidates producer (build_entry_signals.py) requires FMP data and is not executed; step 3 recomputes the native verdict tier from fixture evidence.",
            "stock_memo is generated by the offline build_sop_plan.py planning CLI, not the hand-written stock-note-template one-pager.",
        ]
        if any(row["executor"] == "kanchi_high_yield_screen" for row in report["steps"]):
            limitations.append(
                "Screener steps 1-2 are human-approved candidate-list fixtures; no FINVIZ or FMP screener is called."
            )
        if any(row["executor"] == "kanchi_tax_advice" for row in report["steps"]):
            limitations.append(
                "Step 4 calls the native tax-planning CLI on fictional holdings; account-location advice remains advisory."
            )
        if any(row["executor"] == "kanchi_review_queue" for row in report["steps"]):
            limitations.append(
                "Step 5 calls the native dividend review-queue CLI on fictional holdings; a WARN/REVIEW never triggers an automatic sell."
            )
        limitations.append(
            "Step 6 calls the native trader-memory-core ingest and link_report APIs on disposable temporary state; every thesis stays IDEA and no order is placed or authorized."
        )
        payload["execution_evidence_limitations"] = limitations
    elif workflow["id"] == "multi-asset-opportunity-daily":
        payload["execution_evidence"] = {
            "native_macro_regime_api_executed": any(
                row["executor"] == "multi_macro_regime" for row in report["steps"]
            ),
            "native_hypothesis_cli_executed": any(
                row["executor"] == "multi_hypotheses" for row in report["steps"]
            ),
            "native_position_sizer_cli_executed": any(
                row["executor"] == "multi_position_size" for row in report["steps"]
            ),
            "native_trader_memory_register_executed": any(
                row["executor"] == "multi_register" for row in report["steps"]
            ),
            "broker_or_live_api_calls": False,
            "execution_authorized": False,
        }
        limitations = [
            "Step 1 recomputes the native macro-regime composite, regime classification, and consistency check from fixture component results; provider fetches and calculator histories are not executed.",
            "Step 2 themes are a human-approved fixture bound to the replayed regime brief; no FINVIZ fetch is executed.",
            "Step 4 runs the native trade-hypothesis-ideator CLI on a fixture bundle bound by SHA-256 to the replayed upstream artifacts; hypothesis accept/reject is a human gate decision.",
            "Step 5 sizes actionable cards with the native position-sizer CLI on fictional entries, stops, and risk; portfolio caps are fixture-enforced.",
            "Step 6 calls the native trader-memory-core ingest and link_report APIs on disposable temporary state; every thesis stays IDEA and no order is placed or authorized. Forex output is research-only and never wired to a broker.",
        ]
        payload["execution_evidence_limitations"] = limitations
    (stage / "manifest.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n"
    )
    (stage / "prompt.md").write_text(
        _prompt_text(workflow, variant), encoding="utf-8", newline="\n"
    )


def _cleanup_backup(path: Path) -> None:
    shutil.rmtree(path)


def _publish_tree(stage: Path, destination: Path) -> None:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Defense in depth mirroring _publish_trees_transactionally: today
    # _validate_runtime_output rejects a non-directory output_dir before
    # execution, and execute_replay is the only call site, so this branch is
    # unreachable in practice. It guards against a file destination if that
    # invariant is ever relaxed or this function is called from elsewhere.
    if destination.exists() and not destination.is_dir():
        raise ReplayError(f"publish destination must be a directory: {destination}")
    candidate = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.candidate-", dir=destination.parent)
    )
    backup_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.backup-", dir=destination.parent)
    )
    backup = backup_root / "previous"
    committed = False
    try:
        shutil.copytree(stage, candidate, dirs_exist_ok=True)
        had_destination = destination.exists()
        if had_destination:
            os.replace(destination, backup)
        try:
            os.replace(candidate, destination)
        except Exception:
            if had_destination and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        committed = True
    finally:
        if candidate.exists():
            shutil.rmtree(candidate)
        if committed:
            try:
                _cleanup_backup(backup_root)
            except OSError:
                # Publication already committed. Retain the uniquely named
                # backup for manual cleanup rather than report a false failure.
                pass
        elif backup_root.exists() and not backup.exists():
            shutil.rmtree(backup_root)


def _publish_trees_transactionally(staged_trees: list[tuple[Path, Path]]) -> None:
    """Publish multiple generated trees as one rollback-capable transaction."""
    destinations = [destination.resolve() for _stage, destination in staged_trees]
    for index, destination in enumerate(destinations):
        for other in destinations[index + 1 :]:
            if _paths_overlap(destination, other):
                raise ReplayError(f"transaction destinations overlap: {destination} and {other}")

    prepared: list[dict[str, Any]] = []
    succeeded = False
    try:
        for stage, raw_destination in staged_trees:
            destination = raw_destination.resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not destination.is_dir():
                raise ReplayError(f"transaction destination must be a directory: {destination}")
            candidate = Path(
                tempfile.mkdtemp(prefix=f".{destination.name}.candidate-", dir=destination.parent)
            )
            backup_root = Path(
                tempfile.mkdtemp(prefix=f".{destination.name}.backup-", dir=destination.parent)
            )
            entry = {
                "destination": destination,
                "candidate": candidate,
                "backup_root": backup_root,
                "backup": backup_root / "previous",
                "backup_moved": False,
                "candidate_committed": False,
            }
            prepared.append(entry)
            shutil.copytree(stage, candidate, dirs_exist_ok=True)

        for entry in prepared:
            destination = entry["destination"]
            if destination.exists():
                os.replace(destination, entry["backup"])
                entry["backup_moved"] = True
            os.replace(entry["candidate"], destination)
            entry["candidate_committed"] = True
        succeeded = True
    except Exception as exc:
        rollback_errors: list[str] = []
        for entry in reversed(prepared):
            destination = entry["destination"]
            try:
                if entry["candidate_committed"] and destination.exists():
                    shutil.rmtree(destination)
                if entry["backup_moved"] and entry["backup"].exists():
                    os.replace(entry["backup"], destination)
            except Exception as rollback_exc:  # pragma: no cover - catastrophic filesystem path
                rollback_errors.append(f"{destination}: {rollback_exc}")
        if rollback_errors:
            raise ReplayError(
                f"golden publication failed ({exc}); rollback also failed: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    finally:
        for entry in prepared:
            candidate = entry["candidate"]
            backup_root = entry["backup_root"]
            backup = entry["backup"]
            if candidate.exists():
                shutil.rmtree(candidate)
            if succeeded:
                try:
                    _cleanup_backup(backup_root)
                except OSError:
                    pass
            elif backup_root.exists() and not backup.exists():
                shutil.rmtree(backup_root)


def execute_replay(
    repo_root: Path,
    spec_path: Path,
    variant: str,
    output_dir: Path,
    *,
    input_overrides: Mapping[str, Path] | None = None,
    before_step: Callable[[int, dict[str, dict[str, Any]]], None] | None = None,
    after_step: Callable[[int, dict[str, dict[str, Any]]], None] | None = None,
) -> dict[str, Any]:
    validation = validate_spec(repo_root, spec_path)
    if variant not in VARIANTS:
        raise ReplayError(f"unknown replay variant: {variant}")
    spec = load_yaml(spec_path)
    workflow = load_yaml(repo_root / "workflows" / f"{spec['workflow_id']}.yaml")
    workflow_steps = {int(item["step"]): item for item in workflow["steps"]}
    spec_steps = {int(item["step"]): item for item in spec["steps"]}
    provenance_requirements = {
        artifact_id: number
        for number, step in spec_steps.items()
        for artifact_id in step.get("required_provenance", [])
    }
    inputs = dict(validation["inputs"])
    for name, path in (input_overrides or {}).items():
        if name not in inputs:
            raise ReplayError(f"unknown input override: {name}")
        inputs[name] = Path(path).resolve()
    _validate_runtime_output(repo_root, spec_path, spec, inputs, output_dir)

    completed_steps: list[int] = []
    artifacts: dict[str, dict[str, Any]] = {}
    sealed_artifact_digests: dict[str, str] = {}
    step_reports: list[dict[str, Any]] = []
    status = "completed"
    with tempfile.TemporaryDirectory(prefix="workflow-replay-") as temp_name:
        temp = Path(temp_name)
        stage = temp / "published"
        stage.mkdir()
        try:
            for number in spec["variants"][variant]["enabled_steps"]:
                workflow_step = workflow_steps[number]
                replay_step = spec_steps[number]
                if before_step:
                    before_step(number, artifacts)
                _validate_artifact_files(stage, artifacts, "artifact store")
                consumed: dict[str, dict[str, Any]] = {}
                for artifact_id in workflow_step.get("consumes") or []:
                    if artifact_id in artifacts:
                        consumed[artifact_id] = artifacts[artifact_id]
                        continue
                    contract = next(
                        item for item in workflow["artifacts"] if item["id"] == artifact_id
                    )
                    producer = workflow_steps[int(contract["produced_by_step"])]
                    if not producer.get("optional"):
                        raise ReplayError(
                            f"step {number} missing required consumed artifact {artifact_id!r}",
                            completed_steps,
                        )
                _validate_artifact_provenance(
                    consumed, provenance_requirements, f"step {number} consumed"
                )
                executor_name = replay_step["executor"]
                registration = EXECUTORS.get(executor_name)
                if registration is None:
                    raise ReplayError(f"unknown executor {executor_name!r}", completed_steps)
                step_work = temp / "work" / f"step-{number}"
                step_work.mkdir(parents=True)
                produced = registration.run(
                    repo_root,
                    spec,
                    replay_step,
                    inputs,
                    consumed,
                    step_work,
                    stage,
                )
                if set(produced) != set(workflow_step.get("produces") or []):
                    raise ReplayError(
                        f"step {number} executor produced {sorted(produced)}, expected "
                        f"{sorted(workflow_step.get('produces') or [])}",
                        completed_steps,
                    )
                candidate_artifacts = dict(artifacts)
                candidate_artifacts.update(produced)
                _validate_artifact_files(stage, candidate_artifacts, f"step {number} output")
                _validate_artifact_provenance(
                    produced, provenance_requirements, f"step {number} output"
                )
                produced_digests = _artifact_file_digests(produced)
                duplicate_seals = set(produced_digests) & set(sealed_artifact_digests)
                if duplicate_seals:
                    raise ReplayError(
                        f"step {number} replaced sealed artifacts: {sorted(duplicate_seals)}",
                        completed_steps,
                    )
                sealed_artifact_digests.update(produced_digests)
                artifacts = candidate_artifacts
                completed_steps.append(number)
                step_report = {
                    "step": number,
                    "skill": workflow_step["skill"],
                    "executor": executor_name,
                    "executor_mode": registration.mode,
                    "gate_policy": replay_step["gate_policy"],
                    "consumed": sorted(consumed),
                    "produced": sorted(produced),
                }
                if registration.components:
                    step_report["executor_components"] = list(registration.components)
                step_reports.append(step_report)
                if after_step:
                    after_step(number, artifacts)
                if replay_step["gate_policy"] == "halt":
                    status = "halted"
                    break

            _validate_artifact_files(stage, artifacts, "final artifact store")
            _validate_artifact_provenance(
                artifacts, provenance_requirements, "final artifact store"
            )
            final_digests = _artifact_file_digests(artifacts)
            changed_artifacts = sorted(
                artifact_id
                for artifact_id in set(final_digests) | set(sealed_artifact_digests)
                if final_digests.get(artifact_id) != sealed_artifact_digests.get(artifact_id)
            )
            if changed_artifacts:
                raise ReplayError(
                    f"final artifact integrity mismatch: {changed_artifacts}", completed_steps
                )

            report = {
                "schema_version": 1,
                "workflow_id": spec["workflow_id"],
                "variant": variant,
                "status": status,
                "network_policy": "offline-input-required",
                "steps": step_reports,
                "artifact_ids": sorted(artifacts),
            }
            _write_manifest(stage, workflow, variant, report, artifacts)
            _publish_tree(stage, output_dir)
            return report
        except ReplayError as exc:
            if not exc.completed_steps:
                exc.completed_steps = list(completed_steps)
            raise
        except Exception as exc:
            raise ReplayError(f"replay failed: {exc}", completed_steps) from exc
