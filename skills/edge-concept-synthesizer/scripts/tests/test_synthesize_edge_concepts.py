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


# ---------------------------------------------------------------------------
# Helpers for merge / dedup tests
# ---------------------------------------------------------------------------


def _make_merge_concept(
    concept_id: str,
    hypothesis_type: str,
    mechanism_tag: str,
    ticket_count: int = 2,
    avg_priority: float = 70.0,
    symbols: list[str] | None = None,
    conditions: list[str] | None = None,
    entry_family: str | None = "pivot_breakout",
    real_ticket_count: int | None = None,
    synthetic_ticket_count: int | None = None,
    synthetic_ticket_ids: list[str] | None = None,
) -> dict:
    """Create a concept dict for merge/dedup tests."""
    if symbols is None:
        symbols = ["XP"]
    if conditions is None:
        conditions = ["close > high20_prev", "rel_volume >= 1.5"]

    support: dict = {
        "ticket_count": ticket_count,
        "avg_priority_score": avg_priority,
        "symbols": symbols,
        "entry_family_distribution": {entry_family: ticket_count} if entry_family else {},
        "representative_conditions": conditions,
    }
    if real_ticket_count is not None:
        support["real_ticket_count"] = real_ticket_count
    if synthetic_ticket_count is not None:
        support["synthetic_ticket_count"] = synthetic_ticket_count

    evidence: dict = {
        "ticket_ids": [f"ticket_{i}" for i in range(ticket_count)],
        "matched_hint_titles": [],
    }
    if synthetic_ticket_ids:
        evidence["synthetic_ticket_ids"] = synthetic_ticket_ids

    concept = {
        "id": concept_id,
        "title": f"Test {hypothesis_type}",
        "hypothesis_type": hypothesis_type,
        "mechanism_tag": mechanism_tag,
        "regime": "RiskOn",
        "support": support,
        "abstraction": {
            "thesis": f"Test thesis for {hypothesis_type}",
            "invalidation_signals": ["Signal 1", "Signal 2"],
        },
        "strategy_design": {
            "playbooks": ["test_playbook"],
            "recommended_entry_family": entry_family,
            "export_ready_v1": entry_family in sec.EXPORTABLE_FAMILIES if entry_family else False,
        },
        "evidence": evidence,
    }
    return concept


# ---------------------------------------------------------------------------
# condition_overlap_ratio tests
# ---------------------------------------------------------------------------


def test_overlap_ratio_identical():
    """Identical conditions should return 1.0."""
    assert sec.condition_overlap_ratio(["A > 1", "B < 2"], ["A > 1", "B < 2"]) == 1.0


def test_overlap_ratio_disjoint():
    """Completely different conditions should return 0.0."""
    assert sec.condition_overlap_ratio(["A > 1"], ["B < 2"]) == 0.0


def test_overlap_ratio_partial():
    """Partial overlap should return correct ratio."""
    # |{a,b} ∩ {b,c}| / min(2,2) = 1/2 = 0.5
    assert sec.condition_overlap_ratio(["A > 1", "B < 2"], ["B < 2", "C == 3"]) == 0.5


def test_overlap_ratio_empty():
    """Both empty should return 0.0."""
    assert sec.condition_overlap_ratio([], []) == 0.0


def test_overlap_ratio_one_empty():
    """One empty should return 0.0."""
    assert sec.condition_overlap_ratio(["A > 1"], []) == 0.0
    assert sec.condition_overlap_ratio([], ["B < 2"]) == 0.0


def test_overlap_ratio_case_insensitive():
    """Comparison should be case-insensitive."""
    assert sec.condition_overlap_ratio(["Close > MA50"], ["close > ma50"]) == 1.0


def test_overlap_ratio_asymmetric_containment():
    """Containment uses min(|A|,|B|): small set fully in large set -> 1.0."""
    # A={a,b,c,d}, B={a,b,c} -> |A∩B|/min(4,3) = 3/3 = 1.0
    assert (
        sec.condition_overlap_ratio(
            ["A > 1", "B < 2", "C == 3", "D != 4"],
            ["A > 1", "B < 2", "C == 3"],
        )
        == 1.0
    )


# ---------------------------------------------------------------------------
# merge_concepts tests
# ---------------------------------------------------------------------------


