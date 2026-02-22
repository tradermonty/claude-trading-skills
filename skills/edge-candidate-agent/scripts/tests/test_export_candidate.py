"""Unit tests for exporting ticket payloads to candidate artifacts."""

import json
from pathlib import Path

import pytest
import yaml
from candidate_contract import INTERFACE_VERSION, read_yaml, validate_interface_contract
from export_candidate import ExportError, deep_merge, export_candidate


def write_ticket(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False))


def test_export_pivot_breakout_candidate(tmp_path: Path) -> None:
    ticket_path = tmp_path / "ticket.yaml"
    write_ticket(
        ticket_path,
        {
            "id": "edge_vcp_breakout_v1",
            "hypothesis_type": "breakout",
            "entry_family": "pivot_breakout",
            "name": "Edge VCP Breakout v1",
            "description": "Pivot breakout test candidate",
        },
    )

    strategies_dir = tmp_path / "strategies"
    spec, metadata, candidate_dir = export_candidate(
        ticket_path=ticket_path,
        strategies_dir=strategies_dir,
    )

    assert candidate_dir == strategies_dir / "edge_vcp_breakout_v1"
    assert (candidate_dir / "strategy.yaml").exists()
    assert (candidate_dir / "metadata.json").exists()

    loaded_spec = read_yaml(candidate_dir / "strategy.yaml")
    errors = validate_interface_contract(
        loaded_spec, candidate_id="edge_vcp_breakout_v1", stage="phase1"
    )
    assert errors == []
    assert loaded_spec["signals"]["entry"]["type"] == "pivot_breakout"
    assert "vcp_detection" in loaded_spec

    loaded_metadata = json.loads((candidate_dir / "metadata.json").read_text())
    assert loaded_metadata["interface_version"] == INTERFACE_VERSION
    assert loaded_metadata["candidate_id"] == "edge_vcp_breakout_v1"
    assert metadata["candidate_id"] == "edge_vcp_breakout_v1"
    assert spec["id"] == "edge_vcp_breakout_v1"


def test_export_gap_candidate_with_override_id(tmp_path: Path) -> None:
    ticket_path = tmp_path / "ticket.yaml"
    write_ticket(
        ticket_path,
        {
            "id": "edge_gap_followthrough_v1",
            "hypothesis_type": "earnings_drift",
            "entry_family": "gap_up_continuation",
            "name": "Edge Gap Followthrough v1",
            "description": "Gap continuation test candidate",
        },
    )

    strategies_dir = tmp_path / "strategies"
    spec, _, candidate_dir = export_candidate(
        ticket_path=ticket_path,
        strategies_dir=strategies_dir,
        candidate_id="edge_gap_override_v1",
    )

    assert candidate_dir == strategies_dir / "edge_gap_override_v1"
    assert spec["id"] == "edge_gap_override_v1"
    loaded_spec = read_yaml(candidate_dir / "strategy.yaml")
    assert loaded_spec["signals"]["entry"]["type"] == "gap_up_continuation"
    assert "gap_up_detection" in loaded_spec


def test_export_rejects_unsupported_entry_family(tmp_path: Path) -> None:
    ticket_path = tmp_path / "ticket.yaml"
    write_ticket(
        ticket_path,
        {
            "id": "edge_momentum_v1",
            "hypothesis_type": "momentum",
            "entry_family": "momentum_followthrough",
        },
    )

    strategies_dir = tmp_path / "strategies"
    with pytest.raises(ExportError, match="ticket.entry_family must be one of"):
        export_candidate(ticket_path=ticket_path, strategies_dir=strategies_dir)


def test_export_dry_run_does_not_write_artifacts(tmp_path: Path) -> None:
    ticket_path = tmp_path / "ticket.yaml"
    write_ticket(
        ticket_path,
        {
            "id": "edge_vcp_dry_run_v1",
            "hypothesis_type": "breakout",
            "entry_family": "pivot_breakout",
        },
    )

    strategies_dir = tmp_path / "strategies"
    spec, metadata, candidate_dir = export_candidate(
        ticket_path=ticket_path,
        strategies_dir=strategies_dir,
        dry_run=True,
    )

    assert spec["id"] == "edge_vcp_dry_run_v1"
    assert metadata["candidate_id"] == "edge_vcp_dry_run_v1"
    assert not candidate_dir.exists()
    assert not (candidate_dir / "strategy.yaml").exists()
    assert not (candidate_dir / "metadata.json").exists()


def test_export_force_overwrites_existing_artifacts(tmp_path: Path) -> None:
    ticket_path = tmp_path / "ticket.yaml"
    write_ticket(
        ticket_path,
        {
            "id": "edge_vcp_force_v1",
            "hypothesis_type": "breakout",
            "entry_family": "pivot_breakout",
            "description": "first description",
        },
    )

    strategies_dir = tmp_path / "strategies"
    export_candidate(ticket_path=ticket_path, strategies_dir=strategies_dir)

    write_ticket(
        ticket_path,
        {
            "id": "edge_vcp_force_v1",
            "hypothesis_type": "breakout",
            "entry_family": "pivot_breakout",
            "description": "updated description",
        },
    )

    with pytest.raises(ExportError, match="already exist"):
        export_candidate(ticket_path=ticket_path, strategies_dir=strategies_dir, force=False)

    export_candidate(ticket_path=ticket_path, strategies_dir=strategies_dir, force=True)
    loaded_spec = read_yaml(strategies_dir / "edge_vcp_force_v1" / "strategy.yaml")
    assert loaded_spec["description"] == "updated description"


def test_deep_merge_handles_nested_and_scalar_overrides() -> None:
    base = {
        "a": {"x": 1, "y": 2},
        "b": 10,
    }
    override = {
        "a": {"y": 20, "z": 30},
        "b": {"nested": True},
        "c": 99,
    }
    merged = deep_merge(base, override)

    assert merged["a"] == {"x": 1, "y": 20, "z": 30}
    assert merged["b"] == {"nested": True}
    assert merged["c"] == 99


def test_deep_merge_with_empty_override_returns_same_structure() -> None:
    base = {"a": {"x": 1}, "b": 2}
    merged = deep_merge(base, {})
    assert merged == base
