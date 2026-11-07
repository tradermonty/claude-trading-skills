"""The limited holdings workflow executes the CSV CLI without account access."""

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import workflow_replay as replay

SPEC = ROOT / "examples/workflows/portfolio-holdings-review/replay.yaml"


@pytest.mark.parametrize(
    "variant,golden", [("required-only", "replay-run"), ("full-path", "replay-run-full-path")]
)
def test_holdings_native_roundtrip(tmp_path, variant, golden, monkeypatch):
    # Credentials are neither needed nor forwarded by the native CLI executor.
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    output = tmp_path / "review"
    result = replay.execute_replay(ROOT, SPEC, variant, output)
    assert result["status"] == "completed"
    assert result["steps"][0]["executor_mode"] == "native_cli"
    payload = json.loads((output / "01_holdings_allocation_report.json").read_text())
    assert payload["gross_holdings_value"] == "80"
    assert payload["net_holdings_value"] == "20"
    assert [row["gross_weight_pct"] for row in payload["positions"]] == ["62.5", "37.5"]
    assert payload["provenance"]["source"] == "local_csv"
    assert payload["provenance"]["as_of"] == "2026-10-20T12:00:00+00:00"
    assert replay.compare_trees(output, SPEC.parent / golden) == []
    assert not list(output.rglob("*thesis*"))
    assert "account" not in payload
    assert "private-account" not in json.dumps(payload)


@pytest.mark.parametrize("variant", ["required-only", "full-path"])
@pytest.mark.parametrize("case", ["empty", "header", "duplicate", "quantity", "timestamp"])
def test_invalid_holdings_preserve_published_output(tmp_path, variant, case):
    overrides = {}
    if case == "timestamp":
        path = tmp_path / "context.json"
        path.write_text(json.dumps({"as_of": "2026-10-20", "fictional": True}))
        overrides["review_context"] = path
    else:
        text = (SPEC.parent / "replay-inputs/holdings.csv").read_text()
        if case == "empty":
            text = ""
        elif case == "header":
            text = text.replace("quantity", "wrong_field")
        elif case == "duplicate":
            text += text.splitlines()[1] + "\n"
        else:
            text = text.replace("2.5", "NaN")
        path = tmp_path / "holdings.csv"
        path.write_text(text)
        overrides["holdings_csv"] = path
    published = tmp_path / "published"
    published.mkdir()
    (published / "previous.json").write_bytes(b'{"previous":true}\n')
    with pytest.raises(replay.ReplayError) as error:
        replay.execute_replay(ROOT, SPEC, variant, published, input_overrides=overrides)
    assert error.value.completed_steps == []
    assert [path.name for path in published.iterdir()] == ["previous.json"]
    assert (published / "previous.json").read_bytes() == b'{"previous":true}\n'


def test_native_executor_is_exercised(tmp_path, monkeypatch):
    original = replay._run_cli
    calls = []

    def track(command, *args, **kwargs):
        calls.append(command)
        return original(command, *args, **kwargs)

    monkeypatch.setattr(replay, "_run_cli", track)
    replay.execute_replay(ROOT, SPEC, "required-only", tmp_path / "out")
    assert len(calls) == 1
    assert Path(calls[0][1]).name == "review_csv.py"
    assert "--as-of" in calls[0]
    assert not any("alpaca" in arg.lower() for arg in calls[0])


def test_full_path_prompt_does_not_invent_an_optional_step():
    prompt = (SPEC.parent / "replay-run-full-path/prompt.md").read_text()
    assert "lessons step" not in prompt
    assert "no optional steps" in prompt


def test_workflow_marks_its_cli_inputs_required():
    manifest = yaml.safe_load((ROOT / "workflows/portfolio-holdings-review.yaml").read_text())
    assert {item["id"]: item.get("required") for item in manifest["manual_inputs"]} == {
        "holdings_input": True,
        "source_as_of": True,
    }
