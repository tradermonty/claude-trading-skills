#!/usr/bin/env python3
"""Deterministic workflow contract replay harness (Issue #294, coverage 12/12).

The harness executes real offline CLIs for the Stockbee fluency, 20% study,
trade-memory, market-regime, monthly-performance-review, core-portfolio,
kanchi-dividend-weekly, shapiro-contrarian, stockbee-ep-daily, swing-opportunity-daily,
multi-asset-opportunity-daily, and strategy-research-pipeline workflows. Human decisions
and fixture-backed native API evidence are reported separately from full skill
execution. Golden outputs are comparison targets only and are never used as
replay inputs.

This file is the stable entry point and import surface (Issue #502). The
implementation lives in the ``workflow_replay_pkg`` package next to this file;
see that package's docstring for the layout. Every name the monolithic module
defined is re-exported here, and rebinding one of them on this module (for
example ``monkeypatch.setattr(workflow_replay, "_run_cli", fake)``) is
forwarded to the package modules that share that binding, so patches keep
affecting replay behavior exactly as they did before the split.
"""

from __future__ import annotations

import argparse  # noqa: F401
import hashlib  # noqa: F401
import importlib  # noqa: F401
import importlib.util  # noqa: F401
import json  # noqa: F401
import math  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
import shutil  # noqa: F401
import subprocess  # noqa: F401
import sys
import tempfile  # noqa: F401
import types
from collections.abc import Callable, Mapping, Sequence  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from datetime import datetime  # noqa: F401
from pathlib import Path, PurePosixPath, PureWindowsPath  # noqa: F401
from typing import Any

