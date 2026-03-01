"""Unit tests for design_strategy_drafts.py."""

import design_strategy_drafts as dsd


def _make_concept(hypothesis_type: str, entry_family: str | None, export: bool) -> dict:
    """Create a minimal concept for exit calibration tests."""
    return {
        "id": f"edge_concept_{hypothesis_type}_test",
        "title": f"Test {hypothesis_type}",
        "hypothesis_type": hypothesis_type,
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "support": {"representative_conditions": ["close > high20_prev", "rel_volume >= 1.5"]},
        "abstraction": {"thesis": "Test thesis", "invalidation_signals": ["Signal 1"]},
        "strategy_design": {
            "recommended_entry_family": entry_family,
            "export_ready_v1": export,
        },
    }


# --- Exit calibration tests ---


def test_exit_calibration_breakout_balanced() -> None:
    """Breakout + balanced: stop=0.07*0.85=0.0595, RR=3.0+0.0=3.0, time=20."""
    concept = _make_concept("breakout", "pivot_breakout", export=True)
    draft = dsd.build_draft(
        concept=concept, variant="core", risk_profile="balanced", as_of="2026-02-28"
    )
    assert abs(draft["exit"]["stop_loss_pct"] - 0.0595) < 0.001
    assert draft["exit"]["take_profit_rr"] == 3.0
    assert draft["exit"]["time_stop_days"] == 20
    assert "trailing_stop_hint" in draft["exit"]


def test_exit_calibration_earnings_drift_balanced() -> None:
    """Earnings drift + balanced: stop=0.07*1.15=0.0805, RR=3.0-0.5=2.5, time=10."""
    concept = _make_concept("earnings_drift", "gap_up_continuation", export=True)
    draft = dsd.build_draft(
        concept=concept, variant="core", risk_profile="balanced", as_of="2026-02-28"
    )
    assert abs(draft["exit"]["stop_loss_pct"] - 0.0805) < 0.001
    assert draft["exit"]["take_profit_rr"] == 2.5
    assert draft["exit"]["time_stop_days"] == 10
    assert "trailing_stop_hint" not in draft["exit"]


def test_exit_calibration_panic_reversal_balanced() -> None:
    """Panic reversal + balanced: stop=0.07*0.70=0.049, RR=3.0-0.7=2.3, time=5."""
    concept = _make_concept("panic_reversal", None, export=False)
    draft = dsd.build_draft(
        concept=concept, variant="research_probe", risk_profile="balanced", as_of="2026-02-28"
    )
    assert abs(draft["exit"]["stop_loss_pct"] - 0.049) < 0.001
    assert draft["exit"]["take_profit_rr"] == 2.3
    assert draft["exit"]["time_stop_days"] == 5


def test_exit_rr_floor_clamp_conservative_panic() -> None:
    """Conservative(RR=2.2) + panic_reversal(adj=-0.7): 2.2-0.7=1.5 >= 1.5, OK."""
    concept = _make_concept("panic_reversal", None, export=False)
    draft = dsd.build_draft(
        concept=concept, variant="research_probe", risk_profile="conservative", as_of="2026-02-28"
    )
    assert draft["exit"]["take_profit_rr"] >= dsd.RR_FLOOR  # 1.5


def test_exit_calibration_aggressive_breakout() -> None:
    """Aggressive + breakout: stop=0.09*0.85=0.0765, RR=3.5+0.0=3.5."""
    concept = _make_concept("breakout", "pivot_breakout", export=True)
    draft = dsd.build_draft(
        concept=concept, variant="core", risk_profile="aggressive", as_of="2026-02-28"
    )
    assert abs(draft["exit"]["stop_loss_pct"] - 0.0765) < 0.001
    assert draft["exit"]["take_profit_rr"] == 3.5


def test_exit_calibration_unknown_hypothesis_fallback() -> None:
    """Unknown hypothesis_type uses fallback (multiplier=1.0, adj=0.0, time=10)."""
    concept = _make_concept("unknown_type", None, export=False)
    draft = dsd.build_draft(
        concept=concept, variant="research_probe", risk_profile="balanced", as_of="2026-02-28"
    )
    assert draft["exit"]["stop_loss_pct"] == 0.07  # 0.07 * 1.0
    assert draft["exit"]["take_profit_rr"] == 3.0  # 3.0 + 0.0
    assert draft["exit"]["time_stop_days"] == 10


