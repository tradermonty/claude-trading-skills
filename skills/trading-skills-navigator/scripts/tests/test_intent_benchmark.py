"""Cross-persona routing benchmark and shadowing contract tests."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from intent_benchmark import (  # noqa: E402
    BenchmarkError,
    audit_personas,
    evaluate_benchmark,
    load_benchmark,
)
from recommend import PERSONAS, Persona  # noqa: E402

BENCHMARK_PATH = SCRIPT_DIR.parents[0] / "assets" / "intent_benchmark_v1.json"


def test_versioned_bilingual_corpus_is_complete(repo_metadata: dict) -> None:
    benchmark = load_benchmark(BENCHMARK_PATH)
    report = evaluate_benchmark(benchmark, repo_metadata)

    assert benchmark["schema_version"] == 1
    assert len(benchmark["cases"]) >= 208
    assert {case["language"] for case in benchmark["cases"]} == {"en", "ja"}
    assert {case["label"] for case in benchmark["cases"]} >= {
        "positive",
        "hard_negative",
        "ambiguous",
        "no_api",
        "honest_gap",
    }
    assert report["metrics"] == {
        "candidate_precision": 1.0,
        "candidate_recall": 1.0,
        "selected_accuracy": 1.0,
        "workflow_accuracy": 1.0,
    }
    assert report["failures"] == []


def test_every_persona_and_workflow_has_bilingual_guards(repo_metadata: dict) -> None:
    report = evaluate_benchmark(load_benchmark(BENCHMARK_PATH), repo_metadata)
    expected_personas = {persona.name for persona in PERSONAS}
    expected_workflows = {workflow["id"] for workflow in repo_metadata["workflows"]}

    assert set(report["coverage"]["personas"]) == expected_personas
    for coverage in report["coverage"]["personas"].values():
        assert coverage["positive_languages"] == ["en", "ja"]
        assert coverage["hard_negative_languages"] == ["en", "ja"]
        assert coverage["neighbor_cases"] >= 1
    assert set(report["coverage"]["workflows"]) == expected_workflows
    for coverage in report["coverage"]["workflows"].values():
        assert coverage["positive_cases"] >= 1
        assert coverage["hard_negative_cases"] >= 1


def test_metamorphic_contract_has_required_language_specific_coverage(
    repo_metadata: dict,
) -> None:
    report = evaluate_benchmark(load_benchmark(BENCHMARK_PATH), repo_metadata)
    assert set(report["coverage"]["transformations"]["en"]) >= {
        "case",
        "punctuation",
        "word_order",
        "orthographic",
    }
    assert set(report["coverage"]["transformations"]["ja"]) >= {
        "punctuation",
        "word_order",
        "orthographic",
        "ja_particle",
        "ja_conjugation",
    }


def test_shadowing_contract_matches_persona_table() -> None:
    benchmark = load_benchmark(BENCHMARK_PATH)
    report = audit_personas(PERSONAS, benchmark["shadowing_contracts"])
    assert report["contradictions"] == []
    assert report["duplicate_persona_names"] == []
    assert report["unregistered_overlaps"] == []
    assert report["stale_contracts"] == []


def test_shadowing_contract_requires_a_representative_ambiguous_case(
    repo_metadata: dict,
) -> None:
    benchmark = deepcopy(load_benchmark(BENCHMARK_PATH))
    benchmark["shadowing_contracts"][0]["ambiguous_case_ids"] = ["amb-kanchi-en"]
    report = evaluate_benchmark(benchmark, repo_metadata)
    assert any("does not cover both" in failure for failure in report["failures"])


def test_shadowing_contract_requires_its_winner_to_be_selected(
    repo_metadata: dict,
) -> None:
    benchmark = deepcopy(load_benchmark(BENCHMARK_PATH))
    for case in benchmark["cases"]:
        if case["id"] == "amb-swing-en":
            case["expected_selected_persona"] = "swing-trader"
    report = evaluate_benchmark(benchmark, repo_metadata)
    assert any("does not select contract winner" in failure for failure in report["failures"])


def test_hard_negative_must_use_a_versioned_neighbor_contract(repo_metadata: dict) -> None:
    benchmark = deepcopy(load_benchmark(BENCHMARK_PATH))
    for case in benchmark["cases"]:
        if case["id"] in {"research-n01", "research-n02"}:
            case["query"] = "I am a beginner" if case["language"] == "en" else "初心者です"
            case["expected_candidate_personas"] = ["beginner-onramp"]
            case["expected_selected_persona"] = "beginner-onramp"
            case["expected_primary_workflow"] = "market-regime-daily"
            case["expected_no_api_path"] = True
    report = evaluate_benchmark(benchmark, repo_metadata)
    assert any("is not allowed" in failure for failure in report["failures"])


def test_static_audit_rejects_duplicate_persona_names() -> None:
    duplicate = Persona(name="duplicate", any_terms=("one",), primary="a")
    shadow = Persona(name="duplicate", any_terms=("two",), primary="a")
    report = audit_personas((duplicate, shadow), [])
    assert report["duplicate_persona_names"] == ["duplicate"]


def test_static_audit_rejects_unregistered_and_stale_overlap() -> None:
    personas = (
        Persona(name="specific", any_terms=("swing only when",), primary="a"),
        Persona(name="generic", any_terms=("swing",), primary="b"),
    )
    unregistered = audit_personas(personas, [])
    assert unregistered["unregistered_overlaps"]

    fingerprint = unregistered["computed_overlaps"][0]["fingerprint"]
    contract = {
        "fingerprint": fingerprint,
        "winner": "specific",
        "rationale": "specific phrase wins before generic",
        "ambiguous_case_ids": ["amb-1"],
    }
    assert audit_personas(personas, [contract])["unregistered_overlaps"] == []
    stale = audit_personas(personas[:1], [contract])
    assert stale["stale_contracts"] == [fingerprint]


def test_static_audit_rejects_contradictory_require_exclude_terms() -> None:
    impossible = Persona(
        name="impossible",
        any_terms=("swing",),
        primary="a",
        require_groups=(("market",),),
        exclude_terms=("market",),
    )
    report = audit_personas((impossible,), [])
    assert report["contradictions"]


def test_loader_fails_closed_on_duplicate_case_ids(tmp_path: Path) -> None:
    case = {
        "id": "duplicate",
        "language": "en",
        "label": "positive",
        "query": "swing trading",
        "target_persona": "swing-trader",
        "expected_candidate_personas": ["swing-trader"],
        "expected_selected_persona": "swing-trader",
        "expected_primary_workflow": "swing-opportunity-daily",
        "expected_honest_gap": False,
        "expected_no_api_path": False,
        "neighbor_of": None,
        "base_id": None,
        "transformation": None,
        "tags": [],
    }
    path = tmp_path / "benchmark.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "baseline": {},
                "shadowing_contracts": [],
                "cases": [case, case],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkError, match="duplicate case id"):
        load_benchmark(path)
