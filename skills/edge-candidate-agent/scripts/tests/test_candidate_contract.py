"""Unit tests for edge candidate interface checks."""

from copy import deepcopy

from candidate_contract import validate_interface_contract, validate_ticket_payload


def build_valid_spec() -> dict:
    return {
        "id": "edge_vcp_breakout_v1",
        "name": "Edge VCP Breakout v1",
        "description": "Test strategy",
        "universe": {
            "type": "us_equities",
            "index": "sp500",
            "filters": ["avg_volume > 500_000", "price > 10"],
        },
        "signals": {
            "entry": {
                "type": "pivot_breakout",
                "conditions": ["vcp_pattern_detected"],
                "trend_filter": ["price > sma_200"],
            },
            "exit": {
                "stop_loss": "7% below entry",
                "trailing_stop": "below 21-day EMA",
                "take_profit": "risk_reward_3x",
            },
        },
        "risk": {
            "risk_per_trade": 0.01,
            "max_positions": 5,
            "max_sector_exposure": 0.30,
        },
        "cost_model": {
            "commission_per_share": 0.0,
            "slippage_bps": 5,
        },
        "validation": {"method": "full_sample"},
        "promotion_gates": {
            "min_trades": 200,
            "max_drawdown": 0.15,
            "sharpe": 1.0,
            "profit_factor": 1.2,
        },
        "vcp_detection": {
            "min_contractions": 2,
            "contraction_ratio": 0.75,
        },
    }


def test_valid_phase1_spec_passes() -> None:
    spec = build_valid_spec()
    errors = validate_interface_contract(spec, candidate_id=spec["id"], stage="phase1")
    assert errors == []


def test_phase1_rejects_walk_forward() -> None:
    spec = build_valid_spec()
    spec["validation"] = {"method": "walk_forward", "oos_ratio": 0.3}
    errors = validate_interface_contract(spec, candidate_id=spec["id"], stage="phase1")
    assert any("validation.method" in error for error in errors)
    assert any("validation.oos_ratio" in error for error in errors)


def test_entry_family_requires_matching_detection_block() -> None:
    spec = build_valid_spec()
    spec["signals"]["entry"]["type"] = "gap_up_continuation"
    errors = validate_interface_contract(spec, candidate_id=spec["id"], stage="phase1")
    assert any("gap_up_continuation requires gap_up_detection" in error for error in errors)


def test_candidate_id_mismatch_is_rejected() -> None:
    spec = build_valid_spec()
    errors = validate_interface_contract(spec, candidate_id="different_id", stage="phase1")
    assert any("candidate directory name must match strategy id" in error for error in errors)


def test_risk_bounds_violation_is_rejected() -> None:
    spec = deepcopy(build_valid_spec())
    spec["risk"]["risk_per_trade"] = 0.15
    errors = validate_interface_contract(spec, candidate_id=spec["id"], stage="phase1")
    assert any("risk.risk_per_trade" in error for error in errors)


def test_validate_ticket_payload_accepts_valid_minimum() -> None:
    ticket = {
        "id": "edge_vcp_breakout_v1",
        "hypothesis_type": "breakout",
        "entry_family": "pivot_breakout",
    }
    assert validate_ticket_payload(ticket) == []


def test_validate_ticket_payload_rejects_missing_required_fields() -> None:
    ticket = {"id": "", "hypothesis_type": "breakout"}
    errors = validate_ticket_payload(ticket)
    assert any("ticket.id" in error for error in errors)
    assert any("ticket.entry_family" in error for error in errors)


def test_validate_ticket_payload_rejects_unsupported_entry_family() -> None:
    ticket = {
        "id": "edge_momentum_v1",
        "hypothesis_type": "momentum",
        "entry_family": "momentum_followthrough",
    }
    errors = validate_ticket_payload(ticket)
    assert any("ticket.entry_family must be one of" in error for error in errors)


def test_validate_ticket_payload_rejects_non_phase1_validation_method() -> None:
    ticket = {
        "id": "edge_vcp_breakout_v1",
        "hypothesis_type": "breakout",
        "entry_family": "pivot_breakout",
        "validation": {"method": "walk_forward"},
    }
    errors = validate_ticket_payload(ticket)
    assert any("ticket.validation.method" in error for error in errors)


def test_validate_ticket_payload_rejects_non_null_oos_ratio() -> None:
    ticket = {
        "id": "edge_vcp_breakout_v1",
        "hypothesis_type": "breakout",
        "entry_family": "pivot_breakout",
        "validation": {"method": "full_sample", "oos_ratio": 0.3},
    }
    errors = validate_ticket_payload(ticket)
    assert any("ticket.validation.oos_ratio" in error for error in errors)
