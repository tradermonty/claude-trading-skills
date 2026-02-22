#!/usr/bin/env python3
"""Contract helpers for edge candidate strategy artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

INTERFACE_VERSION = "edge-finder-candidate/v1"

SUPPORTED_ENTRY_FAMILIES = {
    "pivot_breakout",
    "gap_up_continuation",
}

REQUIRED_TOP_LEVEL_KEYS = {
    "id",
    "name",
    "universe",
    "signals",
    "risk",
    "cost_model",
    "validation",
    "promotion_gates",
}


def read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file and return a dict payload."""
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    """Write a dict payload as stable YAML."""
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False))


def validate_ticket_payload(ticket: dict[str, Any]) -> list[str]:
    """Validate research ticket minimum schema for export."""
    errors: list[str] = []

    for key in ("id", "hypothesis_type", "entry_family"):
        value = ticket.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"ticket.{key} must be a non-empty string")

    entry_family = ticket.get("entry_family")
    if isinstance(entry_family, str) and entry_family not in SUPPORTED_ENTRY_FAMILIES:
        allowed = ", ".join(sorted(SUPPORTED_ENTRY_FAMILIES))
        errors.append(f"ticket.entry_family must be one of: {allowed}")

    validation = ticket.get("validation")
    if validation is not None:
        if not isinstance(validation, dict):
            errors.append("ticket.validation must be a mapping when provided")
        else:
            method = validation.get("method", "full_sample")
            if method != "full_sample":
                errors.append("ticket.validation.method must be 'full_sample' for Phase I")
            if validation.get("oos_ratio") is not None:
                errors.append("ticket.validation.oos_ratio must be omitted or null for Phase I")

    return errors


def validate_interface_contract(
    spec: dict[str, Any],
    candidate_id: str | None = None,
    stage: str = "phase1",
) -> list[str]:
    """Validate edge-finder-candidate/v1 constraints."""
    errors: list[str] = []

    missing = sorted(REQUIRED_TOP_LEVEL_KEYS - spec.keys())
    if missing:
        errors.append(f"missing required top-level keys: {', '.join(missing)}")

    if candidate_id is not None and spec.get("id") != candidate_id:
        errors.append(
            "candidate directory name must match strategy id "
            f"(candidate_id={candidate_id}, id={spec.get('id')})"
        )

    signals = spec.get("signals")
    if not isinstance(signals, dict):
        errors.append("signals must be a mapping")
        signals = {}

    entry = signals.get("entry")
    if not isinstance(entry, dict):
        errors.append("signals.entry must be a mapping")
        entry = {}

    exit_rules = signals.get("exit")
    if not isinstance(exit_rules, dict):
        errors.append("signals.exit must be a mapping")
        exit_rules = {}

    entry_type = entry.get("type")
    if not isinstance(entry_type, str) or not entry_type.strip():
        errors.append("signals.entry.type must be a non-empty string")
    elif entry_type not in SUPPORTED_ENTRY_FAMILIES:
        allowed = ", ".join(sorted(SUPPORTED_ENTRY_FAMILIES))
        errors.append(f"signals.entry.type must be one of: {allowed}")

    conditions = entry.get("conditions")
    if not isinstance(conditions, list) or len(conditions) == 0:
        errors.append("signals.entry.conditions must be a non-empty list")

    stop_loss = exit_rules.get("stop_loss")
    if not isinstance(stop_loss, str) or not stop_loss.strip():
        errors.append("signals.exit.stop_loss must be a non-empty string")

    trailing_stop = exit_rules.get("trailing_stop")
    take_profit = exit_rules.get("take_profit")
    trailing_ok = isinstance(trailing_stop, str) and bool(trailing_stop.strip())
    take_profit_ok = isinstance(take_profit, str) and bool(take_profit.strip())
    if not (trailing_ok or take_profit_ok):
        errors.append("signals.exit must include trailing_stop or take_profit")

    risk = spec.get("risk")
    if not isinstance(risk, dict):
        errors.append("risk must be a mapping")
        risk = {}

    risk_per_trade = risk.get("risk_per_trade")
    if not _is_number(risk_per_trade) or not (0 < float(risk_per_trade) <= 0.10):
        errors.append("risk.risk_per_trade must satisfy 0 < value <= 0.10")

    max_positions = risk.get("max_positions")
    if isinstance(max_positions, bool) or not isinstance(max_positions, int) or max_positions < 1:
        errors.append("risk.max_positions must be an integer >= 1")

    max_sector_exposure = risk.get("max_sector_exposure")
    if not _is_number(max_sector_exposure) or not (0 < float(max_sector_exposure) <= 1.0):
        errors.append("risk.max_sector_exposure must satisfy 0 < value <= 1.0")

    validation = spec.get("validation")
    if not isinstance(validation, dict):
        errors.append("validation must be a mapping")
        validation = {}

    if stage == "phase1":
        if validation.get("method") != "full_sample":
            errors.append("validation.method must be 'full_sample' in Phase I")
        if validation.get("oos_ratio") is not None:
            errors.append("validation.oos_ratio must be omitted or null in Phase I")

    vcp_detection = spec.get("vcp_detection")
    if vcp_detection is not None and not isinstance(vcp_detection, dict):
        errors.append("vcp_detection must be a mapping when provided")

    gap_detection = spec.get("gap_up_detection")
    if gap_detection is not None and not isinstance(gap_detection, dict):
        errors.append("gap_up_detection must be a mapping when provided")

    if entry_type == "pivot_breakout" and not isinstance(vcp_detection, dict):
        errors.append("pivot_breakout requires vcp_detection block")
    if entry_type == "gap_up_continuation" and not isinstance(gap_detection, dict):
        errors.append("gap_up_continuation requires gap_up_detection block")

    return errors


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))
