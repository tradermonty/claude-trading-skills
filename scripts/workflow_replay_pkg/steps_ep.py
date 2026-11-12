"""Step adapters for the stockbee-ep-daily workflow."""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .artifacts import _artifact_paths, _latest_report
from .common import (
    ReplayError,
    _assert_finite_json,
    _load_json,
    _repo_module,
    _require_finite_number,
    _run_cli,
    _schema_error_details,
    _write_json,
    _write_yaml,
    load_yaml,
)
from .constants import EP_ANALYZE_SCHEMA, REPO_ROOT
from .normalize import _canonicalize, _file_sha256, _safe_relative
from .steps_kanchi import _kanchi_artifact_link
from .steps_swing import _swing_build_plan, _swing_position_size


def _ep_input(inputs, name, spec):
    envelope = _load_json(inputs[name], f"EP {name} fixture")
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"human_approved", "fictional", "as_of", "data"}
        or envelope["human_approved"] is not True
        or envelope["fictional"] is not True
        or envelope["as_of"] != spec["fixed_timestamp"][:10]
    ):
        raise ReplayError(f"EP {name} requires a dated, approved fictional fixture")
    _assert_finite_json(envelope, f"EP {name}")
    return envelope["data"]


def _ep_parameters(inputs, spec):
    data = _ep_input(inputs, "decision", spec)
    schema = load_yaml(REPO_ROOT / "examples/workflows/stockbee-ep-daily/decision.schema.yaml")
    errors = list(Draft202012Validator(schema).iter_errors(data))
    if errors:
        raise ReplayError(f"invalid EP decision: {errors[0].message}")
    return data


def _ep_read(consumed, artifact):
    return _load_json(Path(consumed[artifact]["files"]["canonical"]), f"EP {artifact} handoff")


def _ep_sources(consumed, stage):
    return {
        key: {
            "file": _kanchi_artifact_link(consumed, key, "canonical", stage),
            "sha256": _file_sha256(Path(bundle["files"]["canonical"])),
        }
        for key, bundle in sorted(consumed.items())
    }


def _ep_circuit(repo_root, spec, step, inputs, consumed, work, stage):
    decision = _ep_parameters(inputs, spec)
    regime = _ep_input(inputs, "exposure", spec)
    if (
        regime.get("recommendation") != "NEW_ENTRY_ALLOWED"
        or regime.get("generated_at") != spec["fixed_timestamp"]
    ):
        raise ReplayError("EP market gate requires a current NEW_ENTRY_ALLOWED decision")
    state = _ep_input(inputs, "account_state", spec)
    if not isinstance(state, list) or not all(isinstance(item, dict) for item in state):
        raise ReplayError("EP account state must be an explicit thesis list")
    ids = set()
    for thesis in state:
        if (
            not isinstance(thesis.get("thesis_id"), str)
            or not thesis["thesis_id"]
            or thesis["thesis_id"] in ids
            or not isinstance(thesis.get("ticker"), str)
            or not thesis["ticker"]
            or thesis.get("status")
            not in {"IDEA", "ACTIVE", "PARTIALLY_CLOSED", "CLOSED", "INVALIDATED"}
        ):
            raise ReplayError(
                "EP account state requires unique identified theses with valid statuses"
            )
        ids.add(thesis["thesis_id"])
    state_dir = work / "state"
    state_dir.mkdir()
    for index, thesis in enumerate(state):
        _write_yaml(state_dir / f"th_fixture_{index}.yaml", thesis)
    reports = work / "reports"
    _run_cli(
        [
            sys.executable,
            str(repo_root / "skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py"),
            "--state-dir",
            str(state_dir),
            "--account-size",
            str(decision["account_size"]),
            "--as-of",
            spec["fixed_timestamp"],
            "--output-dir",
            str(reports),
            "--json-only",
        ],
        repo_root,
    )
    payload = _canonicalize(
        _load_json(
            _latest_report(reports, "circuit_breaker_decision_*.json"), "EP circuit decision"
        ),
        spec["fixed_timestamp"],
        {str(state_dir): "$WORK/account_state", str(reports): "$WORK/reports"},
    )
    if payload.get("recommendation") != "TRADING_ALLOWED":
        raise ReplayError(f"EP circuit breaker halted: {payload.get('recommendation')}")
    payload["replay_inputs"] = {
        key: _file_sha256(inputs[key]) for key in ("exposure", "account_state")
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["circuit_breaker_decision"]["files"]["canonical"]), payload)
    return artifacts


