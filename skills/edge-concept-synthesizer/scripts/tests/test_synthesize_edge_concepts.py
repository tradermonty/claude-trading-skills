"""Unit tests for synthesize_edge_concepts.py."""

from pathlib import Path

import synthesize_edge_concepts as sec
import yaml


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


def test_infer_hypothesis_type_from_explicit_field() -> None:
    """Test explicit hypothesis_type within whitelist is accepted."""
    hint = {"hypothesis_type": "breakout", "title": "whatever"}
    assert sec.infer_hypothesis_type(hint) == "breakout"


def test_infer_hypothesis_type_case_insensitive() -> None:
    """Test that explicit field is case-insensitive."""
    assert sec.infer_hypothesis_type({"hypothesis_type": "Breakout"}) == "breakout"
    assert sec.infer_hypothesis_type({"hypothesis_type": "  PANIC_REVERSAL  "}) == "panic_reversal"


def test_infer_hypothesis_type_rejects_unknown_explicit() -> None:
    """Test unknown explicit value falls back to keyword inference."""
    # "momentum" is not in whitelist, but title has "breakout" keyword
    hint = {"hypothesis_type": "momentum", "title": "breakout pattern detected"}
    assert sec.infer_hypothesis_type(hint) == "breakout"

    # unknown explicit, no keyword match at all
    hint2 = {"hypothesis_type": "xyz_typo", "title": "no match here"}
    assert sec.infer_hypothesis_type(hint2) == sec.FALLBACK_HYPOTHESIS_TYPE


def test_infer_hypothesis_type_from_keywords() -> None:
    """Test keyword-based inference from title and observation."""
    hint = {"title": "Seasonal buyback blackout window", "observation": "Calendar effect detected"}
    assert sec.infer_hypothesis_type(hint) == "calendar_anomaly"


def test_infer_hypothesis_type_fallback() -> None:
    """Test fallback to FALLBACK_HYPOTHESIS_TYPE when no match."""
    hint = {"title": "Unclear signal", "observation": "Unknown pattern"}
    assert sec.infer_hypothesis_type(hint) == sec.FALLBACK_HYPOTHESIS_TYPE


def test_promote_hints_to_tickets_basic() -> None:
    """Test basic hint-to-ticket promotion."""
    hints = [
        {
            "title": "March buyback blackout",
            "observation": "Buyback blackout period",
            "hypothesis_type": "calendar_anomaly",
            "preferred_entry_family": "pivot_breakout",
            "symbols": ["SPY"],
            "regime_bias": "Neutral",
            "mechanism_tag": "flow",
        }
    ]
    tickets = sec.promote_hints_to_tickets(hints, synthetic_priority=30.0)
    assert len(tickets) == 1
    t = tickets[0]
    assert t["id"].startswith(sec.SYNTHETIC_TICKET_PREFIX)
    assert t["hypothesis_type"] == "calendar_anomaly"
    assert t["priority_score"] == 30.0
    assert t["_synthetic"] is True
    assert t["entry_family"] == "pivot_breakout"
    assert t["observation"]["symbol"] == "SPY"


def test_promote_hints_to_tickets_skips_empty_title() -> None:
    """Test that hints with empty title are skipped."""
    hints = [
        {"title": "", "observation": "No title"},
        {"title": "   ", "observation": "Whitespace only"},
        {"title": "Valid", "observation": "ok"},
    ]
    tickets = sec.promote_hints_to_tickets(hints, synthetic_priority=30.0)
    assert len(tickets) == 1
    assert "valid" in tickets[0]["id"]


def test_promote_hints_to_tickets_defaults() -> None:
    """Test default values for minimal hint."""
    hints = [{"title": "Minimal hint"}]
    tickets = sec.promote_hints_to_tickets(hints, synthetic_priority=25.0)
    assert len(tickets) == 1
    t = tickets[0]
    assert t["mechanism_tag"] == "uncertain"
    assert t["regime"] == "Unknown"
    assert t["entry_family"] == "research_only"
    assert t["priority_score"] == 25.0


def test_build_concept_with_synthetic_tickets() -> None:
    """Test that build_concept separates real and synthetic ticket counts."""
    tickets = [
        {
            "id": "edge_auto_real_1",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 74.0,
            "entry_family": "pivot_breakout",
            "observation": {"symbol": "XP"},
        },
        {
            "id": "hint_promo_seasonal_0",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 30.0,
            "entry_family": "research_only",
            "_synthetic": True,
        },
    ]
    concept = sec.build_concept(
        key=("breakout", "behavior", "RiskOn"),
        tickets=tickets,
        hints=[],
    )
    assert concept["support"]["ticket_count"] == 2
    assert concept["support"]["real_ticket_count"] == 1
    assert concept["support"]["synthetic_ticket_count"] == 1
    assert concept["evidence"]["synthetic_ticket_ids"] == ["hint_promo_seasonal_0"]


