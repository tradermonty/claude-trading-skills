"""Step adapters for the kanchi-dividend-weekly workflow."""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import _artifact_paths
from .common import (
    ReplayError,
    _assert_finite_json,
    _load_json,
    _parse_rfc3339,
    _repo_module,
    _run_cli,
    _schema_error_details,
    _write_json,
    load_yaml,
)
from .constants import (
    KANCHI_ACTIONABLE_VERDICTS,
    KANCHI_FORBIDDEN_REVIEW_TOKENS,
    KANCHI_REPLAY_SCHEMA,
)
from .normalize import _canonicalize, _normalize_text_file


def _validate_kanchi_contract(payload: Any, definition: str) -> Mapping[str, Any]:
    schema = _load_json(KANCHI_REPLAY_SCHEMA, "kanchi replay contract schema")
    selected = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{definition}",
    }
    errors = _schema_error_details(selected, payload)
    if errors:
        raise ReplayError(f"invalid kanchi {definition} contract:\n- " + "\n- ".join(errors))
    _assert_finite_json(payload, f"kanchi {definition}")
    return payload


def _kanchi_fixed_date(spec: Mapping[str, Any]) -> str:
    return _parse_rfc3339(spec["fixed_timestamp"], "fixed_timestamp").date().isoformat()


def _kanchi_candidate_screen(
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    stage: Path,
    *,
    input_name: str,
    artifact_id: str,
    expected_source: str,
) -> dict[str, dict[str, Any]]:
    if consumed:
        raise ReplayError(f"kanchi {input_name} screen must not consume prior artifacts")
    payload = _validate_kanchi_contract(
        _load_json(inputs[input_name], f"{input_name} fixture"), "candidate_list"
    )
    if payload["source"] != expected_source:
        raise ReplayError(f"{input_name} source must be {expected_source}")
    if payload["as_of"] != _kanchi_fixed_date(spec):
        raise ReplayError(f"{input_name} as_of must match fixed_timestamp date")
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts[artifact_id]["files"]["canonical"]), payload)
    return artifacts


