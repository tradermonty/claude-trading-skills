"""Step adapters for the swing-opportunity-daily workflow."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import _artifact_paths, _latest_report
from .common import (
    ReplayError,
    _load_json,
    _parse_rfc3339,
    _require_finite_number,
    _run_cli,
    _write_json,
    _write_yaml,
    load_yaml,
)
from .normalize import _canonicalize, _normalize_json_file

_SWING_SCREEN_IDS = [
    "vcp_candidates",
    "momentum_burst_candidates",
    "exhaustion_hammer_candidates",
    "canslim_candidates",
    "theme_candidates",
]


_SWING_CANDIDATE_LIST_KEY = {
    "vcp_candidates": "candidates",
    "momentum_burst_candidates": "candidates",
    "exhaustion_hammer_candidates": "candidates",
    "canslim_candidates": "candidates",
    "theme_candidates": "themes",
}


_SWING_SCREEN_DISPLAY = {
    "vcp_candidates": "VCP",
    "momentum_burst_candidates": "Momentum",
    "exhaustion_hammer_candidates": "Exhaustion Hammer",
    "canslim_candidates": "CANSLIM",
    "theme_candidates": "fictional-theme",
}


_SWING_SCREEN_INPUT_KEY = {
    "vcp_candidates": "vcp_scan",
    "momentum_burst_candidates": "momentum_burst",
    "exhaustion_hammer_candidates": "exhaustion_hammer",
    "canslim_candidates": "canslim",
    "theme_candidates": "theme",
}


_SWING_SCREEN_CANONICAL = {
    "vcp_candidates": "02_vcp_candidates.json",
    "momentum_burst_candidates": "03_momentum_burst_candidates.json",
    "exhaustion_hammer_candidates": "04_exhaustion_hammer_candidates.json",
    "canslim_candidates": "05_canslim_candidates.json",
    "theme_candidates": "06_theme_candidates.json",
}


_SWING_SETUP_CANONICAL = "07_validated_setups.json"


def _swing_screen_symbols(payload: Mapping[str, Any] | None, screen_id: str) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    list_key = _SWING_CANDIDATE_LIST_KEY[screen_id]
    value = payload.get(list_key)
    if not isinstance(value, list):
        return set()
    if screen_id == "theme_candidates":
        symbols: set[str] = set()
        for entry in value:
            if isinstance(entry, dict):
                symbols.update(s for s in entry.get("symbols", []) if isinstance(s, str))
        return symbols
    return {c.get("symbol") for c in value if isinstance(c, dict) and c.get("symbol")}


def _swing_payload_contains_symbol(
    payload: Mapping[str, Any] | None, screen_id: str, symbol: str
) -> bool:
    return symbol in _swing_screen_symbols(payload, screen_id)


def _swing_payloads_from_stage(stage: Path) -> dict[str, Mapping[str, Any]]:
    payloads: dict[str, Mapping[str, Any]] = {}
    for screen_id in _SWING_SCREEN_IDS:
        path = stage / _SWING_SCREEN_CANONICAL[screen_id]
        if path.exists():
            payloads[screen_id] = _load_json(path, f"{screen_id} stage")
    validated_path = stage / _SWING_SETUP_CANONICAL
    if validated_path.exists():
        payloads["validated_setups"] = _load_json(validated_path, "validated setups stage")
    return payloads


def _swing_corroboration_line(contributing: list[str]) -> str | None:
    names = [_SWING_SCREEN_DISPLAY[sid] for sid in contributing]
    if not names:
        return None
    if len(names) == 1:
        return f"{names[0]} screen corroborated the candidate."
    if len(names) == 2:
        return f"{names[0]} and {names[1]} screens corroborated the candidate."
    return f"{', '.join(names[:-1])}, and {names[-1]} screens corroborated the candidate."


def _swing_circuit_breaker(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    sizing = _load_json(inputs["sizing_parameters"], "sizing parameters")
    _require_finite_number(sizing.get("account_size"), "circuit breaker account_size")
    state_dir = work / "empty_state"
    state_dir.mkdir(parents=True)
    reports = work / "reports"
    reports.mkdir(parents=True)
    _run_cli(
        [
            sys.executable,
            str(
                repo_root
                / "skills"
                / "drawdown-circuit-breaker"
                / "scripts"
                / "check_circuit_breaker.py"
            ),
            "--state-dir",
            str(state_dir),
            "--account-size",
            str(int(sizing["account_size"])),
            "--as-of",
            spec["fixed_timestamp"][:10],
            "--output-dir",
            str(reports),
            "--json-only",
        ],
        repo_root,
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    _normalize_json_file(
        _latest_report(reports, "circuit_breaker_decision_*.json"),
        Path(artifacts["circuit_breaker_decision"]["files"]["canonical"]),
        spec["fixed_timestamp"],
        {str(state_dir): "$STATE/empty_state", str(reports): "$WORK/reports"},
    )
    return artifacts


def _swing_screen_executor(artifact_id: str):
    input_key = _SWING_SCREEN_INPUT_KEY[artifact_id]
    list_key = _SWING_CANDIDATE_LIST_KEY[artifact_id]

    def _executor(
        repo_root: Path,
        spec: Mapping[str, Any],
        step: Mapping[str, Any],
        inputs: Mapping[str, Path],
        consumed: Mapping[str, dict[str, Any]],
        work: Path,
        stage: Path,
    ) -> dict[str, dict[str, Any]]:
        if consumed:
            raise ReplayError(f"{artifact_id} must not consume upstream artifacts")
        fixture = _load_json(inputs[input_key], f"{artifact_id} fixture")
        if not isinstance(fixture, dict):
            raise ReplayError(f"{artifact_id} fixture must be a mapping")
        if not isinstance(fixture.get(list_key), list):
            raise ReplayError(f"{artifact_id} fixture {list_key!r} must be a list")
        artifacts = _artifact_paths(stage, step["output_files"])
        _write_json(Path(artifacts[artifact_id]["files"]["canonical"]), fixture)
        return artifacts

    return _executor


def _swing_validate_setups(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    fixture = _load_json(inputs["validated_setups"], "validated setups fixture")
    if not isinstance(fixture, dict) or not isinstance(fixture.get("setups"), list):
        raise ReplayError("validated setups fixture must contain a setups list")
    if "vcp_candidates" not in consumed:
        raise ReplayError("validated setups requires the VCP screen to have been run")
    provided = [sid for sid in _SWING_SCREEN_IDS if sid in consumed]
    missing = [sid for sid in _SWING_SCREEN_IDS if sid not in consumed]
    setups = []
    for item in fixture["setups"]:
        item = dict(item)
        symbol = item.get("symbol")
        if not symbol:
            raise ReplayError("validated setup is missing a symbol")
        vcp_path = Path(consumed["vcp_candidates"]["files"]["canonical"])
        vcp = _load_json(vcp_path, "vcp handoff")
        vcp_candidates = vcp.get("candidates")
        if not isinstance(vcp_candidates, list) or not vcp_candidates:
            raise ReplayError("VCP screen produced no candidates")
        by_symbol = {
            cand.get("symbol"): cand
            for cand in vcp_candidates
            if isinstance(cand, dict) and cand.get("symbol")
        }
        cand = by_symbol.get(symbol)
        if cand is None:
            raise ReplayError(
                f"validated setup symbol {symbol!r} does not match any VCP candidate "
                f"({sorted(by_symbol) or 'none'})"
            )
        pivot = cand.get("pivot_price")
        stop = cand.get("suggested_stop")
        if item.get("entry_price") != pivot:
            raise ReplayError(
                f"validated setup entry {item.get('entry_price')} != VCP pivot {pivot} for {symbol}"
            )
        if item.get("stop_price") != stop:
            raise ReplayError(
                f"validated setup stop {item.get('stop_price')} != VCP suggested stop {stop} "
                f"for {symbol}"
            )
        item["source_artifacts"] = [
            sid
            for sid in provided
            if _swing_payload_contains_symbol(
                _load_json(Path(consumed[sid]["files"]["canonical"]), f"{sid} handoff"),
                sid,
                symbol,
            )
        ]
        setups.append(item)
    payload = {
        "schema_version": fixture.get("schema_version"),
        "as_of": fixture.get("as_of"),
        "inputs_provided": provided,
        "inputs_missing": missing,
        "setups": setups,
        "rejected": fixture.get("rejected", []),
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["validated_setups"]["files"]["canonical"]), payload)
    return artifacts


def _swing_position_size(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    validated = _load_json(
        Path(consumed["validated_setups"]["files"]["canonical"]), "validated setups handoff"
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
        Path(artifacts["position_sizing"]["files"]["canonical"]),
        spec["fixed_timestamp"],
        {},
    )
    return artifacts


def _swing_build_plan(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"validated_setups", "position_sizing"}:
        raise ReplayError(f"swing build_plan received unexpected artifacts: {sorted(consumed)}")
    validated = _load_json(
        Path(consumed["validated_setups"]["files"]["canonical"]), "validated setups handoff"
    )
    sizing = _load_json(
        Path(consumed["position_sizing"]["files"]["canonical"]), "position sizing handoff"
    )
    setup = validated["setups"][0]
    entry = setup["entry_price"]
    stop = setup["stop_price"]
    target = setup["target_price"]
    shares = int(sizing["final_recommended_shares"])
    payload = {
        "schema_version": "1.0",
        "as_of": validated["as_of"],
        "plans": [
            {
                "symbol": setup["symbol"],
                "side": "BUY",
                "entry_type": "STOP_LIMIT",
                "entry_price": entry,
                "limit_price": round(entry * 1.005, 2),
                "stop_price": stop,
                "target_price": target,
                "shares": shares,
                "position_value": sizing["final_position_value"],
                "planned_risk_dollars": sizing["final_risk_dollars"],
                "risk_reward_ratio": round((target - entry) / (entry - stop), 4),
                "order_status": "PROPOSED_NOT_SUBMITTED",
            }
        ],
        "manual_execution_required": True,
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["trade_plans"]["files"]["canonical"]), payload)
    return artifacts


def _swing_thesis_date(spec: Mapping[str, Any]) -> str:
    """Return YYYYMMDD in the RFC3339 timestamp's declared offset, without UTC conversion."""
    fixed = _parse_rfc3339(spec["fixed_timestamp"], "fixed_timestamp")
    return fixed.strftime("%Y%m%d")