import yaml  # noqa: F401
from jsonschema import Draft202012Validator, FormatChecker  # noqa: F401
from validate_provenance import validate_provenance  # noqa: F401
from workflow_replay_pkg import (
    artifacts as _artifacts,
)
from workflow_replay_pkg import (
    cli as _cli,
)
from workflow_replay_pkg import (
    common as _common,
)
from workflow_replay_pkg import (
    constants as _constants,
)
from workflow_replay_pkg import (
    execution as _execution,
)
from workflow_replay_pkg import (
    golden as _golden,
)
from workflow_replay_pkg import (
    manifest as _manifest,
)
from workflow_replay_pkg import (
    normalize as _normalize,
)
from workflow_replay_pkg import (
    registry as _registry,
)
from workflow_replay_pkg import (
    steps_core_portfolio as _steps_core_portfolio,
)
from workflow_replay_pkg import (
    steps_ep as _steps_ep,
)
from workflow_replay_pkg import (
    steps_kanchi as _steps_kanchi,
)
from workflow_replay_pkg import (
    steps_market_regime as _steps_market_regime,
)
from workflow_replay_pkg import (
    steps_monthly as _steps_monthly,
)
from workflow_replay_pkg import (
    steps_multi_asset as _steps_multi_asset,
)
from workflow_replay_pkg import (
    steps_portfolio_holdings as _steps_portfolio_holdings,
)
from workflow_replay_pkg import (
    steps_shapiro as _steps_shapiro,
)
from workflow_replay_pkg import (
    steps_stockbee_fluency as _steps_stockbee_fluency,
)
from workflow_replay_pkg import (
    steps_strategy_research as _steps_strategy_research,
)
from workflow_replay_pkg import (
    steps_swing as _steps_swing,
)
from workflow_replay_pkg import (
    steps_trade_memory as _steps_trade_memory,
)
from workflow_replay_pkg import (
    steps_twenty_pct as _steps_twenty_pct,
)
from workflow_replay_pkg.artifacts import (
    _artifact_file_digests,
    _artifact_paths,
    _latest_report,
    _validate_artifact_files,
    _validate_artifact_provenance,
)
from workflow_replay_pkg.cli import (
    build_parser,
    main,
)
from workflow_replay_pkg.common import (
    ExecutorRegistration,
    ReplayError,
    _assert_finite_json,
    _dump_yaml_with_digest_allowlist,
    _load_json,
    _load_module_from_path,
    _parse_rfc3339,
    _repo_module,
    _require_finite_number,
    _require_mapping_keys,
    _require_non_empty_string,
    _require_rfc3339,
    _run_cli,
    _schema_error_details,
    _scrubbed_environment,
    _trader_memory_modules,
    _write_json,
    _write_yaml,
    load_yaml,
)
from workflow_replay_pkg.constants import (
    CORE_PORTFOLIO_SCHEMA,
    DEFAULT_COVERAGE,
    DIGEST_ALLOWLIST_KEYS,
    EP_ANALYZE_SCHEMA,
    FROZEN_DEFERRED_WORKFLOWS,
    KANCHI_ACTIONABLE_VERDICTS,
    KANCHI_FORBIDDEN_REVIEW_TOKENS,
    KANCHI_REPLAY_SCHEMA,
    MANUAL_LESSONS_SCHEMA,
    MARKET_COMPONENT_CONFIG,
    MULTI_ASSET_REPLAY_SCHEMA,
    REPO_ROOT,
    RFC3339_PATTERN,
    SENSITIVE_ENV_MARKERS,
    SPEC_SCHEMA,
    TIMESTAMP_FIELDS,
    TWENTY_PCT_LESSONS_SCHEMA,
    VARIANTS,
)
from workflow_replay_pkg.execution import (
    _cleanup_backup,
    _prompt_text,
    _publish_tree,
    _publish_trees_transactionally,
    _write_manifest,
    execute_replay,
)
from workflow_replay_pkg.golden import (
    _covered_specs,
    check_goldens,
    compare_trees,
    generate_goldens,
)
from workflow_replay_pkg.manifest import (
    _validate_golden_dirs,
    _validate_runtime_output,
    coverage_errors,
    validate_coverage,
    validate_spec,
)
from workflow_replay_pkg.normalize import (
    _ELAPSED_RE,
    _PYTEST_DOCS_RE,
    _PYTEST_LOCATION_LINE_RE,
    _PYTEST_STATUS_LINE_RE,
    _PYTEST_WARNING_ENTRY_RE,
    _PYTEST_WARNINGS_COUNT_RE,
    _PYTEST_WARNINGS_HEADER_RE,
    _RM_RF_ENTRY_RE,
    _RM_RF_OS_ERROR_RE,
    _RM_RF_WARN_CALL_RE,
    _canonical_json_bytes,
    _canonicalize,
    _canonicalize_values,
    _exact_payload_sha256,
    _file_sha256,
    _is_rm_rf_warnings_noise,
    _is_warning_structural_line,
    _normalize_elapsed,
    _normalize_json_file,
    _normalize_jsonl_file,
    _normalize_review_test_command,
    _normalize_review_test_output,
    _normalize_text_file,
    _paths_overlap,
    _payload_sha256,
    _remove_status_line_warnings_count,
    _safe_relative,
    _strip_banner_framed_rm_rf,
    _strip_pytest_warning_summary,
    _strip_unbannered_tail_rm_rf,
)
from workflow_replay_pkg.registry import (
    EXECUTORS,
)
from workflow_replay_pkg.steps_core_portfolio import (
    _close_number,
    _core_allocation_markdown,
    _core_allocation_payload,
    _core_consumed_path,
    _core_date,
    _core_dividend_payload,
    _core_portfolio_allocation,
    _core_portfolio_dividend,
    _core_portfolio_journal,
    _core_portfolio_rebalance,
    _core_portfolio_snapshot,
    _core_rebalance_payload,
    _core_snapshot_sha256,
    _expected_core_dividend_report,
    _load_core_decision,
    _run_core_dividend_native,
    _validate_core_allocation_decision,
    _validate_core_allocation_handoff,
    _validate_core_contract,
    _validate_core_snapshot,
)
from workflow_replay_pkg.steps_ep import (
    _ep_analyze,
    _ep_circuit,
    _ep_discipline,
    _ep_input,
    _ep_journal,
    _ep_match_size,
    _ep_parameters,
    _ep_plan,
    _ep_read,
    _ep_screen,
    _ep_size,
    _ep_sources,
    _ep_validate,
    _validate_ep_analyze_contract,
)
from workflow_replay_pkg.steps_kanchi import (
    _kanchi_artifact_link,
    _kanchi_candidate_screen,
    _kanchi_fixed_date,
    _kanchi_high_yield_screen,
    _kanchi_pullback_screen,
    _kanchi_register_thesis,
    _kanchi_review_actions,
    _kanchi_review_queue,
    _kanchi_tax_advice,
    _kanchi_underwrite,
    _validate_kanchi_contract,
)
from workflow_replay_pkg.steps_market_regime import (
    MARKET_PROVENANCE_RUN_ID,
    _expected_exposure_decision,
    _load_market_fixture_set,
    _market_analysis,
    _market_composite,
    _market_modules,
    _market_regime_breadth,
    _market_regime_component,
    _market_regime_exposure,
    _market_regime_top_risk,
    _market_regime_uptrend,
    _validate_market_component_fixture,
    _validate_market_report,
)
from workflow_replay_pkg.steps_monthly import (
    _MONTHLY_COACH_ARTIFACTS,
    _canonical_source_record,
    _monthly_aggregate,
    _monthly_backtest,
    _monthly_coach,
    _monthly_decision_log,
    _monthly_postmortem,
    _monthly_skill_review,
    _validate_monthly_coach_decision,
)
from workflow_replay_pkg.steps_multi_asset import (
    _multi_asset_fixed_date,
    _multi_hypotheses,
    _multi_macro_modules,
    _multi_macro_regime,
    _multi_news_brief,
    _multi_position_size,
    _multi_register,
    _multi_theme,
    _require_unique_ids,
    _validate_multi_asset_contract,
)
from workflow_replay_pkg.steps_portfolio_holdings import (
    _portfolio_holdings_review,
)
from workflow_replay_pkg.steps_shapiro import (
    _shapiro_detector,
    _shapiro_gate,
    _shapiro_journal,
    _shapiro_logic,
    _shapiro_manual,
    _shapiro_parameters,
    _shapiro_size,
)
from workflow_replay_pkg.steps_stockbee_fluency import (
    _manual_lessons,
    _stockbee_ingest,
    _stockbee_summarize,
    _stockbee_update,
    _validate_manual_contract,
)
from workflow_replay_pkg.steps_strategy_research import (
    _strategy_research_detect,
    _strategy_research_detect_final,
    _strategy_research_detect_initial,
    _strategy_research_hints,
    _strategy_research_hold,
    _strategy_research_tickets,
)
from workflow_replay_pkg.steps_swing import (
    _SWING_CANDIDATE_LIST_KEY,
    _SWING_SCREEN_CANONICAL,
    _SWING_SCREEN_DISPLAY,
    _SWING_SCREEN_IDS,
    _SWING_SCREEN_INPUT_KEY,
    _SWING_SETUP_CANONICAL,
    _swing_build_plan,
    _swing_canslim,
    _swing_circuit_breaker,
    _swing_corroboration_line,
    _swing_discipline,
    _swing_exhaustion_hammer,
    _swing_journal,
    _swing_momentum_burst,
    _swing_payload_contains_symbol,
    _swing_payloads_from_stage,
    _swing_position_size,
    _swing_screen_executor,
    _swing_screen_symbols,
    _swing_theme,
    _swing_thesis_date,
    _swing_validate_setups,
    _swing_vcp_screen,
)
from workflow_replay_pkg.steps_trade_memory import (
    _trade_memory_backtest,
    _trade_memory_close,
    _trade_memory_coach,
    _trade_memory_lessons,
    _trade_memory_postmortem,
    _without_lesson_side_effects,
)
from workflow_replay_pkg.steps_twenty_pct import (
    _manual_twenty_pct_lessons,
    _stage_state_handoff,
    _twenty_pct_enrich,
    _twenty_pct_scan,
    _twenty_pct_script,
    _twenty_pct_summarize,
    _twenty_pct_update_outcomes,
    _validate_twenty_pct_manual_contract,
)

