"""Tests for generate_pivots.py — self-contained with inline fixtures."""

from __future__ import annotations

import importlib
import os
import sys

import pytest

# Ensure parent directory is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import generate_pivots as gp  # noqa: E402

# ---------------------------------------------------------------------------
# Inline Fixture Helpers
# ---------------------------------------------------------------------------


def _make_breakout_draft() -> dict:
    """Draft matching trend_following_breakout archetype."""
    return {
        "id": "my_breakout_v1",
        "concept_id": "concept_001",
        "hypothesis_type": "breakout",
        "mechanism_tag": "behavior",
        "entry_family": "pivot_breakout",
        "regime": "Bull",
        "exit": {
            "stop_loss_pct": 0.08,
            "take_profit_rr": 3.0,
            "time_stop_days": 20,
        },
        "risk": {
            "position_sizing": "fixed_risk",
            "risk_per_trade": 0.01,
            "max_positions": 5,
            "max_sector_exposure": 0.3,
        },
        "entry": {
            "conditions": ["close > high20_prev", "rel_volume >= 1.5"],
            "trend_filter": ["price > sma_200"],
        },
        "thesis": "Breakout with volume confirmation.",
        "invalidation_signals": ["close < sma_200"],
    }


def _make_mean_reversion_draft() -> dict:
    """Draft matching mean_reversion_pullback archetype."""
    return {
        "id": "mean_rev_v1",
        "concept_id": "concept_002",
        "hypothesis_type": "mean_reversion",
        "mechanism_tag": "statistical",
        "entry_family": "research_only",
        "regime": "Neutral",
        "exit": {
            "stop_loss_pct": 0.04,
            "take_profit_rr": 2.0,
            "time_stop_days": 7,
        },
        "risk": {
            "position_sizing": "fixed_risk",
            "risk_per_trade": 0.005,
            "max_positions": 3,
            "max_sector_exposure": 0.3,
        },
        "entry": {
            "conditions": ["rsi_14 < 30", "price > sma_200"],
            "trend_filter": ["sma_50 > sma_200"],
        },
        "thesis": "RSI oversold bounce.",
        "invalidation_signals": [],
    }


def _make_triggers(trigger_ids: list[str]) -> list[dict]:
    """Build a list of trigger dicts from trigger id strings."""
    return [
        {"trigger": t, "severity": "high", "message": f"Trigger {t} fired"} for t in trigger_ids
    ]


# ---------------------------------------------------------------------------
# Archetype Identification
# ---------------------------------------------------------------------------


class TestIdentifyArchetype:
    def test_identify_archetype_breakout_behavior(self):
        draft = _make_breakout_draft()
        assert gp.identify_current_archetype(draft) == "trend_following_breakout"

    def test_identify_archetype_mean_reversion_statistical(self):
        draft = _make_mean_reversion_draft()
        assert gp.identify_current_archetype(draft) == "mean_reversion_pullback"

    def test_identify_archetype_unknown_returns_none(self):
        draft = {
            "hypothesis_type": "quantum_flux",
            "mechanism_tag": "alien_signal",
            "entry_family": "warp_drive",
        }
        assert gp.identify_current_archetype(draft) is None


# ---------------------------------------------------------------------------
# Module Set Extraction
# ---------------------------------------------------------------------------


class TestComputeModuleSet:
    def test_compute_module_set_basic(self):
        draft = _make_breakout_draft()
        modules = gp.compute_module_set(draft)
        assert isinstance(modules, set)
        # Must contain (key, value) tuples
        assert all(isinstance(m, tuple) and len(m) == 2 for m in modules)
        # Check a few expected entries
        assert ("hypothesis_type", "breakout") in modules
        assert ("mechanism_tag", "behavior") in modules
        assert ("entry_family", "pivot_breakout") in modules

    def test_compute_module_set_horizon_classification(self):
        # short: time_stop_days=5
        draft_short = {"exit": {"time_stop_days": 5, "stop_loss_pct": 0.06}}
        modules_short = gp.compute_module_set(draft_short)
        assert ("horizon", "short") in modules_short

        # medium: time_stop_days=20
        draft_medium = {"exit": {"time_stop_days": 20, "stop_loss_pct": 0.06}}
        modules_medium = gp.compute_module_set(draft_medium)
        assert ("horizon", "medium") in modules_medium

        # long: time_stop_days=60
        draft_long = {"exit": {"time_stop_days": 60, "stop_loss_pct": 0.06}}
        modules_long = gp.compute_module_set(draft_long)
        assert ("horizon", "long") in modules_long

    def test_compute_module_set_risk_style(self):
        # tight: stop_loss_pct=0.03
        draft_tight = {"exit": {"stop_loss_pct": 0.03, "time_stop_days": 20}}
        modules_tight = gp.compute_module_set(draft_tight)
        assert ("risk_style", "tight") in modules_tight

        # normal: stop_loss_pct=0.06
        draft_normal = {"exit": {"stop_loss_pct": 0.06, "time_stop_days": 20}}
        modules_normal = gp.compute_module_set(draft_normal)
        assert ("risk_style", "normal") in modules_normal

        # wide: stop_loss_pct=0.10
        draft_wide = {"exit": {"stop_loss_pct": 0.10, "time_stop_days": 20}}
        modules_wide = gp.compute_module_set(draft_wide)
        assert ("risk_style", "wide") in modules_wide


