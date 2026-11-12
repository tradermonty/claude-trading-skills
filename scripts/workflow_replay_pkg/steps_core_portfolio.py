"""Step adapters for the core-portfolio-weekly workflow."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import _artifact_paths
from .common import (
    ReplayError,
    _assert_finite_json,
    _load_json,
    _load_module_from_path,
    _parse_rfc3339,
    _require_rfc3339,
    _schema_error_details,
    _write_json,
    _write_yaml,
    load_yaml,
)
from .constants import CORE_PORTFOLIO_SCHEMA
from .normalize import _file_sha256


def _validate_core_contract(payload: Any, definition: str) -> Mapping[str, Any]:
    schema = _load_json(CORE_PORTFOLIO_SCHEMA, "core portfolio replay contract schema")
    selected = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{definition}",
    }
    errors = _schema_error_details(selected, payload)
    if errors:
        raise ReplayError(
            f"invalid core portfolio {definition} contract:\n- " + "\n- ".join(errors)
        )
    _assert_finite_json(payload, f"core portfolio {definition}")
    return payload


def _core_date(spec: Mapping[str, Any]) -> str:
    return _parse_rfc3339(spec["fixed_timestamp"], "fixed_timestamp").date().isoformat()


def _core_snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    canonical = (json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()
    return hashlib.sha256(canonical).hexdigest()


def _close_number(left: int | float, right: int | float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0, abs_tol=1e-6)


def _validate_core_snapshot(payload: Any, spec: Mapping[str, Any]) -> Mapping[str, Any]:
    snapshot = _validate_core_contract(payload, "holdings_snapshot")
    if snapshot["as_of"] != _core_date(spec):
        raise ReplayError("holdings snapshot as_of must match fixed_timestamp date")
    account = snapshot["account"]
    if not re.fullmatch(r"SIM-\*{4}-\d{3}", account["account_id"]):
        raise ReplayError("holdings snapshot account_id must be masked and fictional")
    positions = snapshot["positions"]
    symbols = [row["symbol"] for row in positions]
    if len(symbols) != len(set(symbols)):
        raise ReplayError("holdings snapshot symbols must be unique")
    for row in positions:
        expected_value = row["quantity"] * row["current_price"]
        if not _close_number(row["market_value"], expected_value):
            raise ReplayError(f"holdings snapshot market_value mismatch for {row['symbol']}")
        expected_weight = row["market_value"] / account["equity"] * 100
        if not _close_number(row["portfolio_weight_pct"], expected_weight):
            raise ReplayError(f"holdings snapshot weight mismatch for {row['symbol']}")
    long_value = sum(row["market_value"] for row in positions)
    if not _close_number(long_value, account["long_market_value"]):
        raise ReplayError("holdings snapshot long_market_value does not match positions")
    if not _close_number(account["long_market_value"] + account["cash"], account["equity"]):
        raise ReplayError("holdings snapshot cash plus positions does not match equity")
    return snapshot


def _core_consumed_path(consumed: Mapping[str, dict[str, Any]], artifact_id: str) -> Path:
    try:
        return Path(consumed[artifact_id]["files"]["canonical"])
    except (KeyError, TypeError) as exc:
        raise ReplayError(f"missing canonical {artifact_id} handoff") from exc


def _core_portfolio_snapshot(
    _repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if consumed:
        raise ReplayError("core portfolio snapshot must not consume prior artifacts")
    snapshot = _validate_core_snapshot(
        _load_json(inputs["holdings_snapshot"], "core portfolio holdings snapshot"), spec
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["holdings_snapshot"]["files"]["canonical"]), snapshot)
    return artifacts


def _core_allocation_payload(
    snapshot: Mapping[str, Any], decision: Mapping[str, Any]
) -> dict[str, Any]:
    account = snapshot["account"]
    target_by_bucket = {row["bucket"]: row["target_pct"] for row in decision["targets"]}
    allocation = []
    for position in snapshot["positions"]:
        current = position["market_value"] / account["equity"] * 100
        target = target_by_bucket[position["symbol"]]
        allocation.append(
            {
                "bucket": position["symbol"],
                "current_pct": round(current, 6),
                "target_pct": target,
                "variance_pct": round(current - target, 6),
            }
        )
    cash_pct = account["cash"] / account["equity"] * 100
    cash_target = target_by_bucket["CASH"]
    allocation.append(
        {
            "bucket": "CASH",
            "current_pct": round(cash_pct, 6),
            "target_pct": cash_target,
            "variance_pct": round(cash_pct - cash_target, 6),
        }
    )
    largest = max(snapshot["positions"], key=lambda row: row["portfolio_weight_pct"])
    human = decision["human_decision"]
    return {
        "schema_version": "1.0",
        "as_of": snapshot["as_of"],
        "portfolio_value": account["equity"],
        "allocation": allocation,
        "allocation_total_pct": round(sum(row["current_pct"] for row in allocation), 6),
        "largest_position": {
            "symbol": largest["symbol"],
            "weight_pct": largest["portfolio_weight_pct"],
        },
        "decision": human["decision"],
        "rationale": human["rationale"],
    }


def _core_allocation_markdown(payload: Mapping[str, Any]) -> str:
    largest = payload["largest_position"]
    cash = next(row for row in payload["allocation"] if row["bucket"] == "CASH")
    return (
        "# Fictional Allocation Report\n\n"
        f"- Portfolio value: **${payload['portfolio_value']:,.2f}**\n"
        f"- Current cash: **{cash['current_pct']:.1f}%**\n"
        f"- Allocation total: **{payload['allocation_total_pct']:.1f}%**\n"
        f"- Largest position: **{largest['symbol']} at {largest['weight_pct']:.1f}%**\n"
        f"- Human decision: **{payload['decision']}**\n\n"
        "The allocation arithmetic was recomputed from the fictional snapshot and target "
        "fixture. The rebalance decision remains a human contract; no order is placed.\n"
    )


def _load_core_decision(
    inputs: Mapping[str, Path], name: str, definition: str
) -> Mapping[str, Any]:
    return _validate_core_contract(load_yaml(inputs[name]), definition)


def _validate_core_allocation_decision(
    snapshot: Mapping[str, Any], decision: Mapping[str, Any]
) -> None:
    if decision["snapshot_sha256"] != _core_snapshot_sha256(snapshot):
        raise ReplayError("allocation decision snapshot_sha256 does not match step-1 handoff")
    buckets = [row["bucket"] for row in decision["targets"]]
    expected = [row["symbol"] for row in snapshot["positions"]] + ["CASH"]
    if len(buckets) != len(set(buckets)) or set(buckets) != set(expected):
        raise ReplayError("allocation targets must match snapshot symbols plus CASH exactly")
    if not _close_number(sum(row["target_pct"] for row in decision["targets"]), 100):
        raise ReplayError("allocation target percentages must total 100")


def _core_portfolio_allocation(
    _repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"holdings_snapshot"}:
        raise ReplayError("core allocation requires only the holdings_snapshot handoff")
    snapshot_path = _core_consumed_path(consumed, "holdings_snapshot")
    snapshot = _validate_core_snapshot(_load_json(snapshot_path, "holdings_snapshot handoff"), spec)
    decision = _load_core_decision(inputs, "allocation_decision", "allocation_decision")
    _validate_core_allocation_decision(snapshot, decision)
    payload = _core_allocation_payload(snapshot, decision)
    artifacts = _artifact_paths(stage, step["output_files"])
    files = artifacts["allocation_report"]["files"]
    _write_json(Path(files["canonical"]), payload)
    Path(files["companion"]).write_text(
        _core_allocation_markdown(payload), encoding="utf-8", newline="\n"
    )
    return artifacts


def _core_dividend_payload(
    snapshot: Mapping[str, Any], enrichment: Mapping[str, Any]
) -> dict[str, Any]:
    if enrichment["as_of"] != snapshot["as_of"]:
        raise ReplayError("dividend enrichment as_of does not match holdings snapshot")
    if enrichment["snapshot_sha256"] != _core_snapshot_sha256(snapshot):
        raise ReplayError("dividend enrichment snapshot_sha256 does not match step-1 handoff")
    snapshot_symbols = {row["symbol"] for row in snapshot["positions"]}
    covered = enrichment["covered_tickers"]
    enriched = [row["ticker"] for row in enrichment["holdings"]]
    if not covered or len(covered) != len(set(covered)):
        raise ReplayError("dividend covered_tickers must be non-empty and unique")
    if len(enriched) != len(set(enriched)) or set(enriched) != set(covered):
        raise ReplayError("dividend enrichment holdings must match covered_tickers exactly")
    if not set(covered) <= snapshot_symbols:
        raise ReplayError("dividend covered_tickers must be an explicit snapshot symbol subset")
    return {"as_of": snapshot["as_of"], "holdings": enrichment["holdings"]}


def _run_core_dividend_native(
    repo_root: Path, payload: Mapping[str, Any], fixed_timestamp: str
) -> Mapping[str, Any]:
    module = _load_module_from_path(
        repo_root
        / "skills"
        / "kanchi-dividend-review-monitor"
        / "scripts"
        / "build_review_queue.py",
        "core_portfolio_dividend_review",
    )
    try:
        report = module.build_report(dict(payload))
    except Exception as exc:
        raise ReplayError(f"native dividend rule API failed: {exc}") from exc
    report = dict(report)
    _require_rfc3339(report.get("generated_at"), "dividend report generated_at")
    report["generated_at"] = fixed_timestamp
    _assert_finite_json(report, "native dividend report")
    if report.get("as_of") != payload["as_of"]:
        raise ReplayError("native dividend report as_of does not match replay input")
    if not isinstance(report.get("results"), list) or not report["results"]:
        raise ReplayError("native dividend report must contain at least one result")
    return report


def _expected_core_dividend_report(
    repo_root: Path,
    spec: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
) -> Mapping[str, Any]:
    if set(consumed) != {"holdings_snapshot"}:
        raise ReplayError("core dividend review requires the holdings_snapshot handoff")
    snapshot_path = _core_consumed_path(consumed, "holdings_snapshot")
    snapshot = _validate_core_snapshot(_load_json(snapshot_path, "holdings_snapshot handoff"), spec)
    enrichment = _validate_core_contract(
        _load_json(inputs["dividend_enrichment"], "dividend enrichment"),
        "dividend_enrichment",
    )
    if enrichment["as_of"] != _core_date(spec):
        raise ReplayError("dividend enrichment as_of must match fixed_timestamp date")
    payload = _core_dividend_payload(snapshot, enrichment)
    return _run_core_dividend_native(repo_root, payload, spec["fixed_timestamp"])


def _core_portfolio_dividend(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    first = _expected_core_dividend_report(repo_root, spec, inputs, consumed)
    second = _expected_core_dividend_report(repo_root, spec, inputs, consumed)
    if first != second:
        raise ReplayError("native dividend rule API was non-deterministic after normalization")
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["dividend_review_findings"]["files"]["canonical"]), first)
    return artifacts


def _validate_core_allocation_handoff(
    spec: Mapping[str, Any], inputs: Mapping[str, Path], consumed: Mapping[str, dict[str, Any]]
) -> tuple[Mapping[str, Any], Path, Mapping[str, Any], Mapping[str, Any]]:
    allocation_path = _core_consumed_path(consumed, "allocation_report")
    allocation = _load_json(allocation_path, "allocation_report handoff")
    snapshot = _validate_core_snapshot(
        _load_json(inputs["holdings_snapshot"], "core portfolio holdings snapshot"), spec
    )
    decision = _load_core_decision(inputs, "allocation_decision", "allocation_decision")
    # The decision is sealed to the canonical step-1 bytes, not the source fixture's layout.
    if decision["snapshot_sha256"] != _core_snapshot_sha256(snapshot):
        raise ReplayError("allocation decision snapshot_sha256 is not canonical step-1 evidence")
    expected = _core_allocation_payload(snapshot, decision)
    if allocation != expected:
        raise ReplayError("allocation_report handoff does not match recomputed arithmetic")
    return allocation, allocation_path, snapshot, decision


def _core_rebalance_payload(
    allocation: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    decision: Mapping[str, Any],
    dividend_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    positions = {row["symbol"]: row for row in snapshot["positions"]}
    projected_values = {symbol: row["market_value"] for symbol, row in positions.items()}
    projected_cash = snapshot["account"]["cash"]
    action_ids = [row["action_id"] for row in decision["actions"]]
    if len(action_ids) != len(set(action_ids)):
        raise ReplayError("rebalance action_id values must be unique")
    actions = []
    for action in decision["actions"]:
        position = positions.get(action["symbol"])
        if position is None:
            raise ReplayError(f"rebalance action references unknown symbol {action['symbol']}")
        if action["action"] != "TRIM":
            raise ReplayError("core replay supports only manual TRIM proposals")
        if not _close_number(action["reference_price"], position["current_price"]):
            raise ReplayError("rebalance reference price does not match snapshot")
        estimated = action["shares"] * action["reference_price"]
        remaining = projected_values[action["symbol"]] - estimated
        if remaining < 0:
            raise ReplayError("rebalance action cannot trim more than the held market value")
        projected_values[action["symbol"]] = remaining
        projected_cash += estimated
        actions.append(
            {
                **action,
                "estimated_value": estimated,
                "status": "PROPOSED_NOT_SUBMITTED",
            }
        )
    equity = snapshot["account"]["equity"]
    projected = {
        f"{symbol}_pct": round(value / equity * 100, 6)
        for symbol, value in projected_values.items()
    }
    projected["cash_pct"] = round(projected_cash / equity * 100, 6)
    if dividend_report is None:
        dividend_review = {
            "status": "NOT_RUN",
            "reason": "Optional step 3 was skipped in the required-only replay.",
        }
    else:
        warnings = [
            (row, finding)
            for row in dividend_report["results"]
            for finding in row.get("findings", [])
            if row.get("status") == "WARN" and finding.get("trigger") == "T2"
        ]
        if len(warnings) != 1:
            raise ReplayError("full-path dividend review must contain exactly one T2 WARN")
        row, finding = warnings[0]
        response = decision.get("dividend_response")
        if response != "PAUSE_OPTIONAL_ADDS_PENDING_HUMAN_REVIEW":
            raise ReplayError("T2 WARN must propagate PAUSE_OPTIONAL_ADDS to rebalance")
        dividend_review = {
            "status": "WARN",
            "symbol": row["ticker"],
            "trigger": finding["trigger"],
            "response": response,
        }
    return {
        "schema_version": "1.0",
        "as_of": allocation["as_of"],
        "decision": decision["decision"],
        "dividend_review": dividend_review,
        "actions": actions,
        "projected_allocation": projected,
        "manual_execution_required": True,
    }


def _core_portfolio_rebalance(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    expected_consumed = {"allocation_report"}
    full_path = "dividend_review_findings" in consumed
    if full_path:
        expected_consumed.add("dividend_review_findings")
    if set(consumed) != expected_consumed:
        raise ReplayError(f"rebalance received unexpected artifacts: {sorted(consumed)}")
    allocation, allocation_path, snapshot, _ = _validate_core_allocation_handoff(
        spec, inputs, consumed
    )
    input_name = "rebalance_decision_full" if full_path else "rebalance_decision_required"
    decision = _load_core_decision(inputs, input_name, "rebalance_decision")
    if decision["allocation_report_sha256"] != _file_sha256(allocation_path):
        raise ReplayError("rebalance decision allocation_report_sha256 mismatch")
    dividend_report = None
    dividend_path = None
    if full_path:
        dividend_path = _core_consumed_path(consumed, "dividend_review_findings")
        dividend_report = _load_json(dividend_path, "dividend_review_findings handoff")
        expected_dividend = _expected_core_dividend_report(
            repo_root,
            spec,
            inputs,
            {
                "holdings_snapshot": {
                    "files": {
                        "canonical": str(inputs["holdings_snapshot"]),
                    }
                }
            },
        )
        if dividend_report != expected_dividend:
            raise ReplayError("dividend_review_findings handoff failed native recomputation")
        if decision["dividend_review_sha256"] != _file_sha256(dividend_path):
            raise ReplayError("rebalance decision dividend_review_sha256 mismatch")
    elif decision["dividend_review_sha256"] is not None:
        raise ReplayError("required-only rebalance must not bind optional dividend evidence")
    elif decision["dividend_response"] is not None:
        raise ReplayError("required-only rebalance must not include an optional dividend response")
    if decision["human_approved"] is not True or decision["execution_authorized"] is not False:
        raise ReplayError("rebalance decision must be human-approved but not execution-authorized")
    payload = _core_rebalance_payload(allocation, snapshot, decision, dividend_report)
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_yaml(Path(artifacts["rebalance_actions"]["files"]["canonical"]), payload)
    return artifacts


def _core_portfolio_journal(
    _repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"rebalance_actions"}:
        raise ReplayError("core journal requires only the rebalance_actions handoff")
    rebalance_path = _core_consumed_path(consumed, "rebalance_actions")
    rebalance = load_yaml(rebalance_path)
    full_path = rebalance.get("dividend_review", {}).get("status") != "NOT_RUN"
    input_name = "journal_decision_full" if full_path else "journal_decision_required"
    decision = _load_core_decision(inputs, input_name, "journal_decision")
    if decision["rebalance_actions_sha256"] != _file_sha256(rebalance_path):
        raise ReplayError("journal decision rebalance_actions_sha256 mismatch")
    if decision["human_approved"] is not True or decision["execution_authorized"] is not False:
        raise ReplayError("journal decision must be human-approved but not execution-authorized")
    dividend = rebalance["dividend_review"]
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "journal_type": "core_portfolio_weekly",
        "review_date": _core_date(spec),
        "source_snapshot": "01_holdings_snapshot.json",
        "allocation_decision": decision["allocation_decision"],
        "dividend_review_status": dividend["status"],
    }
    if full_path:
        payload["dividend_review"] = {
            key: dividend[key] for key in ("symbol", "trigger", "response")
        }
    payload.update(
        {
            "proposed_actions": [
                {
                    "action_id": row["action_id"],
                    "symbol": row["symbol"],
                    "action": row["action"],
                    "shares": row["shares"],
                    "estimated_value": row["estimated_value"],
                    "broker_status": "NOT_SUBMITTED",
                }
                for row in rebalance["actions"]
            ],
            "projected_cash_pct": rebalance["projected_allocation"]["cash_pct"],
            "human_confirmation": {
                "broker_state_verified": decision["broker_state_verified"],
                "disclosure_reviewed": decision["disclosure_reviewed"],
                "tax_impact_reviewed": decision["tax_impact_reviewed"],
                "execution_authorized": decision["execution_authorized"],
            },
            "note": decision["note"],
        }
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_yaml(Path(artifacts["weekly_journal_entry"]["files"]["canonical"]), payload)
    return artifacts
