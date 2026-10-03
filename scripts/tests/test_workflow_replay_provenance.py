"""Issue #297: provenance failures stop handoffs and preserve published output."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import workflow_replay as replay


def _block():
    return {
        "schema_version": "1.0",
        "provider": "fictional-fixture",
        "endpoint": "synthetic-holdings",
        "retrieved_at": "2026-10-03T00:00:00Z",
        "as_of": "2026-10-02",
        "timezone": "America/New_York",
        "adjusted": False,
        "point_in_time": False,
        "survivorship_free": False,
        "corporate_actions_handled": False,
    }


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    def make(payload, *, suffix=".json", required=True, halt=False, optional=False):
        repo = tmp_path / "repo"
        spec_dir = repo / "examples" / "test"
        (repo / "workflows").mkdir(parents=True)
        (spec_dir / "inputs").mkdir(parents=True)
        (spec_dir / "inputs" / "dummy.json").write_text("{}")
        steps = [
            {
                "step": 1,
                "skill": "fixture-producer",
                "optional": optional,
                "decision_gate": halt,
                "produces": ["source"],
            },
            {
                "step": 2,
                "skill": "fixture-consumer",
                "consumes": [] if optional else ["source"],
                "produces": ["receipt"],
            },
        ]
        workflow = {
            "id": "test-provenance",
            "steps": steps,
            "artifacts": [
                {"id": "source", "produced_by_step": 1},
                {"id": "receipt", "produced_by_step": 2},
            ],
        }
        (repo / "workflows" / "test-provenance.yaml").write_text(yaml.safe_dump(workflow))
        spec = {
            "schema_version": 1,
            "workflow_id": "test-provenance",
            "fixed_timestamp": "2026-10-03T00:00:00Z",
            "inputs": {"dummy": "inputs/dummy.json"},
            "steps": [
                {
                    "step": 1,
                    "executor": "test_provenance_producer",
                    "executor_mode": "manual_contract",
                    "gate_policy": "halt" if halt else "continue",
                    "output_files": {
                        "source": {"canonical": f"source{suffix}", "companion": "source.md"}
                    },
                },
                {
                    "step": 2,
                    "executor": "test_provenance_consumer",
                    "executor_mode": "manual_contract",
                    "gate_policy": "continue",
                    "output_files": {"receipt": {"canonical": "receipt.json"}},
                },
            ],
            "variants": {
                "required-only": {
                    "enabled_steps": [2] if optional else [1, 2],
                    "golden_dir": "golden",
                },
                "full-path": {"enabled_steps": [1, 2], "golden_dir": "golden-full"},
            },
        }
        if required:
            spec["steps"][0]["required_provenance"] = ["source"]
        spec_path = spec_dir / "replay.yaml"
        spec_path.write_text(yaml.safe_dump(spec))
        consumed = []

        def producer(repo_root, spec, step, inputs, handoffs, work, stage):
            artifacts = replay._artifact_paths(stage, step["output_files"])
            path = Path(artifacts["source"]["files"]["canonical"])
            content = json.dumps(payload) if suffix == ".json" else yaml.safe_dump(payload)
            path.write_text(content)
            Path(artifacts["source"]["files"]["companion"]).write_text("Fictional fixture")
            return artifacts

        def consumer(repo_root, spec, step, inputs, handoffs, work, stage):
            if "source" in handoffs:
                path = Path(handoffs["source"]["files"]["canonical"])
                content = path.read_text()
                consumed.append(
                    json.loads(content) if suffix == ".json" else yaml.safe_load(content)
                )
            artifacts = replay._artifact_paths(stage, step["output_files"])
            Path(artifacts["receipt"]["files"]["canonical"]).write_text('{"received": true}')
            return artifacts

        for name, function in [
            ("test_provenance_producer", producer),
            ("test_provenance_consumer", consumer),
        ]:
            monkeypatch.setitem(
                replay.EXECUTORS,
                name,
                replay.ExecutorRegistration(mode="manual_contract", run=function),
            )
        output = tmp_path / "published"
        output.mkdir()
        (output / "sentinel.txt").write_text("previous publication")
        return repo, spec_path, output, consumed

    return make


@pytest.mark.parametrize("suffix", [".json", ".yaml", ".yml"])
@pytest.mark.parametrize("required", [True, False])
def test_valid_provenance_reaches_consumer_and_publication(scenario, suffix, required):
    payload = {"data_provenance": _block(), "value": 1}
    repo, spec, output, consumed = scenario(payload, suffix=suffix, required=required)
    report = replay.execute_replay(repo, spec, "required-only", output)
    assert report["status"] == "completed"
    assert consumed == [payload]
    assert (output / f"source{suffix}").is_file()
    assert not (output / "sentinel.txt").exists()


@pytest.mark.parametrize(
    "payload,required",
    [
        ({}, True),
        ({"data_provenance": None}, True),
        ([], True),
        ({"data_provenance": {**_block(), "schema_version": "2.0"}}, True),
        ({"data_provenance": {**_block(), "adjusted": "false"}}, False),
        ({"data_provenance": {**_block(), "timezone": "not-a-zone"}}, False),
    ],
)
@pytest.mark.parametrize("suffix", [".json", ".yaml"])
def test_invalid_producer_never_completes_or_runs_consumer(scenario, payload, required, suffix):
    repo, spec, output, consumed = scenario(payload, required=required, suffix=suffix)
    with pytest.raises(
        replay.ReplayError, match="step 1 output artifact 'source'.*|data_provenance"
    ) as error:
        replay.execute_replay(repo, spec, "required-only", output)
    assert error.value.completed_steps == []
    assert consumed == []
    assert list(output.iterdir()) == [output / "sentinel.txt"]
    assert (output / "sentinel.txt").read_text() == "previous publication"


@pytest.mark.parametrize("payload", [{}, [], "legacy scalar"])
def test_legacy_artifacts_without_provenance_remain_compatible(scenario, payload):
    repo, spec, output, consumed = scenario(payload, required=False)
    replay.execute_replay(repo, spec, "required-only", output)
    assert consumed == [payload]


@pytest.mark.parametrize("mutation", ["missing_block", "invalid_block", "missing_canonical"])
@pytest.mark.parametrize("boundary", ["consumer", "final", "halt"])
def test_required_provenance_survives_hooks_at_every_boundary(scenario, mutation, boundary):
    repo, spec, output, consumed = scenario({"data_provenance": _block()}, halt=boundary == "halt")

    def mutate(step, artifacts):
        if (boundary == "consumer" and step != 2) or (
            boundary != "consumer" and step != (1 if boundary == "halt" else 2)
        ):
            return
        files = artifacts["source"]["files"]
        if mutation == "missing_canonical":
            del files["canonical"]  # Companion survives the path/existence gate.
        else:
            payload = (
                {} if mutation == "missing_block" else {"data_provenance": {"schema_version": "99"}}
            )
            Path(files["canonical"]).write_text(json.dumps(payload))

    hook = {"before_step": mutate} if boundary == "consumer" else {"after_step": mutate}
    with pytest.raises(replay.ReplayError, match="data_provenance") as error:
        replay.execute_replay(repo, spec, "required-only", output, **hook)
    assert error.value.completed_steps == ([1, 2] if boundary == "final" else [1])
    assert len(consumed) == (1 if boundary == "final" else 0)
    assert list(output.iterdir()) == [output / "sentinel.txt"]


@pytest.mark.parametrize("declaration", [["unknown"], ["source", "source"], [""]])
def test_bad_spec_declarations_fail_before_execution(scenario, declaration):
    repo, spec, output, consumed = scenario({"data_provenance": _block()})
    payload = yaml.safe_load(spec.read_text())
    payload["steps"][0]["required_provenance"] = declaration
    spec.write_text(yaml.safe_dump(payload))
    with pytest.raises(replay.ReplayError):
        replay.execute_replay(repo, spec, "required-only", output)
    assert consumed == []
    assert (output / "sentinel.txt").is_file()


@pytest.mark.parametrize("canonical", [None, "source.md"])
def test_required_spec_needs_structured_canonical(scenario, canonical):
    repo, spec, output, consumed = scenario({"data_provenance": _block()})
    payload = yaml.safe_load(spec.read_text())
    files = payload["steps"][0]["output_files"]["source"]
    if canonical is None:
        del files["canonical"]
    else:
        files["canonical"] = canonical
    spec.write_text(yaml.safe_dump(payload))
    with pytest.raises(replay.ReplayError, match="canonical JSON/YAML"):
        replay.execute_replay(repo, spec, "required-only", output)
    assert consumed == []


def test_unexecuted_optional_producer_does_not_require_artifact(scenario):
    repo, spec, output, consumed = scenario({}, optional=True)
    report = replay.execute_replay(repo, spec, "required-only", output)
    assert [row["step"] for row in report["steps"]] == [2]
    assert consumed == []


@pytest.mark.parametrize("suffix,text", [(".json", "{"), (".yaml", "[unclosed")])
def test_parse_errors_preserve_existing_publication(scenario, suffix, text):
    repo, spec, output, consumed = scenario({"data_provenance": _block()}, suffix=suffix)
    original = replay.EXECUTORS["test_provenance_producer"].run

    def malformed(*args):
        artifacts = original(*args)
        Path(artifacts["source"]["files"]["canonical"]).write_text(text)
        return artifacts

    # Fixture restores the registration via its original monkeypatch teardown.
    replay.EXECUTORS["test_provenance_producer"] = replay.ExecutorRegistration(
        mode="manual_contract", run=malformed
    )
    with pytest.raises(replay.ReplayError, match="cannot parse canonical provenance payload"):
        replay.execute_replay(repo, spec, "required-only", output)
    assert consumed == []
    assert (output / "sentinel.txt").is_file()
