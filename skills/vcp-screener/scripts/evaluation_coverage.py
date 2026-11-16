"""Common evaluation-coverage contract, vendored in standalone consumer skills."""

from __future__ import annotations

from collections import Counter

SCHEMA_VERSION = "1.0"


def build_evaluation_coverage(outcomes: dict) -> dict:
    """Count each universe member once: None means an evaluated decision."""
    reasons = dict(sorted(Counter(reason for reason in outcomes.values() if reason).items()))
    universe_size = len(outcomes)
    evaluated = sum(reason is None for reason in outcomes.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "universe_size": universe_size,
        "evaluated": evaluated,
        "not_evaluated": universe_size - evaluated,
        "not_evaluated_reasons": reasons,
        "verdict": "not_evaluable"
        if evaluated == 0
        else ("complete" if evaluated == universe_size else "partial"),
    }


def validate_evaluation_coverage(block: object) -> list[str]:
    """Validate version, counts, disjoint failure reasons and derived verdict."""
    if not isinstance(block, dict):
        return ["evaluation_coverage must be an object"]
    errors = []
    if block.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    for field in ("universe_size", "evaluated", "not_evaluated"):
        if type(block.get(field)) is not int or block[field] < 0:
            errors.append(f"{field} must be a nonnegative integer")
    reasons = block.get("not_evaluated_reasons")
    if not isinstance(reasons, dict) or any(
        not isinstance(reason, str) or not reason.strip() or type(count) is not int or count <= 0
        for reason, count in (reasons.items() if isinstance(reasons, dict) else [])
    ):
        errors.append("not_evaluated_reasons must map reason names to positive integer counts")
    if errors:
        return errors
    size, evaluated, unavailable = (
        block[k] for k in ("universe_size", "evaluated", "not_evaluated")
    )
    if evaluated + unavailable != size:
        errors.append("evaluated + not_evaluated must equal universe_size")
    if sum(reasons.values()) != unavailable:
        errors.append("reason counts must sum to not_evaluated")
    verdict = "not_evaluable" if evaluated == 0 else ("complete" if unavailable == 0 else "partial")
    if block.get("verdict") != verdict:
        errors.append(f"verdict must be {verdict} for these counts")
    return errors


def evaluation_input_usable(payload: object) -> bool:
    """Keep legacy inputs; exclude declared invalid, partial or unavailable coverage."""
    if not isinstance(payload, dict):
        return False
    if "evaluation_coverage" not in payload:
        return True
    block = payload["evaluation_coverage"]
    return not validate_evaluation_coverage(block) and block["verdict"] == "complete"
