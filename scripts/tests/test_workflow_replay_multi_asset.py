"""Multi-asset opportunity daily replay: gates, sizing, journal, and tamper."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import workflow_replay as replay  # noqa: E402

SPEC = ROOT / "examples/workflows/multi-asset-opportunity-daily/replay.yaml"


def override(tmp_path, name, mutate):
    payload = json.loads((SPEC.parent / "replay-inputs" / f"{name}.json").read_text())
    mutate(payload)
    path = tmp_path / "overrides" / f"{name}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return {name: path}


@pytest.mark.parametrize(
    "variant,golden,steps",
    [
        ("required-only", "replay-run", [1, 2, 4, 5, 6]),
        ("full-path", "replay-run-full-path", [1, 2, 3, 4, 5, 6]),
    ],
)
def test_positive_variants_match_goldens(tmp_path, variant, golden, steps):
    output = tmp_path / "out"
    report = replay.execute_replay(ROOT, SPEC, variant, output)
    assert report["status"] == "completed"
    assert [s["step"] for s in report["steps"]] == steps
    assert replay.compare_trees(output, SPEC.parent / golden) == []

    cards = json.loads((output / "04_hypothesis_cards.json").read_text())
    assert cards["manual_review_required"] is True
    assert cards["execution_authorized"] is False
    assert set(cards["decisions"]) == {card["hypothesis_id"] for card in cards["hypotheses"]}
    sized = json.loads((output / "05_sized_hypotheses.json").read_text())
    sized_ids = [card["hypothesis_id"] for card in sized["sized_cards"]]
    assert sized_ids == ["hyp_zzq_edge_equity", "hyp_zzc_energy_proxy"]
    assert [card["final_recommended_shares"] for card in sized["sized_cards"]] == [60, 120]
    assert sized["research_only_cards"] == [
        {
            "hypothesis_id": "hyp_zzfx_carry_fx",
            "symbol": "ZZFX",
            "asset_class": "FX",
            "reason": "research_only: sizing refused; recorded as journal research only",
        }
    ]
    journal = json.loads((output / "06_opportunity_journal_entries.json").read_text())
    rows = [
        (row["ticker"], row["status"], row["research_only"]) for row in journal["journal_entries"]
    ]
    assert rows == [
        ("ZZC", "IDEA", False),
        ("ZZFX", "IDEA", True),
        ("ZZQ", "IDEA", False),
    ]
    assert journal["execution_authorized"] is False
    for row in journal["journal_entries"]:
        assert row["kill_criteria"]
        assert all(row["linked_reports"])
    assert "workflow-replay-" not in json.dumps(journal)
    assert "/private/" not in json.dumps(journal)
    assert not any(row["status"] != "IDEA" for row in journal["journal_entries"])


@pytest.mark.parametrize(
    "mutate,messages",
    [
        (
            lambda p: p["report"].update(recommendation="CASH_PRIORITY"),
            ["multi-asset market gate halted: CASH_PRIORITY"],
        ),
        (
            lambda p: p["report"].update(recommendation="REDUCE_ONLY"),
            ["multi-asset market gate halted: REDUCE_ONLY"],
        ),
        (
            lambda p: p.update(human_approved=False),
            ["requires a dated, approved fictional fixture"],
        ),
        (
            lambda p: p["report"].update(generated_at="2020-01-01T00:00:00+00:00"),
            ["requires a current exposure decision"],
        ),
    ],
)
def test_market_gate_halt_blocks_everything(tmp_path, mutate, messages):
    with pytest.raises(replay.ReplayError) as exc:
        replay.execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "out",
            input_overrides=override(tmp_path, "exposure", mutate),
        )
    assert exc.value.completed_steps == []
    assert any(message in str(exc.value) for message in messages)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "mutate,message",
    [
        (
            lambda p: p["report"].update(market_state="INSUFFICIENT_EVIDENCE"),
            "INSUFFICIENT_EVIDENCE",
        ),
        (lambda p: p["report"]["themes"].clear(), "should be non-empty"),
        (lambda p: p.update(as_of="2020-01-01"), "dated, approved fictional fixture"),
    ],
)
def test_insufficient_or_stale_themes_halt(tmp_path, mutate, message):
    output = tmp_path / "out"
    with pytest.raises(replay.ReplayError, match=message) as exc_info:
        replay.execute_replay(
            ROOT,
            SPEC,
            "full-path",
            output,
            input_overrides=override(tmp_path, "themes", mutate),
        )
    assert exc_info.value.completed_steps == [1]
    assert not output.exists()


def test_missing_required_macro_input_fails_closed(tmp_path):
    missing = tmp_path / "overrides" / "missing_macro.json"
    missing.parent.mkdir()
    with pytest.raises(replay.ReplayError, match="macro"):
        replay.execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides={"macro_brief": missing},
        )
    for variant in ("required-only", "full-path"):
        output = tmp_path / f"out-{variant}"
        assert not output.exists()


def test_stale_optional_news_halt(tmp_path):
    def mutate(payload):
        payload["report"].update(market_state="INSUFFICIENT_EVIDENCE")

    with pytest.raises(replay.ReplayError, match="multi-asset news halted"):
        replay.execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "out",
            input_overrides=override(tmp_path, "news", mutate),
        )


@pytest.mark.parametrize(
    "name,mutate",
    [
        ("raw_hypotheses", lambda p: p["hypotheses"][0].pop("kill_criteria")),
        (
            "raw_hypotheses",
            lambda p: p["hypotheses"][0].update(score_components={"evidence_strength": 9}),
        ),
        ("raw_hypotheses", lambda p: p.pop("hypotheses")),
        ("hypothesis_decision", lambda p: p.update(allow_entry_ready=True)),
        (
            "hypothesis_decision",
            lambda p: p["cards"].pop("hyp_zzq_edge_equity"),
        ),
        (
            "hypothesis_decision",
            lambda p: p["cards"].update({"hyp_unknown": {"disposition": "reject"}}),
        ),
        (
            "hypothesis_decision",
            lambda p: p["cards"]["hyp_zzq_edge_equity"].update(stop=250.0),
        ),
    ],
)
def test_invalid_cards_or_gates_fail_closed(tmp_path, name, mutate):
    output = tmp_path / "out"
    output.mkdir()
    (output / "existing.txt").write_text("preserve")
    with pytest.raises(replay.ReplayError) as exc:
        replay.execute_replay(
            ROOT,
            SPEC,
            "full-path",
            output,
            input_overrides=override(tmp_path, name, mutate),
        )
    assert 4 not in exc.value.completed_steps
    assert list(p.name for p in output.iterdir()) == ["existing.txt"]
    assert (output / "existing.txt").read_text() == "preserve"


def test_research_only_fx_never_sized(tmp_path):
    def mutate(payload):
        payload["cards"]["hyp_zzfx_carry_fx"] = {
            "disposition": "size",
            "entry": 1.0,
            "stop": 0.9,
        }

    with pytest.raises(replay.ReplayError, match="forbidden"):
        replay.execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "out",
            input_overrides=override(tmp_path, "hypothesis_decision", mutate),
        )


def test_unauthorized_entry_ready_promotion_tamper_rejected(tmp_path):
    def before(number, artifacts):
        if number == 6:
            path = Path(artifacts["hypothesis_cards"]["files"]["canonical"])
            payload = json.loads(path.read_text())
            payload["hypotheses"][0]["promote_to_entry_ready"] = True
            path.write_text(json.dumps(payload))

    with pytest.raises(replay.ReplayError, match="promotion") as exc:
        replay.execute_replay(ROOT, SPEC, "full-path", tmp_path / "out", before_step=before)
    assert exc.value.completed_steps == [1, 2, 3, 4, 5]
    assert not (tmp_path / "out").exists()


def test_decision_fixture_entry_ready_is_never_authorized(tmp_path):
    def mutate(payload):
        payload["cards"]["hyp_zzq_edge_equity"]["disposition"] = "entry_ready"

    with pytest.raises(replay.ReplayError, match="disposition"):
        replay.execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "out",
            input_overrides=override(tmp_path, "hypothesis_decision", mutate),
        )


def test_journal_write_failure_does_not_publish(tmp_path, monkeypatch):
    store = replay._repo_module(ROOT, "thesis_store", ROOT / "skills/trader-memory-core/scripts")

    def fail(*args, **kwargs):
        raise OSError("injected journal failure")

    monkeypatch.setattr(store, "_save_thesis", fail)
    with pytest.raises(replay.ReplayError, match="injected journal failure") as exc:
        replay.execute_replay(ROOT, SPEC, "required-only", tmp_path / "out")
    assert exc.value.completed_steps == [1, 2, 4, 5]
    assert not (tmp_path / "out").exists()


def test_generated_at_utc_is_a_canonicalized_timestamp_field():
    canonical = replay._canonicalize(
        {"generated_at_utc": "leave me"}, "2026-08-15T12:00:00+00:00", {}
    )
    assert canonical == {"generated_at_utc": "2026-08-15T12:00:00+00:00"}
