"""Edge-path tests for contract validation, export CLI and validate CLI."""

from pathlib import Path
from subprocess import CompletedProcess

import candidate_contract as cc
import export_candidate as ec
import pytest
import validate_candidate as vc
import yaml


def _ticket(**over) -> dict:
    base = {
        "id": "edge_t1",
        "hypothesis_type": "breakout",
        "entry_family": "pivot_breakout",
    }
    base.update(over)
    return base


def _write(path: Path, payload) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _spec() -> dict:
    return ec.build_strategy_spec(_ticket(), "edge_t1")


# --- candidate_contract -----------------------------------------------------


def test_read_yaml_rejects_non_mapping_root(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML root must be a mapping"):
        cc.read_yaml(path)


def test_write_yaml_round_trips_in_insertion_order(tmp_path: Path) -> None:
    path = tmp_path / "out.yaml"
    cc.write_yaml(path, {"zeta": 1, "alpha": {"b": 2}})
    assert path.read_text(encoding="utf-8").splitlines()[0] == "zeta: 1"
    assert cc.read_yaml(path) == {"zeta": 1, "alpha": {"b": 2}}


def test_validate_ticket_flags_missing_and_blank_fields() -> None:
    errors = cc.validate_ticket_payload({"id": "  ", "entry_family": 5})
    assert "ticket.id must be a non-empty string" in errors
    assert "ticket.hypothesis_type must be a non-empty string" in errors
    assert "ticket.entry_family must be a non-empty string" in errors


def test_validate_ticket_rejects_non_mapping_validation() -> None:
    errors = cc.validate_ticket_payload(_ticket(validation="full_sample"))
    assert errors == ["ticket.validation must be a mapping when provided"]


def test_validate_ticket_rejects_oos_and_non_full_sample() -> None:
    errors = cc.validate_ticket_payload(
        _ticket(validation={"method": "walk_forward", "oos_ratio": 0.3})
    )
    assert "ticket.validation.method must be 'full_sample' for Phase I" in errors
    assert "ticket.validation.oos_ratio must be omitted or null for Phase I" in errors


def test_contract_reports_missing_top_level_keys_and_id_mismatch() -> None:
    errors = cc.validate_interface_contract({"id": "a"}, candidate_id="b")
    assert any(e.startswith("missing required top-level keys:") for e in errors)
    assert any("candidate_id=b, id=a" in e for e in errors)
    assert "signals must be a mapping" in errors
    assert "signals.entry must be a mapping" in errors
    assert "signals.exit must be a mapping" in errors
    assert "risk must be a mapping" in errors
    assert "validation must be a mapping" in errors


def test_contract_entry_type_and_conditions_errors() -> None:
    spec = _spec()
    spec["signals"]["entry"]["type"] = " "
    spec["signals"]["entry"]["conditions"] = []
    errors = cc.validate_interface_contract(spec)
    assert "signals.entry.type must be a non-empty string" in errors
    assert "signals.entry.conditions must be a non-empty list" in errors

    spec["signals"]["entry"]["type"] = "mean_reversion"
    errors = cc.validate_interface_contract(spec)
    assert any(e.startswith("signals.entry.type must be one of:") for e in errors)


def test_contract_exit_rule_errors() -> None:
    spec = _spec()
    spec["signals"]["exit"]["stop_loss"] = ""
    spec["signals"]["exit"]["trailing_stop"] = None
    spec["signals"]["exit"]["take_profit"] = " "
    errors = cc.validate_interface_contract(spec)
    assert "signals.exit.stop_loss must be a non-empty string" in errors
    assert "signals.exit must include trailing_stop or take_profit" in errors


def test_contract_risk_bounds() -> None:
    spec = _spec()
    spec["risk"]["risk_per_trade"] = 0.5
    spec["risk"]["max_positions"] = True
    spec["risk"]["max_sector_exposure"] = 1.5
    errors = cc.validate_interface_contract(spec)
    assert "risk.risk_per_trade must satisfy 0 < value <= 0.10" in errors
    assert "risk.max_positions must be an integer >= 1" in errors
    assert "risk.max_sector_exposure must satisfy 0 < value <= 1.0" in errors


def test_contract_sector_group_by_rules() -> None:
    spec = _spec()
    spec["risk"]["sector_group_by"] = "country"
    errors = cc.validate_interface_contract(spec)
    assert any("risk.sector_group_by must be one of" in e for e in errors)

    spec["risk"]["sector_group_by"] = None
    spec["risk"]["max_sector_exposure"] = 0.3
    errors = cc.validate_interface_contract(spec)
    assert "risk.sector_group_by is required when risk.max_sector_exposure < 1.0" in errors

    spec["risk"]["max_sector_exposure"] = 1.0
    assert cc.validate_interface_contract(spec) == []


def test_contract_phase1_validation_rules_and_other_stage() -> None:
    spec = _spec()
    spec["validation"] = {"method": "walk_forward", "oos_ratio": 0.3}
    errors = cc.validate_interface_contract(spec, stage="phase1")
    assert "validation.method must be 'full_sample' in Phase I" in errors
    assert "validation.oos_ratio must be omitted or null in Phase I" in errors
    # Other stages do not enforce the Phase I validation constraint.
    assert cc.validate_interface_contract(spec, stage="phase2") == []


def test_contract_dispatch_block_rules() -> None:
    spec = _spec()
    spec["vcp_detection"] = "oops"
    errors = cc.validate_interface_contract(spec)
    assert "vcp_detection must be a mapping when provided" in errors
    assert "pivot_breakout requires vcp_detection block" in errors

    spec = _spec()
    spec["signals"]["entry"]["type"] = "news_reaction"
    errors = cc.validate_interface_contract(spec)
    assert any("news_reaction has no downstream detector" in e for e in errors)


def test_contract_panic_block_must_match_exit() -> None:
    spec = ec.build_strategy_spec(
        _ticket(entry_family="panic_reversal", hypothesis_type="panic_reversal"), "edge_t1"
    )
    assert cc.validate_interface_contract(spec) == []
    spec["panic_reversal"]["stop_loss_pct"] = 0.2
    errors = cc.validate_interface_contract(spec)
    assert "panic_reversal.stop_loss_pct must match signals.exit.stop_loss_pct" in errors


# --- export_candidate -------------------------------------------------------


def test_build_strategy_spec_rejects_non_full_sample_validation() -> None:
    with pytest.raises(ec.ExportError, match="must be 'full_sample'"):
        ec.build_strategy_spec(_ticket(validation={"method": "walk_forward"}), "x")


def test_build_strategy_spec_rejects_oos_ratio() -> None:
    with pytest.raises(ec.ExportError, match="oos_ratio must be omitted"):
        ec.build_strategy_spec(_ticket(validation={"oos_ratio": 0.2}), "x")


def test_build_strategy_spec_default_name_and_description() -> None:
    spec = ec.build_strategy_spec(_ticket(), "my_cand-id")
    assert spec["name"] == "My Cand Id"
    assert spec["description"] == "Auto-generated from ticket edge_t1 (breakout)"


def test_build_strategy_spec_applies_overrides_and_detection() -> None:
    ticket = _ticket(
        entry_family="gap_up_continuation",
        entry={"conditions": ["custom_cond"], "trend_filter": ["tf"]},
        exit={"stop_loss_pct": 0.05},
        risk={"max_positions": 3},
        detection={"gap_up_detection": {"min_gap_pct": 0.09}},
        strategy_overrides={"cost_model": {"slippage_bps": 12}},
    )
    spec = ec.build_strategy_spec(ticket, "c1")
    assert spec["signals"]["entry"]["conditions"] == ["custom_cond"]
    assert spec["signals"]["entry"]["trend_filter"] == ["tf"]
    assert spec["signals"]["exit"]["stop_loss_pct"] == 0.05
    assert spec["risk"]["max_positions"] == 3
    assert spec["gap_up_detection"]["min_gap_pct"] == 0.09
    assert spec["gap_up_detection"]["volume_ratio"] == 2.0
    assert spec["cost_model"] == {"commission_per_share": 0.0, "slippage_bps": 12}


def test_build_strategy_spec_rejects_non_mapping_overrides() -> None:
    with pytest.raises(ec.ExportError, match="strategy_overrides must be a mapping"):
        ec.build_strategy_spec(_ticket(strategy_overrides=["a"]), "c1")


def test_panic_reversal_block_is_derived_from_exit_rules() -> None:
    ticket = _ticket(
        entry_family="panic_reversal",
        exit={"stop_loss_pct": 0.04, "take_profit_rr": 2.0},
        panic_reversal={"stop_loss_pct": 0.99, "extra": 1},
    )
    spec = ec.build_strategy_spec(ticket, "c1")
    assert spec["panic_reversal"] == {"stop_loss_pct": 0.04, "take_profit_rr": 2.0, "extra": 1}


def test_export_candidate_rejects_invalid_ticket(tmp_path: Path) -> None:
    ticket = _write(tmp_path / "t.yaml", {"id": "x"})
    with pytest.raises(ec.ExportError, match="Ticket validation failed"):
        ec.export_candidate(ticket, tmp_path / "s")


def test_export_candidate_rejects_blank_candidate_id(tmp_path: Path) -> None:
    ticket = _write(tmp_path / "t.yaml", _ticket())
    with pytest.raises(ec.ExportError, match="candidate_id must not be empty"):
        ec.export_candidate(ticket, tmp_path / "s", candidate_id="   ")


def test_export_candidate_rejects_contract_violation(tmp_path: Path) -> None:
    # news_reaction has no downstream detector, so the contract refuses to export it.
    ticket = _write(
        tmp_path / "t.yaml", _ticket(entry_family="news_reaction", hypothesis_type="news_reaction")
    )
    with pytest.raises(ec.ExportError, match="does not satisfy contract"):
        ec.export_candidate(ticket, tmp_path / "s")
    assert not (tmp_path / "s").exists()


def test_export_candidate_refuses_overwrite_without_force(tmp_path: Path) -> None:
    ticket = _write(tmp_path / "t.yaml", _ticket())
    ec.export_candidate(ticket, tmp_path / "s")
    with pytest.raises(ec.ExportError, match="already exist"):
        ec.export_candidate(ticket, tmp_path / "s")


def test_build_metadata_fields(tmp_path: Path) -> None:
    meta = ec.build_metadata(
        _ticket(regime="RiskOn", holding_horizon="5D", mechanism_tag="behavior"),
        "c1",
        tmp_path / "t.yaml",
        "9.9.9",
    )
    assert meta["generator"]["version"] == "9.9.9"
    assert meta["generated_at_utc"].endswith("Z")
    assert meta["research_context"]["regime"] == "RiskOn"
    assert meta["research_context"]["holding_horizon"] == "5D"
    assert meta["research_context"]["mechanism_tag"] == "behavior"


def test_export_main_success_and_dry_run(monkeypatch, capsys, tmp_path: Path) -> None:
    ticket = _write(tmp_path / "t.yaml", _ticket())
    out_dir = tmp_path / "strategies"
    monkeypatch.setattr(
        "sys.argv",
        ["export", "--ticket", str(ticket), "--strategies-dir", str(out_dir), "--dry-run"],
    )
    assert ec.main() == 0
    out = capsys.readouterr().out
    assert "[OK] Candidate id: edge_t1" in out
    assert "Dry-run completed" in out
    assert not out_dir.exists()

    monkeypatch.setattr(
        "sys.argv",
        [
            "export",
            "--ticket",
            str(ticket),
            "--strategies-dir",
            str(out_dir),
            "--generator-version",
            "2.0.0",
        ],
    )
    assert ec.main() == 0
    out = capsys.readouterr().out
    assert "Wrote strategy.yaml" in out
    meta = (out_dir / "edge_t1" / "metadata.json").read_text()
    assert '"version": "2.0.0"' in meta


def test_export_main_returns_error_exit_code(monkeypatch, capsys, tmp_path: Path) -> None:
    ticket = _write(tmp_path / "t.yaml", {"id": "x"})
    monkeypatch.setattr(
        "sys.argv", ["export", "--ticket", str(ticket), "--strategies-dir", str(tmp_path / "s")]
    )
    assert ec.main() == 1
    assert "[ERROR] Ticket validation failed" in capsys.readouterr().out


def test_export_main_handles_non_mapping_yaml(monkeypatch, capsys, tmp_path: Path) -> None:
    ticket = tmp_path / "t.yaml"
    ticket.write_text("- 1\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["export", "--ticket", str(ticket)])
    assert ec.main() == 1
    assert "YAML root must be a mapping" in capsys.readouterr().out


# --- validate_candidate -----------------------------------------------------


def test_validate_main_reports_unreadable_yaml(monkeypatch, capsys, tmp_path: Path) -> None:
    strategy = tmp_path / "strategy.yaml"
    strategy.write_text("- not a mapping\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["validate", "--strategy", str(strategy)])
    assert vc.main() == 1
    assert "[ERROR] failed to read strategy YAML" in capsys.readouterr().out


def test_validate_main_lists_contract_errors(monkeypatch, capsys, tmp_path: Path) -> None:
    cand_dir = tmp_path / "wrong_name"
    cand_dir.mkdir()
    strategy = _write(cand_dir / "strategy.yaml", _spec())
    monkeypatch.setattr("sys.argv", ["validate", "--strategy", str(strategy)])
    assert vc.main() == 1
    out = capsys.readouterr().out
    assert "Candidate validation failed" in out
    assert "candidate_id=wrong_name, id=edge_t1" in out


def test_validate_pipeline_uv_rejects_non_list_errors_and_empty_output(
    monkeypatch, tmp_path: Path
) -> None:
    def run_with(stdout: str):
        def fake_run(*a, **k):
            return CompletedProcess(args=a[0], returncode=0, stdout=stdout, stderr="")

        return fake_run

    monkeypatch.setattr(vc.subprocess, "run", run_with('{"errors": "boom"}\n'))
    assert vc.validate_with_pipeline_uv(tmp_path / "s.yaml", tmp_path, "phase1") == [
        "uv validation output missing 'errors' list"
    ]
    monkeypatch.setattr(vc.subprocess, "run", run_with("\n  \n"))
    assert vc.validate_with_pipeline_uv(tmp_path / "s.yaml", tmp_path, "phase1") == [
        "uv pipeline validation produced no output"
    ]


def test_validate_main_pipeline_success_message(monkeypatch, capsys, tmp_path: Path) -> None:
    cand_dir = tmp_path / "edge_t1"
    cand_dir.mkdir()
    strategy = _write(cand_dir / "strategy.yaml", _spec())
    monkeypatch.setattr(vc, "validate_with_pipeline_schema", lambda **k: [])
    monkeypatch.setattr(
        "sys.argv",
        [
            "validate",
            "--strategy",
            str(strategy),
            "--pipeline-root",
            str(tmp_path),
            "--stage",
            "phase2",
        ],
    )
    assert vc.main() == 0
    assert "pipeline schema validated against stage=phase2" in capsys.readouterr().out


def test_uv_env_sets_default_cache_dir_without_overriding(monkeypatch) -> None:
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    assert vc._uv_env()["UV_CACHE_DIR"] == "/tmp/uv-cache-edge-candidate-agent"
    monkeypatch.setenv("UV_CACHE_DIR", "/custom/cache")
    assert vc._uv_env()["UV_CACHE_DIR"] == "/custom/cache"
