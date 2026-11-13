#!/usr/bin/env python3
"""Validate and rank normalized US undervalued-growth candidates (schema v3, contract v3.5).

The evaluator performs no network access. Upstream research must prepare a
source-linked JSON snapshot matching references/data-contract.md. The script
normalizes cash flow, verifies forecast arithmetic, blocks accounting-basis
mixing, validates corporate-action preflight evidence, calculates valuation
scenarios, routes candidates fail-closed, and writes audit-ready JSON/Markdown.
"""

# This file is the stable CLI entry point and import surface (Issue #502). The
# implementation lives in the evaluation_*.py stage modules next to this file,
# each importing only from the stages listed before it:
#   evaluation_common      constants, input coercion, formatting, source helpers
#   evaluation_financials  corporate actions, cash flow, metrics, forecast bridge
#   evaluation_valuation   valuation scenarios, sector profile, score, data quality
#   evaluation_candidate   quality gate and per-candidate evaluation
#   evaluation_ranking     sorting, final-three selection, funnel, evaluate_snapshot
#   evaluation_report      Markdown rendering and output writing
# Every name the monolithic module defined is re-exported here. A stage function
# reads globals from its own module, so a monkeypatch on this module does not
# reach callers inside the stages; patch the defining stage module instead.
# Copies of this file loaded under another name (spec_from_file_location)
# share the same stage modules from sys.modules, so stage state is shared.

from __future__ import annotations

import argparse
import json
import math  # noqa: F401
import statistics  # noqa: F401
import sys
from collections.abc import Iterable, Mapping, Sequence  # noqa: F401
from copy import deepcopy  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
from pathlib import Path
from typing import Any  # noqa: F401

from coverage_semantics import derive_ranking_scope_from_audit  # noqa: F401
from evaluation_candidate import (
    _best_low_case_upside,
    _estimate_range_scenarios,
    _highest_scenario_upside,
    _preferred_three_year_upside,
    _quality_eligibility_gate,
    _screened_out_result,
    evaluate_candidate,
)
from evaluation_common import (
    ALLOWED_CASH_FLOW_METHODS,
    ALLOWED_EXCHANGES,
    ALLOWED_LISTING_STATUSES,
    ALLOWED_METRIC_BASES,
    ALLOWED_MNA_STATUSES,
    ALLOWED_PERIOD_KINDS,
    ALLOWED_SCREENING_STATUSES,
    ALLOWED_SESSIONS,
    ALLOWED_SOURCE_TYPES,
    ALLOWED_SPECIAL_CASES,
    ALLOWED_VALUATION_BASES,
    CONTRACT_REVISION,
    DEFAULT_CONFIG,
    HARD_FLAG_LABELS,
    QUALITY_WEIGHTS,
    RUNTIME_FINGERPRINT,
    SCHEMA_VERSION,
    SCORE_LIMITS,
    SKILL_VERSION,
    ContractError,
    InputError,
    _cagr,
    _candidate_source_ids,
    _cyclicality_penalty,
    _data_quality_penalty,
    _deep_merge,
    _dilution_penalty,
    _dispersion_from_bounds,
    _estimate_breadth_penalty,
    _estimate_dispersion_penalty,
    _evidence_ids,
    _format_number,
    _format_pct,
    _format_price,
    _has_primary_source,
    _has_tier,
    _history_cagr,
    _integer,
    _list,
    _mapping,
    _min_valid,
    _number,
    _parse_date,
    _pct,
    _resolved_sources,
    _round,
    _sbc_penalty,
    _scenario,
    _source_index,
    _sources_resolve,
    _text,
    _years_between,
    parse_iso8601,
    runtime_metadata,
    validate_and_normalize_snapshot,
)
from evaluation_financials import (
    _calculate_financial_metrics,
    _cash_flow_component,
    _cash_flow_sources_support_period,
    _period_record,
    _reconstruct_ttm_cash_flow,
    _validate_corporate_action,
    _validate_forecast_bridge,
    _validate_gaap_reconciliation,
)
from evaluation_ranking import (
    _derive_ranking_scope,
    _review_sort_key,
    _select_final_three,
    _sort_key,
    _validate_funnel,
    evaluate_snapshot,
)
from evaluation_report import (
    _label,
    _md_escape,
    _missing,
    _render_candidate_detail,
    _render_latest_earnings,
    _render_list,
    _render_peers,
    _render_score_table,
    _scenario_value,
    _timestamp_for_filename,
    render_markdown,
    write_outputs,
)
from evaluation_valuation import (
    _calculate_data_quality,
    _calculate_score_components,
    _calculate_valuation,
    _validate_sector_profile,
)