def _kanchi_high_yield_screen(
    _repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    return _kanchi_candidate_screen(
        spec,
        step,
        inputs,
        consumed,
        stage,
        input_name="high_yield_candidates",
        artifact_id="high_yield_candidates",
        expected_source="value-dividend-screener",
    )


def _kanchi_pullback_screen(
    _repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    return _kanchi_candidate_screen(
        spec,
        step,
        inputs,
        consumed,
        stage,
        input_name="pullback_candidates",
        artifact_id="pullback_candidates",
        expected_source="dividend-growth-pullback-screener",
    )


def _kanchi_underwrite(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if not set(consumed) <= {"high_yield_candidates", "pullback_candidates"}:
        raise ReplayError(f"kanchi underwriting received unexpected artifacts: {sorted(consumed)}")
    evidence = _validate_kanchi_contract(
        _load_json(inputs["underwriting_evidence"], "underwriting evidence"),
        "underwriting_evidence",
    )
    decision = _validate_kanchi_contract(
        load_yaml(inputs["underwriting_decision"]), "underwriting_decision"
    )
    fixed_date = _kanchi_fixed_date(spec)
    if evidence["as_of"] != fixed_date:
        raise ReplayError("underwriting evidence as_of must match fixed_timestamp date")
    tickers = [candidate["ticker"] for candidate in evidence["candidates"]]
    if len(tickers) != len(set(tickers)):
        raise ReplayError("underwriting evidence tickers must be unique")

    for artifact_id in sorted(consumed):
        payload = _load_json(
            Path(consumed[artifact_id]["files"]["canonical"]), f"{artifact_id} handoff"
        )
        _validate_kanchi_contract(payload, "candidate_list")
        unknown = {row["ticker"] for row in payload["candidates"]} - set(tickers)
        if unknown:
            raise ReplayError(
                f"{artifact_id} contains tickers missing from underwriting evidence: {sorted(unknown)}"
            )

    verdict_module = _repo_module(
        repo_root,
        "verdict",
        repo_root / "skills" / "kanchi-dividend-sop" / "scripts",
    )

    def _evaluate() -> list[tuple[str, str, bool, tuple[str, ...]]]:
        evaluated: list[tuple[str, str, bool, tuple[str, ...]]] = []
        for candidate in evidence["candidates"]:
            result = verdict_module.synthesize_verdict(
                step1_verdict=candidate["step1_verdict"],
                safety_verdict=candidate["safety_verdict"],
                event_verdict_cap=candidate["event_verdict_cap"],
                event_t1_blocked=candidate["event_t1_blocked"],
                pre_order_blockers=list(candidate["pre_order_blockers"]),
            )
            evaluated.append(
                (
                    candidate["ticker"],
                    result.verdict,
                    bool(result.t1_blocked),
                    tuple(result.reasons),
                )
            )
        return evaluated

    first = _evaluate()
    if first != _evaluate():
        raise ReplayError("native Kanchi verdict synthesis was non-deterministic")

    actionable = [row for row in first if row[1] in KANCHI_ACTIONABLE_VERDICTS]
    excluded = [row for row in first if row[1] not in KANCHI_ACTIONABLE_VERDICTS]
    if [row[0] for row in actionable] != decision["expected_actionable"]:
        raise ReplayError(
            "underwriting decision expected_actionable does not match native verdicts"
        )
    if [row[0] for row in excluded] != decision["expected_excluded"]:
        raise ReplayError("underwriting decision expected_excluded does not match native verdicts")

    kanchi_candidates = {
        "schema_version": 1,
        "as_of": evidence["as_of"],
        "profile": decision["sop_profile"],
        "candidates": [
            {
                "ticker": ticker,
                "verdict": verdict,
                "t1_blocked": flagged,
                "reasons": list(reasons),
            }
            for ticker, verdict, flagged, reasons in actionable
        ],
        "excluded": [
            {"ticker": ticker, "verdict": verdict, "reasons": list(reasons)}
            for ticker, verdict, _flagged, reasons in excluded
        ],
    }
    _validate_kanchi_contract(kanchi_candidates, "kanchi_candidates")

    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["kanchi_candidates"]["files"]["canonical"]), kanchi_candidates)

    sop_input = work / "sop_candidates.json"
    _write_json(
        sop_input,
        {
            "profile": decision["sop_profile"],
            "candidates": [
                {"ticker": ticker, "bucket": "unassigned"} for ticker, _, _, _ in actionable
            ],
        },
    )
    memo_path = Path(artifacts["stock_memo"]["files"]["canonical"])
    _run_cli(
        [
            sys.executable,
            str(repo_root / "skills" / "kanchi-dividend-sop" / "scripts" / "build_sop_plan.py"),
            "--input",
            str(sop_input),
            "--as-of",
            fixed_date,
            "--output-dir",
            str(memo_path.parent),
            "--filename",
            memo_path.name,
        ],
        repo_root,
    )
    _normalize_text_file(memo_path)
    return artifacts


def _kanchi_tax_advice(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if consumed:
        raise ReplayError("kanchi tax advice must not consume prior artifacts")
    payload = _load_json(inputs["tax_holdings"], "tax holdings")
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("holdings"), list)
        or not payload["holdings"]
    ):
        raise ReplayError("tax holdings must provide a non-empty holdings list")
    fixed_date = _kanchi_fixed_date(spec)
    reports = work / "tax"
    reports.mkdir(parents=True)
    _run_cli(
        [
            sys.executable,
            str(
                repo_root
                / "skills"
                / "kanchi-dividend-us-tax-accounting"
                / "scripts"
                / "build_tax_planning_sheet.py"
            ),
            "--input",
            str(inputs["tax_holdings"]),
            "--output-dir",
            str(reports),
            "--as-of",
            fixed_date,
        ],
        repo_root,
    )
    markdown = reports / f"tax_planning_sheet_{fixed_date}.md"
    csv_file = reports / f"tax_planning_sheet_{fixed_date}.csv"
    if not markdown.is_file() or not csv_file.is_file():
        raise ReplayError("native tax planning CLI did not produce both markdown and CSV")
    artifacts = _artifact_paths(stage, step["output_files"])
    markdown_out = Path(artifacts["account_location_advice"]["files"]["markdown"])
    csv_out = Path(artifacts["account_location_advice"]["files"]["csv"])
    markdown_out.write_text(markdown.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    csv_out.write_text(csv_file.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    _normalize_text_file(markdown_out)
    _normalize_text_file(csv_out)
    return artifacts


def _kanchi_review_actions(report: Mapping[str, Any]) -> list[str]:
    results = report.get("results")
    if not isinstance(results, list):
        raise ReplayError("kanchi review queue report must contain a results list")
    actions: list[str] = []
    for row in results:
        if not isinstance(row, dict) or not isinstance(row.get("actions"), list):
            raise ReplayError("kanchi review queue results must declare an actions list")
        actions.extend(str(action) for action in row["actions"])
    return actions


def _kanchi_review_queue(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if consumed:
        raise ReplayError("kanchi review queue must not consume prior artifacts")
    payload = _load_json(inputs["review_monitor"], "review monitor input")
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("holdings"), list)
        or not payload["holdings"]
    ):
        raise ReplayError("review monitor input must provide a non-empty holdings list")
    if payload.get("as_of") != _kanchi_fixed_date(spec):
        raise ReplayError("review monitor as_of must match fixed_timestamp date")
    reports = work / "review"
    reports.mkdir(parents=True)
    json_out = reports / "review_queue.json"
    markdown_out = reports / "review_queue.md"
    _run_cli(
        [
            sys.executable,
            str(
                repo_root
                / "skills"
                / "kanchi-dividend-review-monitor"
                / "scripts"
                / "build_review_queue.py"
            ),
            "--input",
            str(inputs["review_monitor"]),
            "--output",
            str(json_out),
            "--markdown",
            str(markdown_out),
        ],
        repo_root,
    )
    raw = _load_json(json_out, "review queue report")
    generated_at = raw.get("generated_at")
    canonical = _canonicalize(raw, spec["fixed_timestamp"], {})
    for action in _kanchi_review_actions(canonical):
        lowered = action.lower()
        if any(token in lowered for token in KANCHI_FORBIDDEN_REVIEW_TOKENS):
            raise ReplayError(
                f"kanchi review queue must never propose a sell-like action: {action!r}"
            )
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["review_queue"]["files"]["canonical"]), canonical)
    markdown = markdown_out.read_text(encoding="utf-8")
    if isinstance(generated_at, str) and generated_at:
        markdown = re.sub(
            rf"(?m)^- Generated at: `{re.escape(generated_at)}`$",
            lambda _: f"- Generated at: `{spec['fixed_timestamp']}`",
            markdown,
            count=1,
        )
    review_markdown = Path(artifacts["review_queue"]["files"]["companion"])
    review_markdown.write_text(markdown, encoding="utf-8", newline="\n")
    _normalize_text_file(review_markdown)
    return artifacts


