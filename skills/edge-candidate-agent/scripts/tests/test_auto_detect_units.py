"""Unit tests for auto_detect_candidates helpers (hints, scoring, tickets, IO)."""

import json
from datetime import date
from pathlib import Path
from subprocess import CompletedProcess

import auto_detect_candidates as adc
import pytest

AS_OF = date(2026, 2, 20)


# --- small helpers ------------------------------------------------------------


def test_clamp_bounds() -> None:
    assert adc.clamp(-5.0) == 0.0
    assert adc.clamp(150.0) == 100.0
    assert adc.clamp(42.5) == 42.5
    assert adc.clamp(3.0, 1.0, 2.0) == 2.0


def test_sanitize_identifier_collapses_symbols() -> None:
    assert adc.sanitize_identifier("  Edge--Auto__VCP / NVDA ") == "edge_auto_vcp_nvda"


def test_parse_as_of_date() -> None:
    assert adc.parse_as_of_date(None) is None
    assert adc.parse_as_of_date("2026-02-20") == AS_OF
    with pytest.raises(adc.AutoDetectError, match="invalid --as-of format"):
        adc.parse_as_of_date("02/20/2026")


def test_infer_entry_family_returns_none_without_keyword() -> None:
    assert adc.infer_entry_family_from_text("nothing relevant here") is None


# --- hints ----------------------------------------------------------------------


def test_normalize_hints_skips_non_dicts_and_infers_family() -> None:
    hints = adc.normalize_hints(
        [
            "not a dict",
            {"observation": "Post-earnings gap drift", "symbols": [" nvda ", "", 5, "amd"]},
            {"preferred_entry_family": "bogus_family", "title": "Capitulation washout"},
            {
                "preferred_entry_family": "news_reaction",
                "regime_bias": " RiskOn ",
                "mechanism_tag": "flow ",
            },
            {},
        ]
    )
    assert len(hints) == 4
    assert hints[0]["title"] == "Post-earnings gap drift"
    assert hints[0]["entry_family"] == "gap_up_continuation"
    assert hints[0]["symbols"] == {"NVDA", "AMD"}
    assert hints[1]["entry_family"] == "panic_reversal"
    assert hints[2]["entry_family"] == "news_reaction"
    assert hints[2]["regime_bias"] == "RiskOn"
    assert hints[2]["mechanism_tag"] == "flow"
    assert hints[3]["title"] == "hint_5"
    assert hints[3]["entry_family"] is None


def test_hint_match_boost_symbol_generic_and_cap() -> None:
    hints = [
        {"title": "A", "entry_family": "pivot_breakout", "symbols": {"NVDA"}},
        {"title": "B", "entry_family": "pivot_breakout", "symbols": {"AMD"}},
        {"title": "C", "entry_family": "pivot_breakout", "symbols": set()},
        {"title": "D", "entry_family": "panic_reversal", "symbols": set()},
    ]
    boost, titles = adc.hint_match_boost("nvda", "pivot_breakout", hints)
    assert boost == 18.0
    assert titles == ["A", "C"]

    many = [
        {"title": f"h{i}", "entry_family": "pivot_breakout", "symbols": {"X"}} for i in range(5)
    ]
    boost, titles = adc.hint_match_boost("X", "pivot_breakout", many)
    assert boost == 20.0
    assert len(titles) == 5

    assert adc.hint_match_boost("ZZZ", "pivot_breakout", hints[:2]) == (0.0, [])


def test_read_hints_variants(tmp_path: Path) -> None:
    assert adc.read_hints(None) == []

    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert adc.read_hints(empty) == []

    as_list = tmp_path / "list.yaml"
    as_list.write_text("- title: Breakout leaders\n  symbols: [nvda]\n", encoding="utf-8")
    hints = adc.read_hints(as_list)
    assert hints[0]["entry_family"] == "pivot_breakout"
    assert hints[0]["symbols"] == {"NVDA"}

    as_dict = tmp_path / "dict.yaml"
    as_dict.write_text("hints:\n  - title: Panic selloff\n", encoding="utf-8")
    assert adc.read_hints(as_dict)[0]["entry_family"] == "panic_reversal"

    bad = tmp_path / "bad.yaml"
    bad.write_text("just a string\n", encoding="utf-8")
    with pytest.raises(adc.AutoDetectError, match="invalid hints format"):
        adc.read_hints(bad)

    bad_dict = tmp_path / "bad_dict.yaml"
    bad_dict.write_text("hints: 3\n", encoding="utf-8")
    with pytest.raises(adc.AutoDetectError, match="invalid hints format"):
        adc.read_hints(bad_dict)


# --- LLM hints ------------------------------------------------------------------


def _fake_run(stdout: str, returncode: int = 0, stderr: str = "", seen: dict | None = None):
    def run(cmd, **kwargs):
        if seen is not None:
            seen["cmd"] = cmd
            seen["input"] = kwargs.get("input")
        return CompletedProcess(args=cmd, returncode=returncode, stdout=stdout, stderr=stderr)

    return run