__all__ = [
    "REPO_ROOT",
    "DEFAULT_COVERAGE",
    "SPEC_SCHEMA",
    "MANUAL_LESSONS_SCHEMA",
    "TWENTY_PCT_LESSONS_SCHEMA",
    "CORE_PORTFOLIO_SCHEMA",
    "KANCHI_REPLAY_SCHEMA",
    "EP_ANALYZE_SCHEMA",
    "MULTI_ASSET_REPLAY_SCHEMA",
    "KANCHI_ACTIONABLE_VERDICTS",
    "KANCHI_FORBIDDEN_REVIEW_TOKENS",
    "VARIANTS",
    "FROZEN_DEFERRED_WORKFLOWS",
    "MARKET_COMPONENT_CONFIG",
    "TIMESTAMP_FIELDS",
    "SENSITIVE_ENV_MARKERS",
    "DIGEST_ALLOWLIST_KEYS",
    "RFC3339_PATTERN",
    "ReplayError",
    "ExecutorRegistration",
    "load_yaml",
    "_load_json",
    "_dump_yaml_with_digest_allowlist",
    "_schema_error_details",
    "_require_rfc3339",
    "_write_json",
    "_scrubbed_environment",
    "_run_cli",
    "_repo_module",
    "_trader_memory_modules",
    "_write_yaml",
    "_require_mapping_keys",
    "_require_non_empty_string",
    "_require_finite_number",
    "_load_module_from_path",
    "_assert_finite_json",
    "_parse_rfc3339",
    "_safe_relative",
    "_paths_overlap",
    "_canonicalize",
    "_canonicalize_values",
    "_normalize_json_file",
    "_normalize_jsonl_file",
    "_canonical_json_bytes",
    "_payload_sha256",
    "_file_sha256",
    "_ELAPSED_RE",
    "_normalize_elapsed",
    "_normalize_review_test_command",
    "_PYTEST_WARNINGS_HEADER_RE",
    "_PYTEST_DOCS_RE",
    "_PYTEST_WARNINGS_COUNT_RE",
    "_PYTEST_WARNING_ENTRY_RE",
    "_PYTEST_STATUS_LINE_RE",
    "_PYTEST_LOCATION_LINE_RE",
    "_RM_RF_ENTRY_RE",
    "_RM_RF_OS_ERROR_RE",
    "_RM_RF_WARN_CALL_RE",
    "_remove_status_line_warnings_count",
    "_is_warning_structural_line",
    "_is_rm_rf_warnings_noise",
    "_strip_banner_framed_rm_rf",
    "_strip_unbannered_tail_rm_rf",
    "_strip_pytest_warning_summary",
    "_normalize_review_test_output",
    "_exact_payload_sha256",
    "_normalize_text_file",
    "_latest_report",
    "_artifact_paths",
    "_validate_artifact_files",
    "_validate_artifact_provenance",
    "_artifact_file_digests",
    "_validate_manual_contract",
    "_stockbee_ingest",
    "_stockbee_update",
    "_stockbee_summarize",
    "_manual_lessons",
    "_validate_twenty_pct_manual_contract",
    "_twenty_pct_script",
    "_stage_state_handoff",
    "_twenty_pct_scan",
    "_twenty_pct_enrich",
    "_twenty_pct_update_outcomes",
    "_twenty_pct_summarize",
    "_manual_twenty_pct_lessons",
    "_trade_memory_close",
    "_trade_memory_postmortem",
    "_trade_memory_coach",
    "_trade_memory_backtest",
    "_without_lesson_side_effects",
    "_trade_memory_lessons",
    "_validate_market_component_fixture",
    "_load_market_fixture_set",
    "_market_modules",
    "_market_composite",
    "MARKET_PROVENANCE_RUN_ID",
    "_market_analysis",
    "_validate_market_report",
    "_market_regime_component",
    "_market_regime_breadth",
    "_market_regime_uptrend",
    "_market_regime_top_risk",
    "_expected_exposure_decision",
    "_market_regime_exposure",
    "_portfolio_holdings_review",
    "_validate_core_contract",
    "_core_date",
    "_core_snapshot_sha256",
    "_close_number",
    "_validate_core_snapshot",
    "_core_consumed_path",
    "_core_portfolio_snapshot",
    "_core_allocation_payload",
    "_core_allocation_markdown",
    "_load_core_decision",
    "_validate_core_allocation_decision",
    "_core_portfolio_allocation",
    "_core_dividend_payload",
    "_run_core_dividend_native",
    "_expected_core_dividend_report",
    "_core_portfolio_dividend",
    "_validate_core_allocation_handoff",
    "_core_rebalance_payload",
    "_core_portfolio_rebalance",
    "_core_portfolio_journal",
    "_monthly_aggregate",
    "_monthly_postmortem",
    "_canonical_source_record",
    "_MONTHLY_COACH_ARTIFACTS",
    "_validate_monthly_coach_decision",
    "_monthly_coach",
    "_monthly_backtest",
    "_monthly_skill_review",
    "_monthly_decision_log",
    "_SWING_SCREEN_IDS",
    "_SWING_CANDIDATE_LIST_KEY",
    "_SWING_SCREEN_DISPLAY",
    "_SWING_SCREEN_INPUT_KEY",
    "_SWING_SCREEN_CANONICAL",
    "_SWING_SETUP_CANONICAL",
    "_swing_screen_symbols",
    "_swing_payload_contains_symbol",
    "_swing_payloads_from_stage",
    "_swing_corroboration_line",
    "_swing_circuit_breaker",
    "_swing_screen_executor",
    "_swing_validate_setups",
    "_swing_position_size",
    "_swing_build_plan",
    "_swing_thesis_date",
    "_swing_journal",
    "_swing_discipline",
    "_swing_vcp_screen",
    "_swing_momentum_burst",
    "_swing_exhaustion_hammer",
    "_swing_canslim",
    "_swing_theme",
    "_validate_kanchi_contract",
    "_kanchi_fixed_date",
    "_kanchi_candidate_screen",
    "_kanchi_high_yield_screen",
    "_kanchi_pullback_screen",
    "_kanchi_underwrite",
    "_kanchi_tax_advice",
    "_kanchi_review_actions",
    "_kanchi_review_queue",
    "_kanchi_artifact_link",
    "_kanchi_register_thesis",
    "_shapiro_parameters",
    "_shapiro_logic",
    "_shapiro_detector",
    "_shapiro_manual",
    "_shapiro_gate",
    "_shapiro_size",
    "_shapiro_journal",
    "_ep_input",
    "_ep_parameters",
    "_ep_read",
    "_ep_sources",
    "_ep_circuit",
    "_ep_screen",
    "_validate_ep_analyze_contract",
    "_ep_analyze",
    "_ep_validate",
    "_ep_size",
    "_ep_match_size",
    "_ep_plan",
    "_ep_journal",
    "_ep_discipline",
    "_validate_multi_asset_contract",
    "_multi_asset_fixed_date",
    "_multi_macro_modules",
    "_multi_macro_regime",
    "_multi_theme",
    "_multi_news_brief",
    "_require_unique_ids",
    "_multi_hypotheses",
    "_multi_position_size",
    "_multi_register",
    "_strategy_research_tickets",
    "_strategy_research_detect",
    "_strategy_research_detect_initial",
    "_strategy_research_hints",
    "_strategy_research_detect_final",
    "_strategy_research_hold",
    "EXECUTORS",
    "coverage_errors",
    "validate_coverage",
    "_validate_golden_dirs",
    "_validate_runtime_output",
    "validate_spec",
    "_prompt_text",
    "_write_manifest",
    "_cleanup_backup",
    "_publish_tree",
    "_publish_trees_transactionally",
    "execute_replay",
    "compare_trees",
    "_covered_specs",
    "check_goldens",
    "generate_goldens",
    "build_parser",
    "main",
]

