"""Executable contract replay tests for Issue #294."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import workflow_replay as replay_module  # noqa: E402
from workflow_replay import (  # noqa: E402
    EXECUTORS,
    FROZEN_DEFERRED_WORKFLOWS,
    ReplayError,
    check_goldens,
    compare_trees,
    coverage_errors,
    execute_replay,
    generate_goldens,
    load_yaml,
    validate_coverage,
    validate_spec,
)

COVERAGE = ROOT / "examples" / "workflows" / "replay-coverage.yaml"
SPEC = ROOT / "examples" / "workflows" / "stockbee-fluency-loop" / "replay.yaml"


def test_coverage_is_complete_and_four_of_eleven_deferrals_are_frozen() -> None:
    summary = validate_coverage(ROOT, COVERAGE)

    assert summary["covered"] == [
        "market-regime-daily",
        "stockbee-20pct-study-daily",
        "stockbee-fluency-loop",
        "trade-memory-loop",
    ]
    assert set(summary["deferred"]) == FROZEN_DEFERRED_WORKFLOWS
    assert len(summary["deferred"]) == 7
    assert summary["variants"] == {
        "market-regime-daily": ["required-only", "full-path"],
        "stockbee-20pct-study-daily": ["required-only", "full-path"],
        "stockbee-fluency-loop": ["required-only", "full-path"],
        "trade-memory-loop": ["required-only", "full-path"],
    }


def test_new_workflow_cannot_be_silently_deferred() -> None:
    coverage = load_yaml(COVERAGE)
    workflow_ids = {path.stem for path in (ROOT / "workflows").glob("*.yaml")} | {"new-workflow"}

    errors = coverage_errors(workflow_ids, coverage)
    assert any("new-workflow" in error and "missing replay coverage" in error for error in errors)

    coverage["deferred"]["new-workflow"] = {
        "issue": 294,
        "reason": "Do not allow new coverage 4/11 deferrals.",
    }
    errors = coverage_errors(workflow_ids, coverage)
    assert any("frozen coverage 4/11 deferred set" in error for error in errors)


def test_pilot_spec_matches_workflow_and_requires_offline_prices() -> None:
    summary = validate_spec(ROOT, SPEC)

    assert summary["workflow_id"] == "stockbee-fluency-loop"
    assert summary["variants"] == ["required-only", "full-path"]
    assert summary["native_steps"] == [1, 2, 3]
    assert summary["manual_contract_steps"] == [4]


def _copy_spec(tmp_path: Path) -> tuple[Path, dict]:
    shutil.copytree(SPEC.parent / "replay-inputs", tmp_path / "replay-inputs")
    payload = load_yaml(SPEC)
    destination = tmp_path / "replay.yaml"
    destination.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return destination, payload


def test_executor_mode_is_fixed_by_registry_not_self_asserted(tmp_path: Path) -> None:
    spec_path, payload = _copy_spec(tmp_path)
    payload["steps"][3]["executor_mode"] = "native_cli"
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="executor_mode"):
        validate_spec(ROOT, spec_path)


def test_duplicate_output_paths_are_rejected(tmp_path: Path) -> None:
    spec_path, payload = _copy_spec(tmp_path)
    payload["steps"][2]["output_files"]["rule_candidates"]["canonical"] = (
        "03_setup_fluency_summary.json"
    )
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="duplicate output path"):
        validate_spec(ROOT, spec_path)


def test_fixed_timestamp_must_be_rfc3339_without_optional_format_extra(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_path, payload = _copy_spec(tmp_path)
    payload["fixed_timestamp"] = "not-a-date"
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(replay_module, "_schema_error_details", lambda *_args: [])

    with pytest.raises(ReplayError, match="RFC 3339 date-time"):
        validate_spec(ROOT, spec_path)


@pytest.mark.parametrize(
    "golden_dir",
    [".", "replay.yaml", "replay-inputs", "replay-inputs/prices.json"],
)
def test_golden_dir_cannot_overlap_replay_sources(
    golden_dir: str,
    tmp_path: Path,
) -> None:
    spec_path, payload = _copy_spec(tmp_path)
    payload["variants"]["required-only"]["golden_dir"] = golden_dir
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="golden_dir.*overlaps replay source"):
        validate_spec(ROOT, spec_path)


@pytest.mark.parametrize(
    ("required_dir", "full_dir"),
    [
        ("same-output", "same-output"),
        ("parent-output", "parent-output/full-path"),
        ("parent-output/required-only", "parent-output"),
    ],
)
def test_variant_golden_dirs_must_be_disjoint(
    required_dir: str,
    full_dir: str,
    tmp_path: Path,
) -> None:
    spec_path, payload = _copy_spec(tmp_path)
    payload["variants"]["required-only"]["golden_dir"] = required_dir
    payload["variants"]["full-path"]["golden_dir"] = full_dir
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="variant golden_dir paths overlap"):
        validate_spec(ROOT, spec_path)


def test_generate_rejects_source_destination_without_deleting_existing_files(
    tmp_path: Path,
) -> None:
    spec_path, payload = _copy_spec(tmp_path)
    payload["variants"]["required-only"]["golden_dir"] = "."
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    sentinel = tmp_path / "keep.txt"
    sentinel.write_bytes(b"keep\n")
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    coverage = load_yaml(COVERAGE)
    coverage["covered"]["stockbee-fluency-loop"]["spec"] = "replay.yaml"
    for workflow_id, entry in coverage["covered"].items():
        if workflow_id != "stockbee-fluency-loop":
            entry["spec"] = str(COVERAGE.parent / entry["spec"])
    coverage_path = tmp_path / "replay-coverage.yaml"
    coverage_path.write_text(yaml.safe_dump(coverage, sort_keys=False), encoding="utf-8")
    before[coverage_path.relative_to(tmp_path)] = coverage_path.read_bytes()

    with pytest.raises(ReplayError, match="golden_dir.*overlaps replay source"):
        generate_goldens(ROOT, coverage_path)

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_required_only_replays_real_cli_and_handoffs_state(tmp_path: Path) -> None:
    output = tmp_path / "required"
    report = execute_replay(ROOT, SPEC, "required-only", output)

    assert report["status"] == "completed"
    assert [step["step"] for step in report["steps"]] == [1, 2, 3]
    assert all(step["executor_mode"] == "native_cli" for step in report["steps"])
    assert report["steps"][2]["gate_policy"] == "record_only"

    ingest = json.loads((output / "01_model_book_ingest.json").read_text(encoding="utf-8"))
    outcome = json.loads((output / "02_matured_setup_outcomes.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "03_setup_fluency_summary.json").read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in (output / "02_model_book.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert ingest["ingest"]["studyable"] == 6
    assert outcome["update"] == {
        "updated": 6,
        "matured": 6,
        "still_pending": 0,
        "skipped_no_prices": 0,
    }
    assert summary["matured_records"] == 6
    assert len(records) == 6
    assert all(record["matured"] for record in records)
    assert not (output / "04_accepted_lessons_log.yaml").exists()

    manifest = yaml.safe_load((output / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["completed_steps"] == [1, 2, 3]
    assert manifest["required_steps_not_executed"] == []
    bundles = {item["artifact_id"]: item["files"] for item in manifest["artifacts"]}
    assert bundles["model_book_ingest"]["state"] == "01_model_book.jsonl"
    assert bundles["matured_setup_outcomes"]["state"] == "02_model_book.jsonl"


def test_full_path_labels_manual_journal_provenance(tmp_path: Path) -> None:
    output = tmp_path / "full"
    report = execute_replay(ROOT, SPEC, "full-path", output)

    assert [step["step"] for step in report["steps"]] == [1, 2, 3, 4]
    assert report["steps"][-1]["executor_mode"] == "manual_contract"
    assert report["steps"][-1]["gate_policy"] == "record_only"
    lessons = yaml.safe_load((output / "04_accepted_lessons_log.yaml").read_text(encoding="utf-8"))
    assert lessons["provenance"]["execution_mode"] == "manual_contract"
    assert lessons["provenance"]["native_trader_memory_validated"] is False
    assert set(lessons["provenance"]["source_sha256"]) == {
        "setup_fluency_summary",
        "rule_candidates",
    }
    assert all(len(digest) == 64 for digest in lessons["provenance"]["source_sha256"].values())
    assert lessons["source_artifacts"] == ["setup_fluency_summary", "rule_candidates"]


def test_halt_manifest_records_status_and_unexecuted_required_steps(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    workflows_dir = repo_root / "workflows"
    workflows_dir.mkdir(parents=True)
    workflow = load_yaml(ROOT / "workflows" / "stockbee-fluency-loop.yaml")
    workflow["steps"][1]["decision_gate"] = True
    (workflows_dir / "stockbee-fluency-loop.yaml").write_text(
        yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8"
    )
    shutil.copytree(
        ROOT / "skills" / "stockbee-setup-fluency-trainer",
        repo_root / "skills" / "stockbee-setup-fluency-trainer",
    )

    spec_dir = repo_root / "examples" / "workflows" / "stockbee-fluency-loop"
    spec_dir.mkdir(parents=True)
    shutil.copytree(SPEC.parent / "replay-inputs", spec_dir / "replay-inputs")
    spec = load_yaml(SPEC)
    spec["steps"][1]["gate_policy"] = "halt"
    spec_path = spec_dir / "replay.yaml"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    output = tmp_path / "halted"
    report = execute_replay(repo_root, spec_path, "full-path", output)

    assert report["status"] == "halted"
    assert [step["step"] for step in report["steps"]] == [1, 2]
    manifest = yaml.safe_load((output / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["status"] == "halted"
    assert manifest["completed_steps"] == [1, 2]
    assert manifest["required_steps_not_executed"] == [
        {
            "step": 3,
            "skill": "stockbee-setup-fluency-trainer",
            "reason": "halted after step 2",
        }
    ]
    assert manifest["optional_steps_skipped"] == []
    assert not (output / "03_setup_fluency_summary.json").exists()
    assert not (output / "04_accepted_lessons_log.yaml").exists()


@pytest.mark.parametrize("mutation", ["delete", "corrupt"])
def test_manual_step_validates_consumed_artifact_content(
    mutation: str,
    tmp_path: Path,
) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")

    def mutate_before_manual(step: int, artifacts: dict[str, dict]) -> None:
        if step != 4:
            return
        rules = Path(artifacts["rule_candidates"]["files"]["canonical"])
        if mutation == "delete":
            rules.unlink()
        else:
            rules.write_text('{"rule_candidates": ["tampered"]}\n', encoding="utf-8")

    with pytest.raises(ReplayError) as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            output,
            before_step=mutate_before_manual,
        )

    assert exc_info.value.completed_steps == [1, 2, 3]
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_manual_approval_rejects_changed_evidence_hashes(tmp_path: Path) -> None:
    approval = load_yaml(SPEC.parent / "replay-inputs" / "accepted_lessons.yaml")
    approval["source_sha256"]["rule_candidates"] = "0" * 64
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    approval_path = input_dir / "stale-approval.yaml"
    approval_path.write_text(yaml.safe_dump(approval, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="source_sha256") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "published",
            input_overrides={"accepted_lessons": approval_path},
        )

    assert exc_info.value.completed_steps == [1, 2, 3]
    assert not (tmp_path / "published").exists()


@pytest.mark.parametrize(
    "lessons",
    ["not-a-list", [{}], [{"lesson_id": "x", "decision": "unknown"}]],
)
def test_manual_lesson_records_must_match_schema(lessons, tmp_path: Path) -> None:
    approval = load_yaml(SPEC.parent / "replay-inputs" / "accepted_lessons.yaml")
    approval["lessons"] = lessons
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    approval_path = input_dir / "invalid-lessons.yaml"
    approval_path.write_text(yaml.safe_dump(approval, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="manual lessons input schema"):
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "published",
            input_overrides={"accepted_lessons": approval_path},
        )


def test_invalid_json_fails_without_publishing(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    invalid = input_dir / "invalid-prices.json"
    invalid.write_text("{not json\n", encoding="utf-8")
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")

    with pytest.raises(ReplayError, match="prices") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            input_overrides={"prices": invalid},
        )

    assert exc_info.value.completed_steps == [1]
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_corrupt_model_book_stops_before_downstream_and_preserves_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")

    def corrupt_after_step(step: int, artifacts: dict[str, dict]) -> None:
        if step == 1:
            state = Path(artifacts["model_book_ingest"]["files"]["state"])
            state.write_text("not-jsonl\n", encoding="utf-8")

    with pytest.raises(ReplayError) as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            after_step=corrupt_after_step,
        )

    assert exc_info.value.completed_steps == [1]
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_executor_missing_declared_file_fails_before_step_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = EXECUTORS["stockbee_fluency_ingest"]

    def omit_state(*args, **kwargs):
        produced = registration.run(*args, **kwargs)
        Path(produced["model_book_ingest"]["files"]["state"]).unlink()
        return produced

    monkeypatch.setitem(
        EXECUTORS,
        "stockbee_fluency_ingest",
        replay_module.ExecutorRegistration(mode="native_cli", run=omit_state),
    )

    with pytest.raises(ReplayError, match="missing staged file") as exc_info:
        execute_replay(ROOT, SPEC, "required-only", tmp_path / "published")

    assert exc_info.value.completed_steps == []
    assert not (tmp_path / "published").exists()


def test_empty_prices_is_explicit_degraded_behavior_without_network(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    empty_prices = input_dir / "prices.json"
    empty_prices.write_text('{"prices": {}}\n', encoding="utf-8")
    output = tmp_path / "degraded"

    report = execute_replay(
        ROOT,
        SPEC,
        "required-only",
        output,
        input_overrides={"prices": empty_prices},
    )

    assert report["network_policy"] == "offline-input-required"
    update = json.loads((output / "02_matured_setup_outcomes.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "03_setup_fluency_summary.json").read_text(encoding="utf-8"))
    assert update["update"]["skipped_no_prices"] == 6
    assert update["update"]["matured"] == 0
    assert summary["pending_records"] == 6


def test_injected_manual_contract_failure_rolls_back_every_published_file(
    tmp_path: Path,
) -> None:
    output = tmp_path / "published"
    output.mkdir()
    before = output / "existing-journal.yaml"
    before.write_bytes(b"lessons: []\n")

    def fail_before_step(step: int, _artifacts: dict[str, dict]) -> None:
        if step == 4:
            raise OSError("injected manual contract failure")

    with pytest.raises(ReplayError, match="manual contract failure") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            output,
            before_step=fail_before_step,
        )

    assert exc_info.value.completed_steps == [1, 2, 3]
    assert before.read_bytes() == b"lessons: []\n"
    assert {path.name for path in output.iterdir()} == {"existing-journal.yaml"}


def test_publish_replacement_failure_restores_original_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "new.txt").write_bytes(b"new\n")
    destination = tmp_path / "destination"
    destination.mkdir()
    original = destination / "old.txt"
    original.write_bytes(b"old\n")
    real_replace = os.replace

    def fail_candidate_commit(source, target):
        source_path = Path(source)
        target_path = Path(target)
        if ".candidate-" in source_path.name and target_path == destination:
            raise OSError("injected replace failure")
        return real_replace(source, target)

    monkeypatch.setattr(replay_module.os, "replace", fail_candidate_commit)

    with pytest.raises(OSError, match="replace failure"):
        replay_module._publish_tree(stage, destination)

    assert original.read_bytes() == b"old\n"
    assert {path.name for path in destination.iterdir()} == {"old.txt"}


def test_post_commit_backup_cleanup_failure_is_non_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "new.txt").write_bytes(b"new\n")
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "old.txt").write_bytes(b"old\n")

    def fail_cleanup(_path: Path) -> None:
        raise OSError("injected backup cleanup failure")

    monkeypatch.setattr(replay_module, "_cleanup_backup", fail_cleanup)

    replay_module._publish_tree(stage, destination)

    assert (destination / "new.txt").read_bytes() == b"new\n"
    assert {path.name for path in destination.iterdir()} == {"new.txt"}


def test_check_writes_structured_report_when_executor_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_execution(*_args, **_kwargs):
        raise ReplayError("injected execution failure", [1])

    monkeypatch.setattr(replay_module, "execute_replay", fail_execution)
    report_path = tmp_path / "report.json"

    differences = check_goldens(ROOT, COVERAGE, report_path)

    assert any("injected execution failure" in difference for difference in differences)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["rows"][0]["status"] == "error"
    assert report["rows"][0]["completed_steps"] == [1]


@pytest.mark.parametrize(
    ("variant", "golden_dir"),
    (("required-only", "sample-run"), ("full-path", "sample-run-full-path")),
)
def test_committed_goldens_are_reproducible_and_not_executor_inputs(
    variant: str,
    golden_dir: str,
    tmp_path: Path,
) -> None:
    generated = tmp_path / "generated"
    execute_replay(ROOT, SPEC, variant, generated)
    golden = SPEC.parent / golden_dir
    assert compare_trees(generated, golden) == []

    altered = tmp_path / "altered-golden"
    shutil.copytree(golden, altered)
    candidate = next(altered.glob("0*_*.json"))
    candidate.write_text("{}\n", encoding="utf-8")
    assert compare_trees(generated, altered)

    regenerated = tmp_path / "regenerated"
    execute_replay(ROOT, SPEC, variant, regenerated)
    assert compare_trees(generated, regenerated) == []