def _llm(monkeypatch, stdout: str, **kw):
    monkeypatch.setattr(adc.subprocess, "run", _fake_run(stdout, **kw))
    return adc.generate_llm_hints("my-llm --flag", AS_OF, {"risk_on_score": 1}, [])


def test_generate_llm_hints_no_command_returns_empty() -> None:
    assert adc.generate_llm_hints(None, AS_OF, {}, []) == []
    assert adc.generate_llm_hints("", AS_OF, {}, []) == []


def test_generate_llm_hints_blank_command_raises() -> None:
    with pytest.raises(adc.AutoDetectError, match="--llm-ideas-cmd is empty"):
        adc.generate_llm_hints("   ", AS_OF, {}, [])


def test_generate_llm_hints_sends_payload_and_splits_command(monkeypatch) -> None:
    seen: dict = {}
    anomalies = [{"symbol": f"S{i}"} for i in range(30)]
    monkeypatch.setattr(adc.subprocess, "run", _fake_run("[]", seen=seen))
    adc.generate_llm_hints("my-llm --flag 'a b'", AS_OF, {"k": 1}, anomalies)
    assert seen["cmd"] == ["my-llm", "--flag", "a b"]
    payload = json.loads(seen["input"])
    assert payload["as_of"] == "2026-02-20"
    assert payload["market_summary"] == {"k": 1}
    assert len(payload["anomalies"]) == 20


def test_generate_llm_hints_output_variants(monkeypatch) -> None:
    assert _llm(monkeypatch, "   \n") == []
    assert _llm(monkeypatch, "null") == []
    listed = _llm(
        monkeypatch, '[{"title": "Gap drift", "preferred_entry_family": "gap_up_continuation"}]'
    )
    assert listed[0]["entry_family"] == "gap_up_continuation"
    assert _llm(monkeypatch, '{"hints": []}') == []


def test_generate_llm_hints_rejects_invalid_format(monkeypatch) -> None:
    with pytest.raises(adc.AutoDetectError, match="invalid format"):
        _llm(monkeypatch, "plain text answer")
    with pytest.raises(adc.AutoDetectError, match="invalid format"):
        _llm(monkeypatch, '{"hints": "nope"}')


def test_generate_llm_hints_failure_prefers_stderr_then_stdout(monkeypatch) -> None:
    with pytest.raises(adc.AutoDetectError, match="boom-stderr"):
        _llm(monkeypatch, "out", returncode=2, stderr="boom-stderr")
    with pytest.raises(adc.AutoDetectError, match="only-stdout"):
        _llm(monkeypatch, "only-stdout", returncode=2, stderr="")


# --- scoring --------------------------------------------------------------------


def test_breakout_score_regime_and_atr_penalty() -> None:
    record = {
        "rs_rank_pct": 0.9,
        "rel_volume": 3.0,
        "close_pos": 1.0,
        "atr_pct": 0.02,
        "close": 108.0,
        "high20_prev": 100.0,
    }
    # 36 + 20 + 20 + 10 = 86 before regime component
    assert adc.score_breakout_candidate(record, "Neutral") == 91.0
    assert adc.score_breakout_candidate(record, "RiskOff") == 81.0
    assert adc.score_breakout_candidate(record, "Unknown") == 86.0
    # ATR above 15% takes the full 15 point penalty.
    assert adc.score_breakout_candidate({**record, "atr_pct": 0.5}, "Unknown") == 71.0
    # Missing/None values are treated as zero without crashing.
    assert adc.score_breakout_candidate({"rs_rank_pct": None}, "Unknown") == 0.0


def test_gap_score_trend_and_regime() -> None:
    record = {
        "gap": 0.12,
        "rel_volume": 4.0,
        "close_pos": 1.0,
        "close": 100.0,
        "ma50": 90.0,
        "ma200": 80.0,
        "atr_pct": 0.02,
    }
    # 35 + 25 + 20 + 20 trend = 100 -> clamped
    assert adc.score_gap_candidate(record, "RiskOn") == 100.0
    below = {**record, "close": 70.0}
    # trend score 0: 35 + 25 + 20 - 8 = 72
    assert adc.score_gap_candidate(below, "RiskOff") == 72.0
    assert adc.score_gap_candidate(below, "Neutral", hint_boost=3.0) == 87.0


def test_reversal_score_components() -> None:
    record = {"ret_1d": -0.18, "rel_volume": 4.0, "atr_pct": 0.05, "close": 100.0, "ma200": 80.0}
    # 45 + 20 + 15 + 12(RiskOff)
    assert adc.score_reversal_candidate(record, "RiskOff") == 92.0
    broken = {**record, "close": 70.0}
    # trend component drops to 5
    assert adc.score_reversal_candidate(broken, "RiskOff") == 82.0
    # Up-moves produce no shock component.
    assert adc.score_reversal_candidate({**record, "ret_1d": 0.05}, "Neutral") == 42.0


# --- ticket payloads ------------------------------------------------------------


def _payload(candidate: dict, regime: str = "Neutral") -> dict:
    return adc.build_ticket_payload(candidate, AS_OF, regime, 3, {"pct_above_ma50": 0.5})