# ---------------------------------------------------------------------------
# Novelty Scoring
# ---------------------------------------------------------------------------


class TestNoveltyScoring:
    def test_novelty_identical_strategies_zero(self):
        draft = _make_breakout_draft()
        s = gp.compute_module_set(draft)
        assert gp.score_novelty(s, s) == 0.0

    def test_novelty_completely_different_one(self):
        a = {("a", "1"), ("b", "2")}
        b = {("c", "3"), ("d", "4")}
        assert gp.score_novelty(a, b) == 1.0

    def test_novelty_partial_overlap(self):
        a = {("a", "1"), ("b", "2"), ("c", "3")}
        b = {("a", "1"), ("d", "4"), ("e", "5")}
        # intersection={("a","1")}, union=5 items => 1 - 1/5 = 0.8
        novelty = gp.score_novelty(a, b)
        assert 0.0 < novelty < 1.0
        assert abs(novelty - 0.8) < 1e-9


# ---------------------------------------------------------------------------
# Quality Potential
# ---------------------------------------------------------------------------


class TestQualityPotential:
    def test_quality_table_known_pair(self):
        score = gp.score_quality_potential("cost_defeat", "mean_reversion_pullback")
        assert score == 0.8  # exact match from QUALITY_TABLE

    def test_quality_table_unknown_pair(self):
        score = gp.score_quality_potential("nonexistent_trigger", "fake_archetype")
        assert score == gp.DEFAULT_QUALITY  # should return 0.3


# ---------------------------------------------------------------------------
# Inversion Generation
# ---------------------------------------------------------------------------


class TestGenerateInversions:
    def test_generate_inversions_cost_defeat(self):
        draft = _make_breakout_draft()
        triggers = _make_triggers(["cost_defeat"])
        proposals = gp.generate_inversions(draft, triggers, "trend_following_breakout")
        assert len(proposals) > 0

        # cost_defeat inversions should produce proposals with shortened horizon
        has_short_horizon = any(p["exit"]["time_stop_days"] <= 7 for p in proposals)
        assert has_short_horizon, "cost_defeat should produce at least one short-horizon proposal"

    def test_generate_inversions_tail_risk(self):
        draft = _make_breakout_draft()
        triggers = _make_triggers(["tail_risk"])
        proposals = gp.generate_inversions(draft, triggers, "trend_following_breakout")
        assert len(proposals) > 0

        # tail_risk inversions should produce proposals with tighter risk
        has_tight_risk = any(p["exit"]["stop_loss_pct"] <= 0.04 for p in proposals)
        assert has_tight_risk, "tail_risk should produce at least one tight-risk proposal"


# ---------------------------------------------------------------------------
# Archetype Switch
# ---------------------------------------------------------------------------


class TestGenerateArchetypeSwitches:
    def test_generate_archetype_switches_from_breakout(self):
        draft = _make_breakout_draft()
        triggers = _make_triggers(["improvement_plateau"])
        source_arch = "trend_following_breakout"
        proposals = gp.generate_archetype_switches(draft, source_arch, triggers)
        assert len(proposals) > 0

        # trend_following_breakout's compatible targets
        expected_targets = {
            "mean_reversion_pullback",
            "volatility_contraction",
            "sector_rotation_momentum",
        }
        actual_targets = {p["pivot_metadata"]["target_archetype"] for p in proposals}
        assert actual_targets == expected_targets

    def test_generate_archetype_switches_unknown_archetype(self):
        draft = _make_breakout_draft()
        triggers = _make_triggers(["cost_defeat"])
        proposals = gp.generate_archetype_switches(draft, None, triggers)
        assert proposals == []

        proposals2 = gp.generate_archetype_switches(draft, "nonexistent_arch", triggers)
        assert proposals2 == []


# ---------------------------------------------------------------------------
# Ranking and Selection
# ---------------------------------------------------------------------------


