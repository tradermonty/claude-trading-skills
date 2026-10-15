"""Additional coverage tests for design_strategy_drafts.py (Issue #293)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import design_strategy_drafts as dsd
import pytest
import yaml


def _concept(
    cid: str = "c1",
    family: str | None = "pivot_breakout",
    export: bool = True,
    hypothesis: str = "breakout",
    **extra,
) -> dict:
    concept = {
        "id": cid,
        "title": f"Title {cid}",
        "hypothesis_type": hypothesis,
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "support": {"representative_conditions": ["cond_a", "cond_b"]},
        "abstraction": {"thesis": "T", "invalidation_signals": ["S1"]},
        "strategy_design": {"recommended_entry_family": family, "export_ready_v1": export},
    }
    concept.update(extra)
    return concept


def _write_concepts(path: Path, concepts: list, as_of=None) -> Path:
    payload: dict = {"concepts": concepts}
    if as_of is not None:
        payload["as_of"] = as_of
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _run_main(monkeypatch, capsys, *argv: str) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["design_strategy_drafts.py", *argv])
    rc = dsd.main()
    return rc, capsys.readouterr().out


# --- sanitize_identifier / safe_float ---


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Draft Concept-1 (core)", "draft_concept_1_core"),
        ("  A..B  ", "a_b"),
        ("UPPER_lower", "upper_lower"),
        ("!!!", "draft"),
        ("", "draft"),
    ],
)
def test_sanitize_identifier(raw: str, expected: str) -> None:
    assert dsd.sanitize_identifier(raw) == expected


@pytest.mark.parametrize(
    "value,default,expected",
    [
        ("1.5", 0.0, 1.5),
        (2, 0.0, 2.0),
        (None, 7.0, 7.0),
        ("abc", 3.0, 3.0),
        ([], 9.0, 9.0),
    ],
)
def test_safe_float(value, default, expected) -> None:
    assert dsd.safe_float(value, default) == expected


# --- apply_hypothesis_exit_overrides ---


def test_exit_overrides_rr_floor_clamps_low_result() -> None:
    result = dsd.apply_hypothesis_exit_overrides(0.05, 1.8, "panic_reversal")
    # 1.8 - 0.7 = 1.1 < floor
    assert result["take_profit_rr"] == dsd.RR_FLOOR
    assert result["stop_loss_pct"] == 0.035
    assert result["time_stop_days"] == 5


def test_exit_overrides_unknown_type_uses_fallback_without_trailing_hint() -> None:
    result = dsd.apply_hypothesis_exit_overrides(0.07, 3.0, "no_such_type")
    assert result == {"stop_loss_pct": 0.07, "take_profit_rr": 3.0, "time_stop_days": 10}


def test_exit_overrides_futures_trigger_has_trailing_hint() -> None:
    result = dsd.apply_hypothesis_exit_overrides(0.07, 3.0, "futures_trigger")
    assert result["trailing_stop_hint"] == "ATR trailing recommended"
    assert result["stop_loss_pct"] == 0.0595


# --- load_concepts ---


def test_load_concepts_filters_invalid_entries(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "concepts": [
                    {"id": "ok"},
                    {"title": "no id"},
                    {"id": ""},
                    "string-entry",
                    {"id": "ok2", "x": 1},
                ]
            }
        ),
        encoding="utf-8",
    )
    result = dsd.load_concepts(path)
    assert [c["id"] for c in result] == ["ok", "ok2"]


def test_load_concepts_missing_key_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("as_of: '2026-01-01'\n", encoding="utf-8")
    assert dsd.load_concepts(path) == []


def test_load_concepts_non_mapping_raises(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(dsd.StrategyDesignError, match="must be a mapping"):
        dsd.load_concepts(path)


def test_load_concepts_empty_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(dsd.StrategyDesignError, match="must be a mapping"):
        dsd.load_concepts(path)


def test_load_concepts_concepts_not_list_raises(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("concepts: {a: 1}\n", encoding="utf-8")
    with pytest.raises(dsd.StrategyDesignError, match="must contain concepts list"):
        dsd.load_concepts(path)


# --- resolve_variants ---


def test_resolve_variants_export_ready_gives_core_and_conservative() -> None:
    assert dsd.resolve_variants(_concept(), 2) == ["core", "conservative"]


def test_resolve_variants_limit_one_and_clamped_to_one() -> None:
    assert dsd.resolve_variants(_concept(), 1) == ["core"]
    assert dsd.resolve_variants(_concept(), 0) == ["core"]
    assert dsd.resolve_variants(_concept(), -3) == ["core"]


def test_resolve_variants_non_export_ready_is_research_probe() -> None:
    concept = _concept(family=None, export=False)
    assert dsd.resolve_variants(concept, 2) == ["research_probe"]


def test_resolve_variants_missing_strategy_design() -> None:
    assert dsd.resolve_variants({"id": "x"}, 2) == ["research_probe"]


def test_resolve_variants_family_override_downgrades() -> None:
    concept = _concept(family="pivot_breakout")
    assert dsd.resolve_variants(concept, 2, exportable_families={"news_reaction"}) == [
        "research_probe"
    ]


def test_resolve_variants_family_override_keeps_matching() -> None:
    concept = _concept(family="pivot_breakout")
    assert dsd.resolve_variants(concept, 2, exportable_families={"pivot_breakout"}) == [
        "core",
        "conservative",
    ]


# --- resolve_entry_settings ---


def test_resolve_entry_settings_known_family() -> None:
    family, template, ready = dsd.resolve_entry_settings(_concept(family="news_reaction"))
    assert family == "news_reaction"
    assert template is dsd.ENTRY_TEMPLATE["news_reaction"]
    assert ready is True


@pytest.mark.parametrize("family", [None, "bogus_family", 42])
def test_resolve_entry_settings_unknown_family(family) -> None:
    result = dsd.resolve_entry_settings(_concept(family=family))
    assert result == ("research_only", {"conditions": [], "trend_filter": []}, False)


# --- build_draft ---


def test_build_draft_full_field_values() -> None:
    draft = dsd.build_draft(_concept(), "core", "balanced", "2026-02-20")
    assert draft["id"] == "draft_c1_core"
    assert draft["as_of"] == "2026-02-20"
    assert draft["concept_id"] == "c1"
    assert draft["variant"] == "core"
    assert draft["name"] == "Title c1 (core)"
    assert draft["hypothesis_type"] == "breakout"
    assert draft["mechanism_tag"] == "behavior"
    assert draft["regime"] == "RiskOn"
    assert draft["entry"] == {
        "conditions": ["cond_a", "cond_b"],
        "trend_filter": dsd.ENTRY_TEMPLATE["pivot_breakout"]["trend_filter"],
        "note": "Use baseline confirmation and trend filter.",
    }
    assert draft["risk"] == {
        "position_sizing": "fixed_risk",
        "risk_per_trade": 0.01,
        "max_positions": 5,
        "max_sector_exposure": 0.3,
        "sector_group_by": "sector",
    }
    assert draft["validation_plan"]["hold_days"] == [5, 20, 60]
    assert draft["validation_plan"]["entry_timing"] == "next_open"
    assert draft["thesis"] == "T"
    assert draft["invalidation_signals"] == ["S1"]


@pytest.mark.parametrize(
    "variant,profile,rpt,max_pos",
    [
        ("core", "conservative", 0.005, 3),
        ("conservative", "balanced", 0.0075, 4),
        ("research_probe", "balanced", 0.005, 2),
        ("research_probe", "aggressive", 0.0075, 4),
        ("research_probe", "conservative", 0.0025, 2),
    ],
)
def test_build_draft_variant_risk_scaling(variant, profile, rpt, max_pos) -> None:
    draft = dsd.build_draft(_concept(), variant, profile, None)
    assert draft["risk"]["risk_per_trade"] == rpt
    assert draft["risk"]["max_positions"] == max_pos
    assert draft["as_of"] is None


def test_build_draft_max_positions_floor_of_one(monkeypatch) -> None:
    monkeypatch.setitem(dsd.VARIANT_OVERRIDES["research_probe"], "risk_multiplier", 0.01)
    draft = dsd.build_draft(_concept(), "research_probe", "conservative", None)
    assert draft["risk"]["max_positions"] == 1
    assert draft["risk"]["risk_per_trade"] == 0.0001


def test_build_draft_falls_back_to_template_conditions() -> None:
    concept = _concept()
    concept["support"] = {"representative_conditions": ["", "   ", 5, None]}
    draft = dsd.build_draft(concept, "core", "balanced", None)
    assert draft["entry"]["conditions"] == dsd.ENTRY_TEMPLATE["pivot_breakout"]["conditions"]


def test_build_draft_non_list_conditions_falls_back() -> None:
    concept = _concept()
    concept["support"] = {"representative_conditions": "close > x"}
    draft = dsd.build_draft(concept, "core", "balanced", None)
    assert draft["entry"]["conditions"] == dsd.ENTRY_TEMPLATE["pivot_breakout"]["conditions"]


def test_build_draft_research_only_has_empty_conditions_when_none_supplied() -> None:
    concept = _concept(family=None, export=False)
    concept["support"] = {}
    draft = dsd.build_draft(concept, "research_probe", "balanced", None)
    assert draft["entry"]["conditions"] == []
    assert draft["entry"]["trend_filter"] == []
    assert draft["entry_family"] == "research_only"


def test_build_draft_non_dict_support_and_abstraction_default() -> None:
    concept = _concept()
    concept["support"] = "bad"
    concept["abstraction"] = ["bad"]
    draft = dsd.build_draft(concept, "core", "balanced", None)
    assert draft["entry"]["conditions"] == dsd.ENTRY_TEMPLATE["pivot_breakout"]["conditions"]
    assert draft["thesis"] == ""
    assert draft["invalidation_signals"] == []


def test_build_draft_missing_optional_fields_use_defaults() -> None:
    draft = dsd.build_draft({"id": "bare"}, "research_probe", "balanced", None)
    assert draft["hypothesis_type"] == "unknown"
    assert draft["mechanism_tag"] == "uncertain"
    assert draft["regime"] == "Unknown"
    assert draft["name"] == "bare (research_probe)"
    assert draft["export_ready_v1"] is False
    assert draft["exit"]["time_stop_days"] == 10


def test_build_draft_non_string_id_is_stringified() -> None:
    draft = dsd.build_draft({"id": 123}, "research_probe", "balanced", None)
    assert draft["concept_id"] == "123"
    assert draft["id"] == "draft_123_research_probe"


def test_build_draft_id_is_sanitized() -> None:
    draft = dsd.build_draft(_concept(cid="My Concept/1"), "core", "balanced", None)
    assert draft["id"] == "draft_my_concept_1_core"


def test_build_draft_exportable_families_override_blocks_export() -> None:
    draft = dsd.build_draft(
        _concept(), "core", "balanced", None, exportable_families={"news_reaction"}
    )
    assert draft["entry_family"] == "pivot_breakout"
    assert draft["export_ready_v1"] is False


def test_build_draft_exportable_families_override_allows_export() -> None:
    draft = dsd.build_draft(
        _concept(family="news_reaction", hypothesis="news_reaction"),
        "core",
        "balanced",
        None,
        exportable_families={"news_reaction"},
    )
    assert draft["export_ready_v1"] is True


def test_build_draft_ignores_concept_export_flag_for_known_family() -> None:
    # Characterization, not intended behavior: the draft flag follows ENTRY_TEMPLATE
    # membership only, so a concept marked not export-ready still yields an
    # export-ready draft when its recommended family is a template family.
    concept = _concept(export=False, family="pivot_breakout")
    draft2 = dsd.build_draft(concept, "research_probe", "balanced", None)
    assert draft2["entry_family"] == "pivot_breakout"
    assert draft2["export_ready_v1"] is True  # pins current behavior: concept flag not consulted


def test_build_draft_invalid_risk_profile_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        dsd.build_draft(_concept(), "core", "nope", None)


def test_build_draft_invalid_variant_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        dsd.build_draft(_concept(), "nope", "balanced", None)


# --- build_export_ticket ---


def test_build_export_ticket_fields() -> None:
    draft = dsd.build_draft(_concept(), "core", "balanced", "2026-02-20")
    ticket = dsd.build_export_ticket(draft)
    assert ticket["id"] == "edge_c1_core"
    assert ticket["name"] == "Title c1 (core)"
    assert ticket["description"] == "Draft-derived ticket from concept c1 (core)."
    assert ticket["hypothesis_type"] == "breakout"
    assert ticket["entry_family"] == "pivot_breakout"
    assert ticket["holding_horizon"] == "20D"
    assert ticket["entry"]["conditions"] == ["cond_a", "cond_b"]
    assert ticket["risk"] == draft["risk"]
    assert ticket["exit"] == {"stop_loss_pct": 0.0595, "take_profit_rr": 3.0}
    assert ticket["cost_model"] == {"commission_per_share": 0.0, "slippage_bps": 5}


def test_build_export_ticket_unknown_hypothesis_pivot_maps_to_breakout() -> None:
    concept = _concept(hypothesis="whatever")
    del concept["hypothesis_type"]
    draft = dsd.build_draft(concept, "core", "balanced", None)
    assert draft["hypothesis_type"] == "unknown"
    assert dsd.build_export_ticket(draft)["hypothesis_type"] == "breakout"


def test_build_export_ticket_unknown_hypothesis_gap_maps_to_earnings_drift() -> None:
    concept = _concept(family="gap_up_continuation")
    del concept["hypothesis_type"]
    draft = dsd.build_draft(concept, "core", "balanced", None)
    assert dsd.build_export_ticket(draft)["hypothesis_type"] == "earnings_drift"


def test_build_export_ticket_unknown_hypothesis_other_family_stays_unknown() -> None:
    concept = _concept(family="news_reaction")
    del concept["hypothesis_type"]
    draft = dsd.build_draft(concept, "core", "balanced", None)
    assert dsd.build_export_ticket(draft)["hypothesis_type"] == "unknown"


def test_build_export_ticket_defaults_when_draft_sparse() -> None:
    draft = {
        "id": "draft_x_core",
        "name": "N",
        "concept_id": "x",
        "variant": "core",
        "entry_family": "news_reaction",
    }
    ticket = dsd.build_export_ticket(draft)
    assert ticket["id"] == "edge_x_core"
    assert ticket["hypothesis_type"] == "unknown"
    assert ticket["mechanism_tag"] == "uncertain"
    assert ticket["regime"] == "Neutral"
    assert ticket["entry"] == {"conditions": [], "trend_filter": []}
    assert ticket["risk"] == {}
    assert ticket["exit"] == {"stop_loss_pct": 0.07, "take_profit_rr": 3.0}


# --- parse_args ---


def test_parse_args_defaults(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["prog", "--concepts", "c.yaml"])
    args = dsd.parse_args()
    assert args.concepts == "c.yaml"
    assert args.output_dir == "reports/edge_strategy_drafts"
    assert args.risk_profile == "balanced"
    assert args.variants_per_concept == 2
    assert args.exportable_tickets_dir is None
    assert args.exportable_families is None


def test_parse_args_rejects_bad_risk_profile(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["prog", "--concepts", "c.yaml", "--risk-profile", "wild"])
    with pytest.raises(SystemExit) as exc:
        dsd.parse_args()
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_parse_args_requires_concepts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["prog"])
    with pytest.raises(SystemExit) as exc:
        dsd.parse_args()
    assert exc.value.code == 2
    assert "--concepts" in capsys.readouterr().err


# --- main ---


def test_main_missing_concepts_file(tmp_path, monkeypatch, capsys) -> None:
    missing = tmp_path / "nope.yaml"
    rc, out = _run_main(
        monkeypatch, capsys, "--concepts", str(missing), "--output-dir", str(tmp_path / "o")
    )
    assert rc == 1
    assert "[ERROR] concepts file not found:" in out
    assert str(missing.resolve()) in out
    assert not (tmp_path / "o").exists()


def test_main_empty_concepts_list_errors(tmp_path, monkeypatch, capsys) -> None:
    path = _write_concepts(tmp_path / "c.yaml", [])
    rc, out = _run_main(
        monkeypatch, capsys, "--concepts", str(path), "--output-dir", str(tmp_path / "o")
    )
    assert rc == 1
    assert "[ERROR] no concepts available in file" in out
    assert not (tmp_path / "o").exists()


def test_main_non_mapping_concepts_errors(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("- 1\n- 2\n", encoding="utf-8")
    rc, out = _run_main(
        monkeypatch, capsys, "--concepts", str(path), "--output-dir", str(tmp_path / "o")
    )
    assert rc == 1
    assert "[ERROR] concept file must be a mapping" in out


def test_main_generates_drafts_tickets_and_manifest(tmp_path, monkeypatch, capsys) -> None:
    path = _write_concepts(
        tmp_path / "c.yaml",
        [
            _concept("a"),
            _concept("b", family=None, export=False, hypothesis="news_reaction"),
        ],
        as_of="2026-02-20",
    )
    out_dir = tmp_path / "drafts"
    tickets_dir = tmp_path / "tickets"
    rc, out = _run_main(
        monkeypatch,
        capsys,
        "--concepts",
        str(path),
        "--output-dir",
        str(out_dir),
        "--exportable-tickets-dir",
        str(tickets_dir),
    )
    assert rc == 0
    assert out.startswith("[OK] drafts=3 exportable_tickets=2 ")
    assert f"output_dir={out_dir.resolve()}" in out

    names = sorted(p.name for p in out_dir.glob("*.yaml"))
    assert names == [
        "draft_a_conservative.yaml",
        "draft_a_core.yaml",
        "draft_b_research_probe.yaml",
    ]
    core = yaml.safe_load((out_dir / "draft_a_core.yaml").read_text())
    assert core["as_of"] == "2026-02-20"
    assert core["export_ready_v1"] is True
    assert core["risk_profile"] == "balanced"
    cons = yaml.safe_load((out_dir / "draft_a_conservative.yaml").read_text())
    assert cons["risk"]["risk_per_trade"] == 0.0075
    probe = yaml.safe_load((out_dir / "draft_b_research_probe.yaml").read_text())
    assert probe["entry_family"] == "research_only"
    assert probe["export_ready_v1"] is False

    assert sorted(p.name for p in tickets_dir.glob("*.yaml")) == [
        "edge_a_conservative.yaml",
        "edge_a_core.yaml",
    ]
    ticket = yaml.safe_load((tickets_dir / "edge_a_core.yaml").read_text())
    assert ticket["entry_family"] == "pivot_breakout"
    assert ticket["exit"]["stop_loss_pct"] == 0.0595

    manifest = json.loads((out_dir / "run_manifest.json").read_text())
    assert manifest["draft_count"] == 3
    assert manifest["exportable_ticket_count"] == 2
    assert manifest["risk_profile"] == "balanced"
    assert manifest["concepts_file"] == str(path.resolve())
    assert manifest["output_dir"] == str(out_dir.resolve())
    assert manifest["exportable_tickets_dir"] == str(tickets_dir.resolve())
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", manifest["generated_at_utc"])


def test_main_without_tickets_dir_writes_no_tickets(tmp_path, monkeypatch, capsys) -> None:
    path = _write_concepts(tmp_path / "c.yaml", [_concept("a")])
    out_dir = tmp_path / "drafts"
    rc, out = _run_main(
        monkeypatch,
        capsys,
        "--concepts",
        str(path),
        "--output-dir",
        str(out_dir),
        "--risk-profile",
        "aggressive",
        "--variants-per-concept",
        "1",
    )
    assert rc == 0
    assert "drafts=1 exportable_tickets=0" in out
    assert [p.name for p in out_dir.glob("*.yaml")] == ["draft_a_core.yaml"]
    draft = yaml.safe_load((out_dir / "draft_a_core.yaml").read_text())
    assert draft["as_of"] is None
    assert draft["risk_profile"] == "aggressive"
    assert draft["risk"]["max_positions"] == 7
    manifest = json.loads((out_dir / "run_manifest.json").read_text())
    assert manifest["exportable_tickets_dir"] is None
    assert manifest["risk_profile"] == "aggressive"


def test_main_exportable_families_override(tmp_path, monkeypatch, capsys) -> None:
    path = _write_concepts(
        tmp_path / "c.yaml",
        [_concept("a", family="pivot_breakout"), _concept("n", family="news_reaction")],
    )
    out_dir = tmp_path / "drafts"
    tickets_dir = tmp_path / "tickets"
    rc, out = _run_main(
        monkeypatch,
        capsys,
        "--concepts",
        str(path),
        "--output-dir",
        str(out_dir),
        "--exportable-tickets-dir",
        str(tickets_dir),
        "--exportable-families",
        " news_reaction , ,",
    )
    assert rc == 0
    assert "drafts=3 exportable_tickets=2" in out
    # pivot_breakout concept is downgraded to a single research_probe draft
    assert (out_dir / "draft_a_research_probe.yaml").exists()
    assert not (out_dir / "draft_a_core.yaml").exists()
    assert (out_dir / "draft_n_core.yaml").exists()
    assert sorted(p.name for p in tickets_dir.glob("*.yaml")) == [
        "edge_n_conservative.yaml",
        "edge_n_core.yaml",
    ]
    probe = yaml.safe_load((out_dir / "draft_a_research_probe.yaml").read_text())
    assert probe["export_ready_v1"] is False
    assert probe["entry_family"] == "pivot_breakout"


def test_main_skips_invalid_concepts_but_processes_valid(tmp_path, monkeypatch, capsys) -> None:
    path = _write_concepts(tmp_path / "c.yaml", [{"title": "no id"}, _concept("ok")])
    out_dir = tmp_path / "drafts"
    rc, out = _run_main(
        monkeypatch,
        capsys,
        "--concepts",
        str(path),
        "--output-dir",
        str(out_dir),
        "--variants-per-concept",
        "1",
    )
    assert rc == 0
    assert "drafts=1 " in out
    assert [p.name for p in out_dir.glob("*.yaml")] == ["draft_ok_core.yaml"]


def test_main_creates_nested_output_dirs(tmp_path, monkeypatch, capsys) -> None:
    path = _write_concepts(tmp_path / "c.yaml", [_concept("a", family=None, export=False)])
    out_dir = tmp_path / "x" / "y" / "drafts"
    tickets_dir = tmp_path / "p" / "q" / "tickets"
    rc, out = _run_main(
        monkeypatch,
        capsys,
        "--concepts",
        str(path),
        "--output-dir",
        str(out_dir),
        "--exportable-tickets-dir",
        str(tickets_dir),
    )
    assert rc == 0
    assert "drafts=1 exportable_tickets=0" in out
    assert tickets_dir.is_dir()
    assert list(tickets_dir.iterdir()) == []
    assert (out_dir / "run_manifest.json").exists()


def test_main_non_dict_as_of_source_is_handled(tmp_path, monkeypatch, capsys) -> None:
    # as_of present but a YAML date: safe_load returns date, dumped back as a date scalar
    path = tmp_path / "c.yaml"
    path.write_text(
        "as_of: 2026-02-20\nconcepts:\n  - id: a\n    strategy_design: {}\n", encoding="utf-8"
    )
    out_dir = tmp_path / "drafts"
    rc, _ = _run_main(
        monkeypatch,
        capsys,
        "--concepts",
        str(path),
        "--output-dir",
        str(out_dir),
    )
    assert rc == 0
    text = (out_dir / "draft_a_research_probe.yaml").read_text()
    assert "as_of: 2026-02-20" in text
    assert yaml.safe_load(text)["entry_family"] == "research_only"