def test_export_ticket_preserves_calibrated_exit() -> None:
    """Export ticket should carry the calibrated exit parameters."""
    concept = _make_concept("breakout", "pivot_breakout", export=True)
    draft = dsd.build_draft(
        concept=concept, variant="core", risk_profile="balanced", as_of="2026-02-28"
    )
    ticket = dsd.build_export_ticket(draft)
    assert abs(ticket["exit"]["stop_loss_pct"] - 0.0595) < 0.001
    assert ticket["exit"]["take_profit_rr"] == 3.0


def test_c5_bounds_all_combinations() -> None:
    """All hypothesis x profile combinations should have RR >= 1.5 and stop <= 0.15."""
    for hyp_type in list(dsd.HYPOTHESIS_EXIT_OVERRIDES.keys()) + ["unknown_xyz"]:
        for profile_name, profile in dsd.RISK_PROFILES.items():
            result = dsd.apply_hypothesis_exit_overrides(
                base_stop=profile["stop_loss_pct"],
                base_rr=profile["take_profit_rr"],
                hypothesis_type=hyp_type,
            )
            assert result["take_profit_rr"] >= dsd.RR_FLOOR, f"{hyp_type}/{profile_name} RR too low"
            assert result["stop_loss_pct"] <= 0.15, f"{hyp_type}/{profile_name} stop too high"


def test_trailing_stop_hint_present_for_breakout() -> None:
    """Breakout should include trailing_stop_hint, panic_reversal should not."""
    result_breakout = dsd.apply_hypothesis_exit_overrides(0.07, 3.0, "breakout")
    assert "trailing_stop_hint" in result_breakout
    result_panic = dsd.apply_hypothesis_exit_overrides(0.07, 3.0, "panic_reversal")
    assert "trailing_stop_hint" not in result_panic


def test_existing_tests_still_pass() -> None:
    """Re-run existing test scenarios to confirm no regression."""
    concept = {
        "id": "edge_concept_breakout_behavior_riskon",
        "title": "Participation-backed trend breakout",
        "hypothesis_type": "breakout",
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "support": {"representative_conditions": ["close > high20_prev", "rel_volume >= 1.5"]},
        "abstraction": {
            "thesis": "Breakout thesis",
            "invalidation_signals": ["Breakout fails quickly"],
        },
        "strategy_design": {"recommended_entry_family": "pivot_breakout", "export_ready_v1": True},
    }
    draft = dsd.build_draft(
        concept=concept, variant="core", risk_profile="balanced", as_of="2026-02-20"
    )
    assert draft["export_ready_v1"] is True
    assert draft["entry_family"] == "pivot_breakout"


# --- Original tests ---


def test_build_draft_export_ready_breakout() -> None:
    concept = {
        "id": "edge_concept_breakout_behavior_riskon",
        "title": "Participation-backed trend breakout",
        "hypothesis_type": "breakout",
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "support": {
            "representative_conditions": ["close > high20_prev", "rel_volume >= 1.5"],
        },
        "abstraction": {
            "thesis": "Breakout thesis",
            "invalidation_signals": ["Breakout fails quickly"],
        },
        "strategy_design": {
            "recommended_entry_family": "pivot_breakout",
            "export_ready_v1": True,
        },
    }

    draft = dsd.build_draft(
        concept=concept,
        variant="core",
        risk_profile="balanced",
        as_of="2026-02-20",
    )

    assert draft["export_ready_v1"] is True
    assert draft["entry_family"] == "pivot_breakout"
    assert draft["risk_profile"] == "balanced"
    assert draft["risk"]["risk_per_trade"] == 0.01

    ticket = dsd.build_export_ticket(draft)
    assert ticket["entry_family"] == "pivot_breakout"
    assert ticket["id"].startswith("edge_")


def test_build_draft_research_probe_for_non_exportable_concept() -> None:
    concept = {
        "id": "edge_concept_news_reaction_behavior_riskon",
        "title": "Event overreaction and drift",
        "hypothesis_type": "news_reaction",
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "support": {"representative_conditions": ["reaction_1d=-0.132"]},
        "abstraction": {},
        "strategy_design": {
            "recommended_entry_family": None,
            "export_ready_v1": False,
        },
    }

    draft = dsd.build_draft(
        concept=concept,
        variant="research_probe",
        risk_profile="conservative",
        as_of="2026-02-20",
    )

    assert draft["entry_family"] == "research_only"
    assert draft["export_ready_v1"] is False
    assert draft["risk_profile"] == "conservative"