class TestRankAndSelect:
    def test_rank_and_select_top_n(self):
        draft = _make_breakout_draft()
        triggers = _make_triggers(["cost_defeat"])
        source_arch = "trend_following_breakout"

        all_proposals = gp.generate_inversions(draft, triggers, source_arch)
        all_proposals += gp.generate_archetype_switches(draft, source_arch, triggers)
        assert len(all_proposals) > 3  # ensure we have enough to select from

        selected = gp.rank_and_select(all_proposals, draft, triggers, max_pivots=3)
        assert len(selected) <= 3

        # Verify combined scores are in descending order
        scores = [p["pivot_metadata"]["scores"]["combined"] for p in selected]
        assert scores == sorted(scores, reverse=True)

    def test_rank_and_select_diversity_constraint(self):
        """Max 1 per target archetype."""
        draft = _make_breakout_draft()
        triggers = _make_triggers(["cost_defeat"])
        source_arch = "trend_following_breakout"

        all_proposals = gp.generate_inversions(draft, triggers, source_arch)
        all_proposals += gp.generate_archetype_switches(draft, source_arch, triggers)

        selected = gp.rank_and_select(all_proposals, draft, triggers, max_pivots=10)

        archetypes = [p["pivot_metadata"]["target_archetype"] for p in selected]
        assert len(archetypes) == len(set(archetypes)), "Each archetype should appear at most once"

    def test_rank_and_select_tiebreak_deterministic(self):
        """Same combined score -> higher novelty wins; same novelty -> alphabetical id."""
        draft = _make_breakout_draft()

        # Create synthetic proposals with identical combined but different novelty/ids
        p_a = {
            "id": "alpha",
            "hypothesis_type": "breakout",
            "mechanism_tag": "behavior",
            "entry_family": "pivot_breakout",
            "regime": "Bull",
            "exit": {"stop_loss_pct": 0.08, "time_stop_days": 20},
            "pivot_metadata": {
                "target_archetype": "arch_a",
                "targeted_triggers": ["cost_defeat"],
            },
        }
        p_b = {
            "id": "beta",
            "hypothesis_type": "mean_reversion",
            "mechanism_tag": "statistical",
            "entry_family": "research_only",
            "regime": "Neutral",
            "exit": {"stop_loss_pct": 0.04, "time_stop_days": 7},
            "pivot_metadata": {
                "target_archetype": "arch_b",
                "targeted_triggers": ["cost_defeat"],
            },
        }
        p_c = {
            "id": "charlie",
            "hypothesis_type": "mean_reversion",
            "mechanism_tag": "statistical",
            "entry_family": "research_only",
            "regime": "Neutral",
            "exit": {"stop_loss_pct": 0.04, "time_stop_days": 7},
            "pivot_metadata": {
                "target_archetype": "arch_c",
                "targeted_triggers": ["cost_defeat"],
            },
        }

        triggers = _make_triggers(["cost_defeat"])

        # Run selection multiple times — result must be deterministic
        results = []
        for _ in range(5):
            selected = gp.rank_and_select([p_a, p_b, p_c], draft, triggers, max_pivots=10)
            results.append([s["id"] for s in selected])

        # All 5 runs must produce the same order
        assert all(r == results[0] for r in results), "Selection must be deterministic"

        # Verify tiebreak: among those with same combined score, higher novelty wins
        selected = gp.rank_and_select([p_a, p_b, p_c], draft, triggers, max_pivots=10)
        for i in range(len(selected) - 1):
            s_i = selected[i]["pivot_metadata"]["scores"]
            s_j = selected[i + 1]["pivot_metadata"]["scores"]
            if s_i["combined"] == s_j["combined"]:
                if s_i["novelty"] == s_j["novelty"]:
                    assert selected[i]["id"] < selected[i + 1]["id"], (
                        "Same combined and novelty -> alphabetical id order"
                    )
                else:
                    assert s_i["novelty"] >= s_j["novelty"], "Same combined -> higher novelty first"


# ---------------------------------------------------------------------------
# Export Ticket
# ---------------------------------------------------------------------------


class TestBuildExportTicket:
    def test_build_export_ticket_eligible(self):
        draft = {
            "id": "pivot_my_breakout_v1_switch_volatility_contraction",
            "name": "Volatility Contraction (pivoted from my_breakout_v1)",
            "hypothesis_type": "breakout",
            "mechanism_tag": "structural",
            "entry_family": "pivot_breakout",
            "regime": "Bull",
            "entry": {
                "conditions": ["volatility_contraction_detected"],
                "trend_filter": ["price > sma_200"],
            },
            "exit": {
                "stop_loss_pct": 0.05,
                "take_profit_rr": 3.0,
                "time_stop_days": 20,
            },
            "risk": {
                "position_sizing": "fixed_risk",
                "risk_per_trade": 0.005,
                "max_positions": 5,
                "max_sector_exposure": 0.3,
            },
            "pivot_metadata": {
                "source_strategy_id": "my_breakout_v1",
            },
        }
        ticket = gp.build_export_ticket_if_eligible(draft)
        assert ticket is not None
        assert ticket["entry_family"] == "pivot_breakout"
        assert "id" in ticket
        assert ticket["hypothesis_type"] == "breakout"

    def test_build_export_ticket_research_only(self):
        draft = {
            "id": "pivot_test_switch_mean_reversion",
            "name": "Mean Reversion Pullback",
            "hypothesis_type": "mean_reversion",
            "mechanism_tag": "statistical",
            "entry_family": "research_only",
            "exit": {"stop_loss_pct": 0.04, "take_profit_rr": 2.0, "time_stop_days": 7},
            "risk": {},
            "pivot_metadata": {"source_strategy_id": "test"},
        }
        ticket = gp.build_export_ticket_if_eligible(draft)
        assert ticket is None