def _ep_screen(repo_root, spec, step, inputs, consumed, work, stage):
    name = "earnings" if step["step"] == 2 else "momentum"
    payload = _ep_input(inputs, name, spec)
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ReplayError(f"EP {name} requires explicit screen results")
    events = _ep_input(inputs, "events", spec)["events"]
    symbols = {e["symbol"] for e in events}
    if any(not isinstance(row, dict) or row.get("symbol") not in symbols for row in rows):
        raise ReplayError(f"EP {name} contains an unbound symbol")
    date_key = "earnings_date" if name == "earnings" else "setup_date"
    if any(row.get(date_key) != spec["fixed_timestamp"][:10] for row in rows):
        raise ReplayError(f"EP {name} contains a stale date")
    artifacts = _artifact_paths(stage, step["output_files"])
    for bundle in artifacts.values():
        _write_json(Path(bundle["files"]["canonical"]), payload)
    return artifacts


def _validate_ep_analyze_contract(payload: Any) -> Mapping[str, Any]:
    schema = _load_json(EP_ANALYZE_SCHEMA, "stockbee-ep analyze replay contract schema")
    selected = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/analyze_ep_report",
    }
    errors = _schema_error_details(selected, payload)
    if errors:
        raise ReplayError("invalid stockbee-ep analyze report contract:\n- " + "\n- ".join(errors))
    _assert_finite_json(payload, "stockbee-ep analyze report")
    return payload


def _ep_analyze(repo_root, spec, step, inputs, consumed, work, stage):
    decision = _ep_parameters(inputs, spec)
    events = _ep_input(inputs, "events", spec)
    prices = _ep_input(inputs, "prices", spec)
    rows = events.get("events") if isinstance(events, dict) else None
    if not isinstance(rows, list) or not rows or any(not isinstance(e, dict) for e in rows):
        raise ReplayError("EP requires nonempty catalyst events")
    symbols = [e.get("symbol") for e in rows]
    if any(
        not isinstance(s, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{0,9}", s) for s in symbols
    ) or len(set(symbols)) != len(symbols):
        raise ReplayError("EP event symbols must be valid and unique")
    bars_by_symbol = prices.get("prices") if isinstance(prices, dict) else None
    if not isinstance(bars_by_symbol, dict) or set(bars_by_symbol) != set(symbols):
        raise ReplayError("EP prices must cover exactly the event symbols")
    for event in rows:
        if event.get("event_date") != spec["fixed_timestamp"][:10] or not event.get("headline"):
            raise ReplayError("EP requires a current explicit catalyst")
        bars = bars_by_symbol[event["symbol"]]
        if not isinstance(bars, list) or len(bars) < 51:
            raise ReplayError("EP requires complete offline OHLCV history")
        dates = []
        for bar in bars:
            if not isinstance(bar, dict):
                raise ReplayError("EP invalid OHLCV row")
            dates.append(datetime.strptime(bar["date"], "%Y-%m-%d").date().isoformat())
            for field in ("open", "high", "low", "close", "volume"):
                _require_finite_number(bar.get(field), f"EP {field}", minimum=0)
            if (
                not 0
                < bar["low"]
                <= min(bar["open"], bar["close"])
                <= max(bar["open"], bar["close"])
                <= bar["high"]
            ):
                raise ReplayError("EP inconsistent OHLC prices")
        if dates != sorted(set(dates)) or dates[-1] != event["event_date"]:
            raise ReplayError("EP history must be ordered, unique, and end on the event date")
    event_path, prices_path = work / "events.json", work / "prices.json"
    _write_json(event_path, events)
    _write_json(prices_path, prices)
    reports = work / "reports"
    command = [
        sys.executable,
        str(repo_root / "skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py"),
        "--events-json",
        str(event_path),
        "--prices-json",
        str(prices_path),
        "--max-api-calls",
        "0",
        "--max-risk-pct",
        str(decision["max_ep_risk_pct"]),
        "--output-dir",
        str(reports),
    ]
    replacements = {str(event_path): "$INPUT/events", str(prices_path): "$INPUT/prices"}
    for artifact, flag in (
        ("earnings_candidates", "--earnings-json"),
        ("momentum_burst_candidates", "--momentum-json"),
    ):
        if artifact in consumed:
            path = Path(consumed[artifact]["files"]["canonical"])
            screen = _load_json(path, artifact)
            if any(row.get("symbol") not in symbols for row in screen["results"]):
                raise ReplayError("EP screen handoff symbol mismatch")
            command += [flag, str(path)]
            replacements[str(path)] = _kanchi_artifact_link(consumed, artifact, "canonical", stage)
    _run_cli(command, repo_root)
    payload = _canonicalize(
        _load_json(_latest_report(reports, "stockbee_episodic_pivot_*.json"), "native EP result"),
        spec["fixed_timestamp"],
        replacements,
    )
    _validate_ep_analyze_contract(payload)
    if payload["metadata"].get("api_stats") is not None:
        raise ReplayError("EP replay unexpectedly enabled live API enrichment")
    if {r["symbol"] for r in payload["results"]} != set(symbols):
        raise ReplayError("native EP result lost or added symbols")
    actionable = [r["symbol"] for r in payload["results"] if r["state"] == "ACTIONABLE_DAY1"]
    if actionable != [decision["symbol"]]:
        raise ReplayError("EP gate requires exactly the reviewed ACTIONABLE_DAY1 candidate")
    payload["sources"] = _ep_sources(consumed, stage)
    payload["input_sha256"] = {key: _file_sha256(inputs[key]) for key in ("events", "prices")}
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["episodic_pivot_candidates"]["files"]["canonical"]), payload)
    for key in ("pead_handoff_candidates", "delayed_ep_watchlist"):
        _write_json(
            Path(artifacts[key]["files"]["canonical"]),
            {"candidates": payload[key], "order_authorized": False},
        )
    return artifacts