def _swing_journal(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    decision = load_yaml(inputs["journal"])
    fixed_ts = spec["fixed_timestamp"]
    has_trade_plans = "trade_plans" in consumed
    sizing = _load_json(
        Path(consumed["position_sizing"]["files"]["canonical"]), "position sizing handoff"
    )
    shares = int(sizing["final_recommended_shares"])
    entry_price = sizing["parameters"]["entry_price"]
    stop_price = sizing["parameters"]["stop_price"]

    stage_payloads = _swing_payloads_from_stage(stage)
    validated = stage_payloads.get("validated_setups")
    if not validated or not isinstance(validated.get("setups"), list):
        raise ReplayError("journal requires the validated setups artifact")
    setup_list = validated["setups"]
    if len(setup_list) != 1:
        raise ReplayError(
            f"journal must be tied to exactly one validated setup; found {len(setup_list)}"
        )
    setup = setup_list[0]
    symbol = setup.get("symbol")
    if not symbol:
        raise ReplayError("journal validated setup is missing a symbol")
    if setup.get("entry_price") != entry_price:
        raise ReplayError(
            f"journal setup entry {setup.get('entry_price')} != position sizing entry "
            f"{entry_price} for {symbol}"
        )
    if setup.get("stop_price") != stop_price:
        raise ReplayError(
            f"journal setup stop {setup.get('stop_price')} != position sizing stop "
            f"{stop_price} for {symbol}"
        )

    contributing = [
        sid
        for sid in _SWING_SCREEN_IDS
        if sid in stage_payloads
        and _swing_payload_contains_symbol(stage_payloads[sid], sid, symbol)
    ]
    non_vcp = [sid for sid in contributing if sid != "vcp_candidates"]
    corroboration = _swing_corroboration_line(non_vcp)
    evidence = [decision["evidence_base"]]
    if corroboration:
        evidence.append(corroboration)
    evidence.append(decision["evidence_manual"])

    if has_trade_plans:
        origin_skill = "breakout-trade-planner"
        origin_file = "09_trade_plans.json"
        idea_reason = decision["reason_full_path"]
        entry_ready_reason = "Weekly setup, position size, and optional trade plan were reviewed."
        thesis_suffix = "_cd34"
    else:
        origin_skill = "vcp-screener"
        origin_file = "02_vcp_candidates.json"
        idea_reason = decision["reason_required_only"]
        entry_ready_reason = "Weekly setup and position size were reviewed."
        thesis_suffix = "_ab12"
    thesis_date = _swing_thesis_date(spec)
    thesis_id = f"th_{symbol.lower()}_gro_{thesis_date}{thesis_suffix}"

    payload = {
        "thesis_id": thesis_id,
        "ticker": symbol,
        "created_at": fixed_ts,
        "updated_at": fixed_ts,
        "thesis_type": decision["thesis_type"],
        "setup_type": decision["setup_type"],
        "catalyst": decision.get("catalyst"),
        "status": "ENTRY_READY",
        "status_history": [
            {"status": "IDEA", "at": fixed_ts, "reason": idea_reason},
            {"status": "ENTRY_READY", "at": fixed_ts, "reason": entry_ready_reason},
        ],
        "thesis_statement": (
            f"{symbol} holds the fictional {entry_price:.2f} pivot after a tightening VCP base."
        ),
        "mechanism_tag": "behavior",
        "evidence": evidence,
        "kill_criteria": [f"Close below the planned {stop_price:.2f} stop invalidates the setup."],
        "confidence": decision["confidence"],
        "confidence_score": decision["confidence_score"],
        "entry": {
            "target_price": entry_price,
            "conditions": decision["entry_conditions"],
            "actual_price": None,
            "actual_date": None,
        },
        "exit": {
            "stop_loss": stop_price,
            "stop_loss_pct": decision["exit"]["stop_loss_pct"],
            "take_profit": decision["exit"]["take_profit"],
            "take_profit_rr": decision["exit"]["take_profit_rr"],
            "time_stop_days": decision["exit"]["time_stop_days"],
            "actual_price": None,
            "actual_date": None,
            "exit_reason": None,
        },
        "position": {
            "shares": shares,
            "shares_remaining": shares,
            "position_value": sizing["final_position_value"],
            "risk_dollars": sizing["final_risk_dollars"],
            "risk_pct_of_account": sizing["final_risk_pct"],
            "account_type": decision["account_type"],
            "sizing_method": decision["sizing_method"],
            "raw_source": {
                "skill": "position-sizer",
                "file": "08_position_sizing.json",
                "fields": {
                    "final_recommended_shares": shares,
                    "final_risk_dollars": sizing["final_risk_dollars"],
                },
            },
        },
        "market_context": decision["market_context"],
        "monitoring": {
            "review_interval_days": decision["monitoring"]["review_interval_days"],
            "next_review_date": decision["monitoring"]["next_review_date"],
            "last_review_date": None,
            "review_status": "OK",
            "triggers_config": [],
            "alerts": [],
        },
        "origin": {
            "skill": origin_skill,
            "output_file": origin_file,
            "screening_grade": decision["screening_grade"],
            "screening_score": decision["screening_score"],
            "raw_provenance": {"fixture": "fictional"},
        },
        "linked_reports": [],
        "outcome": {
            "pnl_dollars": None,
            "pnl_pct": None,
            "holding_days": None,
            "mae_pct": None,
            "mfe_pct": None,
            "mae_mfe_source": None,
            "lessons_learned": None,
        },
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_yaml(Path(artifacts["candidate_journal_entry"]["files"]["canonical"]), payload)
    return artifacts


def _swing_discipline(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    expected = {"candidate_journal_entry", "position_sizing", "circuit_breaker_decision"}
    if "trade_plans" in consumed:
        expected.add("trade_plans")
    if set(consumed) != expected:
        raise ReplayError(f"swing discipline received unexpected artifacts: {sorted(consumed)}")
    journal = load_yaml(Path(consumed["candidate_journal_entry"]["files"]["canonical"]))
    sizing = _load_json(
        Path(consumed["position_sizing"]["files"]["canonical"]), "position sizing handoff"
    )
    regime_path = inputs["exposure_decision"].resolve()
    cb_path = Path(consumed["circuit_breaker_decision"]["files"]["canonical"]).resolve()

    symbol = journal["ticker"]
    planned_risk = sizing["final_risk_dollars"]
    _require_finite_number(planned_risk, "discipline planned_risk_dollars")
    journal_shares = journal.get("position", {}).get("shares")
    if journal_shares != sizing["final_recommended_shares"]:
        raise ReplayError(
            f"journal shares {journal_shares} != position sizing "
            f"{sizing['final_recommended_shares']} for {symbol}"
        )
    if journal.get("position", {}).get("risk_dollars") != planned_risk:
        raise ReplayError(
            f"journal risk_dollars {journal.get('position', {}).get('risk_dollars')} != "
            f"position sizing {planned_risk} for {symbol}"
        )
    if journal.get("entry", {}).get("target_price") != sizing["parameters"]["entry_price"]:
        raise ReplayError(f"journal entry != position sizing entry for {symbol}")
    if journal.get("exit", {}).get("stop_loss") != sizing["parameters"]["stop_price"]:
        raise ReplayError(f"journal stop != position sizing stop for {symbol}")

    has_trade_plans = "trade_plans" in consumed
    plan_checks = {
        "entry_in_written_plan": False,
        "stop_predefined": False,
        "size_within_plan": False,
    }
    if has_trade_plans:
        plans_path = Path(consumed["trade_plans"]["files"]["canonical"]).resolve()
        plans = _load_json(plans_path, "trade plans handoff")
        plan_list = plans.get("plans")
        if not isinstance(plan_list, list) or not plan_list:
            raise ReplayError("trade plan handoff has no plans")
        if len(plan_list) != 1:
            raise ReplayError(f"discipline expects exactly one trade plan; found {len(plan_list)}")
        plan = plan_list[0]
        checks = [
            ("symbol", plan.get("symbol"), symbol),
            ("entry_price", plan.get("entry_price"), sizing["parameters"]["entry_price"]),
            ("stop_price", plan.get("stop_price"), sizing["parameters"]["stop_price"]),
            ("shares", plan.get("shares"), sizing["final_recommended_shares"]),
            ("position_value", plan.get("position_value"), sizing["final_position_value"]),
            (
                "planned_risk_dollars",
                plan.get("planned_risk_dollars"),
                sizing["final_risk_dollars"],
            ),
        ]
        mismatches = [
            (field, got, expected_val) for field, got, expected_val in checks if got != expected_val
        ]
        if mismatches:
            detail = ", ".join(
                f"{field}={got!r} != {expected_val!r}" for field, got, expected_val in mismatches
            )
            raise ReplayError(f"trade plan for {symbol} inconsistent with sizing/journal: {detail}")
        plan_checks["entry_in_written_plan"] = True
        plan_checks["stop_predefined"] = True
        plan_checks["size_within_plan"] = True

    answers_path = work / "answers.json"
    _write_json(
        answers_path,
        {
            "candidates": [
                {
                    "symbol": symbol,
                    "thesis_id": journal["thesis_id"],
                    "order_intent": "MANUAL_ORDER",
                    "entry_in_written_plan": plan_checks["entry_in_written_plan"],
                    "stop_predefined": plan_checks["stop_predefined"],
                    "size_within_plan": plan_checks["size_within_plan"],
                    "planned_risk_dollars": planned_risk,
                    "actual_risk_dollars": planned_risk,
                    "notes": f"Fictional {journal_shares}-share plan; no order submitted.",
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
        "json": "11_pre_trade_discipline_decision.json",
        "markdown": "11_pre_trade_discipline_decision.md",
    }
    _write_json(Path(artifacts["pre_trade_discipline_decision"]["files"]["canonical"]), payload)
    markdown_sources = sorted(reports.glob("pre_trade_discipline_decision_*.md"))
    if not markdown_sources:
        raise ReplayError("pre-trade discipline markdown report was not produced")
    Path(artifacts["pre_trade_discipline_decision"]["files"]["companion"]).write_text(
        markdown_sources[-1].read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    return artifacts


_swing_vcp_screen = _swing_screen_executor("vcp_candidates")


_swing_momentum_burst = _swing_screen_executor("momentum_burst_candidates")


_swing_exhaustion_hammer = _swing_screen_executor("exhaustion_hammer_candidates")


_swing_canslim = _swing_screen_executor("canslim_candidates")


_swing_theme = _swing_screen_executor("theme_candidates")