def test_ticket_ids_and_text_by_family() -> None:
    base = {"symbol": "nvda", "priority_score": 80.0, "close": 100.12345678}
    brk = _payload({**base, "entry_family": "pivot_breakout"})
    gap = _payload({**base, "entry_family": "gap_up_continuation"})
    assert brk["id"] == "edge_auto_vcp_nvda_20260220"
    assert gap["id"] == "edge_auto_gap_nvda_20260220"
    assert brk["name"] == "Pivot Breakout NVDA 20260220"
    assert brk["description"] == "Auto-detected Pivot Breakout candidate for NVDA."
    assert brk["hypothesis_type"] == "breakout"
    assert gap["hypothesis_type"] == "earnings_drift"
    assert gap["mechanism_tag"] == "structure"
    assert brk["observation"]["close"] == 100.1235
    assert brk["rank"] == 3
    assert brk["market_context"]["pct_above_ma50"] == 0.5
    assert brk["signal_definition"]["entry_family"] == "pivot_breakout"


def test_ticket_for_family_without_hypothesis_type_uses_mapping() -> None:
    payload = _payload({"symbol": "TSLA", "entry_family": "panic_reversal", "priority_score": 70})
    assert payload["hypothesis_type"] == "panic_reversal"
    assert payload["id"] == "edge_auto_panic_reversal_tsla_20260220"


def test_research_ticket_defaults_and_fallback_text() -> None:
    payload = _payload(
        {
            "symbol": "X",
            "entry_family": None,
            "hypothesis_type": "calendar_anomaly",
            "priority_score": 55.0,
        }
    )
    assert payload["research_only"] is True
    assert "entry_family" not in payload
    assert payload["mechanism_tag"] == "uncertain"
    assert payload["signal_definition"]["entry_family"] == "research_only"
    assert payload["name"] == "Calendar Anomaly X 20260220"
    assert payload["description"] == "Auto-detected Calendar Anomaly research candidate."
    assert payload["hypothesis"].startswith("if observed pattern repeats")
    assert payload["holding_horizon"] == "20D"


def test_research_ticket_without_hypothesis_type_defaults_to_regime_shift() -> None:
    payload = _payload({"symbol": "M", "priority_score": 50.0, "hypothesis": "custom idea"})
    assert payload["hypothesis_type"] == "regime_shift"
    assert payload["hypothesis"] == "custom idea"
    assert payload["id"] == "edge_auto_regime_shift_m_20260220"


def test_news_ticket_direction_up() -> None:
    payload = _payload(
        {
            "symbol": "A",
            "entry_family": "news_reaction",
            "priority_score": 60.0,
            "reaction_1d": 0.075,
        }
    )
    assert payload["observation"]["reaction_direction"] == "up"
    assert payload["observation"]["abs_reaction_1d"] == 0.075
    assert "news reaction magnitude" in payload["hypothesis"]


def test_ticket_honors_overrides_for_rationale_and_conditions() -> None:
    payload = _payload(
        {
            "symbol": "A",
            "entry_family": "pivot_breakout",
            "priority_score": 60.0,
            "rationale": ["r1"],
            "conditions": ["c1"],
            "trend_filter": ["t1"],
            "holding_horizon": "5D",
            "mechanism_tag": "flow",
            "matched_hints": ["h"],
        }
    )
    assert payload["rationale"] == ["r1"]
    assert payload["entry"] == {"conditions": ["c1"], "trend_filter": ["t1"]}
    assert payload["holding_horizon"] == "5D"
    assert payload["mechanism_tag"] == "flow"
    assert payload["observation"]["matched_hints"] == ["h"]


# --- report ---------------------------------------------------------------------


def test_render_daily_report_populated() -> None:
    report = adc.render_daily_report(
        AS_OF,
        "RiskOn",
        {"pct_above_ma50": 0.6, "risk_on_score": 80},
        [{"symbol": "NVDA", "metric": "gap", "value": 0.1, "z": 3.2}, {}],
        [{"id": "t1", "entry_family": "pivot_breakout", "priority_score": 90, "regime": "RiskOn"}],
        [
            {
                "id": "t2",
                "hypothesis_type": "regime_shift",
                "priority_score": 60,
                "observation": {"symbol": "MARKET_BASKET"},
            }
        ],
        7,
        ["news_reaction(no_input)"],
    )
    assert "# Edge Candidate Daily Report (2026-02-20)" in report
    assert "- Watchlist candidates: **7**" in report
    assert "- Optional modules skipped: news_reaction(no_input)" in report
    assert "- NVDA: gap=0.1 (z=3.2)" in report
    assert "- MARKET: n/a=n/a (z=n/a)" in report
    assert "- t1 | pivot_breakout | score=90 | regime=RiskOn" in report
    assert "- t2 | regime_shift | score=60 | symbol=MARKET_BASKET" in report


def test_render_daily_report_empty_sections() -> None:
    report = adc.render_daily_report(AS_OF, "Neutral", {}, [], [], [], 0, [])
    assert "No high-z anomalies detected." in report
    assert "No exportable tickets generated." in report
    assert "No research-only tickets generated." in report
    assert "Optional modules skipped" not in report
    assert "- pct_above_ma50: None" in report