def test_merge_concepts_basic():
    """Merge two concepts with different mechanism_tag."""
    primary = _make_merge_concept(
        "c1",
        "breakout",
        "behavior",
        ticket_count=3,
        avg_priority=70.0,
        symbols=["XP", "NOK"],
        conditions=["close > high20_prev", "rel_volume >= 1.5"],
    )
    secondary = _make_merge_concept(
        "c2",
        "breakout",
        "flow",
        ticket_count=2,
        avg_priority=60.0,
        symbols=["NOK", "AAPL"],
        conditions=["close > high20_prev", "volume > 2x"],
    )
    merged = sec.merge_concepts(primary, secondary)
    assert merged["mechanism_tag"] == "behavior+flow"
    assert merged["support"]["ticket_count"] == 5
    assert "XP" in merged["support"]["symbols"]
    assert "AAPL" in merged["support"]["symbols"]
    assert "c2" in merged.get("merged_from", [])


def test_merge_concepts_entry_family_adoption():
    """If primary has no entry_family, adopt secondary's."""
    primary = _make_merge_concept(
        "c1",
        "breakout",
        "behavior",
        ticket_count=3,
        entry_family=None,
    )
    secondary = _make_merge_concept(
        "c2",
        "breakout",
        "flow",
        ticket_count=2,
        entry_family="pivot_breakout",
    )
    merged = sec.merge_concepts(primary, secondary)
    assert merged["strategy_design"]["recommended_entry_family"] == "pivot_breakout"


def test_merge_concepts_keeps_primary():
    """Primary's title, thesis, invalidation_signals should be preserved."""
    primary = _make_merge_concept("c1", "breakout", "behavior", ticket_count=3)
    secondary = _make_merge_concept("c2", "breakout", "flow", ticket_count=2)
    merged = sec.merge_concepts(primary, secondary)
    assert merged["abstraction"]["thesis"] == primary["abstraction"]["thesis"]


def test_merge_concepts_synthetic_fields():
    """If both have synthetic ticket counts, they should be summed."""
    primary = _make_merge_concept(
        "c1",
        "breakout",
        "behavior",
        ticket_count=3,
        real_ticket_count=2,
        synthetic_ticket_count=1,
        synthetic_ticket_ids=["hint_promo_1"],
    )
    secondary = _make_merge_concept(
        "c2",
        "breakout",
        "flow",
        ticket_count=2,
        real_ticket_count=1,
        synthetic_ticket_count=1,
        synthetic_ticket_ids=["hint_promo_2"],
    )
    merged = sec.merge_concepts(primary, secondary)
    assert merged["support"].get("real_ticket_count") == 3
    assert merged["support"].get("synthetic_ticket_count") == 2
    assert "hint_promo_1" in merged["evidence"].get("synthetic_ticket_ids", [])
    assert "hint_promo_2" in merged["evidence"].get("synthetic_ticket_ids", [])


def test_merge_concepts_id_regeneration():
    """Merged concept should have regenerated id."""
    primary = _make_merge_concept("old_id_1", "breakout", "behavior", ticket_count=3)
    secondary = _make_merge_concept("old_id_2", "breakout", "flow", ticket_count=2)
    merged = sec.merge_concepts(primary, secondary)
    # mechanism_tag becomes "behavior+flow"
    expected_id = sec.sanitize_identifier("edge_concept_breakout_behavior_flow_RiskOn")
    assert merged["id"] == expected_id


# ---------------------------------------------------------------------------
# deduplicate_concepts tests
# ---------------------------------------------------------------------------


def test_dedup_high_overlap_merge():
    """Two concepts with high overlap should be merged."""
    c1 = _make_merge_concept(
        "c1",
        "breakout",
        "behavior",
        ticket_count=3,
        conditions=["close > high20", "volume > 2x", "RSI > 50"],
    )
    c2 = _make_merge_concept(
        "c2",
        "breakout",
        "flow",
        ticket_count=2,
        conditions=["close > high20", "volume > 2x"],
    )
    result, count = sec.deduplicate_concepts([c1, c2], overlap_threshold=0.75)
    assert len(result) == 1
    assert count == 1


