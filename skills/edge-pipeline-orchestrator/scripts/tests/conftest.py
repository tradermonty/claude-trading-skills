"""Shared fixtures for edge-pipeline-orchestrator tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture()
def sample_draft_pass() -> dict[str, Any]:
    """A draft that should PASS review and be export-eligible."""
    return {
        "id": "draft_edge_concept_breakout_behavior_riskon_core",
        "concept_id": "edge_concept_breakout_behavior_riskon",
        "variant": "core",
        "risk_profile": "balanced",
        "name": "Participation-backed trend breakout (core)",
        "hypothesis_type": "breakout",
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "export_ready_v1": True,
        "entry_family": "pivot_breakout",
        "entry": {
            "conditions": [
                "close > high20_prev",
                "rel_volume >= 1.5",
                "close > ma50 > ma200",
            ],
            "trend_filter": ["price > sma_200", "price > sma_50"],
            "note": "Use baseline confirmation and trend filter.",
        },
        "exit": {"stop_loss_pct": 0.07, "take_profit_rr": 3.0, "time_stop_days": 20},
        "risk": {
            "position_sizing": "fixed_risk",
            "risk_per_trade": 0.01,
            "max_positions": 5,
            "max_sector_exposure": 0.3,
        },
    }


@pytest.fixture()
def sample_draft_revise() -> dict[str, Any]:
    """A draft that receives REVISE verdict."""
    return {
        "id": "draft_edge_concept_breakout_behavior_riskon_conservative",
        "concept_id": "edge_concept_breakout_behavior_riskon",
        "variant": "conservative",
        "risk_profile": "balanced",
        "name": "Participation-backed trend breakout (conservative)",
        "hypothesis_type": "breakout",
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "export_ready_v1": True,
        "entry_family": "pivot_breakout",
        "entry": {
            "conditions": [
                "close > high20_prev",
                "rel_volume >= 1.5",
                "close > ma50 > ma200",
                "rsi_14 > 50",
                "macd_histogram > 0",
                "adx > 25",
                "obv_rising",
            ],
            "trend_filter": ["price > sma_200", "price > sma_50"],
            "note": "Require stricter confirmation before entry.",
        },
        "exit": {"stop_loss_pct": 0.07, "take_profit_rr": 3.0, "time_stop_days": 20},
        "risk": {
            "position_sizing": "fixed_risk",
            "risk_per_trade": 0.0075,
            "max_positions": 4,
            "max_sector_exposure": 0.3,
        },
    }


@pytest.fixture()
def sample_draft_reject() -> dict[str, Any]:
    """A draft that receives REJECT verdict."""
    return {
        "id": "draft_edge_concept_panic_reversal_risk_premium_riskoff_research_probe",
        "concept_id": "edge_concept_panic_reversal_risk_premium_riskoff",
        "variant": "research_probe",
        "risk_profile": "balanced",
        "name": "Shock overshoot mean reversion (research_probe)",
        "hypothesis_type": "panic_reversal",
        "mechanism_tag": "risk_premium",
        "regime": "RiskOff",
        "export_ready_v1": False,
        "entry_family": "research_only",
        "entry": {"conditions": [], "trend_filter": []},
        "exit": {"stop_loss_pct": 0.07, "take_profit_rr": 3.0},
        "risk": {
            "position_sizing": "fixed_risk",
            "risk_per_trade": 0.005,
            "max_positions": 3,
            "max_sector_exposure": 0.3,
        },
    }


@pytest.fixture()
def sample_draft_gap_up() -> dict[str, Any]:
    """A draft with gap_up_continuation family."""
    return {
        "id": "draft_edge_concept_earnings_drift_behavior_neutral_core",
        "concept_id": "edge_concept_earnings_drift_behavior_neutral",
        "variant": "core",
        "risk_profile": "balanced",
        "name": "Event-driven continuation drift (core)",
        "hypothesis_type": "earnings_drift",
        "mechanism_tag": "behavior",
        "regime": "Neutral",
        "export_ready_v1": True,
        "entry_family": "gap_up_continuation",
        "entry": {
            "conditions": [
                "gap_up_detected",
                "close_above_gap_day_high",
                "volume > 2.0 * avg_volume_50",
            ],
            "trend_filter": ["price > sma_200", "price > sma_50"],
        },
        "exit": {"stop_loss_pct": 0.07, "take_profit_rr": 3.0},
        "risk": {
            "position_sizing": "fixed_risk",
            "risk_per_trade": 0.01,
            "max_positions": 5,
            "max_sector_exposure": 0.3,
        },
    }


@pytest.fixture()
def sample_review_pass() -> dict[str, Any]:
    """Review result with PASS verdict."""
    return {
        "draft_id": "draft_edge_concept_breakout_behavior_riskon_core",
        "verdict": "PASS",
        "confidence_score": 82,
        "revision_instructions": [],
    }


@pytest.fixture()
def sample_review_revise() -> dict[str, Any]:
    """Review result with REVISE verdict."""
    return {
        "draft_id": "draft_edge_concept_breakout_behavior_riskon_conservative",
        "verdict": "REVISE",
        "confidence_score": 55,
        "revision_instructions": ["Reduce entry conditions", "Add volume filter"],
    }


@pytest.fixture()
def sample_review_reject() -> dict[str, Any]:
    """Review result with REJECT verdict."""
    return {
        "draft_id": "draft_edge_concept_panic_reversal_risk_premium_riskoff_research_probe",
        "verdict": "REJECT",
        "confidence_score": 20,
        "revision_instructions": [],
    }


@pytest.fixture()
def drafts_dir(
    tmp_path: Path, sample_draft_pass: dict, sample_draft_revise: dict, sample_draft_reject: dict
) -> Path:
    """Create a temporary drafts directory with sample draft YAML files."""
    d = tmp_path / "drafts"
    d.mkdir()
    for draft in [sample_draft_pass, sample_draft_revise, sample_draft_reject]:
        (d / f"{draft['id']}.yaml").write_text(yaml.safe_dump(draft, sort_keys=False))
    return d


@pytest.fixture()
def reviews_dir(
    tmp_path: Path, sample_review_pass: dict, sample_review_revise: dict, sample_review_reject: dict
) -> Path:
    """Create a temporary reviews directory with sample review YAML files."""
    d = tmp_path / "reviews"
    d.mkdir()
    for review in [sample_review_pass, sample_review_revise, sample_review_reject]:
        (d / f"{review['draft_id']}_review.yaml").write_text(
            yaml.safe_dump(review, sort_keys=False)
        )
    return d


@pytest.fixture()
def tickets_dir(tmp_path: Path) -> Path:
    """Create a temporary tickets directory with sample ticket YAML files."""
    d = tmp_path / "tickets"
    d.mkdir()
    ticket = {
        "id": "edge_breakout_AAPL_20260101",
        "hypothesis_type": "breakout",
        "entry_family": "pivot_breakout",
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "priority_score": 75,
        "observation": {"symbol": "AAPL", "date": "2026-01-01"},
    }
    (d / "edge_breakout_AAPL_20260101.yaml").write_text(yaml.safe_dump(ticket, sort_keys=False))
    return d


@pytest.fixture()
def hints_file(tmp_path: Path) -> Path:
    """Create a sample hints YAML file."""
    path = tmp_path / "hints.yaml"
    payload = {
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "hints": [
            {
                "title": "Breadth-supported breakout regime",
                "observation": "Risk-on regime with pct_above_ma50=0.650",
                "regime_bias": "RiskOn",
                "mechanism_tag": "behavior",
            }
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


@pytest.fixture()
def concepts_file(tmp_path: Path) -> Path:
    """Create a sample concepts YAML file."""
    path = tmp_path / "edge_concepts.yaml"
    payload = {
        "concept_count": 1,
        "concepts": [
            {
                "id": "edge_concept_breakout_behavior_riskon",
                "hypothesis_type": "breakout",
                "mechanism_tag": "behavior",
                "regime": "RiskOn",
                "strategy_design": {
                    "recommended_entry_family": "pivot_breakout",
                    "export_ready_v1": True,
                },
            }
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


@pytest.fixture()
def market_summary_file(tmp_path: Path) -> Path:
    """Create a sample market summary JSON file."""
    path = tmp_path / "market_summary.json"
    payload = {
        "regime_label": "RiskOn",
        "pct_above_ma50": 0.65,
        "vol_trend": 0.85,
        "risk_on_score": 70,
        "risk_off_score": 30,
    }
    path.write_text(json.dumps(payload))
    return path


@pytest.fixture()
def anomalies_file(tmp_path: Path) -> Path:
    """Create a sample anomalies JSON file."""
    path = tmp_path / "anomalies.json"
    payload = [
        {"symbol": "AAPL", "metric": "gap", "z": 3.2},
        {"symbol": "MSFT", "metric": "rel_volume", "z": 2.8},
    ]
    path.write_text(json.dumps(payload))
    return path


@pytest.fixture()
def exportable_tickets_dir(tmp_path: Path, sample_draft_pass: dict) -> Path:
    """Create a directory with pre-generated exportable ticket YAML files."""
    d = tmp_path / "exportable_tickets"
    d.mkdir()
    ticket_id = sample_draft_pass["id"].replace("draft_", "edge_")
    ticket = {
        "id": ticket_id,
        "name": sample_draft_pass["name"],
        "description": f"Draft-derived ticket from concept {sample_draft_pass['concept_id']} ({sample_draft_pass['variant']}).",
        "hypothesis_type": sample_draft_pass["hypothesis_type"],
        "entry_family": sample_draft_pass["entry_family"],
        "mechanism_tag": sample_draft_pass.get("mechanism_tag", "uncertain"),
        "regime": sample_draft_pass.get("regime", "Neutral"),
        "holding_horizon": "20D",
        "entry": sample_draft_pass["entry"],
        "risk": sample_draft_pass["risk"],
        "exit": {
            "stop_loss_pct": sample_draft_pass["exit"]["stop_loss_pct"],
            "take_profit_rr": sample_draft_pass["exit"]["take_profit_rr"],
        },
        "cost_model": {"commission_per_share": 0.0, "slippage_bps": 5},
    }
    (d / f"{ticket_id}.yaml").write_text(yaml.safe_dump(ticket, sort_keys=False))
    return d
