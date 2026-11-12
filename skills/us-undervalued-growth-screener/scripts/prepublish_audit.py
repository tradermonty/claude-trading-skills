#!/usr/bin/env python3
"""Fail-closed publication audit for US undervalued-growth screening runs.

This script validates the *published* report, not only the evaluator input.  It
catches missing audit artifacts, inconsistent counts, scenario arithmetic drift,
forced final-three labels, and prose that asks the user to continue an unfinished
run.  Exit 0 means the run can be bundled and shown as final; exit 2 means the
same execution must repair the diagnostics and rerun.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from skill_version import runtime_metadata
except ModuleNotFoundError:
    import importlib.util

    _path = Path(__file__).with_name("skill_version.py")
    _spec = importlib.util.spec_from_file_location("skill_version", _path)
    if _spec is None or _spec.loader is None:
        raise
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    runtime_metadata = _mod.runtime_metadata


class AuditError(ValueError):
    pass


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AuditError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AuditError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise AuditError(f"{path} must contain a JSON object")
    return dict(value)


def _safe_path(root: Path, raw: str) -> Path:
    candidate = (root / raw).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise AuditError(f"artifact path escapes root: {raw}") from exc
    return candidate


def _verify_artifact(section: Mapping[str, Any], root: Path, label: str, errors: list[str]) -> None:
    path_text = _text(section.get("artifact_path"))
    expected = _text(section.get("artifact_sha256"))
    if not path_text:
        errors.append(f"{label}.artifact_path is missing")
        return
    path = _safe_path(root, path_text)
    if not path.is_file():
        # Discovery artifacts written by run_pipeline are referenced relative
        # to the audit directory; accept that base as well so a run root and
        # its audit/ subdirectory both resolve.
        fallback = (
            _safe_path(root, f"audit/{path_text}") if not path_text.startswith("audit/") else None
        )
        if fallback is not None and fallback.is_file():
            path = fallback
        else:
            errors.append(f"{label} artifact is missing: {path_text}")
            return
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected and actual != expected:
        errors.append(f"{label} SHA-256 mismatch")


def _scenario_arithmetic(report: Mapping[str, Any], errors: list[str]) -> None:
    for candidate in _list(report.get("ranked_candidates")):
        row = _mapping(candidate)
        symbol = _text(row.get("symbol")) or "UNKNOWN"
        valuation = _mapping(row.get("valuation"))
        for scenario_name in ("constant_multiple", "multiple_contraction", "peer_median"):
            scenario = _mapping(valuation.get(scenario_name))
            for horizon in ("year_2", "year_3"):
                item = _mapping(scenario.get(horizon))
                metric = _number(item.get("metric"))
                multiple = _number(item.get("multiple"))
                price = _number(item.get("implied_price"))
                if None in {metric, multiple, price}:
                    continue
                expected = metric * multiple
                if abs(price - expected) > max(0.02, abs(expected) * 0.0005):
                    errors.append(
                        f"{symbol} {scenario_name}.{horizon} implied price does not equal metric × multiple"
                    )


def audit_publication(
    report: Mapping[str, Any],
    *,
    report_markdown: str,
    artifact_root: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected_runtime = runtime_metadata()
    runtime = _mapping(report.get("runtime"))
    for key, value in expected_runtime.items():
        if runtime.get(key) != value:
            errors.append(f"runtime.{key} does not match installed skill")

    contract = _mapping(report.get("contract"))
    if contract.get("valid") is not True:
        errors.append("contract.valid is not true")
    if report.get("ranking_status") != "final":
        errors.append("ranking_status is not final")
    run_metadata = _mapping(report.get("run_metadata"))
    if run_metadata.get("status") != "complete":
        errors.append("run_metadata.status is not complete")
    if _list(run_metadata.get("unprocessed_candidates")):
        errors.append("unprocessed_candidates is not empty")

    audit = _mapping(report.get("screening_audit"))
    _verify_artifact(_mapping(audit.get("universe")), artifact_root, "universe", errors)
    _verify_artifact(_mapping(audit.get("candidate_pool")), artifact_root, "candidate_pool", errors)
    enrichment = _mapping(audit.get("enrichment"))
    if _text(enrichment.get("artifact_path")):
        _verify_artifact(enrichment, artifact_root, "enrichment", errors)
    generation = _mapping(_mapping(audit.get("candidate_pool")).get("generation_audit"))
    if generation and _text(generation.get("artifact_path")):
        _verify_artifact(generation, artifact_root, "candidate_pool_generation", errors)

    if enrichment.get("queue_count") not in {0, None}:
        errors.append("enrichment queue is not empty")
    if enrichment.get("unresolved_count") not in {0, None}:
        errors.append("enrichment unresolved_count is not zero")
    if enrichment.get("all_rows_resolved") is not True:
        errors.append("enrichment.all_rows_resolved is not true")

    counts = _mapping(report.get("counts"))
    status_counts = {
        "eligible": len(_list(report.get("ranked_candidates"))),
        "conditional": len(_list(report.get("conditional"))),
        "review_required": len(_list(report.get("review_required"))),
        "screened_out": len(_list(report.get("screened_out"))),
        "excluded": len(_list(report.get("excluded"))),
    }
    for key, actual in status_counts.items():
        declared = counts.get("ranked" if key == "eligible" else key)
        if declared is not None and int(declared) != actual:
            errors.append(f"counts.{key} does not match published rows")

    for row in _list(report.get("ranked_candidates")):
        candidate = _mapping(row)
        if candidate.get("status") != "eligible":
            errors.append(f"ranked candidate {candidate.get('symbol')} is not eligible")
        if _list(candidate.get("quality_gate_failures")):
            errors.append(f"ranked candidate {candidate.get('symbol')} has quality-gate failures")

    ranked_symbols = {
        str(_mapping(row).get("symbol") or "").upper()
        for row in _list(report.get("ranked_candidates"))
    }
    for label, raw in _mapping(report.get("final_three")).items():
        item = _mapping(raw)
        symbol = str(item.get("symbol") or "").upper()
        if symbol and symbol not in ranked_symbols:
            errors.append(f"final_three.{label} references a non-ranked symbol")

    forbidden_phrases = (
        "say continue",
        "send continue",
        "tell me continue",
        "続きと送",
        "続けてと送",
        "次のターンで",
        "正式ランキングではなく暫定",
        "temporary partial result",
    )
    lower_md = report_markdown.lower()
    for phrase in forbidden_phrases:
        if phrase.lower() in lower_md:
            errors.append(f"published markdown contains unfinished-run phrase: {phrase!r}")

    _scenario_arithmetic(report, errors)
    return {
        "runtime": expected_runtime,
        "valid": not errors,
        "errors": list(dict.fromkeys(errors)),
        "warnings": list(dict.fromkeys(warnings)),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--report-md", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--version", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in raw_argv:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    args = parse_args(raw_argv)
    if args.version:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    try:
        report = _read_json(args.report_json)
        markdown = args.report_md.read_text(encoding="utf-8")
        result = audit_publication(
            report, report_markdown=markdown, artifact_root=args.artifact_root
        )
    except (AuditError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