def test_dedup_keeps_distinct():
    """Two concepts with low overlap should NOT be merged."""
    c1 = _make_merge_concept(
        "c1",
        "breakout",
        "behavior",
        ticket_count=3,
        conditions=["close > high20", "volume > 2x"],
    )
    c2 = _make_merge_concept(
        "c2",
        "breakout",
        "flow",
        ticket_count=2,
        conditions=["RSI < 30", "price < SMA200"],
    )
    result, count = sec.deduplicate_concepts([c1, c2], overlap_threshold=0.75)
    assert len(result) == 2
    assert count == 0


def test_dedup_different_hypothesis_never_merge():
    """Concepts with different hypothesis_type should never be merged."""
    c1 = _make_merge_concept(
        "c1",
        "breakout",
        "behavior",
        ticket_count=3,
        conditions=["close > high20", "volume > 2x"],
    )
    c2 = _make_merge_concept(
        "c2",
        "panic_reversal",
        "behavior",
        ticket_count=2,
        conditions=["close > high20", "volume > 2x"],
    )
    result, count = sec.deduplicate_concepts([c1, c2], overlap_threshold=0.5)
    assert len(result) == 2
    assert count == 0


def test_dedup_single_concept():
    """Single concept should pass through unchanged."""
    c1 = _make_merge_concept("c1", "breakout", "behavior", ticket_count=3)
    result, count = sec.deduplicate_concepts([c1], overlap_threshold=0.75)
    assert len(result) == 1
    assert count == 0


def test_dedup_empty_list():
    """Empty list should return empty."""
    result, count = sec.deduplicate_concepts([], overlap_threshold=0.75)
    assert len(result) == 0
    assert count == 0


# ---------------------------------------------------------------------------
# main() integration tests for dedup
# ---------------------------------------------------------------------------


def test_main_no_dedup_flag(tmp_path: Path, monkeypatch) -> None:
    """--no-dedup should disable deduplication."""
    tickets_dir, hints_path = _setup_main_fixtures(tmp_path)
    # Add a second ticket to create potential duplicate
    ticket2 = {
        "id": "edge_auto_test_2",
        "hypothesis_type": "breakout",
        "mechanism_tag": "flow",
        "regime": "RiskOn",
        "priority_score": 65.0,
        "entry_family": "pivot_breakout",
        "observation": {"symbol": "XP"},
        "signal_definition": {"conditions": ["close > high20_prev", "rel_volume >= 1.5"]},
        "date": "2026-02-20",
    }
    (tickets_dir / "ticket_2.yaml").write_text(yaml.safe_dump(ticket2))
    output_path = tmp_path / "concepts.yaml"

    monkeypatch.setattr(
        "sys.argv",
        [
            "synthesize_edge_concepts.py",
            "--tickets-dir",
            str(tickets_dir),
            "--output",
            str(output_path),
            "--no-dedup",
        ],
    )
    assert sec.main() == 0
    result = yaml.safe_load(output_path.read_text())
    assert result["source"]["dedup_enabled"] is False
    assert result["source"]["dedup_merged_count"] == 0


def test_main_overlap_threshold_effect(tmp_path: Path, monkeypatch) -> None:
    """--overlap-threshold should affect merge behavior."""
    tickets_dir, _ = _setup_main_fixtures(tmp_path)
    # Create two tickets in different mechanism groups with same conditions
    for i, mech in enumerate(["behavior", "flow"]):
        ticket = {
            "id": f"edge_auto_dup_{i}",
            "hypothesis_type": "breakout",
            "mechanism_tag": mech,
            "regime": "RiskOn",
            "priority_score": 70.0,
            "entry_family": "pivot_breakout",
            "observation": {"symbol": "XP"},
            "signal_definition": {"conditions": ["close > high20_prev", "rel_volume >= 1.5"]},
            "date": "2026-02-20",
        }
        (tickets_dir / f"ticket_dup_{i}.yaml").write_text(yaml.safe_dump(ticket))
    output_path = tmp_path / "concepts.yaml"

    # With low threshold -> should merge
    monkeypatch.setattr(
        "sys.argv",
        [
            "synthesize_edge_concepts.py",
            "--tickets-dir",
            str(tickets_dir),
            "--output",
            str(output_path),
            "--overlap-threshold",
            "0.5",
        ],
    )
    assert sec.main() == 0
    result = yaml.safe_load(output_path.read_text())
    assert result["source"]["dedup_enabled"] is True
    assert result["source"]["overlap_threshold"] == 0.5
