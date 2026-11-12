"""Deterministic workflow contract replay harness (Issue #294, coverage 14/14).

The harness executes real offline CLIs for the Stockbee fluency, 20% study,
trade-memory, market-regime, monthly-performance-review, core-portfolio,
kanchi-dividend-weekly, shapiro-contrarian, stockbee-ep-daily, swing-opportunity-daily,
multi-asset-opportunity-daily, and strategy-research-pipeline workflows. Human decisions
and fixture-backed native API evidence are reported separately from full skill
execution. Golden outputs are comparison targets only and are never used as
replay inputs.
"""

# Command-line parser and entry point. The module docstring above is the
# ``--help`` description (``build_parser`` passes ``__doc__``), so it stays
# identical to the docstring of the pre-split scripts/workflow_replay.py.

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .constants import DEFAULT_COVERAGE, REPO_ROOT, VARIANTS
from .execution import execute_replay
from .golden import check_goldens, generate_goldens
from .manifest import validate_coverage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate coverage and replay specs")
    validate.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)

    run = subparsers.add_parser("run", help="Run one replay variant")
    run.add_argument("--spec", type=Path, required=True)
    run.add_argument("--variant", choices=VARIANTS, required=True)
    run.add_argument("--output-dir", type=Path, required=True)

    check = subparsers.add_parser("check", help="Regenerate in temp and compare goldens")
    check.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    check.add_argument("--report", type=Path)

    generate = subparsers.add_parser(
        "generate", help="Regenerate committed example goldens from source inputs"
    )
    generate.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        summary = validate_coverage(REPO_ROOT, args.coverage.resolve())
        print(json.dumps(summary, indent=2))
        return 0
    if args.command == "run":
        report = execute_replay(
            REPO_ROOT, args.spec.resolve(), args.variant, args.output_dir.resolve()
        )
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "check":
        differences = check_goldens(
            REPO_ROOT,
            args.coverage.resolve(),
            args.report.resolve() if args.report else None,
        )
        if differences:
            print("Workflow replay drift detected:", file=sys.stderr)
            for difference in differences:
                print(f"- {difference}", file=sys.stderr)
            return 1
        print("Workflow replay goldens are current.")
        return 0
    if args.command == "generate":
        generate_goldens(REPO_ROOT, args.coverage.resolve())
        print("Workflow replay goldens regenerated.")
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