def test_build_concept_synthetic_only_not_export_ready() -> None:
    """Test that hint-only concepts are NOT export_ready even with exportable entry_family."""
    tickets = [
        {
            "id": "hint_promo_breakout_0",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 30.0,
            "entry_family": "pivot_breakout",
            "_synthetic": True,
        },
    ]
    concept = sec.build_concept(
        key=("breakout", "behavior", "RiskOn"),
        tickets=tickets,
        hints=[],
    )
    assert concept["strategy_design"]["export_ready_v1"] is False
    assert concept["strategy_design"]["recommended_entry_family"] is None
    assert concept["support"]["entry_family_distribution"] == {}


def test_build_concept_without_synthetic_omits_breakdown() -> None:
    """Test backward compatibility: no synthetic fields when all real."""
    tickets = [
        {
            "id": "edge_auto_real_1",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 74.0,
            "entry_family": "pivot_breakout",
            "observation": {"symbol": "XP"},
        },
    ]
    concept = sec.build_concept(
        key=("breakout", "behavior", "RiskOn"),
        tickets=tickets,
        hints=[],
    )
    assert "real_ticket_count" not in concept["support"]
    assert "synthetic_ticket_count" not in concept["support"]
    assert "synthetic_ticket_ids" not in concept["evidence"]


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


def _setup_main_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    """Create minimal ticket + hints fixture files for main() tests."""
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir()

    ticket = {
        "id": "edge_auto_test_1",
        "hypothesis_type": "breakout",
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "priority_score": 70.0,
        "entry_family": "pivot_breakout",
        "observation": {"symbol": "XP"},
        "date": "2026-02-20",
    }
    (tickets_dir / "ticket_1.yaml").write_text(yaml.safe_dump(ticket))

    hints_path = tmp_path / "hints.yaml"
    hints_payload = {
        "hints": [
            {
                "title": "Seasonal buyback blackout",
                "observation": "Calendar-driven supply gap",
                "hypothesis_type": "calendar_anomaly",
                "symbols": ["SPY"],
                "regime_bias": "Neutral",
                "mechanism_tag": "flow",
            }
        ]
    }
    hints_path.write_text(yaml.safe_dump(hints_payload))
    return tickets_dir, hints_path


def test_main_promote_hints_source_metadata(tmp_path: Path, monkeypatch) -> None:
    """Test that --promote-hints populates source metadata correctly."""
    tickets_dir, hints_path = _setup_main_fixtures(tmp_path)
    output_path = tmp_path / "concepts.yaml"

    # Run WITH --promote-hints
    monkeypatch.setattr(
        "sys.argv",
        [
            "synthesize_edge_concepts.py",
            "--tickets-dir",
            str(tickets_dir),
            "--hints",
            str(hints_path),
            "--output",
            str(output_path),
            "--promote-hints",
        ],
    )
    assert sec.main() == 0

    result = yaml.safe_load(output_path.read_text())
    assert result["source"]["promote_hints"] is True
    assert result["source"]["real_ticket_count"] == 1
    assert result["source"]["synthetic_ticket_count"] == 1

    # Run WITHOUT --promote-hints
    output_path2 = tmp_path / "concepts_no_promote.yaml"
    monkeypatch.setattr(
        "sys.argv",
        [
            "synthesize_edge_concepts.py",
            "--tickets-dir",
            str(tickets_dir),
            "--hints",
            str(hints_path),
            "--output",
            str(output_path2),
        ],
    )
    assert sec.main() == 0

    result2 = yaml.safe_load(output_path2.read_text())
    assert "promote_hints" not in result2["source"]
    assert "real_ticket_count" not in result2["source"]
    assert "synthetic_ticket_count" not in result2["source"]


def test_cap_synthetic_tickets_limits_count() -> None:
    """cap_synthetic_tickets should limit synthetic count to max(real_count * ratio, floor)."""
    real_tickets = [
        {
            "id": f"edge_auto_real_{i}",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 70.0 + i,
            "entry_family": "pivot_breakout",
        }
        for i in range(3)
    ]
    synthetic_tickets = [
        {
            "id": f"hint_promo_test_{i}",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 30.0,
            "entry_family": "research_only",
            "_synthetic": True,
        }
        for i in range(10)
    ]
    # ratio=1.5 → max_synthetic = max(3*1.5, 3) = 4 (ceil of 4.5)
    capped = sec.cap_synthetic_tickets(
        real_tickets=real_tickets,
        synthetic_tickets=synthetic_tickets,
        max_ratio=1.5,
        floor=3,
    )
    assert len(capped) == 5  # ceil(3 * 1.5) = 5