_PACKAGE_MODULES = (
    _constants,
    _common,
    _normalize,
    _artifacts,
    _steps_stockbee_fluency,
    _steps_twenty_pct,
    _steps_trade_memory,
    _steps_market_regime,
    _steps_portfolio_holdings,
    _steps_core_portfolio,
    _steps_monthly,
    _steps_swing,
    _steps_kanchi,
    _steps_shapiro,
    _steps_ep,
    _steps_multi_asset,
    _steps_strategy_research,
    _registry,
    _manifest,
    _execution,
    _golden,
    _cli,
)


class _ReplayShimModule(types.ModuleType):
    """Module type that forwards attribute rebinding into the package modules.

    Package functions resolve helpers through their own module globals. When a
    caller rebinds a name on this shim, every package module whose global of
    the same name is still the object the shim held is rebound too, matching
    the single-namespace behavior of the former monolithic module.

    Patch through this shim (``monkeypatch.setattr(workflow_replay, ...)``).
    Patching one package module directly does not reach the others, and only
    rebinding is forwarded, not ``delattr``. Every new submodule of
    ``workflow_replay_pkg`` must be added to ``_PACKAGE_MODULES``; a test
    enforces this.
    """

    def __setattr__(self, name: str, value: Any) -> None:
        missing = object()
        previous = self.__dict__.get(name, missing)
        super().__setattr__(name, value)
        if previous is missing:
            return
        for module in _PACKAGE_MODULES:
            if module.__dict__.get(name, missing) is previous:
                setattr(module, name, value)


sys.modules[__name__].__class__ = _ReplayShimModule


if __name__ == "__main__":
    raise SystemExit(main())
