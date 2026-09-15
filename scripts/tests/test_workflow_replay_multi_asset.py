"""Executable replay coverage for multi-asset-opportunity-daily (Issue #294)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import workflow_replay as replay_module  # noqa: E402
from workflow_replay import (  # noqa: E402
    ReplayError,
    compare_trees,
    execute_replay,
    load_yaml,
)

SPEC = ROOT / "examples" / "workflows" / "multi-asset-opportunity-daily" / "replay.yaml"
INPUTS = SPEC.parent / "replay-inputs"


def _override(tmp_path: Path, name: str, payload) -> Path:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir(exist_ok=True)
    path = input_dir / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_multi_asset_spec_uses_one_native_cli_step() -> None:
    summary = replay_module.validate_spec(ROOT, SPEC)

    assert summary["workflow_id"] == "multi-asset-opportunity-daily"
    assert summary["native_steps"] == [5]
    assert summary["manual_contract_steps"] == [1, 2, 3, 4, 6]


def test_required_only_replays_core_and_skips_catalyst(tmp_path: Path) -> None:
    output = tmp_path / "required"
    report = execute_replay(ROOT, SPEC, "required-only", output)

    assert report["status"] == "completed"
    assert report["network_policy"] == "offline-input-required"
    assert [step["executor_mode"] for step in report["steps"]] == [
        "manual_contract",
        "manual_contract",
        "manual_contract",
        "native_cli",
        "manual_contract",
    ]

    regime = json.loads((output / "01_macro_regime_brief.json").read_text())
    themes = json.loads((output / "02_hot_themes.json").read_text())
    cards = json.loads((output / "04_hypothesis_cards.json").read_text())
    sized = json.loads((output / "05_sized_hypotheses.json").read_text())
    journal = json.loads((output / "06_opportunity_journal_entries.json").read_text())

    assert regime["exposure_posture"] == "NEW_ENTRY_ALLOWED"
    assert regime["regime"] == "BROADENING"
    assert [theme["theme"] for theme in themes["themes"]] == [
        "Fictional Cloud Efficiency",
        "Fictional Data Center Buildout",
        "Fictional Semiconductor Upturn",
    ]
    assert [card["symbol"] for card in cards["cards"]] == ["CLOUDX", "ELECGY", "METALX", "SEMIX"]
    assert len(sized["plans"]) == 4

    entries = journal["entries"]
    assert [entry["ticker"] for entry in entries] == ["CLOUDX", "ELECGY", "METALX", "SEMIX"]
    by_ticker = {entry["ticker"]: entry for entry in entries}
    assert by_ticker["CLOUDX"]["status"] == "ENTRY_READY"
    assert by_ticker["ELECGY"]["status"] == "ENTRY_READY"
    assert by_ticker["METALX"]["status"] == "IDEA"
    assert by_ticker["SEMIX"]["status"] == "IDEA"
    assert [item["status"] for item in by_ticker["CLOUDX"]["status_history"]] == [
        "IDEA",
        "ENTRY_READY",
    ]

    manifest = load_yaml(output / "manifest.yaml")
    assert manifest["completed_steps"] == [1, 2, 4, 5, 6]
    assert manifest["optional_steps_skipped"] == [
        {
            "step": 3,
            "skill": "market-news-analyst",
            "reason": "required-only executable replay",
        }
    ]
    assert not (output / "03_catalyst_news_brief.json").exists()


def test_full_path_includes_catalyst_scenario(tmp_path: Path) -> None:
    output = tmp_path / "full"
    report = execute_replay(ROOT, SPEC, "full-path", output)

    assert report["status"] == "completed"
    catalyst = json.loads((output / "03_catalyst_news_brief.json").read_text())
    assert catalyst["as_of"] == "2026-06-29"
    assert sum(scenario["probability_pct"] for scenario in catalyst["scenarios"]) == 100
    assert catalyst["asset_mix"] == ["ELECGY", "METALX", "CLOUDX", "SEMIX"]


def test_closed_gap_cards_are_filtered_by_hypothesis_gate(tmp_path: Path) -> None:
    fixture = json.loads((INPUTS / "hypothesis-cards.json").read_text())
    fixture["cards"].append(
        {
            **fixture["cards"][0],
            "hypothesis_id": "hyp_closed",
            "symbol": "CLOSED",
            "thesis": "A closed-gap card that must be dropped by the hypothesis gate.",
            "recommendation": "reject",
            "gap_to_consensus": "CLOSED",
        }
    )
    output = tmp_path / "required"
    execute_replay(
        ROOT,
        SPEC,
        "required-only",
        output,
        input_overrides={"hypothesis_fixture": _override(tmp_path, "hypothesis_fixture", fixture)},
    )

    cards = json.loads((output / "04_hypothesis_cards.json").read_text())
    assert [card["hypothesis_id"] for card in cards["cards"]] == [
        "hyp_cloudex",
        "hyp_elergy",
        "hyp_metafx",
        "hyp_semifx",
    ]


def test_missing_kill_criteria_halts_fail_closed(tmp_path: Path) -> None:
    fixture = json.loads((INPUTS / "hypothesis-cards.json").read_text())
    fixture["cards"][0].pop("kill_criteria")

    with pytest.raises(ReplayError, match="kill_criteria"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={
                "hypothesis_fixture": _override(tmp_path, "hypothesis_fixture", fixture)
            },
        )

    assert not (tmp_path / "published").exists()


def test_unknown_theme_symbol_halts_hypothesis_gate(tmp_path: Path) -> None:
    fixture = json.loads((INPUTS / "hypothesis-cards.json").read_text())
    fixture["cards"][0]["symbol"] = "GHOST"

    with pytest.raises(ReplayError, match="not in.*symbols"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={
                "hypothesis_fixture": _override(tmp_path, "hypothesis_fixture", fixture)
            },
        )

    assert not (tmp_path / "published").exists()


def test_park_card_cannot_be_promoted_to_entry_ready(tmp_path: Path) -> None:
    decision = json.loads((INPUTS / "journal-decision.json").read_text())
    decision["per_card"]["hyp_metafx"]["status"] = "ENTRY_READY"

    with pytest.raises(ReplayError, match="recommendation is not pursue"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={"journal_decision": _override(tmp_path, "journal_decision", decision)},
        )

    assert not (tmp_path / "published").exists()


def test_forex_research_only_cannot_be_entry_ready(tmp_path: Path) -> None:
    fixture = json.loads((INPUTS / "hypothesis-cards.json").read_text())
    fixture["cards"][0]["asset_type"] = "forex"
    decision = json.loads((INPUTS / "journal-decision.json").read_text())
    decision["per_card"]["hyp_cloudex"]["status"] = "ENTRY_READY"

    with pytest.raises(ReplayError, match="research-only"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={
                "hypothesis_fixture": _override(tmp_path, "hypothesis_fixture", fixture),
                "journal_decision": _override(tmp_path, "journal_decision", decision),
            },
        )

    assert not (tmp_path / "published").exists()


def test_rejected_cards_are_excluded_from_journal(tmp_path: Path) -> None:
    decision = json.loads((INPUTS / "journal-decision.json").read_text())
    decision["per_card"]["hyp_semifx"]["status"] = "REJECTED"

    output = tmp_path / "required"
    execute_replay(
        ROOT,
        SPEC,
        "required-only",
        output,
        input_overrides={"journal_decision": _override(tmp_path, "journal_decision", decision)},
    )

    journal = json.loads((output / "06_opportunity_journal_entries.json").read_text())
    assert [entry["ticker"] for entry in journal["entries"]] == ["CLOUDX", "ELECGY", "METALX"]


def test_cash_priority_regime_halts_before_trade_idea(tmp_path: Path) -> None:
    regime = json.loads((INPUTS / "macro-regime.json").read_text())
    regime["exposure_posture"] = "CASH_PRIORITY"

    with pytest.raises(ReplayError, match="cash-priority"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={
                "macro_regime_fixture": _override(tmp_path, "macro_regime_fixture", regime)
            },
        )

    assert not (tmp_path / "published").exists()


def test_empty_hypothesis_gate_halts_when_no_card_survives(tmp_path: Path) -> None:
    fixture = json.loads((INPUTS / "hypothesis-cards.json").read_text())
    for card in fixture["cards"]:
        card["gap_to_consensus"] = "CLOSED"

    with pytest.raises(ReplayError, match="no.*cards"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={
                "hypothesis_fixture": _override(tmp_path, "hypothesis_fixture", fixture)
            },
        )

    assert not (tmp_path / "published").exists()


def test_corrupt_hypothesis_handoff_halts_sizing_and_preserves_output(tmp_path: Path) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")

    def corrupt_after_hypothesis(step: int, artifacts: dict[str, dict]) -> None:
        if step == 4:
            path = Path(artifacts["hypothesis_cards"]["files"]["canonical"])
            path.write_text("{not json\n", encoding="utf-8")

    with pytest.raises(ReplayError) as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            after_step=corrupt_after_hypothesis,
        )

    assert exc_info.value.completed_steps == [1, 2, 4]
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


@pytest.mark.parametrize(
    ("variant", "golden_dir"),
    (("required-only", "replay-run"), ("full-path", "replay-run-full-path")),
)
def test_committed_goldens_are_reproducible(
    variant: str,
    golden_dir: str,
    tmp_path: Path,
) -> None:
    generated = tmp_path / "generated"
    execute_replay(ROOT, SPEC, variant, generated)

    golden = SPEC.parent / golden_dir
    assert compare_trees(generated, golden) == []
