"""Shared coverage accounting and consumer handoff regressions (#711)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import workflow_replay as replay

SPEC = ROOT / "examples/workflows/market-regime-daily/replay.yaml"


def block(**changes):
    value = {
        "schema_version": "1.0",
        "universe_size": 2,
        "evaluated": 0,
        "not_evaluated": 2,
        "not_evaluated_reasons": {"missing_data": 2},
        "verdict": "not_evaluable",
    }
    value.update(changes)
    return value


def contract():
    spec = importlib.util.spec_from_file_location(
        "coverage_contract", ROOT / "scripts/evaluation_coverage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "changes",
    [
        {"evaluated": True},
        {"universe_size": -1},
        {"not_evaluated": 1},
        {"verdict": "complete"},
        {"not_evaluated_reasons": {"missing_data": 1}},
        {"not_evaluated_reasons": {"missing_data": True}},
        {"schema_version": "future"},
    ],
)
def test_invalid_accounting_is_rejected(changes):
    assert contract().validate_evaluation_coverage(block(**changes))


def test_standalone_copies_match_shared_contract():
    source = (ROOT / "scripts/evaluation_coverage.py").read_bytes()
    for skill in ("vcp-screener", "exposure-coach"):
        assert (ROOT / "skills" / skill / "scripts/evaluation_coverage.py").read_bytes() == source


@pytest.mark.parametrize("verdict,evaluated", [("not_evaluable", 0), ("partial", 1)])
def test_replay_excludes_unavailable_breadth_without_raising_confidence(
    monkeypatch,
    tmp_path,
    verdict,
    evaluated,
):
    replay.execute_replay(ROOT, SPEC, "full-path", tmp_path / "baseline")
    baseline = json.loads((tmp_path / "baseline/04_exposure_decision.json").read_text())
    original = replay._market_analysis

    def with_coverage(*args, **kwargs):
        payload = original(*args, **kwargs)
        if args[1] == "breadth":
            payload["evaluation_coverage"] = block(
                evaluated=evaluated,
                not_evaluated=2 - evaluated,
                not_evaluated_reasons={"missing_data": 2 - evaluated},
                verdict=verdict,
            )
        return payload

    monkeypatch.setattr(replay, "_market_analysis", with_coverage)
    replay.execute_replay(ROOT, SPEC, "full-path", tmp_path / "unavailable")
    decision = json.loads((tmp_path / "unavailable/04_exposure_decision.json").read_text())
    assert "breadth" in decision["inputs_missing"]
    assert "breadth" not in decision["inputs_provided"]
    assert "breadth_score" not in decision["component_scores"]
    assert baseline["confidence"] == "MEDIUM"
    assert decision["confidence"] == "LOW"
    confidence = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    assert confidence[decision["confidence"]] <= confidence[baseline["confidence"]]


def test_replay_rejects_inconsistent_coverage_before_replacing_publication(monkeypatch, tmp_path):
    original = replay._market_analysis

    def inconsistent(*args, **kwargs):
        payload = original(*args, **kwargs)
        payload["evaluation_coverage"] = block(verdict="complete")
        return payload

    monkeypatch.setattr(replay, "_market_analysis", inconsistent)
    published = tmp_path / "published"
    published.mkdir()
    marker = published / "keep.txt"
    marker.write_text("unchanged")
    with pytest.raises(replay.ReplayError, match="evaluation_coverage"):
        replay.execute_replay(ROOT, SPEC, "required-only", published)
    assert list(published.iterdir()) == [marker]
    assert marker.read_text() == "unchanged"