__all__ = [
    "CONTRACT_REVISION",
    "RUNTIME_FINGERPRINT",
    "SCHEMA_VERSION",
    "SKILL_VERSION",
    "runtime_metadata",
    "ContractError",
    "validate_and_normalize_snapshot",
    "DEFAULT_CONFIG",
    "ALLOWED_EXCHANGES",
    "ALLOWED_SPECIAL_CASES",
    "ALLOWED_VALUATION_BASES",
    "ALLOWED_METRIC_BASES",
    "ALLOWED_SOURCE_TYPES",
    "ALLOWED_PERIOD_KINDS",
    "ALLOWED_SESSIONS",
    "ALLOWED_SCREENING_STATUSES",
    "ALLOWED_CASH_FLOW_METHODS",
    "ALLOWED_MNA_STATUSES",
    "ALLOWED_LISTING_STATUSES",
    "SCORE_LIMITS",
    "QUALITY_WEIGHTS",
    "HARD_FLAG_LABELS",
    "InputError",
    "_mapping",
    "_list",
    "_text",
    "_number",
    "_integer",
    "_round",
    "parse_iso8601",
    "_parse_date",
    "_years_between",
    "_pct",
    "_cagr",
    "_history_cagr",
    "_format_number",
    "_format_pct",
    "_format_price",
    "_deep_merge",
    "_scenario",
    "_min_valid",
    "_estimate_breadth_penalty",
    "_estimate_dispersion_penalty",
    "_data_quality_penalty",
    "_cyclicality_penalty",
    "_sbc_penalty",
    "_dilution_penalty",
    "_dispersion_from_bounds",
    "_source_index",
    "_evidence_ids",
    "_resolved_sources",
    "_sources_resolve",
    "_has_tier",
    "_has_primary_source",
    "_candidate_source_ids",
    "_validate_corporate_action",
    "_cash_flow_component",
    "_cash_flow_sources_support_period",
    "_reconstruct_ttm_cash_flow",
    "_calculate_financial_metrics",
    "_period_record",
    "_validate_forecast_bridge",
    "_validate_gaap_reconciliation",
    "_calculate_valuation",
    "_validate_sector_profile",
    "_calculate_score_components",
    "_calculate_data_quality",
    "_highest_scenario_upside",
    "_preferred_three_year_upside",
    "_estimate_range_scenarios",
    "_best_low_case_upside",
    "_quality_eligibility_gate",
    "_screened_out_result",
    "evaluate_candidate",
    "_sort_key",
    "_review_sort_key",
    "_select_final_three",
    "_validate_funnel",
    "evaluate_snapshot",
    "_label",
    "_missing",
    "_md_escape",
    "_scenario_value",
    "_derive_ranking_scope",
    "_render_list",
    "_render_latest_earnings",
    "_render_peers",
    "_render_score_table",
    "_render_candidate_detail",
    "render_markdown",
    "_timestamp_for_filename",
    "write_outputs",
    "parse_args",
    "main",
]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate, score, and rank normalized US undervalued-growth candidates (schema v3, contract v3.5)."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Normalized schema-3 / contract-3.5 candidate JSON input",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/us-undervalued-growth-screener"),
        help="Output directory for JSON and Markdown reports",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Root used to resolve and hash broad-screen audit artifacts; defaults to input directory",
    )
    parser.add_argument("--top", type=int, default=None, help="Maximum ranked candidates")
    parser.add_argument("--language", choices=("en", "ja"), default="en")
    parser.add_argument("--strict", action="store_true", help="Enable fail-closed research gates")
    parser.add_argument("--stdout", action="store_true", help="Print the Markdown report to stdout")
    parser.add_argument(
        "--require-final",
        action="store_true",
        help="Return exit code 2 after writing outputs when the run is provisional or the global contract is invalid",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if "--version" in raw_argv:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    args = parse_args(raw_argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise InputError("top-level JSON must be an object")
        artifact_root = args.artifact_root or args.input.parent
        report = evaluate_snapshot(
            payload, strict=args.strict, top=args.top, artifact_root=artifact_root
        )
        json_path, md_path = write_outputs(report, args.output_dir, language=args.language)
    except (OSError, json.JSONDecodeError, InputError, ContractError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"wrote: {json_path}")
    print(f"wrote: {md_path}")
    if args.stdout:
        print()
        print(md_path.read_text(encoding="utf-8"))
    if args.require_final and (
        report.get("ranking_status") != "final" or not _mapping(report.get("contract")).get("valid")
    ):
        print(
            "ERROR: final-run gate failed; see generated report for contract blockers",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