# ---------------------------------------------------------------------------
# ID Sanitization
# ---------------------------------------------------------------------------


class TestSanitizeIdentifier:
    def test_sanitize_identifier_special_chars(self):
        result = gp.sanitize_identifier("Hello World! @#$%")
        assert result == "hello_world"
        assert " " not in result
        assert all(c.isalnum() or c == "_" for c in result)

    def test_sanitize_identifier_empty_string_returns_pivot(self):
        result = gp.sanitize_identifier("")
        assert result == "pivot"

        result2 = gp.sanitize_identifier("   ")
        assert result2 == "pivot"


# ---------------------------------------------------------------------------
# Cross-Validation with candidate_contract.py
# ---------------------------------------------------------------------------


class TestCrossValidation:
    """Verify generate_pivots constants match candidate_contract.py."""

    @pytest.fixture(autouse=True)
    def _load_candidate_contract(self):
        """Import candidate_contract via importlib for cross-validation."""
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
        )
        contract_path = os.path.join(
            project_root,
            "skills",
            "edge-candidate-agent",
            "scripts",
            "candidate_contract.py",
        )
        if not os.path.exists(contract_path):
            pytest.skip(f"candidate_contract.py not found at {contract_path}")

        spec = importlib.util.spec_from_file_location("candidate_contract", contract_path)
        self.contract_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.contract_mod)

    def test_exportable_families_match_supported_entry_families(self):
        assert gp.EXPORTABLE_FAMILIES == self.contract_mod.SUPPORTED_ENTRY_FAMILIES

    def test_required_validation_fields_consistent(self):
        """The fields validated by _validate_ticket_minimal must match
        the required string fields in validate_ticket_payload."""
        # candidate_contract checks these as required non-empty strings:
        # ("id", "hypothesis_type", "entry_family")
        # Our minimal validator must check the same set.
        dummy_empty = {"id": "", "hypothesis_type": "", "entry_family": ""}
        our_errors = gp._validate_ticket_minimal(dummy_empty)
        their_errors = self.contract_mod.validate_ticket_payload(dummy_empty)

        # Both should flag all three fields
        our_fields = {e.split(".")[1].split(" ")[0] for e in our_errors if "must be" in e}
        their_fields = {e.split(".")[1].split(" ")[0] for e in their_errors if "must be" in e}
        required = {"id", "hypothesis_type", "entry_family"}
        assert required <= our_fields
        assert required <= their_fields

    def test_validation_method_constraint_consistent(self):
        """Both validators must reject non-full_sample method and non-null oos_ratio."""
        # Bad method
        ticket_bad_method = {
            "id": "t1",
            "hypothesis_type": "breakout",
            "entry_family": "pivot_breakout",
            "validation": {"method": "walk_forward", "oos_ratio": None},
        }
        our_errors = gp._validate_ticket_minimal(ticket_bad_method)
        their_errors = self.contract_mod.validate_ticket_payload(ticket_bad_method)
        assert any("full_sample" in e for e in our_errors)
        assert any("full_sample" in e for e in their_errors)

        # Bad oos_ratio
        ticket_bad_oos = {
            "id": "t2",
            "hypothesis_type": "breakout",
            "entry_family": "pivot_breakout",
            "validation": {"method": "full_sample", "oos_ratio": 0.3},
        }
        our_errors = gp._validate_ticket_minimal(ticket_bad_oos)
        their_errors = self.contract_mod.validate_ticket_payload(ticket_bad_oos)
        assert any("oos_ratio" in e for e in our_errors)
        assert any("oos_ratio" in e for e in their_errors)

        # Valid validation block — no errors from either
        ticket_ok = {
            "id": "t3",
            "hypothesis_type": "breakout",
            "entry_family": "pivot_breakout",
            "validation": {"method": "full_sample"},
        }
        our_errors = gp._validate_ticket_minimal(ticket_ok)
        their_errors = self.contract_mod.validate_ticket_payload(ticket_ok)
        our_val_errors = [e for e in our_errors if "validation" in e]
        their_val_errors = [e for e in their_errors if "validation" in e]
        assert our_val_errors == []
        assert their_val_errors == []