def _ep_validate(repo_root, spec, step, inputs, consumed, work, stage):
    decision = _ep_parameters(inputs, spec)
    analysis = _ep_read(consumed, "episodic_pivot_candidates")
    _validate_ep_analyze_contract(analysis)
    selected = [
        r
        for r in analysis["results"]
        if r["symbol"] == decision["symbol"] and r["state"] == "ACTIONABLE_DAY1"
    ]
    if len(selected) != 1:
        raise ReplayError("EP chart review requires the actionable native classification")
    setup = _ep_input(inputs, "chart", spec)
    row = selected[0]
    if (
        setup.get("verdict") != "CONFIRMED"
        or setup.get("symbol") != row["symbol"]
        or setup.get("entry_price") != row["trade_plan_inputs"]["entry_reference"]
        or setup.get("stop_price") != row["trade_plan_inputs"]["stop_reference"]
    ):
        raise ReplayError("EP chart confirmation does not match the native entry/EP-day low")
    for key in ("entry_price", "stop_price", "target_price"):
        _require_finite_number(setup.get(key), f"EP chart {key}", minimum=0)
    if not 0 < setup["stop_price"] < setup["entry_price"] < setup["target_price"]:
        raise ReplayError("EP chart requires a sizeable long setup")
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(
        Path(artifacts["validated_ep_setups"]["files"]["canonical"]),
        {
            "as_of": spec["fixed_timestamp"][:10],
            "setups": [setup],
            "sources": _ep_sources(consumed, stage),
            "watchlist": [
                {"symbol": r["symbol"], "state": r["state"], "pead_handoff": r["pead_handoff"]}
                for r in analysis["results"]
                if r["state"] != "ACTIONABLE_DAY1"
            ],
        },
    )
    return artifacts


def _ep_size(repo_root, spec, step, inputs, consumed, work, stage):
    decision = _ep_parameters(inputs, spec)
    validated = _ep_read(consumed, "validated_ep_setups")
    if len(validated["setups"]) != 1 or validated["setups"][0]["symbol"] != decision["symbol"]:
        raise ReplayError("EP sizing requires one reviewed setup")
    setup = validated["setups"][0]
    for key in ("entry_price", "stop_price", "target_price"):
        _require_finite_number(setup.get(key), f"EP sizing {key}", minimum=0)
    if not 0 < setup["stop_price"] < setup["entry_price"] < setup["target_price"]:
        raise ReplayError("EP sizing requires a valid long setup")
    parameters = work / "parameters.json"
    _write_json(parameters, decision)
    result = _swing_position_size(
        repo_root,
        spec,
        dict(step, output_files={"position_sizing": step["output_files"]["ep_position_sizing"]}),
        {"sizing_parameters": parameters},
        {"validated_setups": consumed["validated_ep_setups"]},
        work,
        stage,
    )
    return {"ep_position_sizing": result["position_sizing"]}