def _kanchi_artifact_link(
    consumed: Mapping[str, dict[str, Any]], artifact_id: str, role: str, stage: Path
) -> str:
    """Derive a stable link token from the artifact actually handed forward.

    The token keeps the full path relative to the published staging root, so a
    nested output such as ``nested/03_stock_memo.md`` is not truncated to its
    basename. A target that escapes staging or does not exist fails closed.
    """
    try:
        raw_path = Path(consumed[artifact_id]["files"][role])
    except (KeyError, TypeError) as exc:
        raise ReplayError(
            f"kanchi registration is missing the {artifact_id}.{role} handoff"
        ) from exc
    resolved = raw_path.resolve()
    stage_root = stage.resolve()
    try:
        relative = resolved.relative_to(stage_root)
    except ValueError as exc:
        raise ReplayError(
            f"kanchi registration link target escapes staging: {artifact_id}.{role}"
        ) from exc
    if not resolved.is_file():
        raise ReplayError(f"kanchi registration link target does not exist: {artifact_id}.{role}")
    return f"$ARTIFACT/{relative.as_posix()}"


def _kanchi_register_thesis(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    required = {"kanchi_candidates", "stock_memo"}
    optional = {"account_location_advice", "review_queue"}
    if not required <= set(consumed) or not set(consumed) <= required | optional:
        raise ReplayError(f"kanchi registration received unexpected artifacts: {sorted(consumed)}")
    decision = _validate_kanchi_contract(
        load_yaml(inputs["register_decision"]), "register_decision"
    )
    fixed_date = _kanchi_fixed_date(spec)
    candidates_path = Path(consumed["kanchi_candidates"]["files"]["canonical"])
    candidates = _validate_kanchi_contract(
        _load_json(candidates_path, "kanchi candidates handoff"), "kanchi_candidates"
    )
    memo_path = Path(consumed["stock_memo"]["files"]["canonical"])
    if not memo_path.is_file():
        raise ReplayError("kanchi registration requires the stock_memo handoff")
    if [row["ticker"] for row in candidates["candidates"]] != decision["expected_idea"]:
        raise ReplayError("register decision expected_idea does not match kanchi_candidates")

    scripts_dir = repo_root / "skills" / "trader-memory-core" / "scripts"
    thesis_ingest = _repo_module(repo_root, "thesis_ingest", scripts_dir)
    thesis_store = _repo_module(repo_root, "thesis_store", scripts_dir)
    state_dir = work / "kanchi-state"
    state_dir.mkdir(parents=True)
    thesis_ids = thesis_ingest.ingest("kanchi-dividend-sop", str(candidates_path), str(state_dir))
    if not thesis_ids:
        raise ReplayError("native thesis ingest registered no theses")
    theses = [thesis_store.get(state_dir, thesis_id) for thesis_id in thesis_ids]
    if sorted(row["ticker"] for row in theses) != sorted(decision["expected_idea"]):
        raise ReplayError("native thesis ingest did not register the expected IDEA theses")

    linked_specs = [
        ("kanchi-dividend-sop", _kanchi_artifact_link(consumed, "stock_memo", "canonical", stage))
    ]
    if "account_location_advice" in consumed:
        linked_specs.append(
            (
                "kanchi-dividend-us-tax-accounting",
                _kanchi_artifact_link(consumed, "account_location_advice", "markdown", stage),
            )
        )
    if "review_queue" in consumed:
        linked_specs.append(
            (
                "kanchi-dividend-review-monitor",
                _kanchi_artifact_link(consumed, "review_queue", "canonical", stage),
            )
        )
    for thesis in theses:
        for skill, token in linked_specs:
            thesis_store.link_report(state_dir, thesis["thesis_id"], skill, token, fixed_date)

    entries = []
    for thesis in theses:
        reloaded = thesis_store.get(state_dir, thesis["thesis_id"])
        if reloaded["status"] != "IDEA":
            raise ReplayError("kanchi registration must never leave IDEA status")
        if decision["expected_active"]:
            raise ReplayError("register decision must not promote any thesis to ACTIVE")
        linked = reloaded.get("linked_reports") or []
        memo_link = {
            "skill": "kanchi-dividend-sop",
            "file": linked_specs[0][1],
            "date": fixed_date,
        }
        if memo_link not in linked:
            raise ReplayError("stock_memo was not linked to the IDEA thesis")
        entries.append(
            {
                "ticker": reloaded["ticker"],
                "thesis_type": reloaded["thesis_type"],
                "status": reloaded["status"],
                "created_at": reloaded["created_at"],
                "next_review_date": reloaded["monitoring"]["next_review_date"],
                "origin_skill": reloaded["origin"]["skill"],
                "linked_reports": linked,
            }
        )
    entries.sort(key=lambda row: row["ticker"])
    record = {
        "schema_version": 1,
        "workflow_id": "kanchi-dividend-weekly",
        "recorded_at": spec["fixed_timestamp"],
        "theses": entries,
        "provenance": {
            "execution_mode": "composite",
            "components": ["manual_contract", "native_api"],
            "native_component": "trader-memory-core.thesis_ingest + thesis_store.link_report",
            "source_date": fixed_date,
            "limitation": (
                "Human register decision is a fixture; no broker fill exists, so every "
                "thesis stays IDEA and no order is placed."
            ),
        },
    }
    _validate_kanchi_contract(record, "thesis_record")
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["thesis_record"]["files"]["canonical"]), record)
    return artifacts
