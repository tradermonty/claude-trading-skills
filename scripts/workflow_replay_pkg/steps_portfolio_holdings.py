"""Step adapter for the portfolio-holdings-review workflow."""

from __future__ import annotations

import sys
from pathlib import Path

from .artifacts import _artifact_paths
from .common import (
    ReplayError,
    _load_json,
    _require_mapping_keys,
    _require_non_empty_string,
    _run_cli,
)


def _portfolio_holdings_review(repo_root, spec, step, inputs, consumed, work, stage):
    """Execute the offline CSV analyzer; no broker or journal step is involved."""
    if consumed:
        raise ReplayError("offline holdings review must not consume prior artifacts")
    context = _require_mapping_keys(
        _load_json(inputs["review_context"], "holdings review context"),
        label="holdings review context",
        required={"fictional", "as_of"},
    )
    if context["fictional"] is not True:
        raise ReplayError("holdings replay requires explicitly fictional input")
    stamp = _require_non_empty_string(context["as_of"], "holdings source as_of")
    reports = work / "reports"
    _run_cli(
        [
            sys.executable,
            str(repo_root / "skills/portfolio-manager/scripts/review_csv.py"),
            "--input",
            str(inputs["holdings_csv"]),
            "--as-of",
            stamp,
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    roles = artifacts["holdings_allocation_report"]["files"]
    for role, suffix in (("canonical", "json"), ("markdown", "md")):
        Path(roles[role]).write_bytes((reports / f"portfolio_csv_review.{suffix}").read_bytes())
    return artifacts
