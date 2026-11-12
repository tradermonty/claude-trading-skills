"""Step adapters for the earnings-weekly workflow (Issue #216)."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import _artifact_paths, _latest_report
from .common import (
    ReplayError,
    _load_json,
    _repo_module,
    _require_finite_number,
    _run_cli,
    _write_json,
    load_yaml,
)
from .normalize import _canonicalize, _normalize_json_file
from .steps_core_portfolio import _close_number

# The analyzer's default budget (200) cannot cover a 28-day window on a real key:
# the real client spends one request per calendar day plus one per reporting symbol.
# The value mirrors the analyzer SKILL.md example; real volume is not measured here.
EARNINGS_MAX_API_CALLS = "600"


def _earnings_fmp_cli(
    repo_root: Path,
    skill: str,
    script: str,
    fixture: Path,
    cli_args: list[str],
) -> None:
    """Run a real FMP-backed skill CLI against the fictional offline fixture."""
    _run_cli(
        [
            sys.executable,
            str(repo_root / "scripts" / "replay_offline_fmp_cli.py"),
            "--skill-dir",
            str(repo_root / "skills" / skill / "scripts"),
            "--script",
            script,
            "--fixture",
            str(fixture),
            "--",
            *cli_args,
        ],
        repo_root,
    )


def _earnings_analyze(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if consumed:
        raise ReplayError("earnings analysis must not consume upstream artifacts")
    reports = work / "analysis_reports"
    reports.mkdir(parents=True)
    _earnings_fmp_cli(
        repo_root,
        "earnings-trade-analyzer",
        "analyze_earnings_trades.py",
        inputs["fmp_fixture"],
        [
            "--api-key",
            "offline",
            "--as-of",
            spec["fixed_timestamp"][:10],
            "--lookback-days",
            "28",
            "--min-market-cap",
            "500000000",
            "--apply-entry-filter",
            "--top",
            "20",
            "--max-api-calls",
            EARNINGS_MAX_API_CALLS,
            "--output-dir",
            str(reports),
        ],
    )
    source = _latest_report(reports, "earnings_trade_analyzer_*.json")
    payload = _load_json(source, "earnings-trade-analyzer report")
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise ReplayError("earnings-trade-analyzer report must carry schema_version 1.0")
    rows = payload.get("results")
    if not isinstance(rows, list) or not rows:
        raise ReplayError("earnings-trade-analyzer produced no scored candidates")
    fixture = _load_json(inputs["fmp_fixture"], "earnings fixture")
    unknown = {row.get("symbol") for row in rows} - set(fixture["profiles"])
    if unknown:
        raise ReplayError(f"analyzer reported symbols outside the fixture: {sorted(unknown)}")
    artifacts = _artifact_paths(stage, step["output_files"])
    _normalize_json_file(
        source,
        Path(artifacts["earnings_trade_analysis"]["files"]["canonical"]),
        spec["fixed_timestamp"],
        {str(reports): "$WORK/analysis_reports"},
    )
    return artifacts


def _earnings_pead(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"earnings_trade_analysis"}:
        raise ReplayError("PEAD screening requires exactly the earnings_trade_analysis handoff")
    candidates = Path(consumed["earnings_trade_analysis"]["files"]["canonical"])
    analysis = _load_json(candidates, "earnings analysis handoff")
    reports = work / "pead_reports"
    reports.mkdir(parents=True)
    _earnings_fmp_cli(
        repo_root,
        "pead-screener",
        "screen_pead.py",
        inputs["fmp_fixture"],
        [
            "--api-key",
            "offline",
            "--candidates-json",
            str(candidates),
            "--min-grade",
            "B",
            "--max-api-calls",
            EARNINGS_MAX_API_CALLS,
            "--output-dir",
            str(reports),
        ],
    )
    source = _latest_report(reports, "pead_screener_*.json")
    payload = _load_json(source, "PEAD report")
    if payload.get("metadata", {}).get("mode") != "B":
        raise ReplayError("PEAD screening must run in Mode B on the analyzer JSON")
    rows = payload.get("results")
    if not isinstance(rows, list) or not rows:
        raise ReplayError("PEAD screening produced no candidates")
    analysed = {row["symbol"] for row in analysis["results"]}
    if {row["symbol"] for row in rows} - analysed:
        raise ReplayError("PEAD results include a symbol absent from the analyzer handoff")
    artifacts = _artifact_paths(stage, step["output_files"])
    _normalize_json_file(
        source,
        Path(artifacts["pead_screen"]["files"]["canonical"]),
        spec["fixed_timestamp"],
        {
            str(candidates): candidates.name,
            str(reports): "$WORK/pead_reports",
        },
    )
    return artifacts


def _earnings_validate(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"pead_screen"}:
        raise ReplayError("earnings chart validation requires exactly the pead_screen handoff")
    review = _load_json(inputs["technical_review"], "technical review fixture")
    if not isinstance(review, dict):
        raise ReplayError("technical review fixture must be a mapping")
    setups = review.get("setups")
    rejected = review.get("rejected")
    if not isinstance(setups, list) or not isinstance(rejected, list):
        raise ReplayError("technical review needs setups and rejected lists")
    if len(setups) != 1:
        raise ReplayError(f"expected exactly one validated setup, found {len(setups)}")
    if review.get("as_of") != spec["fixed_timestamp"][:10]:
        raise ReplayError("technical review as_of differs from the replay date")
    pead = _load_json(Path(consumed["pead_screen"]["files"]["canonical"]), "PEAD handoff")
    by_symbol = {row["symbol"]: row for row in pead["results"]}
    for setup in setups:
        symbol = setup.get("symbol")
        row = by_symbol.get(symbol)
        if row is None:
            raise ReplayError(f"validated setup {symbol!r} is not a PEAD candidate")
        if row["stage"] != "BREAKOUT":
            raise ReplayError(
                f"validated setup {symbol} must be a PEAD BREAKOUT; screener stage is {row['stage']}"
            )
        for field, label in (
            ("entry_price", "entry"),
            ("stop_price", "stop"),
            ("target_price", "target"),
        ):
            if setup.get(field) != row[field]:
                raise ReplayError(
                    f"validated setup {label} {setup.get(field)} != PEAD {label} {row[field]} "
                    f"for {symbol}"
                )
        if not _close_number(
            setup.get("risk_per_share"), round(row["entry_price"] - row["stop_price"], 2)
        ):
            raise ReplayError(f"validated setup risk_per_share is inconsistent for {symbol}")
        if setup.get("manual_chart_review") != "PASS" or setup.get("decision") != "VALIDATED":
            raise ReplayError(f"validated setup {symbol} is not a passed manual chart review")
    validated = {setup["symbol"] for setup in setups}
    dropped = {item.get("symbol") for item in rejected}
    if dropped & validated or (validated | dropped) != set(by_symbol):
        raise ReplayError(
            "every PEAD candidate needs exactly one chart-review disposition "
            f"(validated {sorted(validated)}, held {sorted(dropped)}, screened {sorted(by_symbol)})"
        )
    payload = {
        "schema_version": review.get("schema_version"),
        "as_of": review["as_of"],
        "setups": [{**setup, "source_artifact": "pead_screen"} for setup in setups],
        "rejected": rejected,
        "provenance": {
            "execution": "manual_contract",
            "limitation": (
                "The chart review is a fictional human-approved fixture bound to the "
                "PEAD screener output; no chart image was analyzed."
            ),
        },
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["validated_earnings_setups"]["files"]["canonical"]), payload)
    return artifacts


def _earnings_size(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"validated_earnings_setups"}:
        raise ReplayError("earnings sizing requires exactly the validated_earnings_setups handoff")
    validated = _load_json(
        Path(consumed["validated_earnings_setups"]["files"]["canonical"]),
        "validated earnings setups handoff",
    )
    setup = validated["setups"][0]
    sizing = _load_json(inputs["sizing_parameters"], "sizing parameters")
    reports = work / "reports"
    reports.mkdir(parents=True)
    _run_cli(
        [
            sys.executable,
            str(repo_root / "skills" / "position-sizer" / "scripts" / "position_sizer.py"),
            "--account-size",
            str(sizing["account_size"]),
            "--entry",
            str(setup["entry_price"]),
            "--stop",
            str(setup["stop_price"]),
            "--risk-pct",
            str(sizing["risk_pct"]),
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    _normalize_json_file(
        _latest_report(reports, "position_sizer_*.json"),
        Path(artifacts["earnings_position_sizing"]["files"]["canonical"]),
        spec["fixed_timestamp"],
        {},
    )
    return artifacts


def _earnings_journal(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    expected = {"pead_screen", "validated_earnings_setups", "earnings_position_sizing"}
    if set(consumed) != expected:
        raise ReplayError(f"earnings journal received unexpected artifacts: {sorted(consumed)}")
    decision = load_yaml(inputs["journal_decision"])
    if decision.get("human_approved") is not True:
        raise ReplayError("earnings journal requires a human-approved register decision")
    register = decision.get("register")
    if not isinstance(register, list) or not register or len(set(register)) != len(register):
        raise ReplayError("register decision must list each symbol to register exactly once")
    if decision.get("order_intent") not in {"MANUAL_ORDER", "WATCHLIST"}:
        raise ReplayError("register decision order_intent must be MANUAL_ORDER or WATCHLIST")
    fixed_date = spec["fixed_timestamp"][:10]
    validated = _load_json(
        Path(consumed["validated_earnings_setups"]["files"]["canonical"]),
        "validated earnings setups handoff",
    )
    setups = {item["symbol"]: item for item in validated["setups"]}
    for symbol in register:
        if symbol not in setups:
            raise ReplayError(
                f"register decision names {symbol!r}, which was not validated at the chart review"
            )
    sizing = _load_json(
        Path(consumed["earnings_position_sizing"]["files"]["canonical"]), "sizing handoff"
    )
    pead_path = Path(consumed["pead_screen"]["files"]["canonical"])
    pead = _load_json(pead_path, "PEAD handoff")

    # The real PEAD report has no top-level date, so the adapter would stamp the
    # thesis with the wall clock. Hand it a filtered copy carrying the replay date.
    selected = {
        "as_of": fixed_date,
        "results": [row for row in pead["results"] if row["symbol"] in set(register)],
    }
    ingest_input = work / "pead_selected.json"
    _write_json(ingest_input, selected)

    scripts_dir = repo_root / "skills" / "trader-memory-core" / "scripts"
    thesis_ingest = _repo_module(repo_root, "thesis_ingest", scripts_dir)
    thesis_store = _repo_module(repo_root, "thesis_store", scripts_dir)
    state_dir = work / "earnings-state"
    state_dir.mkdir(parents=True)
    thesis_ids = thesis_ingest.ingest("pead-screener", str(ingest_input), str(state_dir))
    if len(thesis_ids) != len(register):
        raise ReplayError("native thesis ingest did not register every approved symbol")

    links = [
        ("pead-screener", pead_path.name),
        (
            "technical-analyst",
            Path(consumed["validated_earnings_setups"]["files"]["canonical"]).name,
        ),
        ("position-sizer", Path(consumed["earnings_position_sizing"]["files"]["canonical"]).name),
    ]
    entries = []
    for thesis_id in thesis_ids:
        for skill, token in links:
            thesis_store.link_report(state_dir, thesis_id, skill, token, fixed_date)
        thesis = thesis_store.get(state_dir, thesis_id)
        symbol = thesis["ticker"]
        setup = setups[symbol]
        if thesis["status"] != "IDEA":
            raise ReplayError("earnings registration must never leave IDEA status")
        if thesis["entry"].get("target_price") != setup["entry_price"]:
            raise ReplayError(f"registered entry differs from the validated setup for {symbol}")
        if thesis["exit"].get("stop_loss") != setup["stop_price"]:
            raise ReplayError(f"registered stop differs from the validated setup for {symbol}")
        entries.append(
            {
                "ticker": symbol,
                "thesis_type": thesis["thesis_type"],
                "status": thesis["status"],
                "created_at": thesis["created_at"],
                "next_review_date": thesis["monitoring"]["next_review_date"],
                "origin_skill": thesis["origin"]["skill"],
                "entry_target_price": thesis["entry"]["target_price"],
                "stop_loss": thesis["exit"]["stop_loss"],
                "linked_reports": [
                    {"skill": skill, "file": token, "date": fixed_date} for skill, token in links
                ],
            }
        )
    entries.sort(key=lambda row: row["ticker"])
    record = {
        "schema_version": "1.0",
        "workflow_id": "earnings-weekly",
        "recorded_at": spec["fixed_timestamp"],
        "order_intent": decision["order_intent"],
        "order_submitted": False,
        "plan": {
            "shares": sizing["final_recommended_shares"],
            "position_value": sizing["final_position_value"],
            "risk_dollars": sizing["final_risk_dollars"],
            "account_type": decision.get("account_type"),
        },
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
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["earnings_journal_entry"]["files"]["canonical"]), record)
    return artifacts


def _earnings_discipline(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    expected = {"circuit_breaker_decision", "earnings_position_sizing", "earnings_journal_entry"}
    if set(consumed) != expected:
        raise ReplayError(f"earnings discipline received unexpected artifacts: {sorted(consumed)}")
    journal = _load_json(
        Path(consumed["earnings_journal_entry"]["files"]["canonical"]), "earnings journal handoff"
    )
    sizing = _load_json(
        Path(consumed["earnings_position_sizing"]["files"]["canonical"]), "sizing handoff"
    )
    if len(journal["theses"]) != 1:
        raise ReplayError(
            f"discipline expects exactly one registered thesis; found {len(journal['theses'])}"
        )
    thesis = journal["theses"][0]
    symbol = thesis["ticker"]
    planned_risk = sizing["final_risk_dollars"]
    _require_finite_number(planned_risk, "discipline planned_risk_dollars")
    plan = journal["plan"]
    if plan["shares"] != sizing["final_recommended_shares"]:
        raise ReplayError(f"journal shares {plan['shares']} != position sizing for {symbol}")
    if plan["risk_dollars"] != planned_risk:
        raise ReplayError(f"journal risk_dollars {plan['risk_dollars']} != sizing for {symbol}")
    if thesis["entry_target_price"] != sizing["parameters"]["entry_price"]:
        raise ReplayError(f"journal entry != position sizing entry for {symbol}")
    if thesis["stop_loss"] != sizing["parameters"]["stop_price"]:
        raise ReplayError(f"journal stop != position sizing stop for {symbol}")

    regime_path = inputs["exposure_decision"].resolve()
    cb_path = Path(consumed["circuit_breaker_decision"]["files"]["canonical"]).resolve()
    answers_path = work / "answers.json"
    _write_json(
        answers_path,
        {
            "candidates": [
                {
                    "symbol": symbol,
                    "order_intent": journal["order_intent"],
                    "entry_in_written_plan": True,
                    "stop_predefined": True,
                    "size_within_plan": True,
                    "planned_risk_dollars": planned_risk,
                    "actual_risk_dollars": planned_risk,
                    "notes": f"Fictional {plan['shares']}-share plan; no order submitted.",
                }
            ]
        },
    )
    reports = work / "reports"
    reports.mkdir(parents=True)
    journal_dir = work / "journal"
    journal_dir.mkdir(parents=True)
    _run_cli(
        [
            sys.executable,
            str(
                repo_root
                / "skills"
                / "pre-trade-discipline-gate"
                / "scripts"
                / "check_pre_trade_discipline.py"
            ),
            "--answers-file",
            str(answers_path),
            "--as-of",
            spec["fixed_timestamp"],
            "--market-regime-decision",
            str(regime_path),
            "--circuit-breaker-decision",
            str(cb_path),
            "--output-dir",
            str(reports),
            "--journal-dir",
            str(journal_dir),
        ],
        repo_root,
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    source = _latest_report(reports, "pre_trade_discipline_decision_*.json")
    payload = _canonicalize(
        _load_json(source, "pre-trade discipline decision"),
        spec["fixed_timestamp"],
        {
            str(regime_path): "00_exposure_decision.json",
            str(cb_path): "01_circuit_breaker_decision.json",
            str(reports): "$WORK/reports",
            str(journal_dir): "$WORK/journal",
        },
    )
    payload["artifact_paths"] = {
        "json": "07_pre_trade_discipline_decision.json",
        "markdown": "07_pre_trade_discipline_decision.md",
    }
    _write_json(Path(artifacts["pre_trade_discipline_decision"]["files"]["canonical"]), payload)
    markdown_sources = sorted(reports.glob("pre_trade_discipline_decision_*.md"))
    if not markdown_sources:
        raise ReplayError("pre-trade discipline markdown report was not produced")
    Path(artifacts["pre_trade_discipline_decision"]["files"]["companion"]).write_text(
        markdown_sources[-1].read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    return artifacts