def _ep_match_size(consumed, decision):
    setup = _ep_read(consumed, "validated_ep_setups")["setups"][0]
    size = _ep_read(consumed, "ep_position_sizing")
    if (
        setup["symbol"] != decision["symbol"]
        or size["parameters"]["entry_price"] != setup["entry_price"]
        or size["parameters"]["stop_price"] != setup["stop_price"]
    ):
        raise ReplayError("EP sizing/setup mismatch")
    shares = _require_finite_number(
        size["final_recommended_shares"], "EP shares", integer=True, minimum=1
    )
    risk = _require_finite_number(size["final_risk_dollars"], "EP risk", minimum=0)
    value = _require_finite_number(size["final_position_value"], "EP position value", minimum=0)
    if not math.isclose(value, shares * setup["entry_price"], abs_tol=0.01):
        raise ReplayError("EP position value disagrees with shares and entry")
    if (
        not math.isclose(risk, shares * (setup["entry_price"] - setup["stop_price"]), abs_tol=0.01)
        or risk > decision["account_size"] * decision["risk_pct"] / 100 + 0.01
    ):
        raise ReplayError("EP sizing exceeds the reviewed risk budget")
    return setup, size


def _ep_plan(repo_root, spec, step, inputs, consumed, work, stage):
    _ep_match_size(consumed, _ep_parameters(inputs, spec))
    result = _swing_build_plan(
        repo_root,
        spec,
        dict(step, output_files={"trade_plans": step["output_files"]["ep_trade_plan"]}),
        inputs,
        {
            "validated_setups": consumed["validated_ep_setups"],
            "position_sizing": consumed["ep_position_sizing"],
        },
        work,
        stage,
    )
    return {"ep_trade_plan": result["trade_plans"]}


def _ep_journal(repo_root, spec, step, inputs, consumed, work, stage):
    decision = _ep_parameters(inputs, spec)
    setup, size = _ep_match_size(consumed, decision)
    sources = _ep_sources(consumed, stage)
    store = _repo_module(repo_root, "thesis_store", repo_root / "skills/trader-memory-core/scripts")
    state = work / "journal"
    tid = store.register(
        state,
        {
            "ticker": setup["symbol"],
            "thesis_type": "growth_momentum",
            "thesis_statement": decision["thesis_statement"],
            "kill_criteria": [decision["kill_criterion"]],
            "_source_date": spec["fixed_timestamp"][:10],
            "entry": {"target_price": setup["entry_price"]},
            "exit": {"stop_loss": setup["stop_price"]},
            "origin": {
                "skill": "stockbee-episodic-pivot-analyzer",
                "output_file": sources["validated_ep_setups"]["file"],
            },
        },
    )
    path = Path(consumed["ep_position_sizing"]["files"]["canonical"])
    store.attach_position(
        state,
        tid,
        str(path),
        expected_entry=setup["entry_price"],
        expected_stop=setup["stop_price"],
    )
    producer_skills = {
        "validated_ep_setups": "technical-analyst",
        "ep_position_sizing": "position-sizer",
        "ep_trade_plan": "breakout-trade-planner",
    }
    for artifact, source in sources.items():
        store.link_report(
            state, tid, producer_skills[artifact], source["file"], spec["fixed_timestamp"][:10]
        )
    thesis = store.get(state, tid)
    if thesis["status"] != "IDEA" or thesis["entry"]["actual_price"] is not None:
        raise ReplayError("EP must retain IDEA without a fill")
    payload = {
        k: thesis[k]
        for k in (
            "ticker",
            "status",
            "created_at",
            "thesis_statement",
            "kill_criteria",
            "entry",
            "exit",
            "position",
            "linked_reports",
        )
    }
    payload["sources"] = sources
    payload["watchlist"] = _ep_read(consumed, "validated_ep_setups")["watchlist"]
    payload["execution_authorized"] = False
    payload = _canonicalize(
        payload, spec["fixed_timestamp"], {str(path): sources["ep_position_sizing"]["file"]}
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["ep_journal_entry"]["files"]["canonical"]), payload)
    return artifacts


