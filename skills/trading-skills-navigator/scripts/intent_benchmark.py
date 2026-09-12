#!/usr/bin/env python3
"""Validate the versioned EN/JA Navigator intent-routing benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from recommend import PERSONAS, Persona, load_ssot, match_personas, normalize_query, recommend

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK = SKILL_ROOT / "assets" / "intent_benchmark_v1.json"
ALLOWED_LABELS = frozenset({"positive", "hard_negative", "ambiguous", "no_api", "honest_gap"})
REQUIRED_CASE_KEYS = frozenset(
    {
        "id",
        "language",
        "label",
        "query",
        "target_persona",
        "expected_candidate_personas",
        "expected_selected_persona",
        "expected_primary_workflow",
        "expected_honest_gap",
        "expected_no_api_path",
        "neighbor_of",
        "base_id",
        "transformation",
        "tags",
    }
)
EXPECTED_METRICS = {
    "candidate_precision": 1.0,
    "candidate_recall": 1.0,
    "selected_accuracy": 1.0,
    "workflow_accuracy": 1.0,
}
REQUIRED_TRANSFORMATIONS = {
    "en": {"case", "punctuation", "word_order", "orthographic"},
    "ja": {"punctuation", "word_order", "orthographic", "ja_particle", "ja_conjugation"},
}


class BenchmarkError(RuntimeError):
    """Raised when the benchmark schema or coverage contract is invalid."""


def load_benchmark(path: Path) -> dict[str, Any]:
    try:
        benchmark = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"unable to load benchmark {path}: {exc}") from exc
    if not isinstance(benchmark, dict) or benchmark.get("schema_version") != 1:
        raise BenchmarkError("benchmark schema_version must be 1")
    cases = benchmark.get("cases")
    if not isinstance(cases, list):
        raise BenchmarkError("benchmark cases must be a list")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise BenchmarkError(f"case #{index} must be an object")
        missing = REQUIRED_CASE_KEYS - set(case)
        if missing:
            raise BenchmarkError(f"case #{index} missing keys: {sorted(missing)}")
        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id:
            raise BenchmarkError(f"case #{index} has invalid id")
        if case_id in seen:
            raise BenchmarkError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        if case["language"] not in {"en", "ja"}:
            raise BenchmarkError(f"{case_id}: language must be en or ja")
        if case["label"] not in ALLOWED_LABELS:
            raise BenchmarkError(f"{case_id}: unsupported label {case['label']!r}")
        if not isinstance(case["query"], str) or not case["query"].strip():
            raise BenchmarkError(f"{case_id}: query must be non-empty")
        if not isinstance(case["expected_candidate_personas"], list):
            raise BenchmarkError(f"{case_id}: expected_candidate_personas must be a list")
        if not isinstance(case["tags"], list):
            raise BenchmarkError(f"{case_id}: tags must be a list")
    if not isinstance(benchmark.get("shadowing_contracts"), list):
        raise BenchmarkError("shadowing_contracts must be a list")
    fingerprints = [contract.get("fingerprint") for contract in benchmark["shadowing_contracts"]]
    if len(fingerprints) != len(set(fingerprints)):
        raise BenchmarkError("duplicate shadowing contract fingerprint")
    if not isinstance(benchmark.get("neighbor_contracts"), list):
        raise BenchmarkError("neighbor_contracts must be a list")
    if benchmark.get("baseline") != EXPECTED_METRICS:
        raise BenchmarkError("baseline metrics must be fail-closed at 1.0")
    return benchmark


def _normalized_term(term: str) -> str:
    return normalize_query(term)


def _term_relation(earlier: str, later: str) -> str | None:
    if earlier == later:
        return "equal"
    if earlier in later:
        return "earlier_in_later"
    if later in earlier:
        return "later_in_earlier"
    return None


def _overlap_fingerprint(
    earlier_index: int,
    earlier_name: str,
    earlier_term: str,
    later_index: int,
    later_name: str,
    later_term: str,
    relation: str,
) -> str:
    payload = [
        earlier_index,
        earlier_name,
        earlier_term,
        later_index,
        later_name,
        later_term,
        relation,
    ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _computed_overlaps(personas: tuple[Persona, ...]) -> list[dict[str, Any]]:
    overlaps: list[dict[str, Any]] = []
    for earlier_index, earlier in enumerate(personas):
        for later_index in range(earlier_index + 1, len(personas)):
            later = personas[later_index]
            for raw_earlier_term in earlier.any_terms:
                earlier_term = _normalized_term(raw_earlier_term)
                for raw_later_term in later.any_terms:
                    later_term = _normalized_term(raw_later_term)
                    relation = _term_relation(earlier_term, later_term)
                    if relation is None:
                        continue
                    overlaps.append(
                        {
                            "fingerprint": _overlap_fingerprint(
                                earlier_index,
                                earlier.name,
                                earlier_term,
                                later_index,
                                later.name,
                                later_term,
                                relation,
                            ),
                            "earlier_persona": earlier.name,
                            "later_persona": later.name,
                            "earlier_term": earlier_term,
                            "later_term": later_term,
                            "relation": relation,
                            "winner": earlier.name,
                        }
                    )
    return overlaps


def _terms_overlap(left: str, right: str) -> bool:
    left_norm = _normalized_term(left)
    right_norm = _normalized_term(right)
    return left_norm in right_norm or right_norm in left_norm


def _contradictions(personas: tuple[Persona, ...]) -> list[str]:
    problems: list[str] = []
    for persona in personas:
        for group_index, group in enumerate(persona.require_groups):
            if group and all(
                any(_terms_overlap(required, excluded) for excluded in persona.exclude_terms)
                for required in group
            ):
                problems.append(f"{persona.name}: require_group[{group_index}] is fully excluded")
        if (
            persona.any_terms
            and persona.exclude_terms
            and all(
                any(_terms_overlap(term, excluded) for excluded in persona.exclude_terms)
                for term in persona.any_terms
            )
        ):
            problems.append(f"{persona.name}: all any_terms are excluded")
    return problems


def audit_personas(
    personas: tuple[Persona, ...], shadowing_contracts: list[dict[str, Any]]
) -> dict[str, Any]:
    computed = _computed_overlaps(personas)
    computed_by_fingerprint = {item["fingerprint"]: item for item in computed}
    contract_by_fingerprint = {
        str(contract.get("fingerprint")): contract for contract in shadowing_contracts
    }
    unregistered = sorted(set(computed_by_fingerprint) - set(contract_by_fingerprint))
    stale = sorted(set(contract_by_fingerprint) - set(computed_by_fingerprint))
    invalid_contracts: list[str] = []
    for fingerprint in sorted(set(computed_by_fingerprint) & set(contract_by_fingerprint)):
        overlap = computed_by_fingerprint[fingerprint]
        contract = contract_by_fingerprint[fingerprint]
        if contract.get("winner") != overlap["winner"]:
            invalid_contracts.append(f"{fingerprint}: winner does not match persona order")
        if not str(contract.get("rationale") or "").strip():
            invalid_contracts.append(f"{fingerprint}: rationale is required")
        case_ids = contract.get("ambiguous_case_ids")
        if not isinstance(case_ids, list) or not case_ids:
            invalid_contracts.append(f"{fingerprint}: ambiguous_case_ids is required")
    names = [persona.name for persona in personas]
    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    return {
        "computed_overlaps": computed,
        "contradictions": _contradictions(personas),
        "duplicate_persona_names": duplicate_names,
        "unregistered_overlaps": unregistered,
        "stale_contracts": stale,
        "invalid_contracts": invalid_contracts,
    }


def _primary_id(result: dict[str, Any]) -> str | None:
    primary = result["primary_workflow"]
    return primary["id"] if primary else None


def evaluate_benchmark(benchmark: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    cases = benchmark["cases"]
    case_by_id = {case["id"]: case for case in cases}
    persona_by_name = {persona.name: persona for persona in PERSONAS}
    neighbor_contracts = benchmark["neighbor_contracts"]
    neighbor_by_target: dict[str, dict[str, Any]] = {}
    for contract in neighbor_contracts:
        target = contract.get("target_persona")
        if target in neighbor_by_target:
            failures.append(f"duplicate neighbor contract for {target!r}")
            continue
        neighbor_by_target[target] = contract
        allowed = contract.get("allowed_selected_personas")
        if target not in persona_by_name:
            failures.append(f"neighbor contract has unknown target {target!r}")
        if not isinstance(allowed, list) or not allowed:
            failures.append(f"{target}: neighbor contract needs allowed personas")
            continue
        if target in allowed:
            failures.append(f"{target}: neighbor contract cannot allow itself")
        unknown = sorted(set(allowed) - set(persona_by_name))
        if unknown:
            failures.append(f"{target}: unknown allowed neighbor personas {unknown}")
        if not str(contract.get("rationale") or "").strip():
            failures.append(f"{target}: neighbor contract rationale is required")
    missing_neighbor_contracts = sorted(set(persona_by_name) - set(neighbor_by_target))
    stale_neighbor_contracts = sorted(set(neighbor_by_target) - set(persona_by_name))
    if missing_neighbor_contracts:
        failures.append(f"missing neighbor contracts: {missing_neighbor_contracts}")
    if stale_neighbor_contracts:
        failures.append(f"stale neighbor contracts: {stale_neighbor_contracts}")
    persona_coverage: dict[str, dict[str, Any]] = {
        name: {
            "positive_languages": set(),
            "hard_negative_languages": set(),
            "neighbor_cases": 0,
        }
        for name in persona_by_name
    }
    workflow_coverage: dict[str, dict[str, int]] = {
        workflow["id"]: {"positive_cases": 0, "hard_negative_cases": 0}
        for workflow in metadata["workflows"]
    }
    transformations: dict[str, set[str]] = {"en": set(), "ja": set()}

    predicted_candidate_total = 0
    expected_candidate_total = 0
    true_candidate_total = 0
    selected_correct = 0
    workflow_correct = 0

    for case in cases:
        case_id = case["id"]
        matches = match_personas(case["query"])
        actual_candidates = [persona.name for persona in matches]
        expected_candidates = case["expected_candidate_personas"]
        result = recommend(case["query"], metadata)
        actual_selected = result["routing_diagnostics"]["selected_persona"]
        actual_primary = _primary_id(result)

        predicted_candidate_total += len(actual_candidates)
        expected_candidate_total += len(expected_candidates)
        true_candidate_total += len(set(actual_candidates) & set(expected_candidates))
        if actual_selected == case["expected_selected_persona"]:
            selected_correct += 1
        else:
            failures.append(
                f"{case_id}: selected {actual_selected!r}, expected "
                f"{case['expected_selected_persona']!r}"
            )
        if actual_primary == case["expected_primary_workflow"]:
            workflow_correct += 1
        else:
            failures.append(
                f"{case_id}: primary {actual_primary!r}, expected "
                f"{case['expected_primary_workflow']!r}"
            )
        if actual_candidates != expected_candidates:
            failures.append(
                f"{case_id}: candidates {actual_candidates!r}, expected {expected_candidates!r}"
            )
        if result["honest_gap"] is not case["expected_honest_gap"]:
            failures.append(f"{case_id}: honest_gap mismatch")
        if result["no_api_path"] is not case["expected_no_api_path"]:
            failures.append(f"{case_id}: no_api_path mismatch")

        target = case["target_persona"]
        if target not in persona_coverage:
            failures.append(f"{case_id}: unknown target persona {target!r}")
            continue
        if case["label"] == "hard_negative":
            persona_coverage[target]["hard_negative_languages"].add(case["language"])
            if target in actual_candidates:
                failures.append(f"{case_id}: hard-negative matched target {target!r}")
            contract = neighbor_by_target.get(target) or {}
            allowed_neighbors = contract.get("allowed_selected_personas") or []
            expected_neighbor = case["expected_selected_persona"]
            if case["neighbor_of"] != target:
                failures.append(f"{case_id}: hard-negative neighbor_of must name its target")
            if expected_neighbor not in allowed_neighbors:
                failures.append(
                    f"{case_id}: selected neighbor {expected_neighbor!r} is not allowed for {target!r}"
                )
            elif actual_selected == expected_neighbor:
                persona_coverage[target]["neighbor_cases"] += 1
            target_workflow = persona_by_name[target].primary
            if target_workflow in workflow_coverage:
                workflow_coverage[target_workflow]["hard_negative_cases"] += 1
        else:
            persona_coverage[target]["positive_languages"].add(case["language"])
            if target not in actual_candidates:
                failures.append(f"{case_id}: target persona {target!r} did not match")
            target_workflow = persona_by_name[target].primary
            if target_workflow in workflow_coverage:
                workflow_coverage[target_workflow]["positive_cases"] += 1

        if case["neighbor_of"] is not None and case["label"] != "hard_negative":
            neighbor = case["neighbor_of"]
            if neighbor not in persona_coverage:
                failures.append(f"{case_id}: unknown neighbor_of {neighbor!r}")
        transformation = case["transformation"]
        if transformation is not None:
            transformations[case["language"]].add(transformation)
            base = case_by_id.get(case["base_id"])
            if base is None:
                failures.append(f"{case_id}: missing metamorphic base {case['base_id']!r}")
            elif (
                base["expected_candidate_personas"] != expected_candidates
                or base["expected_selected_persona"] != case["expected_selected_persona"]
            ):
                failures.append(f"{case_id}: metamorphic expectation differs from base")

    case_count = len(cases)
    precision = (
        true_candidate_total / predicted_candidate_total if predicted_candidate_total else 1.0
    )
    recall = true_candidate_total / expected_candidate_total if expected_candidate_total else 1.0
    metrics = {
        "candidate_precision": round(precision, 6),
        "candidate_recall": round(recall, 6),
        "selected_accuracy": round(selected_correct / case_count, 6) if case_count else 0.0,
        "workflow_accuracy": round(workflow_correct / case_count, 6) if case_count else 0.0,
    }
    if metrics != benchmark["baseline"]:
        failures.append(f"metrics {metrics!r} do not match baseline {benchmark['baseline']!r}")

    for name, coverage in persona_coverage.items():
        if coverage["positive_languages"] != {"en", "ja"}:
            failures.append(f"{name}: missing bilingual positive coverage")
        if coverage["hard_negative_languages"] != {"en", "ja"}:
            failures.append(f"{name}: missing bilingual hard-negative coverage")
        if coverage["neighbor_cases"] < 1:
            failures.append(f"{name}: missing neighboring-intent coverage")
    for workflow_id, coverage in workflow_coverage.items():
        if coverage["positive_cases"] < 1 or coverage["hard_negative_cases"] < 1:
            failures.append(f"{workflow_id}: incomplete positive/hard-negative coverage")
    for language, required in REQUIRED_TRANSFORMATIONS.items():
        missing = required - transformations[language]
        if missing:
            failures.append(f"{language}: missing transformations {sorted(missing)}")

    audit = audit_personas(PERSONAS, benchmark["shadowing_contracts"])
    for key in (
        "contradictions",
        "duplicate_persona_names",
        "unregistered_overlaps",
        "stale_contracts",
        "invalid_contracts",
    ):
        failures.extend(f"persona audit {key}: {item}" for item in audit[key])
    ambiguous_ids = {case["id"] for case in cases if case["label"] == "ambiguous"}
    overlap_by_fingerprint = {
        overlap["fingerprint"]: overlap for overlap in audit["computed_overlaps"]
    }
    for contract in benchmark["shadowing_contracts"]:
        overlap = overlap_by_fingerprint.get(contract.get("fingerprint"))
        for case_id in contract.get("ambiguous_case_ids") or []:
            if case_id not in ambiguous_ids:
                failures.append(
                    f"shadow contract {contract.get('fingerprint')}: "
                    f"{case_id!r} is not an ambiguous case"
                )
                continue
            if overlap is None:
                continue
            required_candidates = {
                overlap["earlier_persona"],
                overlap["later_persona"],
            }
            case_candidates = set(case_by_id[case_id]["expected_candidate_personas"])
            if not required_candidates <= case_candidates:
                failures.append(
                    f"shadow contract {contract.get('fingerprint')}: {case_id!r} "
                    "does not cover both overlapping personas"
                )
            if case_by_id[case_id]["expected_selected_persona"] != overlap["winner"]:
                failures.append(
                    f"shadow contract {contract.get('fingerprint')}: {case_id!r} "
                    f"does not select contract winner {overlap['winner']!r}"
                )

    return {
        "schema_version": 1,
        "case_count": case_count,
        "metrics": metrics,
        "coverage": {
            "personas": {
                name: {
                    "positive_languages": sorted(value["positive_languages"]),
                    "hard_negative_languages": sorted(value["hard_negative_languages"]),
                    "neighbor_cases": value["neighbor_cases"],
                }
                for name, value in sorted(persona_coverage.items())
            },
            "workflows": dict(sorted(workflow_coverage.items())),
            "transformations": {
                language: sorted(values) for language, values in transformations.items()
            },
        },
        "persona_audit": audit,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--json", action="store_true", help="Print the full JSON report")
    args = parser.parse_args(argv)
    try:
        benchmark = load_benchmark(args.benchmark)
        metadata = load_ssot(args.project_root)
        report = evaluate_benchmark(benchmark, metadata)
    except (BenchmarkError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    elif report["failures"]:
        for failure in report["failures"]:
            print(f"ERROR: {failure}", file=sys.stderr)
    else:
        print(
            f"OK: {report['case_count']} intent cases; "
            f"precision={report['metrics']['candidate_precision']:.3f}; "
            f"recall={report['metrics']['candidate_recall']:.3f}"
        )
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