def test_cap_synthetic_tickets_floor_applies() -> None:
    """When real_count * ratio < floor, use floor."""
    real_tickets = [
        {
            "id": "edge_auto_real_0",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 70.0,
            "entry_family": "pivot_breakout",
        }
    ]
    synthetic_tickets = [
        {
            "id": f"hint_promo_test_{i}",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 30.0,
            "_synthetic": True,
        }
        for i in range(10)
    ]
    # ratio=1.5 → max_synthetic = max(ceil(1*1.5), 3) = max(2, 3) = 3
    capped = sec.cap_synthetic_tickets(
        real_tickets=real_tickets,
        synthetic_tickets=synthetic_tickets,
        max_ratio=1.5,
        floor=3,
    )
    assert len(capped) == 3


def test_cap_synthetic_tickets_no_truncation_needed() -> None:
    """When synthetic count is already within limit, no truncation."""
    real_tickets = [{"id": f"r{i}", "priority_score": 70.0} for i in range(5)]
    synthetic_tickets = [
        {"id": f"s{i}", "priority_score": 30.0, "_synthetic": True} for i in range(2)
    ]
    capped = sec.cap_synthetic_tickets(
        real_tickets=real_tickets,
        synthetic_tickets=synthetic_tickets,
        max_ratio=1.5,
        floor=3,
    )
    assert len(capped) == 2  # 2 < max(ceil(5*1.5), 3) = max(8, 3) = 8


def test_main_max_synthetic_ratio(tmp_path: Path, monkeypatch) -> None:
    """Test that --max-synthetic-ratio caps synthetic tickets in main()."""
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir()

    # Create 2 real tickets
    for i in range(2):
        ticket = {
            "id": f"edge_auto_test_{i}",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "regime": "RiskOn",
            "priority_score": 70.0 + i,
            "entry_family": "pivot_breakout",
            "observation": {"symbol": f"SYM{i}"},
            "date": "2026-02-20",
        }
        (tickets_dir / f"ticket_{i}.yaml").write_text(yaml.safe_dump(ticket))

    # Create hints with 8 entries
    hints_path = tmp_path / "hints.yaml"
    hints_payload = {
        "hints": [
            {
                "title": f"Hint {i}",
                "observation": f"Signal {i}",
                "hypothesis_type": "breakout",
                "symbols": [f"H{i}"],
                "regime_bias": "RiskOn",
                "mechanism_tag": "behavior",
            }
            for i in range(8)
        ]
    }
    hints_path.write_text(yaml.safe_dump(hints_payload))
    output_path = tmp_path / "concepts.yaml"

    monkeypatch.setattr(
        "sys.argv",
        [
            "synthesize_edge_concepts.py",
            "--tickets-dir",
            str(tickets_dir),
            "--hints",
            str(hints_path),
            "--output",
            str(output_path),
            "--promote-hints",
            "--max-synthetic-ratio",
            "1.5",
        ],
    )
    assert sec.main() == 0

    result = yaml.safe_load(output_path.read_text())
    # 2 real tickets, ratio=1.5, floor=3 → max_synthetic = max(ceil(2*1.5), 3) = 3
    assert result["source"]["synthetic_ticket_count"] == 3


def test_main_promote_hints_zero_promotions(tmp_path: Path, monkeypatch) -> None:
    """Test that --promote-hints with no hints still outputs promote_hints=True."""
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir()

    ticket = {
        "id": "edge_auto_test_1",
        "hypothesis_type": "breakout",
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "priority_score": 70.0,
        "entry_family": "pivot_breakout",
        "observation": {"symbol": "XP"},
        "date": "2026-02-20",
    }
    (tickets_dir / "ticket_1.yaml").write_text(yaml.safe_dump(ticket))
    output_path = tmp_path / "concepts.yaml"

    # --promote-hints ON but no hints file provided
    monkeypatch.setattr(
        "sys.argv",
        [
            "synthesize_edge_concepts.py",
            "--tickets-dir",
            str(tickets_dir),
            "--output",
            str(output_path),
            "--promote-hints",
        ],
    )
    assert sec.main() == 0

    result = yaml.safe_load(output_path.read_text())
    assert result["source"]["promote_hints"] is True
    assert result["source"]["real_ticket_count"] == 1
    assert result["source"]["synthetic_ticket_count"] == 0