def _ep_discipline(repo_root, spec, step, inputs, consumed, work, stage):
    decision = _ep_parameters(inputs, spec)
    journal = _ep_read(consumed, "ep_journal_entry")
    size = _ep_read(consumed, "ep_position_sizing")
    circuit = _ep_read(consumed, "circuit_breaker_decision")
    if circuit.get("recommendation") != "TRADING_ALLOWED":
        raise ReplayError("EP discipline received a stopped circuit breaker")
    if (
        journal["ticker"] != decision["symbol"]
        or journal["status"] != "IDEA"
        or journal["position"]["shares"] != size["final_recommended_shares"]
        or journal["position"]["risk_dollars"] != size["final_risk_dollars"]
        or journal["entry"]["target_price"] != size["parameters"]["entry_price"]
        or journal["exit"]["stop_loss"] != size["parameters"]["stop_price"]
    ):
        raise ReplayError("EP journal/sizing discipline mismatch")
    answers = _ep_input(inputs, "checklist", spec)
    fields = ("entry_in_written_plan", "stop_predefined", "size_within_plan")
    if answers.get("symbol") != journal["ticker"] or any(
        type(answers.get(k)) is not bool for k in fields
    ):
        raise ReplayError(
            "EP checklist must contain explicit reviewed booleans for the same symbol"
        )
    candidate = {
        "symbol": journal["ticker"],
        "order_intent": "MANUAL_ORDER",
        **{k: answers[k] for k in fields},
        "planned_risk_dollars": size["final_risk_dollars"],
        "actual_risk_dollars": size["final_risk_dollars"],
    }
    if "ep_trade_plan" not in consumed:
        candidate.update({k: False for k in fields})
    else:
        plans = _ep_read(consumed, "ep_trade_plan").get("plans")
        expected = {
            "symbol": journal["ticker"],
            "entry_price": size["parameters"]["entry_price"],
            "stop_price": size["parameters"]["stop_price"],
            "shares": size["final_recommended_shares"],
            "position_value": size["final_position_value"],
            "planned_risk_dollars": size["final_risk_dollars"],
        }
        if (
            not isinstance(plans, list)
            or len(plans) != 1
            or any(plans[0].get(k) != v for k, v in expected.items())
        ):
            raise ReplayError("EP written plan does not match journal and sizing")
    answer_path, regime_path = work / "answers.json", work / "regime.json"
    watch_answers = [
        {"symbol": row["symbol"], "order_intent": "WATCHLIST"} for row in journal["watchlist"]
    ]
    _write_json(answer_path, {"candidates": [candidate, *watch_answers]})
    _write_json(regime_path, _ep_input(inputs, "exposure", spec))
    circuit_path = Path(consumed["circuit_breaker_decision"]["files"]["canonical"])
    state_dir = work / "account_state"
    state_dir.mkdir()
    for index, thesis in enumerate(_ep_input(inputs, "account_state", spec)):
        _write_yaml(state_dir / f"th_fixture_{index}.yaml", thesis)
    reports, journal_dir = work / "reports", work / "discipline_journal"
    _run_cli(
        [
            sys.executable,
            str(
                repo_root / "skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py"
            ),
            "--state-dir",
            str(state_dir),
            "--answers-file",
            str(answer_path),
            "--as-of",
            spec["fixed_timestamp"],
            "--market-regime-decision",
            str(regime_path),
            "--circuit-breaker-decision",
            str(circuit_path),
            "--output-dir",
            str(reports),
            "--journal-dir",
            str(journal_dir),
        ],
        repo_root,
    )
    payload = _load_json(
        _latest_report(reports, "pre_trade_discipline_decision_*.json"), "native EP discipline"
    )
    payload = _canonicalize(
        payload,
        spec["fixed_timestamp"],
        {
            str(regime_path): "$INPUT/exposure",
            str(state_dir): "$WORK/account_state",
            str(circuit_path): _kanchi_artifact_link(
                consumed, "circuit_breaker_decision", "canonical", stage
            ),
            str(reports): "$WORK/reports",
            str(journal_dir): "$WORK/discipline_journal",
        },
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    payload["artifact_paths"] = {
        "json": _safe_relative(
            stage,
            step["output_files"]["pre_trade_discipline_decision"]["canonical"],
            "EP discipline output",
        )
        .relative_to(stage.resolve())
        .as_posix()
    }
    payload["replay_sources"] = _ep_sources(consumed, stage)
    payload["checklist_sha256"] = _file_sha256(inputs["checklist"])
    payload["execution_authorized"] = False
    _write_json(Path(artifacts["pre_trade_discipline_decision"]["files"]["canonical"]), payload)
    return artifacts
