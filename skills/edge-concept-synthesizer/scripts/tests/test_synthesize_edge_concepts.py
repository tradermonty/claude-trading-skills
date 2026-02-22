"""Unit tests for synthesize_edge_concepts.py."""

import synthesize_edge_concepts as sec


def test_build_concept_for_breakout_is_export_ready() -> None:
    tickets = [
        {
            "id": "edge_auto_vcp_xp_20260220",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 74.2,
            "entry_family": "pivot_breakout",
            "observation": {"symbol": "XP"},
            "signal_definition": {"conditions": ["close > high20_prev", "rel_volume >= 1.5"]},
        },
        {
            "id": "edge_auto_vcp_nok_20260220",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 73.0,
            "entry_family": "pivot_breakout",
            "observation": {"symbol": "NOK"},
            "signal_definition": {"conditions": ["close > high20_prev"]},
        },
    ]

    concept = sec.build_concept(
        key=("breakout", "behavior", "RiskOn"),
        tickets=tickets,
        hints=[
            {
                "title": "Breadth-supported breakout regime",
                "preferred_entry_family": "pivot_breakout",
                "regime_bias": "RiskOn",
            }
        ],
    )

    assert concept["strategy_design"]["export_ready_v1"] is True
    assert concept["strategy_design"]["recommended_entry_family"] == "pivot_breakout"
    assert concept["support"]["ticket_count"] == 2


def test_build_concept_for_news_reaction_is_research_only() -> None:
    concept = sec.build_concept(
        key=("news_reaction", "behavior", "RiskOn"),
        tickets=[
            {
                "id": "edge_auto_news_reaction_tsla_20260220",
                "hypothesis_type": "news_reaction",
                "mechanism_tag": "behavior",
                "regime": "RiskOn",
                "priority_score": 90.0,
                "entry_family": "research_only",
                "observation": {"symbol": "TSLA"},
                "signal_definition": {"conditions": ["reaction_1d=-0.132"]},
            }
        ],
        hints=[],
    )

    assert concept["strategy_design"]["export_ready_v1"] is False
    assert concept["strategy_design"]["recommended_entry_family"] is None
