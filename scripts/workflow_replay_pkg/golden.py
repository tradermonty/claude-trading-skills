"""Golden tree comparison, check, and regeneration."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .common import _write_json, load_yaml
from .execution import _publish_trees_transactionally, execute_replay
from .manifest import validate_coverage


def compare_trees(actual: Path, expected: Path) -> list[str]:
    actual_files = {
        path.relative_to(actual).as_posix(): path for path in actual.rglob("*") if path.is_file()
    }
    expected_files = {
        path.relative_to(expected).as_posix(): path
        for path in expected.rglob("*")
        if path.is_file()
    }
    differences = []
    for name in sorted(set(actual_files) - set(expected_files)):
        differences.append(f"unexpected generated file: {name}")
    for name in sorted(set(expected_files) - set(actual_files)):
        differences.append(f"missing generated file: {name}")
    for name in sorted(set(actual_files) & set(expected_files)):
        if actual_files[name].read_bytes() != expected_files[name].read_bytes():
            differences.append(f"content drift: {name}")
    return differences


def _covered_specs(coverage_path: Path) -> list[tuple[str, Path, Mapping[str, Any]]]:
    coverage = load_yaml(coverage_path)
    result = []
    for workflow_id, entry in sorted((coverage.get("covered") or {}).items()):
        result.append((workflow_id, (coverage_path.parent / entry["spec"]).resolve(), entry))
    return result


def check_goldens(repo_root: Path, coverage_path: Path, report_path: Path | None) -> list[str]:
    rows = []
    all_differences: list[str] = []
    coverage_counts = {
        "covered": 0,
        "total": len(list((repo_root / "workflows").glob("*.yaml"))),
    }
    try:
        coverage_summary = validate_coverage(repo_root, coverage_path)
        coverage_counts["covered"] = len(coverage_summary["covered"])
        covered_specs = _covered_specs(coverage_path)
        with tempfile.TemporaryDirectory(prefix="workflow-replay-check-") as temp_name:
            temp = Path(temp_name)
            for workflow_id, spec_path, entry in covered_specs:
                spec = load_yaml(spec_path)
                for variant in entry["variants"]:
                    generated = temp / workflow_id / variant
                    try:
                        execution = execute_replay(repo_root, spec_path, variant, generated)
                        golden = (
                            spec_path.parent / spec["variants"][variant]["golden_dir"]
                        ).resolve()
                        differences = compare_trees(generated, golden)
                        rows.append(
                            {
                                "workflow_id": workflow_id,
                                "variant": variant,
                                "status": "pass" if not differences else "drift",
                                "execution": execution,
                                "differences": differences,
                            }
                        )
                        all_differences.extend(
                            f"{workflow_id}/{variant}: {difference}" for difference in differences
                        )
                    except Exception as exc:
                        difference = f"{workflow_id}/{variant}: execution error: {exc}"
                        all_differences.append(difference)
                        rows.append(
                            {
                                "workflow_id": workflow_id,
                                "variant": variant,
                                "status": "error",
                                "error": str(exc),
                                "completed_steps": list(getattr(exc, "completed_steps", []) or []),
                            }
                        )
    except Exception as exc:
        all_differences.append(f"coverage validation error: {exc}")
        rows.append(
            {
                "workflow_id": None,
                "variant": None,
                "status": "error",
                "stage": "validation",
                "error": str(exc),
                "completed_steps": list(getattr(exc, "completed_steps", []) or []),
            }
        )
    finally:
        if report_path:
            _write_json(
                report_path,
                {
                    "schema_version": 1,
                    "coverage": coverage_counts,
                    "issue": 294,
                    "rows": rows,
                },
            )
    return all_differences


def generate_goldens(repo_root: Path, coverage_path: Path) -> dict[str, list[str]]:
    validate_coverage(repo_root, coverage_path)
    staged_trees: list[tuple[Path, Path]] = []
    generated: list[str] = []
    with tempfile.TemporaryDirectory(prefix="workflow-replay-generate-") as temp_name:
        temp = Path(temp_name)
        for workflow_id, spec_path, entry in _covered_specs(coverage_path):
            spec = load_yaml(spec_path)
            for variant in entry["variants"]:
                staged = temp / workflow_id / variant
                execute_replay(repo_root, spec_path, variant, staged)
                destination = (spec_path.parent / spec["variants"][variant]["golden_dir"]).resolve()
                staged_trees.append((staged, destination))
                generated.append(f"{workflow_id}:{variant}")
        _publish_trees_transactionally(staged_trees)
    return {"generated": generated}
