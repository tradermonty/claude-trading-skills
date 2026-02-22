"""Unit tests for design_strategy_drafts.py."""

import design_strategy_drafts as dsd


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
